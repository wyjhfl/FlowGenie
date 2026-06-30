"""RunRecord 生命周期管理服务 - 统一创建/更新/通知逻辑

三处入口(routers/execute.py / routers/webhooks.py / scheduler/manager.py)
统一调用本服务,消除字段更新顺序、dashboard 缓存失效、通知触发点的差异。
"""
import json
import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from db.models import RunRecord
from core.error_sanitize import sanitize_error_text, extract_error
from core.notify import maybe_notify_failure

logger = logging.getLogger(__name__)


def create_running(
    db: Session,
    workflow_id: str,
    trigger_type: str,
    trigger_data: dict | None = None,
) -> RunRecord:
    """创建 status=running 的 RunRecord 并提交

    :param trigger_type: manual | schedule | webhook
    :param trigger_data: 触发数据(用于重试恢复),None 则不存储
    :return: 已提交并刷新的 RunRecord
    """
    run = RunRecord(
        workflow_id=workflow_id,
        trigger_type=trigger_type,
        status="running",
        started_at=datetime.now(timezone.utc),
        trigger_data=json.dumps(trigger_data, ensure_ascii=False, default=str) if trigger_data else None,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def finalize(
    db: Session,
    run: RunRecord,
    result: dict,
) -> None:
    """执行完成后更新 RunRecord 终态 + 失效 dashboard 缓存

    :param result: executor.execute 返回的 dict(status/steps_result/total_time_ms/logs/token_usage)
    """
    run.status = result["status"]
    run.total_time_ms = result["total_time_ms"]
    run.steps_result = json.dumps(result["steps_result"], ensure_ascii=False, default=str)
    run.logs = json.dumps(result.get("logs", []), ensure_ascii=False, default=str)
    # B4: 持久化 LLM token 用量统计(无 LLM 调用时为全 0,仍存储便于聚合)
    token_usage = result.get("token_usage")
    if token_usage is not None:
        run.token_usage = json.dumps(token_usage, ensure_ascii=False, default=str)
    run.finished_at = datetime.now(timezone.utc)
    if result["status"] != "success":
        # extract_error 已内置 sanitize_error_text
        run.error = extract_error(result["steps_result"])
    db.commit()
    _invalidate_dashboard_cache()
    # A3: 链式触发——按 on_complete_trigger 配置异步触发目标工作流
    # finalize 在所有执行入口(execute/webhooks/scheduler/chain)被调用,集中在此触发
    # maybe_trigger_chain 内部用独立 SessionLocal + loop.create_task,不阻塞当前请求
    try:
        from core.chain_trigger import maybe_trigger_chain
        trigger_data = json.loads(run.trigger_data) if run.trigger_data else {}
        maybe_trigger_chain(run.workflow_id, result["status"], trigger_data)
    except Exception:
        # 链式触发失败不影响 finalize 主流程
        pass


def finalize_error(
    db: Session,
    run: RunRecord,
    error: str,
    status: str = "failed",
) -> None:
    """执行异常时更新 RunRecord 为 failed/aborted + 失效 dashboard 缓存

    :param error: 原始错误文本(会自动脱敏)
    :param status: failed 或 aborted
    """
    run.status = status
    run.error = sanitize_error_text(error)
    run.finished_at = datetime.now(timezone.utc)
    db.commit()
    _invalidate_dashboard_cache()


def pause_run(
    db: Session,
    run: RunRecord,
    result: dict,
    paused_step_id: str,
) -> None:
    """A1: 工作流执行暂停于审批节点——保存 context 到 RunRecord,等待审批恢复

    :param result: executor.execute 返回的 dict(status="paused", steps_result, logs, token_usage)
    :param paused_step_id: 触发暂停的 approve_node 步骤 ID
    """
    run.status = "paused"
    run.paused_step_id = paused_step_id
    run.paused_at = datetime.now(timezone.utc)
    run.steps_result = json.dumps(result["steps_result"], ensure_ascii=False, default=str)
    run.logs = json.dumps(result.get("logs", []), ensure_ascii=False, default=str)
    # 序列化 ExecutionContext 供 resume_execution 恢复:
    # {step_results, trigger_data, logs, token_usage}
    token_usage = result.get("token_usage")
    paused_ctx = {
        "step_results": result["steps_result"],
        "trigger_data": json.loads(run.trigger_data) if run.trigger_data else {},
        "logs": result.get("logs", []),
        "token_usage": token_usage or {
            "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "calls": 0, "by_model": {}
        },
    }
    run.paused_context = json.dumps(paused_ctx, ensure_ascii=False, default=str)
    db.commit()
    _invalidate_dashboard_cache()


async def notify_failure_if_needed(
    db: Session,
    workflow_name: str,
    run_id: str,
    status: str,
    error: str,
    steps_result: dict | None = None,
) -> None:
    """非 success 时按用户偏好发送失败通知(异常不影响主流程)

    统一委托给 core.notify.maybe_notify_failure,读取用户偏好渠道。
    """
    if status == "success":
        return
    await maybe_notify_failure(
        db,
        workflow_name=workflow_name,
        run_id=run_id,
        status=status,
        error=error or "",
        steps_result=steps_result or {},
    )


def _invalidate_dashboard_cache() -> None:
    """失效 dashboard 缓存(best-effort,失败不影响主流程)"""
    try:
        from routers.stats import invalidate_dashboard_cache
        invalidate_dashboard_cache()
    except Exception:
        pass
