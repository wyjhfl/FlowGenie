"""Webhook 触发路由"""
import json
import hmac
import hashlib
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from db.database import SessionLocal, get_db
from db.models import Workflow, RunRecord
from engine.executor import executor
from core.preference_schema import load_preferences_from_db
from core.error_sanitize import sanitize_error_text, extract_error
from core.rate_limiter import webhook_limiter
from core.run_record_service import finalize, finalize_error, notify_failure_if_needed, pause_run
from routers.ws import notify_workflow_paused

router = APIRouter()
logger = logging.getLogger(__name__)


def _verify_signature(secret: str, body: bytes, signature_header: str | None) -> bool:
    """校验 HMAC-SHA256 签名

    :param secret: workflow 的 webhook_secret
    :param body: 请求原始 body 字节
    :param signature_header: X-FlowGenie-Signature 头,格式 "sha256=<hex>"
    :return: True=校验通过;False=校验失败
    """
    if not signature_header:
        return False
    # 期望格式: sha256=<hex>
    if not signature_header.startswith("sha256="):
        return False
    expected = signature_header[len("sha256="):]
    # 用 hmac.compare_digest 防止时序攻击
    mac = hmac.new(secret.encode(), body, hashlib.sha256)
    return hmac.compare_digest(mac.hexdigest(), expected)


async def _run_workflow_background(
    run_id: str,
    workflow_id: str,
    steps: list[dict],
    edges: list[dict],
    trigger_data: dict,
    on_failure: str,
):
    """后台异步执行工作流并更新 RunRecord。

    使用独立 DB 会话（请求会话在响应返回后已关闭）。
    执行期间不持有 DB 会话，避免长工作流占用连接池；仅在执行前/后用短会话读写 RunRecord。
    RunRecord 已在触发请求中创建并 commit，此处按 run_id 查询更新。
    """
    # 1. 执行前：用短会话确认 RunRecord 存在并读取工作流名（用于失败通知），随后立即关闭
    workflow_name = ""
    db = SessionLocal()
    try:
        run = db.query(RunRecord).filter(RunRecord.id == run_id).first()
        if not run:
            return
        wf = db.query(Workflow).filter(Workflow.id == workflow_id).first()
        workflow_name = wf.name if wf else ""
    finally:
        db.close()

    # 2. 执行中：不持有 DB 会话，executor 内部自管理上下文
    result = None
    status = "failed"
    error = None
    try:
        result = await executor.execute(
            steps=steps,
            edges=edges,
            trigger_data=trigger_data,
            on_failure=on_failure,
            preferences=load_preferences_from_db(),
        )
        status = result["status"]
        if status != "success":
            error = extract_error(result["steps_result"])
    except Exception as e:
        status = "failed"
        error = sanitize_error_text(str(e))

    # 3. 执行完毕：用新会话查询 RunRecord 并更新状态(统一走 RunRecordService)
    db = SessionLocal()
    try:
        run = db.query(RunRecord).filter(RunRecord.id == run_id).first()
        if run:
            # A1: 审批暂停——保存 context + 推送 WS(不调用 finalize,不触发失败通知)
            if result is not None and status == "paused":
                paused_step_id = result.get("paused_step_id", "")
                pause_run(db, run, result, paused_step_id)
                try:
                    await notify_workflow_paused(
                        run_id=run_id, workflow_id=workflow_id,
                        message=result.get("paused_message", "请审批此步骤以继续执行"),
                        approvers=result.get("paused_approvers", []),
                        paused_step_id=paused_step_id,
                    )
                except Exception as e:
                    logger.warning(f"推送审批 WS 通知失败: {e}")
            elif result is not None:
                finalize(db, run, result)
            else:
                finalize_error(db, run, error or "执行异常")

        # 失败通知（暂停不触发;异常不影响主流程,error 已脱敏)
        if status != "paused":
            await notify_failure_if_needed(
                db,
                workflow_name=workflow_name,
                run_id=run_id,
                status=status,
                error=error or "",
                steps_result=result.get("steps_result") if result else None,
            )
    finally:
        db.close()


@router.post("/webhooks/{webhook_id}")
async def trigger_via_webhook(
    webhook_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Webhook 触发端点：根据 webhook_id 查找工作流并异步执行。
    立即返回 run_id（HTTP 202），工作流在 BackgroundTasks 中异步执行，
    避免长工作流 HTTP 超时。请求 body 作为 trigger_data 传入工作流。

    安全:
    - 限流:每 webhook_id 30 秒内最多 10 次,超限返回 429
    - 签名:若 workflow 配置了 webhook_secret,必须提供 X-FlowGenie-Signature 头
      格式 "sha256=<hmac>",用 secret 对原始 body 做 HMAC-SHA256;无 secret 配置时跳过(向后兼容)
    """
    # 0. 限流:每 webhook_id 独立桶
    if not webhook_limiter.is_allowed(webhook_id):
        return JSONResponse(
            status_code=429,
            content={"detail": "请求过于频繁,请稍后重试"},
        )

    # 1. 查找含此 webhook_id 的工作流
    wf = db.query(Workflow).filter(Workflow.webhook_id == webhook_id).first()
    if not wf:
        raise HTTPException(status_code=404, detail="Webhook 不存在")

    # 2. 读取原始 body(签名校验需要原始字节,不能先 json 解析)
    raw_body = await request.body()

    # 3. 签名校验:若配置了 webhook_secret,必须提供有效签名
    if wf.webhook_secret:
        signature = request.headers.get("X-FlowGenie-Signature")
        if not _verify_signature(wf.webhook_secret, raw_body, signature):
            raise HTTPException(status_code=401, detail="签名校验失败")

    # 4. 解析请求 body 作为 trigger_data(保留非 JSON body 兜底)
    try:
        body = json.loads(raw_body.decode("utf-8")) if raw_body else {}
    except Exception:
        body = {"raw": raw_body.decode("utf-8", errors="replace")} if raw_body else {}

    # 5. 加载工作流定义
    steps = json.loads(wf.steps) if wf.steps else []
    edges = json.loads(wf.edges) if wf.edges else []

    # 6. 校验工作流是否有 steps
    if not steps:
        raise HTTPException(status_code=400, detail="工作流无 steps，无法执行")

    # 7. 立即创建 RunRecord（status=running）
    run = RunRecord(
        workflow_id=wf.id,
        trigger_type="webhook",
        status="running",
        started_at=datetime.now(timezone.utc),
        trigger_data=json.dumps(body, ensure_ascii=False, default=str) if body else None,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    # 8. 后台异步执行工作流（不阻塞 HTTP 响应）
    background_tasks.add_task(
        _run_workflow_background,
        run_id=run.id,
        workflow_id=wf.id,
        steps=steps,
        edges=edges,
        trigger_data=body,
        on_failure=wf.on_failure or "stop",
    )

    # 9. 立即返回 202 Accepted
    return JSONResponse(
        status_code=202,
        content={
            "run_id": run.id,
            "status": "running",
            "workflow_id": wf.id,
        },
    )
