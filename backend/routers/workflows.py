"""工作流 CRUD 路由"""
import json
import uuid
import secrets
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request, Query
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc
from db.database import get_db
from db.models import Workflow, RunRecord, WorkflowVersion
from core.validator import validate_on_complete_trigger
from cachetools import TTLCache
import threading
from sqlalchemy.orm import load_only

router = APIRouter()
logger = logging.getLogger(__name__)

# 工作流列表缓存(60s TTL,写操作后主动失效)
_list_cache: TTLCache = TTLCache(maxsize=16, ttl=60)
_list_cache_lock = threading.Lock()


def _generate_webhook_secret() -> str:
    """生成 webhook HMAC 签名密钥(32 字节随机,hex 编码 = 64 字符)"""
    return secrets.token_hex(32)


class WorkflowCreate(BaseModel):
    name: str
    scenario: str = ""
    summary: str = ""
    steps: list[dict] = []
    edges: list[dict] = []
    on_failure: str = "stop"
    tags: Optional[list[str]] = None
    on_complete_trigger: Optional[list[dict]] = None  # A3: [{workflow_id, on}]


class WorkflowUpdate(BaseModel):
    name: Optional[str] = None
    scenario: Optional[str] = None
    summary: Optional[str] = None
    steps: Optional[list[dict]] = None
    edges: Optional[list[dict]] = None
    on_failure: Optional[str] = None
    tags: Optional[list[str]] = None
    on_complete_trigger: Optional[list[dict]] = None  # A3: [{workflow_id, on}]


class BatchActionRequest(BaseModel):
    """批量操作请求体"""
    ids: list[str]
    action: str  # enable_schedule | disable_schedule | delete


@router.post("/workflows")
def create_workflow(req: WorkflowCreate, db: Session = Depends(get_db)):
    # A3: 校验 on_complete_trigger 结构(创建时无 workflow_id,跳过自引用检测)
    trigger_errors = validate_on_complete_trigger(req.on_complete_trigger)
    if trigger_errors:
        raise HTTPException(status_code=400, detail="; ".join(trigger_errors))

    # 检查是否含 webhook_trigger,生成 webhook_id 和 webhook_secret
    webhook_id = None
    webhook_secret = None
    for step in req.steps:
        if step.get("tool") == "webhook_trigger":
            webhook_id = str(uuid.uuid4())
            webhook_secret = _generate_webhook_secret()
            break

    wf = Workflow(
        name=req.name,
        scenario=req.scenario,
        summary=req.summary,
        steps=json.dumps(req.steps, ensure_ascii=False),
        edges=json.dumps(req.edges, ensure_ascii=False),
        on_failure=req.on_failure,
        tags=json.dumps(req.tags, ensure_ascii=False) if req.tags is not None else "[]",
        on_complete_trigger=json.dumps(req.on_complete_trigger, ensure_ascii=False) if req.on_complete_trigger is not None else "[]",
        webhook_id=webhook_id,
        webhook_secret=webhook_secret,
    )
    db.add(wf)
    db.commit()
    db.refresh(wf)
    with _list_cache_lock:
        _list_cache.clear()
    return wf.to_dict()


@router.post("/workflows/import")
async def import_workflow(request: Request, db: Session = Depends(get_db)):
    """导入工作流：接收 JSON body（含 name + steps + edges，或完整导出 JSON）。
    校验 steps 为非空 list、edges 为 list，生成新 workflow_id 和 webhook_id。
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="JSON 格式无效")

    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="请求体必须是 JSON 对象")

    name = body.get("name")
    steps = body.get("steps")
    edges = body.get("edges", [])
    scenario = body.get("scenario", "") or ""
    summary = body.get("summary", "") or ""
    on_failure = body.get("on_failure", "stop") or "stop"
    on_complete_trigger = body.get("on_complete_trigger", []) or []

    if not isinstance(name, str) or not name.strip():
        raise HTTPException(status_code=400, detail="name 必须是非空字符串")
    if not isinstance(steps, list) or len(steps) == 0:
        raise HTTPException(status_code=400, detail="steps 必须是非空列表")
    if not isinstance(edges, list):
        raise HTTPException(status_code=400, detail="edges 必须是列表")

    # 检查是否含 webhook_trigger，生成新 webhook_id 和 webhook_secret
    webhook_id = None
    webhook_secret = None
    for step in steps:
        if isinstance(step, dict) and step.get("tool") == "webhook_trigger":
            webhook_id = str(uuid.uuid4())
            webhook_secret = _generate_webhook_secret()
            break

    wf = Workflow(
        name=name.strip(),
        scenario=scenario,
        summary=summary,
        steps=json.dumps(steps, ensure_ascii=False),
        edges=json.dumps(edges, ensure_ascii=False),
        on_failure=on_failure,
        on_complete_trigger=json.dumps(on_complete_trigger, ensure_ascii=False),
        webhook_id=webhook_id,
        webhook_secret=webhook_secret,
    )
    db.add(wf)
    db.commit()
    db.refresh(wf)
    with _list_cache_lock:
        _list_cache.clear()
    return wf.to_dict()


@router.get("/workflows")
def list_workflows(
    tags: str = Query(None, description="逗号分隔的标签,工作流需全部包含"),
    db: Session = Depends(get_db),
):
    cache_key = f"list:{tags or 'all'}"
    with _list_cache_lock:
        cached = _list_cache.get(cache_key)
        if cached is not None:
            return cached
    # P2: 用 load_only 限定列,避免加载 summary/edges 等大字段(N+1 字段冗余优化)
    # 仅取列表所需列:steps 用于提取 trigger 工具名,tags 用于筛选
    wfs = (
        db.query(Workflow)
        .options(load_only(
            Workflow.id, Workflow.name, Workflow.scenario,
            Workflow.schedule_enabled, Workflow.webhook_id,
            Workflow.steps, Workflow.tags,
            Workflow.created_at, Workflow.updated_at,
        ))
        .order_by(Workflow.updated_at.desc())
        .all()
    )
    # 解析标签筛选参数：逗号分隔，工作流需全部包含
    filter_tags = [t.strip() for t in tags.split(",")] if tags else []
    # 列表不含 steps/edges 大字段，但提取 trigger 工具列表供前端筛选
    result = []
    for w in wfs:
        wf_tags = json.loads(w.tags) if w.tags else []
        # 标签筛选：工作流需包含所有传入标签
        if filter_tags and not all(ft in wf_tags for ft in filter_tags):
            continue
        steps = json.loads(w.steps) if w.steps else []
        triggers = [
            s.get("tool") for s in steps
            if isinstance(s, dict) and isinstance(s.get("tool"), str) and s.get("tool", "").endswith("_trigger")
        ]
        result.append({
            "id": w.id,
            "name": w.name,
            "scenario": w.scenario,
            "schedule_enabled": w.schedule_enabled,
            "webhook_id": w.webhook_id,
            "triggers": triggers,
            "tags": wf_tags,
            "created_at": w.created_at.isoformat() if w.created_at else None,
            "updated_at": w.updated_at.isoformat() if w.updated_at else None,
        })
    with _list_cache_lock:
        _list_cache[cache_key] = result
    return result


@router.get("/workflows/schedule/status")
def get_schedule_status(db: Session = Depends(get_db)):
    """返回所有 schedule_enabled=True 的工作流的定时任务详情"""
    from scheduler.manager import scheduler_manager

    workflows = db.query(Workflow).filter(Workflow.schedule_enabled == True).all()
    result = []
    for wf in workflows:
        # 从 schedule_trigger 节点 params.cron 读取 cron 表达式
        steps = json.loads(wf.steps) if wf.steps else []
        cron_expr = None
        for step in steps:
            if step.get("tool") == "schedule_trigger":
                cron_expr = step.get("params", {}).get("cron")
                break

        # 从调度器获取下次执行时间
        next_run_time = None
        job = scheduler_manager.get_job(wf.id) if scheduler_manager else None
        if job and job.next_run_time:
            next_run_time = job.next_run_time.isoformat()

        # 最近一次 run 的状态
        last_run = (
            db.query(RunRecord)
            .filter(RunRecord.workflow_id == wf.id)
            .order_by(RunRecord.started_at.desc())
            .first()
        )
        last_run_info = None
        if last_run:
            last_run_info = {
                "id": last_run.id,
                "status": last_run.status,
                "started_at": last_run.started_at.isoformat() if last_run.started_at else None,
                "finished_at": last_run.finished_at.isoformat() if last_run.finished_at else None,
            }

        result.append({
            "workflow_id": wf.id,
            "name": wf.name,
            "cron": cron_expr,
            "next_run_time": next_run_time,
            "last_run": last_run_info,
        })
    return result


@router.get("/workflows/{workflow_id}")
def get_workflow(workflow_id: str, db: Session = Depends(get_db)):
    wf = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not wf:
        raise HTTPException(status_code=404, detail="工作流不存在")
    return wf.to_dict()


@router.post("/workflows/{workflow_id}/duplicate")
def duplicate_workflow(workflow_id: str, db: Session = Depends(get_db)):
    """复制工作流：创建新工作流，name = 原 name + "(副本)"，steps/edges 相同，
    生成新 workflow_id 和 webhook_id。
    """
    wf = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not wf:
        raise HTTPException(status_code=404, detail="工作流不存在")

    steps = json.loads(wf.steps) if wf.steps else []
    edges = json.loads(wf.edges) if wf.edges else []

    # 生成新 webhook_id 和 webhook_secret(若含 webhook_trigger)
    webhook_id = None
    webhook_secret = None
    for step in steps:
        if isinstance(step, dict) and step.get("tool") == "webhook_trigger":
            webhook_id = str(uuid.uuid4())
            webhook_secret = _generate_webhook_secret()
            break

    new_wf = Workflow(
        name=f"{wf.name}(副本)",
        scenario=wf.scenario,
        summary=wf.summary,
        steps=json.dumps(steps, ensure_ascii=False),
        edges=json.dumps(edges, ensure_ascii=False),
        on_failure=wf.on_failure,
        webhook_id=webhook_id,
        webhook_secret=webhook_secret,
    )
    db.add(new_wf)
    db.commit()
    db.refresh(new_wf)
    with _list_cache_lock:
        _list_cache.clear()
    return new_wf.to_dict()


@router.put("/workflows/{workflow_id}")
def update_workflow(workflow_id: str, req: WorkflowUpdate, db: Session = Depends(get_db)):
    wf = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not wf:
        raise HTTPException(status_code=404, detail="工作流不存在")

    # A3: 校验 on_complete_trigger 结构(含自引用检测)
    trigger_errors = validate_on_complete_trigger(req.on_complete_trigger, workflow_id)
    if trigger_errors:
        raise HTTPException(status_code=400, detail="; ".join(trigger_errors))

    # 捕获更新前的 webhook 状态，用于后续检测增删并重新生成 webhook_id
    old_steps = json.loads(wf.steps) if wf.steps else []
    had_webhook = any(s.get("tool") == "webhook_trigger" for s in old_steps)

    # 检测是否需要创建版本快照（steps/edges/summary/on_failure/tags/on_complete_trigger 任一变更时才快照）
    need_snapshot = any(
        v is not None for v in [req.steps, req.edges, req.summary, req.on_failure, req.tags, req.on_complete_trigger]
    )
    if need_snapshot:
        try:
            latest = (
                db.query(WorkflowVersion)
                .filter(WorkflowVersion.workflow_id == workflow_id)
                .order_by(WorkflowVersion.version_number.desc())
                .first()
            )
            next_version = (latest.version_number + 1) if latest else 1
            version = WorkflowVersion(
                workflow_id=workflow_id,
                version_number=next_version,
                steps=wf.steps,
                edges=wf.edges,
                summary=wf.summary,
                on_failure=wf.on_failure,
                tags=wf.tags,
                note="自动快照",
            )
            db.add(version)
        except Exception as e:
            # 快照创建失败不应阻断更新，仅记录日志
            logger.warning(f"创建版本快照失败 (workflow={workflow_id}): {e}")

    if req.name is not None:
        wf.name = req.name
    if req.scenario is not None:
        wf.scenario = req.scenario
    if req.summary is not None:
        wf.summary = req.summary
    if req.steps is not None:
        wf.steps = json.dumps(req.steps, ensure_ascii=False)
    if req.edges is not None:
        wf.edges = json.dumps(req.edges, ensure_ascii=False)
    if req.on_failure is not None:
        wf.on_failure = req.on_failure
    if req.tags is not None:
        wf.tags = json.dumps(req.tags, ensure_ascii=False)
    # A3: 链式触发配置更新(None 视为清空,存 "[]")
    if req.on_complete_trigger is not None:
        wf.on_complete_trigger = json.dumps(req.on_complete_trigger, ensure_ascii=False)

    # 检测 webhook_trigger 增删并重新生成 webhook_id 和 webhook_secret
    if req.steps is not None:
        has_webhook = any(s.get("tool") == "webhook_trigger" for s in req.steps)
        if has_webhook != had_webhook:
            wf.webhook_id = str(uuid.uuid4()) if has_webhook else None
            wf.webhook_secret = _generate_webhook_secret() if has_webhook else None

    db.commit()
    db.refresh(wf)

    # 检测 schedule_trigger 变更并同步调度器（commit 后调度器才能读到新配置）
    if req.steps is not None:
        has_schedule = any(s.get("tool") == "schedule_trigger" for s in req.steps)
        if has_schedule and wf.schedule_enabled:
            from scheduler.manager import scheduler_manager
            # 先移除旧 job,再用新配置注册（best-effort,job 可能不存在）
            try:
                scheduler_manager.remove_job(wf.id)
            except Exception:
                pass
            # add_job 内部从 DB 读取最新 steps 解析 cron 并注册
            scheduler_manager.add_job(wf.id)

    with _list_cache_lock:
        _list_cache.clear()
    return wf.to_dict()


@router.delete("/workflows/{workflow_id}")
def delete_workflow(workflow_id: str, db: Session = Depends(get_db)):
    wf = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not wf:
        raise HTTPException(status_code=404, detail="工作流不存在")
    # 先移除调度任务（best-effort,job 可能不存在）
    from scheduler.manager import scheduler_manager
    try:
        scheduler_manager.remove_job(wf.id)
    except Exception:
        pass
    db.delete(wf)  # cascade 会自动删除关联的 RunRecord
    db.commit()
    with _list_cache_lock:
        _list_cache.clear()
    return {"success": True}


@router.get("/workflows/{workflow_id}/runs")
def list_runs(workflow_id: str, db: Session = Depends(get_db)):
    runs = (
        db.query(RunRecord)
        .filter(RunRecord.workflow_id == workflow_id)
        .order_by(RunRecord.started_at.desc())
        .limit(50)
        .all()
    )
    return [
        {
            "id": r.id,
            "trigger_type": r.trigger_type,
            "status": r.status,
            "total_time_ms": r.total_time_ms,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            "error": r.error,
        }
        for r in runs
    ]


@router.delete("/workflows/{workflow_id}/runs/cleanup")
def cleanup_workflow_runs(
    workflow_id: str,
    before: Optional[str] = Query(None, description="ISO 8601 截止时间,清理此时间之前 started_at 的已完成记录;省略则按偏好 archive_retention_days"),
    retention_days: Optional[int] = Query(None, description="保留天数(覆盖偏好值);0=永久保留"),
    db: Session = Depends(get_db),
):
    """D4: 手动清理指定工作流的超期已完成执行记录

    清理规则:
    - 仅清理 status in (success, partial_success) 的记录;failed 始终保留供复盘
    - before 参数:手动指定截止时间(ISO 8601),优先于 retention_days
    - retention_days 参数:覆盖偏好值;0 表示永久保留(返回 deleted=0)
    - 二者均省略时:从偏好 archive_retention_days 读取(默认 90)
    """
    wf = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not wf:
        raise HTTPException(status_code=404, detail="工作流不存在")

    from core.run_archive import cleanup_old_run_records
    try:
        deleted = cleanup_old_run_records(
            db,
            retention_days=retention_days,
            workflow_id=workflow_id,
            before_iso=before,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 失效 dashboard 缓存(执行记录被清理,统计已变化)
    try:
        from routers.stats import _dashboard_cache
        _dashboard_cache.clear()
    except Exception:
        pass

    return {"deleted": deleted, "workflow_id": workflow_id}


@router.get("/workflows/{workflow_id}/runs/{run_id}")
def get_run(workflow_id: str, run_id: str, db: Session = Depends(get_db)):
    run = db.query(RunRecord).filter(
        RunRecord.id == run_id, RunRecord.workflow_id == workflow_id
    ).first()
    if not run:
        raise HTTPException(status_code=404, detail="执行记录不存在")
    return run.to_dict()


@router.get("/workflows/{workflow_id}/runs/{run_id1}/compare/{run_id2}")
def compare_runs(workflow_id: str, run_id1: str, run_id2: str, db: Session = Depends(get_db)):
    """对比同工作流的两次执行,返回步骤级 diff(状态/耗时/错误变化)"""
    run1 = db.query(RunRecord).filter(
        RunRecord.id == run_id1, RunRecord.workflow_id == workflow_id
    ).first()
    run2 = db.query(RunRecord).filter(
        RunRecord.id == run_id2, RunRecord.workflow_id == workflow_id
    ).first()
    if not run1:
        raise HTTPException(status_code=404, detail="执行记录 1 不存在")
    if not run2:
        raise HTTPException(status_code=404, detail="执行记录 2 不存在")

    # 取工作流步骤定义,构建 step_id → name 映射
    wf = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    step_name_map: dict = {}
    if wf:
        try:
            wf_steps = json.loads(wf.steps) if wf.steps else []
            for s in wf_steps:
                if isinstance(s, dict) and s.get("id"):
                    step_name_map[s["id"]] = s.get("name", s["id"])
        except (json.JSONDecodeError, TypeError):
            pass

    # 解析两次执行的 steps_result
    try:
        sr1 = json.loads(run1.steps_result) if run1.steps_result else {}
    except (json.JSONDecodeError, TypeError):
        sr1 = {}
    try:
        sr2 = json.loads(run2.steps_result) if run2.steps_result else {}
    except (json.JSONDecodeError, TypeError):
        sr2 = {}

    # 按 step_id 自然顺序对齐(step_1, step_2, ... step_10)
    def _num_key(sid: str) -> tuple:
        import re
        m = re.search(r"(\d+)$", sid)
        return (int(m.group(1)),) if m else (float("inf"), sid)

    all_step_ids = sorted(set(sr1.keys()) | set(sr2.keys()), key=_num_key)

    diffs = []
    for sid in all_step_ids:
        r1 = sr1.get(sid, {}) if isinstance(sr1.get(sid), dict) else {}
        r2 = sr2.get(sid, {}) if isinstance(sr2.get(sid), dict) else {}
        status1 = r1.get("status")
        status2 = r2.get("status")
        time1 = r1.get("time_ms")
        time2 = r2.get("time_ms")
        error1 = r1.get("error")
        error2 = r2.get("error")
        # 是否变化:状态/耗时/错误任一不同
        changed = (status1 != status2) or (time1 != time2) or (error1 != error2)
        diffs.append({
            "step_id": sid,
            "name": step_name_map.get(sid, sid),
            "status1": status1,
            "status2": status2,
            "time1": time1,
            "time2": time2,
            "error1": error1,
            "error2": error2,
            "changed": changed,
        })

    return {
        "run1": {
            "id": run1.id,
            "status": run1.status,
            "total_time_ms": run1.total_time_ms,
            "started_at": run1.started_at.isoformat() if run1.started_at else None,
            "trigger_type": run1.trigger_type,
        },
        "run2": {
            "id": run2.id,
            "status": run2.status,
            "total_time_ms": run2.total_time_ms,
            "started_at": run2.started_at.isoformat() if run2.started_at else None,
            "trigger_type": run2.trigger_type,
        },
        "steps": diffs,
    }


@router.post("/workflows/{workflow_id}/schedule/enable")
def enable_schedule(workflow_id: str, db: Session = Depends(get_db)):
    wf = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not wf:
        raise HTTPException(status_code=404, detail="工作流不存在")

    # 检查是否含 schedule_trigger
    steps = json.loads(wf.steps) if wf.steps else []
    has_schedule = any(s.get("tool") == "schedule_trigger" for s in steps)
    if not has_schedule:
        raise HTTPException(status_code=400, detail="工作流不含 schedule_trigger 步骤，无法启用调度")

    # 先注册到调度器，失败则不启用，避免 DB 与调度器状态不一致
    from scheduler.manager import scheduler_manager
    try:
        scheduler_manager.add_job(workflow_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"启用调度失败: {e}")

    # 调度任务注册成功后再更新 DB
    wf.schedule_enabled = True
    db.commit()
    with _list_cache_lock:
        _list_cache.clear()

    return {"success": True, "schedule_enabled": True}


@router.post("/workflows/{workflow_id}/schedule/disable")
def disable_schedule(workflow_id: str, db: Session = Depends(get_db)):
    wf = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not wf:
        raise HTTPException(status_code=404, detail="工作流不存在")

    # 先从调度器移除，再更新 DB，避免 DB 已禁用但 job 仍触发
    from scheduler.manager import scheduler_manager
    try:
        scheduler_manager.remove_job(workflow_id)
    except Exception:
        # remove_job 失败不阻断（job 可能已不存在），仅忽略
        pass

    wf.schedule_enabled = False
    db.commit()
    with _list_cache_lock:
        _list_cache.clear()

    return {"success": True, "schedule_enabled": False}


@router.post("/workflows/{workflow_id}/schedule/run-now")
async def run_schedule_now(
    workflow_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """立即触发一次定时工作流执行，返回 run_id（后台异步执行）"""
    wf = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not wf:
        raise HTTPException(status_code=404, detail="工作流不存在")

    # 预创建 RunRecord 以便立即返回 run_id，后台复用调度器执行逻辑
    run = RunRecord(
        workflow_id=workflow_id,
        trigger_type="schedule",
        status="running",
        started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    from scheduler.manager import _execute_scheduled_workflow
    background_tasks.add_task(_execute_scheduled_workflow, workflow_id, run.id)

    return {"run_id": run.id}


@router.post("/workflows/{workflow_id}/webhook/reset-secret")
def reset_webhook_secret(workflow_id: str, db: Session = Depends(get_db)):
    """重置 webhook 签名密钥(原 secret 立即失效)。

    仅当工作流含 webhook_trigger 时有效。返回新 secret(仅本次返回,后续不再可见)。
    """
    wf = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not wf:
        raise HTTPException(status_code=404, detail="工作流不存在")
    if not wf.webhook_id:
        raise HTTPException(status_code=400, detail="工作流未启用 webhook 触发")

    wf.webhook_secret = _generate_webhook_secret()
    db.commit()
    db.refresh(wf)
    return {"webhook_id": wf.webhook_id, "webhook_secret": wf.webhook_secret}


# ===== 批量操作 =====


@router.post("/workflows/batch")
def batch_workflows(req: BatchActionRequest, db: Session = Depends(get_db)):
    """批量操作工作流：enable_schedule / disable_schedule / delete。
    单个失败不影响其他，返回成功/失败计数与失败 id 列表。
    """
    from scheduler.manager import scheduler_manager

    success = 0
    failed = 0
    failed_ids: list[str] = []

    for wid in req.ids:
        try:
            wf = db.query(Workflow).filter(Workflow.id == wid).first()
            if not wf:
                raise ValueError("工作流不存在")

            if req.action == "enable_schedule":
                steps = json.loads(wf.steps) if wf.steps else []
                has_schedule = any(s.get("tool") == "schedule_trigger" for s in steps)
                if not has_schedule:
                    raise ValueError("工作流不含 schedule_trigger 步骤")
                scheduler_manager.add_job(wid)
                wf.schedule_enabled = True
                db.commit()
            elif req.action == "disable_schedule":
                try:
                    scheduler_manager.remove_job(wid)
                except Exception:
                    pass
                wf.schedule_enabled = False
                db.commit()
            elif req.action == "delete":
                try:
                    scheduler_manager.remove_job(wid)
                except Exception:
                    pass
                db.delete(wf)
                db.commit()
            else:
                raise ValueError(f"未知 action: {req.action}")
            success += 1
        except Exception as e:
            # 单个失败回滚当前事务，不影响后续项
            db.rollback()
            failed += 1
            failed_ids.append(wid)
            logger.warning(f"批量操作失败 (id={wid}, action={req.action}): {e}")

    with _list_cache_lock:
        _list_cache.clear()
    return {"success": success, "failed": failed, "failed_ids": failed_ids}


# ===== 版本管理 =====


@router.get("/workflows/{workflow_id}/versions")
def list_versions(workflow_id: str, db: Session = Depends(get_db)):
    """返回工作流的版本列表（按 version_number 降序）"""
    wf = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not wf:
        raise HTTPException(status_code=404, detail="工作流不存在")
    versions = (
        db.query(WorkflowVersion)
        .filter(WorkflowVersion.workflow_id == workflow_id)
        .order_by(desc(WorkflowVersion.version_number))
        .all()
    )
    return [v.to_dict() for v in versions]


@router.get("/workflows/{workflow_id}/versions/{version_id}")
def get_version(workflow_id: str, version_id: str, db: Session = Depends(get_db)):
    """返回单个版本详情"""
    version = (
        db.query(WorkflowVersion)
        .filter(
            WorkflowVersion.id == version_id,
            WorkflowVersion.workflow_id == workflow_id,
        )
        .first()
    )
    if not version:
        raise HTTPException(status_code=404, detail="版本不存在")
    return version.to_dict()


@router.post("/workflows/{workflow_id}/versions/{version_id}/restore")
def restore_version(workflow_id: str, version_id: str, db: Session = Depends(get_db)):
    """回滚到指定版本：先创建当前状态快照，再恢复为该版本内容，最后同步调度器"""
    wf = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not wf:
        raise HTTPException(status_code=404, detail="工作流不存在")
    version = (
        db.query(WorkflowVersion)
        .filter(
            WorkflowVersion.id == version_id,
            WorkflowVersion.workflow_id == workflow_id,
        )
        .first()
    )
    if not version:
        raise HTTPException(status_code=404, detail="版本不存在")

    # 先创建当前状态的快照（note 标记本次回滚目标版本）
    try:
        latest = (
            db.query(WorkflowVersion)
            .filter(WorkflowVersion.workflow_id == workflow_id)
            .order_by(WorkflowVersion.version_number.desc())
            .first()
        )
        next_version = (latest.version_number + 1) if latest else 1
        rollback_snapshot = WorkflowVersion(
            workflow_id=workflow_id,
            version_number=next_version,
            steps=wf.steps,
            edges=wf.edges,
            summary=wf.summary,
            on_failure=wf.on_failure,
            tags=wf.tags,
            note=f"回滚到版本 {version.version_number}",
        )
        db.add(rollback_snapshot)
    except Exception as e:
        logger.warning(f"回滚前创建快照失败 (workflow={workflow_id}): {e}")

    # 恢复为该版本内容（version.steps 等已是 JSON 字符串，直接赋值）
    wf.steps = version.steps
    wf.edges = version.edges
    wf.summary = version.summary
    wf.on_failure = version.on_failure
    wf.tags = version.tags

    # 同步 webhook_id 和 webhook_secret:若回滚后 webhook_trigger 增删变化则重新生成
    restored_steps = json.loads(version.steps) if version.steps else []
    has_webhook_after = any(s.get("tool") == "webhook_trigger" for s in restored_steps)
    has_webhook_before = wf.webhook_id is not None
    if has_webhook_after != has_webhook_before:
        wf.webhook_id = str(uuid.uuid4()) if has_webhook_after else None
        wf.webhook_secret = _generate_webhook_secret() if has_webhook_after else None

    db.commit()
    db.refresh(wf)

    # 同步调度器：若 schedule_enabled 则重新注册（steps 可能已变）
    if wf.schedule_enabled:
        from scheduler.manager import scheduler_manager
        try:
            scheduler_manager.remove_job(wf.id)
        except Exception:
            pass
        try:
            scheduler_manager.add_job(wf.id)
        except Exception as e:
            logger.warning(f"回滚后重新注册调度失败 (workflow={workflow_id}): {e}")

    with _list_cache_lock:
        _list_cache.clear()
    return wf.to_dict()
