"""A3: 链式触发——工作流完成后按状态自动触发关联工作流

集成点:run_record_service.finalize 末尾调用 maybe_trigger_chain
触发方式:loop.create_task 异步执行,不阻塞当前 run 返回
深度限制:trigger_data._chain_depth 默认 0,>= MAX_CHAIN_DEPTH 时拒绝触发并记录 warning

链式触发流程:
1. 工作流 A 执行完成 → finalize → maybe_trigger_chain(A, status, trigger_data)
2. 读取 A.on_complete_trigger,按 on(success/failed/always)过滤匹配项
3. 检查 _chain_depth(从 trigger_data 解析),>= MAX_CHAIN_DEPTH 则拒绝
4. 对每个匹配的目标工作流 B,loop.create_task(_execute_chain_target(B, chain_data))
   - chain_data = 父 trigger_data + {_chain_depth: depth+1, _chain_from: A}
5. _execute_chain_target 用独立 SessionLocal 加载 B,创建 RunRecord(trigger_type="chain"),
   调用 executor.execute,finalize(B 的 on_complete_trigger 又会触发下一层,递进至深度上限)
"""
import asyncio
import json
import logging

logger = logging.getLogger(__name__)

# 链式触发最大深度(防止 A→B→C→A... 无限循环)
# depth=0 为首次执行,depth=1..3 为链式触发的 1..3 层
MAX_CHAIN_DEPTH = 3


def maybe_trigger_chain(workflow_id: str, run_status: str, trigger_data: dict | None) -> None:
    """同步入口:检测 workflow.on_complete_trigger,按状态过滤后异步触发目标工作流

    在 finalize 末尾调用。不阻塞当前请求(loop.create_task)。
    无运行中的事件循环时静默跳过(避免在同步测试上下文中报错)。

    :param workflow_id: 刚完成的工作流 ID
    :param run_status: 工作流执行状态(success/failed/aborted)
    :param trigger_data: 本次执行的触发数据(含可能的 _chain_depth)
    """
    if not workflow_id:
        return

    try:
        triggers, depth = _load_triggers_and_depth(workflow_id, trigger_data)
        if not triggers:
            return

        # 深度限制:已达上限则拒绝触发
        if depth >= MAX_CHAIN_DEPTH:
            logger.warning(
                f"链式触发深度超限(workflow_id={workflow_id}, depth={depth}),"
                f"跳过 {len(triggers)} 个目标工作流触发"
            )
            return

        # 按状态过滤匹配项
        matched = [
            t for t in triggers
            if isinstance(t, dict)
            and _status_matches(run_status, t.get("on", "always"))
            and t.get("workflow_id")
        ]
        if not matched:
            return

        # 获取运行中的事件循环(无则静默跳过)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.debug(f"无运行中的事件循环,跳过链式触发(workflow_id={workflow_id})")
            return

        # 异步触发每个目标工作流
        for t in matched:
            target_wf_id = t["workflow_id"]
            # 子触发数据:继承父 trigger_data + 深度 +1 + 标记来源
            chain_data = dict(trigger_data) if isinstance(trigger_data, dict) else {}
            chain_data["_chain_depth"] = depth + 1
            chain_data["_chain_from"] = workflow_id
            loop.create_task(_execute_chain_target(target_wf_id, chain_data))
            logger.info(
                f"链式触发: {workflow_id} -> {target_wf_id} "
                f"(depth={depth + 1}, on={t.get('on')}, parent_status={run_status})"
            )

    except Exception as e:
        # 链式触发失败不影响主流程
        logger.exception(f"maybe_trigger_chain 异常 (workflow_id={workflow_id}): {e}")


def _load_triggers_and_depth(workflow_id: str, trigger_data: dict | None):
    """从 DB 加载 on_complete_trigger 配置,并解析 _chain_depth"""
    from db.database import SessionLocal
    from db.models import Workflow

    db = SessionLocal()
    try:
        wf = db.query(Workflow).filter(Workflow.id == workflow_id).first()
        if not wf or not wf.on_complete_trigger:
            return [], 0
        triggers = json.loads(wf.on_complete_trigger)
        if not isinstance(triggers, list):
            return [], 0
    finally:
        db.close()

    # 深度从 trigger_data 解析(首次执行为 0,链式触发递增)
    depth = 0
    if isinstance(trigger_data, dict):
        try:
            depth = int(trigger_data.get("_chain_depth", 0) or 0)
        except (TypeError, ValueError):
            depth = 0
    return triggers, depth


def _status_matches(run_status: str, on: str) -> bool:
    """判断工作流状态是否匹配触发条件

    :param run_status: success / failed / aborted
    :param on: success / failed / always
    """
    if on == "always":
        return True
    if on == "success":
        return run_status == "success"
    if on == "failed":
        # aborted 也视为失败
        return run_status in ("failed", "aborted")
    return False


async def _execute_chain_target(target_wf_id: str, chain_trigger_data: dict) -> None:
    """异步执行链式触发的目标工作流(独立 DB 会话,不依赖请求级 session)

    复用全局 executor 单例 + run_record_service 完整执行流程。
    失败通知由 finalize 后的 notify 逻辑处理(此处不重复)。
    """
    from db.database import SessionLocal
    from db.models import Workflow
    from engine.executor import executor
    from core.run_record_service import create_running, finalize, finalize_error, pause_run
    from core.preference_schema import load_preferences_from_db

    db = SessionLocal()
    run = None
    try:
        wf = db.query(Workflow).filter(Workflow.id == target_wf_id).first()
        if not wf:
            logger.warning(f"链式触发目标工作流不存在: {target_wf_id}")
            return
        steps = json.loads(wf.steps) if wf.steps else []
        edges = json.loads(wf.edges) if wf.edges else []
        on_failure = wf.on_failure or "stop"

        # 创建 RunRecord(trigger_type="chain")
        run = create_running(db, target_wf_id, "chain", chain_trigger_data)

        result = await executor.execute(
            steps=steps,
            edges=edges,
            trigger_data=chain_trigger_data,
            on_failure=on_failure,
            preferences=load_preferences_from_db(),
        )

        # paused 状态:保存 context,不调用 finalize(不触发链式,等待人工审批恢复)
        if result.get("status") == "paused":
            pause_run(db, run, result, result.get("paused_step_id", ""))
            return

        # finalize 内部会再次调用 maybe_trigger_chain(递进至深度上限)
        finalize(db, run, result)

    except Exception as e:
        logger.exception(f"链式触发执行异常 (target_wf_id={target_wf_id}): {e}")
        if run:
            try:
                finalize_error(db, run, str(e))
            except Exception:
                logger.exception(f"链式触发 finalize_error 异常 (target_wf_id={target_wf_id})")
    finally:
        db.close()
