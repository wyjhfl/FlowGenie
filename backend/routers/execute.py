"""工作流执行路由"""
import asyncio
import csv
import io
import json
import logging
import re
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Depends, Query, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from engine.executor import executor, WorkflowExecutor
from tools import TOOL_EXECUTORS
from db.database import get_db, SessionLocal
from db.models import Workflow, RunRecord, UserPreference
from core.notify import send_failure_notification
from core.preference_schema import load_preferences_from_db
from core.error_sanitize import sanitize_error_text, extract_error
from core.run_record_service import (
    create_running, finalize, finalize_error, notify_failure_if_needed, pause_run,
)
from routers.ws import notify_workflow_paused, notify_workflow_resumed

router = APIRouter()
logger = logging.getLogger(__name__)

# 调试会话：{run_id: {"executor": WorkflowExecutor, "step_event": asyncio.Event, "workflow_id": str}}
_debug_sessions: dict[str, dict] = {}

# 注册所有工具执行器
for tool_name, tool_func in TOOL_EXECUTORS.items():
    executor.register_executor(tool_name, tool_func)


def _load_preferences() -> dict:
    """从 DB 加载用户偏好(委托给 core.preference_schema 公共函数)"""
    return load_preferences_from_db()


class RunRequest(BaseModel):
    """执行工作流请求"""
    steps: list[dict]
    edges: list[dict] = []
    trigger_data: dict | None = None
    workflow_id: Optional[str] = None
    on_failure: str = "stop"


class RunResponse(BaseModel):
    """执行结果响应"""
    status: str  # success | failed | partial_success | paused
    steps_result: dict
    total_time_ms: int
    on_failure: str = "stop"
    logs: list = []
    warnings: list = []
    # A1: 仅 status==paused 时有值,供前端展示审批信息
    paused_step_id: Optional[str] = None
    paused_message: Optional[str] = None


class ApproveRequest(BaseModel):
    """A1: 审批请求"""
    decision: Literal["approved", "rejected"]
    comment: str = ""


# 向后兼容别名:本模块内历史代码仍使用 _sanitize_error_text / _extract_error 名称
_sanitize_error_text = sanitize_error_text
_extract_error = extract_error


def _get_failure_notify_config(db: Session) -> tuple[str, str]:
    """从用户偏好读取失败通知配置：返回 (channel, email)"""
    prefs = db.query(UserPreference).filter(
        UserPreference.key.in_(["failure_notify_channel", "failure_notify_email"])
    ).all()
    pref_map = {p.key: p.value for p in prefs}
    channel = pref_map.get("failure_notify_channel", "none")
    email = pref_map.get("failure_notify_email", "")
    return channel, email


async def _maybe_notify_failure(
    db: Session,
    workflow_name: str,
    run_id: str,
    status: str,
    error: str,
    steps_result: dict,
):
    """工作流执行非 success 时按用户偏好发送失败通知（异常不影响主流程）"""
    if status == "success":
        return
    try:
        channel, notify_email = _get_failure_notify_config(db)
        if channel and channel != "none":
            await send_failure_notification(
                workflow_name=workflow_name,
                run_id=run_id,
                error=error or "",
                channel=channel,
                steps_result=steps_result,
                notify_email=notify_email,
            )
    except Exception as e:
        logger.warning(f"发送失败通知失败: {e}")


async def _notify_paused(
    run_id: str,
    workflow_id: str,
    message: str,
    approvers: list,
    paused_step_id: str,
) -> None:
    """A1: 工作流暂停时推送 WebSocket 审批通知(异常不影响主流程)"""
    try:
        await notify_workflow_paused(
            run_id=run_id,
            workflow_id=workflow_id,
            message=message or "请审批此步骤以继续执行",
            approvers=approvers or [],
            paused_step_id=paused_step_id,
        )
    except Exception as e:
        logger.warning(f"推送审批 WS 通知失败: {e}")


def _format_sse(event: str, data: dict) -> str:
    """格式化 SSE 事件流消息：event: {name}\ndata: {json}\n\n"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


@router.post("/run", response_model=RunResponse)
async def run_workflow(req: RunRequest, db: Session = Depends(get_db)):
    """
    执行工作流
    接收工作流定义（steps + edges），按拓扑排序执行，返回每步结果。
    若提供 workflow_id，则创建 RunRecord 记录执行历史。
    """
    if not req.steps:
        raise HTTPException(status_code=400, detail="steps 不能为空")

    # 若关联工作流，执行前创建 RunRecord（status=running）
    run_record = None
    workflow_name = ""
    if req.workflow_id:
        wf = db.query(Workflow).filter(Workflow.id == req.workflow_id).first()
        if not wf:
            raise HTTPException(status_code=404, detail="工作流不存在")
        workflow_name = wf.name
        run_record = create_running(db, req.workflow_id, "manual", req.trigger_data)

    try:
        result = await executor.execute(
            steps=req.steps,
            edges=req.edges,
            trigger_data=req.trigger_data,
            on_failure=req.on_failure,
            preferences=_load_preferences(),
        )
    except Exception as e:
        # executor 异常时更新 RunRecord 为 failed，避免永久卡 running
        logger.exception(f"工作流执行异常 run_id={run_record.id if run_record else '-'}: {e}")
        if run_record:
            finalize_error(db, run_record, str(e))
        raise

    # A1: 审批暂停——保存 context 到 RunRecord + 推送 WS(不调用 finalize,不触发失败通知)
    if run_record and result.get("status") == "paused":
        paused_step_id = result.get("paused_step_id", "")
        pause_run(db, run_record, result, paused_step_id)
        await _notify_paused(
            run_record.id, req.workflow_id or "",
            result.get("paused_message", ""), result.get("paused_approvers", []),
            paused_step_id,
        )
        return RunResponse(**result)

    # 执行后更新 RunRecord(统一走 RunRecordService,内置 dashboard 缓存失效)
    if run_record:
        finalize(db, run_record, result)

    # 失败通知：status != success 时按用户偏好发送（异常不影响主流程）
    await notify_failure_if_needed(
        db,
        workflow_name=workflow_name,
        run_id=run_record.id if run_record else "",
        status=result["status"],
        error=extract_error(result["steps_result"]) or "",
        steps_result=result["steps_result"],
    )

    return RunResponse(**result)


@router.post("/run/stream")
async def run_workflow_stream(req: RunRequest, debug: bool = Query(False), db: Session = Depends(get_db)):
    """
    SSE 流式执行工作流
    每步完成即推送进度（step 事件），全部完成后推送 done 事件，异常推送 error 事件。
    若提供 workflow_id，同样创建 RunRecord 记录执行历史。
    debug=True 时启用调试模式：每步完成后暂停，等待步进接口触发下一步。
    """
    if not req.steps:
        raise HTTPException(status_code=400, detail="steps 不能为空")

    # 若关联工作流，执行前创建 RunRecord（status=running）
    run_record = None
    workflow_name = ""
    if req.workflow_id:
        wf = db.query(Workflow).filter(Workflow.id == req.workflow_id).first()
        if not wf:
            raise HTTPException(status_code=404, detail="工作流不存在")
        workflow_name = wf.name
        run_record = create_running(db, req.workflow_id, "manual", req.trigger_data)

    # 调试模式：创建独立的 executor 实例与 step_event，并注册到调试会话表
    step_event = None
    if debug:
        step_event = asyncio.Event()
        run_executor = WorkflowExecutor(debug_mode=True, step_event=step_event)
        for tool_name, tool_func in TOOL_EXECUTORS.items():
            run_executor.register_executor(tool_name, tool_func)
        if run_record:
            _debug_sessions[run_record.id] = {
                "executor": run_executor,
                "step_event": step_event,
                "workflow_id": req.workflow_id,
            }
    else:
        run_executor = executor

    async def event_generator():
        queue: asyncio.Queue = asyncio.Queue()

        def progress_callback(progress: dict):
            # B1: 识别事件类型——step(步骤完成)/step_token(LLM 流式增量)
            event_type = progress.get("type", "step")
            queue.put_nowait((event_type, progress))

        async def run():
            try:
                result = await run_executor.execute(
                    steps=req.steps,
                    edges=req.edges,
                    trigger_data=req.trigger_data,
                    on_failure=req.on_failure,
                    progress_callback=progress_callback,
                    preferences=_load_preferences(),
                )
                queue.put_nowait(("done", result))
            except Exception as e:
                queue.put_nowait(("error", str(e)))

        # 1. 推送 start 事件（含 run_id，供调试模式前端调用步进接口）
        yield _format_sse("start", {
            "workflow_id": req.workflow_id,
            "run_id": run_record.id if run_record else None,
        })

        # 2. 后台执行工作流，每步完成推送 step 事件
        task = asyncio.create_task(run())
        try:
            while True:
                try:
                    event_type, payload = await asyncio.wait_for(queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    # 15s 心跳保活，防止代理/浏览器断开空闲连接
                    yield ": ping\n\n"
                    continue
                if event_type == "step":
                    yield _format_sse("step", payload)
                elif event_type == "step_token":
                    # B1: LLM 流式 token 增量,推送 step_token 事件(step_id + delta)
                    yield _format_sse("step_token", payload)
                elif event_type == "done":
                    # 3. 推送 done 事件
                    yield _format_sse("done", {
                        "status": payload["status"],
                        "total_time_ms": payload["total_time_ms"],
                        "steps_result": payload["steps_result"],
                        "logs": payload.get("logs", []),
                        "token_usage": payload.get("token_usage"),
                        "paused_step_id": payload.get("paused_step_id"),
                        "paused_message": payload.get("paused_message"),
                    })
                    # A1: 审批暂停——保存 context + 推送 WS(不调用 finalize,不触发失败通知)
                    if run_record and payload.get("status") == "paused":
                        paused_step_id = payload.get("paused_step_id", "")
                        pause_run(db, run_record, payload, paused_step_id)
                        await _notify_paused(
                            run_record.id, req.workflow_id or "",
                            payload.get("paused_message", ""),
                            payload.get("paused_approvers", []),
                            paused_step_id,
                        )
                        break
                    # 更新 RunRecord(统一走 RunRecordService,内置 dashboard 缓存失效)
                    if run_record:
                        finalize(db, run_record, payload)
                    # 失败通知：status != success 时按用户偏好发送（异常不影响主流程）
                    await notify_failure_if_needed(
                        db,
                        workflow_name=workflow_name,
                        run_id=run_record.id if run_record else "",
                        status=payload["status"],
                        error=extract_error(payload["steps_result"]) or "",
                        steps_result=payload["steps_result"],
                    )
                    break
                elif event_type == "error":
                    # 4. 推送 error 事件
                    yield _format_sse("error", {"error": sanitize_error_text(str(payload))})
                    if run_record:
                        # 检测是否为用户主动中止（debug 模式 step/abort）
                        is_aborted = getattr(run_executor, "_aborted", False)
                        finalize_error(
                            db, run_record, str(payload),
                            status="aborted" if is_aborted else "failed",
                        )
                    # 失败通知：执行异常时按用户偏好发送（异常不影响主流程）
                    await notify_failure_if_needed(
                        db,
                        workflow_name=workflow_name,
                        run_id=run_record.id if run_record else "",
                        status="failed",
                        error=sanitize_error_text(str(payload)),
                        steps_result={},
                    )
                    break
        finally:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            # 调试模式：执行结束（正常完成/异常/断开）后清理调试会话
            if debug and run_record is not None:
                _debug_sessions.pop(run_record.id, None)
            # 客户端断开连接或任务被取消,修复 RunRecord 卡 running
            if task.cancelled() and run_record is not None:
                db_sess = SessionLocal()
                try:
                    stale = db_sess.query(RunRecord).filter(RunRecord.id == run_record.id).first()
                    if stale and stale.status == "running":
                        finalize_error(db_sess, stale, "客户端断开连接")
                finally:
                    db_sess.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.post("/{workflow_id}/runs/{run_id}/retry")
async def retry_run(
    workflow_id: str,
    run_id: str,
    mode: str = "from_failed",
    db: Session = Depends(get_db),
):
    """
    重试执行：基于指定 RunRecord 创建新的 RunRecord 并重新执行。
    :param mode: "from_failed"（默认，从第一个失败步骤继续，恢复 prev_context）
                 "from_start"（从头重新执行，忽略 prev_context，使用原 trigger_data 从 step_1 重跑）
    """
    # 1. 加载原 RunRecord（校验 workflow_id 防越权）
    run = db.query(RunRecord).filter(
        RunRecord.id == run_id, RunRecord.workflow_id == workflow_id
    ).first()
    if not run:
        raise HTTPException(status_code=404, detail="执行记录不存在")

    # 2. 加载 Workflow
    wf = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not wf:
        raise HTTPException(status_code=404, detail="工作流不存在")

    steps = json.loads(wf.steps) if wf.steps else []
    edges = json.loads(wf.edges) if wf.edges else []
    prev_steps_result = json.loads(run.steps_result) if run.steps_result else {}

    # 恢复触发数据上下文
    restored_trigger_data = json.loads(run.trigger_data) if run.trigger_data else None

    if mode == "from_start":
        # 从头重试：忽略 prev_context，使用原 trigger_data 从 step_1 重新执行
        new_run = create_running(db, workflow_id, "manual", restored_trigger_data)

        # 普通执行（不恢复上下文）
        try:
            result = await executor.execute(
                steps=steps,
                edges=edges,
                trigger_data=restored_trigger_data,
                on_failure=wf.on_failure or "stop",
                preferences=_load_preferences(),
            )
        except Exception as e:
            # executor 异常时更新 RunRecord 为 failed(统一脱敏 + 缓存失效)
            finalize_error(db, new_run, str(e))
            raise HTTPException(status_code=500, detail=f"重试执行失败: {e}")
    else:
        # from_failed（默认）：从第一个失败步骤继续，恢复 prev_context
        # 3. 找到失败的步骤
        failed_step_ids = [
            sid for sid, sr in prev_steps_result.items()
            if isinstance(sr, dict) and sr.get("status") == "failed"
        ]
        if not failed_step_ids:
            raise HTTPException(status_code=400, detail="没有失败的步骤可重试")

        # 4. 创建新 RunRecord
        new_run = create_running(db, workflow_id, "manual", restored_trigger_data)

        # 5. 恢复上下文并重跑（从第一个失败步骤开始）
        try:
            result = await executor.execute_with_context(
                steps=steps,
                edges=edges,
                trigger_data=restored_trigger_data,
                on_failure=wf.on_failure or "stop",
                prev_context=prev_steps_result,
                start_from=failed_step_ids[0],
                preferences=_load_preferences(),
            )
        except Exception as e:
            # executor 异常时更新 RunRecord 为 failed(统一脱敏 + 缓存失效)
            finalize_error(db, new_run, str(e))
            raise HTTPException(status_code=500, detail=f"重试执行失败: {e}")

    # 6. 更新 RunRecord(统一走 RunRecordService,内置 dashboard 缓存失效)
    finalize(db, new_run, result)

    # 失败通知：status != success 时按用户偏好发送（异常不影响主流程）
    await notify_failure_if_needed(
        db,
        workflow_name=wf.name,
        run_id=new_run.id,
        status=result["status"],
        error=extract_error(result["steps_result"]) or "",
        steps_result=result["steps_result"],
    )

    return new_run.to_dict()


@router.post("/{workflow_id}/runs/{run_id}/approve")
async def approve_run(
    workflow_id: str,
    run_id: str,
    req: ApproveRequest,
    db: Session = Depends(get_db),
):
    """A1: 审批暂停的工作流——批准继续执行后续步骤,拒绝则标记失败。

    :param req.decision: "approved" | "rejected"
    :param req.comment: 审批评论
    """
    # 1. 加载 RunRecord(校验 workflow_id 防越权)
    run = db.query(RunRecord).filter(
        RunRecord.id == run_id, RunRecord.workflow_id == workflow_id
    ).first()
    if not run:
        raise HTTPException(status_code=404, detail="执行记录不存在")
    if run.status != "paused":
        raise HTTPException(
            status_code=400,
            detail=f"执行记录状态为 {run.status},仅 paused 状态可审批",
        )
    if not run.paused_context:
        raise HTTPException(status_code=400, detail="缺少暂停上下文,无法恢复")

    # 2. 加载 Workflow
    wf = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not wf:
        raise HTTPException(status_code=404, detail="工作流不存在")

    steps = json.loads(wf.steps) if wf.steps else []
    edges = json.loads(wf.edges) if wf.edges else []

    # 3. 反序列化暂停上下文
    try:
        paused_context = json.loads(run.paused_context)
    except (json.JSONDecodeError, TypeError):
        raise HTTPException(status_code=500, detail="暂停上下文解析失败")

    # 4. 调用 executor.resume_execution 恢复执行
    try:
        result = await executor.resume_execution(
            steps=steps,
            edges=edges,
            paused_context=paused_context,
            paused_step_id=run.paused_step_id or "",
            decision=req.decision,
            comment=req.comment,
            on_failure=wf.on_failure or "stop",
            preferences=_load_preferences(),
        )
    except Exception as e:
        logger.exception(f"审批恢复执行异常 run_id={run_id}: {e}")
        finalize_error(db, run, str(e))
        raise HTTPException(status_code=500, detail=f"审批恢复执行失败: {e}")

    # 5. 更新 RunRecord 终态
    finalize(db, run, result)

    # 6. 推送 WS 恢复通知(异常不影响主流程)
    try:
        await notify_workflow_resumed(run_id, workflow_id, req.decision)
    except Exception as e:
        logger.warning(f"推送审批恢复 WS 通知失败: {e}")

    # 7. 失败通知(rejected 或恢复执行失败时按用户偏好发送)
    await notify_failure_if_needed(
        db,
        workflow_name=wf.name,
        run_id=run_id,
        status=result["status"],
        error=extract_error(result["steps_result"]) or result.get("error", "") or "",
        steps_result=result["steps_result"],
    )

    return run.to_dict()


@router.post("/{workflow_id}/runs/{run_id}/step/next")
async def step_next(workflow_id: str, run_id: str, db: Session = Depends(get_db)):
    """调试模式：执行下一步（释放 step_event 让等待的 executor 继续）"""
    session = _debug_sessions.get(run_id)
    if not session:
        raise HTTPException(status_code=404, detail="调试会话不存在或已结束")
    session["step_event"].set()  # 让等待的 executor 继续
    return {"ok": True}


@router.post("/{workflow_id}/runs/{run_id}/step/continue")
async def step_continue(workflow_id: str, run_id: str, db: Session = Depends(get_db)):
    """调试模式：全速继续执行（关闭 debug_mode 并释放当前等待）"""
    session = _debug_sessions.get(run_id)
    if not session:
        raise HTTPException(status_code=404, detail="调试会话不存在或已结束")
    session["executor"].set_debug_mode(False)
    session["step_event"].set()
    return {"ok": True}


@router.post("/{workflow_id}/runs/{run_id}/step/abort")
async def step_abort(workflow_id: str, run_id: str, db: Session = Depends(get_db)):
    """调试模式：中止执行（置位 _aborted 并释放等待，RunRecord 状态由异常流程标记）"""
    session = _debug_sessions.get(run_id)
    if not session:
        raise HTTPException(status_code=404, detail="调试会话不存在或已结束")
    session["executor"].abort()
    return {"ok": True}


def _steps_result_of(run: RunRecord) -> dict:
    """从 RunRecord 解析 steps_result 为 dict"""
    return json.loads(run.steps_result) if run.steps_result else {}


def _to_local_str(dt) -> str:
    """UTC datetime 转本地时区可读字符串；为空时返回"未记录" """
    if not dt:
        return "未记录"
    # DB 中 datetime 可能为 naive（无 tzinfo），按 UTC 处理后转本地
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _build_csv(run: RunRecord) -> str:
    """把 steps_result 展平为 CSV 表格字符串"""
    steps_result = _steps_result_of(run)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["step_id", "step_name", "tool", "status", "time_ms", "output_summary"])
    if not steps_result:
        writer.writerow(["", "", "", "", "", "无步骤数据"])
    else:
        for step_id, sr in steps_result.items():
            if not isinstance(sr, dict):
                continue
            raw_output = sr.get("output")
            if raw_output is None:
                summary = ""
            else:
                summary = str(raw_output).replace("\n", " ")[:200]
            writer.writerow([
                step_id,
                sr.get("name", ""),
                sr.get("tool", ""),
                sr.get("status", ""),
                sr.get("time_ms", ""),
                summary,
            ])
    return buf.getvalue()


def _build_markdown(run: RunRecord, workflow) -> str:
    """生成 Markdown 执行报告"""
    steps_result = _steps_result_of(run)
    workflow_name = workflow.name if workflow else ""

    lines = [
        "# 工作流执行报告",
        "",
        f"- **工作流**: {workflow_name}",
        f"- **执行 ID**: {run.id}",
        f"- **触发类型**: {run.trigger_type}",
        f"- **状态**: {run.status}",
        f"- **开始时间**: {_to_local_str(run.started_at)}",
        f"- **结束时间**: {_to_local_str(run.finished_at)}",
        f"- **总耗时**: {run.total_time_ms} ms",
        "",
        "## 步骤详情",
        "",
    ]

    if not steps_result:
        lines.append("无步骤数据")
    else:
        for idx, (step_id, sr) in enumerate(steps_result.items(), 1):
            if not isinstance(sr, dict):
                continue
            output_str = json.dumps(
                sr.get("output"), ensure_ascii=False, indent=2, default=str
            )
            if len(output_str) > 2000:
                output_str = output_str[:2000]
            error = sr.get("error") or "无"
            lines.extend([
                f"### {idx}. {sr.get('name', '')} (`{step_id}`)",
                f"- **工具**: {sr.get('tool', '')}",
                f"- **状态**: {sr.get('status', '')}",
                f"- **耗时**: {sr.get('time_ms', '')} ms",
                "- **输出**:",
                "```",
                output_str,
                "```",
                f"- **错误**: {error}",
                "",
            ])

    return "\n".join(lines)


@router.get("/runs/{run_id}/export")
async def export_run(
    run_id: str,
    format: Literal["json", "csv", "markdown"] = Query("json"),
    db: Session = Depends(get_db),
):
    """导出执行结果，支持 json / csv / markdown 三种格式"""
    run = db.query(RunRecord).filter(RunRecord.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="执行记录不存在")
    workflow = run.workflow  # 关联 Workflow，用于报告标题

    if format == "json":
        content = json.dumps(run.to_dict(), ensure_ascii=False, indent=2)
        media_type = "application/json"
        filename = f"run_{run_id}.json"
    elif format == "csv":
        content = _build_csv(run)
        media_type = "text/csv"
        filename = f"run_{run_id}.csv"
    else:  # markdown
        content = _build_markdown(run, workflow)
        media_type = "text/markdown"
        filename = f"run_{run_id}.md"

    return Response(
        content=content.encode("utf-8"),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
