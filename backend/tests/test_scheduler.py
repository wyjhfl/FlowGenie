"""scheduler 集成测试 - cron 解析/任务增删/执行回调/时区/run=None 防护/启停同步

覆盖迭代计划 B3:
- cron 表达式解析(有效/无效/缺失)
- job 增删(add_job/remove_job/get_job/replace_existing)
- _execute_scheduled_workflow 函数(成功/失败/异常/工作流不存在/复用 run_id)
- 时区处理(有效/无效回退)
- run=None 处理(防止 UnboundLocalError)
- schedule_enabled 切换时 scheduler 与 DB 同步
"""
import json
import pytest
from unittest.mock import patch, AsyncMock
from sqlalchemy.orm import sessionmaker

from db.models import Workflow, RunRecord
from scheduler.manager import SchedulerManager, _execute_scheduled_workflow


# ---------- 辅助函数 ----------

def _make_workflow(wf_id="wf-test", name="调度测试", cron="0 9 * * *",
                   timezone_str="Asia/Shanghai", schedule_enabled=True,
                   steps=None, edges="[]"):
    """构造 Workflow 对象(不依赖 DB),默认含 schedule_trigger 步骤"""
    if steps is None:
        steps = [{"id": "s1", "name": "定时触发", "tool": "schedule_trigger",
                  "params": {"cron": cron, "timezone": timezone_str}}]
    return Workflow(
        id=wf_id,
        name=name,
        steps=json.dumps(steps),
        edges=edges,
        schedule_enabled=schedule_enabled,
        on_failure="stop",
    )


# ---------- fixtures ----------

@pytest.fixture
def fresh_manager():
    """独立 SchedulerManager(未 start,仅测试注册/查询,不触发真实 cron)。

    用独立实例避免污染全局 scheduler_manager 单例。
    """
    mgr = SchedulerManager()
    yield mgr
    try:
        mgr.scheduler.remove_all_jobs()
    except Exception:
        pass


@pytest.fixture
def patched_session_local(test_engine):
    """将 scheduler.manager.SessionLocal 替换为绑定到测试内存 DB 的 sessionmaker。

    使 _execute_scheduled_workflow / add_job / _load_all_jobs 读写到测试 DB。
    注意:StaticPool 共享单连接,调用方需先 commit test_db 释放连接。
    """
    TestSession = sessionmaker(bind=test_engine, autocommit=False, autoflush=False)
    with patch("scheduler.manager.SessionLocal", TestSession):
        yield TestSession


# ---------- cron 表达式解析 ----------

@pytest.mark.asyncio
async def test_add_job_valid_cron(fresh_manager):
    """有效 cron 表达式(5 字段)正确注册任务"""
    cases = [
        ("0 9 * * *", "wf-daily"),        # 每天 9 点
        ("*/5 * * * *", "wf-every5"),     # 每 5 分钟
        ("0 0 1 * *", "wf-monthly"),      # 每月 1 号
        ("30 8 * * 1-5", "wf-weekday"),   # 工作日 8:30
    ]
    for cron_expr, wf_id in cases:
        wf = _make_workflow(wf_id=wf_id, cron=cron_expr)
        fresh_manager._add_job_from_workflow(wf)
        job = fresh_manager.get_job(wf_id)
        assert job is not None, f"cron='{cron_expr}' 应注册成功"
        assert job.id == f"workflow_{wf_id}"


@pytest.mark.asyncio
async def test_add_job_invalid_cron(fresh_manager):
    """无效 cron 表达式(字段数不对)不注册任务,异常被捕获"""
    cases = [
        ("0 9 * *", "wf-4field"),       # 4 字段
        ("0 9 * * * 0", "wf-6field"),   # 6 字段
        ("not-a-cron", "wf-words"),     # 1 字段(非 cron)
    ]
    for cron_expr, wf_id in cases:
        wf = _make_workflow(wf_id=wf_id, cron=cron_expr)
        fresh_manager._add_job_from_workflow(wf)  # 不应抛异常
        assert fresh_manager.get_job(wf_id) is None, f"cron='{cron_expr}' 不应注册"


@pytest.mark.asyncio
async def test_add_job_no_cron(fresh_manager):
    """无 schedule_trigger 步骤或无 cron 参数时跳过注册"""
    # 无 schedule_trigger 步骤
    wf_no_trigger = _make_workflow(
        wf_id="wf-notrigger",
        steps=[{"id": "s1", "tool": "manual_trigger", "params": {}}],
    )
    fresh_manager._add_job_from_workflow(wf_no_trigger)
    assert fresh_manager.get_job("wf-notrigger") is None

    # schedule_trigger 但无 cron 参数
    wf_no_cron = _make_workflow(
        wf_id="wf-nocron",
        steps=[{"id": "s1", "tool": "schedule_trigger", "params": {"timezone": "Asia/Shanghai"}}],
    )
    fresh_manager._add_job_from_workflow(wf_no_cron)
    assert fresh_manager.get_job("wf-nocron") is None


# ---------- job 增删查 ----------

@pytest.mark.asyncio
async def test_add_remove_get_job(fresh_manager, test_db, patched_session_local):
    """add_job 从 DB 读取工作流并注册;remove_job 移除;get_job 查询"""
    wf = _make_workflow(wf_id="wf-addrm", cron="0 9 * * *")
    test_db.add(wf)
    test_db.commit()  # 释放连接供 scheduler session 使用

    # add_job 通过 workflow_id 从 DB 查询并注册
    fresh_manager.add_job("wf-addrm")
    assert fresh_manager.get_job("wf-addrm") is not None

    # remove_job 移除
    fresh_manager.remove_job("wf-addrm")
    assert fresh_manager.get_job("wf-addrm") is None


@pytest.mark.asyncio
async def test_get_remove_nonexistent_job(fresh_manager):
    """不存在的工作流:get_job 返回 None;remove_job 不抛异常"""
    assert fresh_manager.get_job("nonexistent-id") is None
    # 移除不存在的任务应静默忽略(不抛异常)
    fresh_manager.remove_job("nonexistent-id")


@pytest.mark.asyncio
async def test_add_job_replace_existing(fresh_manager):
    """重复注册同一工作流时替换旧任务(replace_existing=True)"""
    wf = _make_workflow(wf_id="wf-replace", cron="0 9 * * *")
    fresh_manager._add_job_from_workflow(wf)
    assert fresh_manager.get_job("wf-replace") is not None

    # 修改 cron 后重新注册,不应抛异常且 job 仍存在
    wf2 = _make_workflow(wf_id="wf-replace", cron="0 10 * * *")
    fresh_manager._add_job_from_workflow(wf2)
    job = fresh_manager.get_job("wf-replace")
    assert job is not None


# ---------- _execute_scheduled_workflow ----------

@pytest.mark.asyncio
async def test_execute_success(test_db, patched_session_local):
    """成功执行:创建 RunRecord(status=success),返回 run_id,不触发通知"""
    wf = _make_workflow(wf_id="wf-exec-ok", cron="0 9 * * *")
    test_db.add(wf)
    test_db.commit()  # 释放连接供 scheduler session 使用

    mock_result = {
        "status": "success",
        "steps_result": {"s1": {"status": "success", "output": "done"}},
        "total_time_ms": 100,
        "logs": [{"level": "INFO", "msg": "done"}],
    }
    with patch("scheduler.manager.executor") as mock_executor, \
         patch("core.run_record_service.maybe_notify_failure", new_callable=AsyncMock) as mock_notify, \
         patch("scheduler.manager.load_preferences_from_db", return_value={}):
        mock_executor.execute = AsyncMock(return_value=mock_result)
        run_id = await _execute_scheduled_workflow("wf-exec-ok")

    assert run_id is not None
    test_db.expire_all()
    run = test_db.query(RunRecord).filter(RunRecord.id == run_id).first()
    assert run is not None
    assert run.status == "success"
    assert run.trigger_type == "schedule"
    assert run.total_time_ms == 100
    assert run.finished_at is not None
    # success 时 notify_failure_if_needed 直接 return,不调用 maybe_notify_failure
    mock_notify.assert_not_called()


@pytest.mark.asyncio
async def test_execute_failure(test_db, patched_session_local):
    """执行失败(status=failed):RunRecord 标记 failed,error 脱敏,触发通知"""
    wf = _make_workflow(wf_id="wf-exec-fail", cron="0 9 * * *")
    test_db.add(wf)
    test_db.commit()

    mock_result = {
        "status": "failed",
        "steps_result": {"s1": {"status": "failed", "error": "认证失败: Bearer secret_token_123"}},
        "total_time_ms": 50,
        "logs": [],
    }
    with patch("scheduler.manager.executor") as mock_executor, \
         patch("core.run_record_service.maybe_notify_failure", new_callable=AsyncMock) as mock_notify, \
         patch("scheduler.manager.load_preferences_from_db", return_value={}):
        mock_executor.execute = AsyncMock(return_value=mock_result)
        run_id = await _execute_scheduled_workflow("wf-exec-fail")

    assert run_id is not None
    test_db.expire_all()
    run = test_db.query(RunRecord).filter(RunRecord.id == run_id).first()
    assert run is not None
    assert run.status == "failed"
    assert run.error is not None
    # Bearer token 应被脱敏
    assert "secret_token_123" not in run.error
    mock_notify.assert_called_once()  # 失败触发通知


@pytest.mark.asyncio
async def test_execute_exception(test_db, patched_session_local):
    """executor 抛异常:RunRecord 标记 failed,返回 None,error 脱敏"""
    wf = _make_workflow(wf_id="wf-exec-exc", cron="0 9 * * *")
    test_db.add(wf)
    test_db.commit()

    with patch("scheduler.manager.executor") as mock_executor, \
         patch("core.run_record_service.maybe_notify_failure", new_callable=AsyncMock), \
         patch("scheduler.manager.load_preferences_from_db", return_value={}):
        mock_executor.execute = AsyncMock(side_effect=RuntimeError("连接超时 10.0.0.1"))
        run_id = await _execute_scheduled_workflow("wf-exec-exc")

    assert run_id is None  # 异常路径返回 None
    test_db.expire_all()
    runs = test_db.query(RunRecord).filter(RunRecord.workflow_id == "wf-exec-exc").all()
    assert len(runs) == 1
    assert runs[0].status == "failed"
    assert runs[0].error is not None
    # 内网 IP 应被脱敏
    assert "10.0.0.1" not in runs[0].error


@pytest.mark.asyncio
async def test_execute_workflow_not_found(patched_session_local):
    """工作流不存在时返回 None,不创建 RunRecord,不调用 executor"""
    with patch("scheduler.manager.executor") as mock_executor, \
         patch("scheduler.manager.load_preferences_from_db", return_value={}):
        result = await _execute_scheduled_workflow("nonexistent-wf")
    assert result is None
    mock_executor.execute.assert_not_called()


@pytest.mark.asyncio
async def test_execute_run_none_no_unbound_error(test_db, patched_session_local):
    """steps 为非法 JSON 时异常路径中 run=None,不触发 UnboundLocalError"""
    wf = Workflow(
        id="wf-badjson",
        name="坏JSON",
        steps="{invalid json",  # 非法 JSON,触发 json.loads 异常(run 创建前)
        edges="[]",
        schedule_enabled=True,
        on_failure="stop",
    )
    test_db.add(wf)
    test_db.commit()

    with patch("scheduler.manager.executor") as mock_executor, \
         patch("core.run_record_service.maybe_notify_failure", new_callable=AsyncMock), \
         patch("scheduler.manager.load_preferences_from_db", return_value={}):
        # 不应抛 UnboundLocalError,异常被捕获后返回 None
        result = await _execute_scheduled_workflow("wf-badjson")

    assert result is None
    mock_executor.execute.assert_not_called()  # 异常在 executor 调用前发生
    test_db.expire_all()
    runs = test_db.query(RunRecord).filter(RunRecord.workflow_id == "wf-badjson").all()
    assert len(runs) == 0  # run 未创建,不写 RunRecord


@pytest.mark.asyncio
async def test_execute_with_existing_run_id(test_db, patched_session_local):
    """提供 run_id 时复用已有 RunRecord,不创建新记录"""
    wf = _make_workflow(wf_id="wf-runid", cron="0 9 * * *")
    test_db.add(wf)
    # 预创建 RunRecord(running 状态)
    pre_run = RunRecord(
        id="pre-existing-run",
        workflow_id="wf-runid",
        trigger_type="schedule",
        status="running",
    )
    test_db.add(pre_run)
    test_db.commit()

    mock_result = {
        "status": "success",
        "steps_result": {},
        "total_time_ms": 10,
        "logs": [],
    }
    with patch("scheduler.manager.executor") as mock_executor, \
         patch("core.run_record_service.maybe_notify_failure", new_callable=AsyncMock), \
         patch("scheduler.manager.load_preferences_from_db", return_value={}):
        mock_executor.execute = AsyncMock(return_value=mock_result)
        returned_id = await _execute_scheduled_workflow("wf-runid", run_id="pre-existing-run")

    assert returned_id == "pre-existing-run"
    test_db.expire_all()
    runs = test_db.query(RunRecord).filter(RunRecord.workflow_id == "wf-runid").all()
    assert len(runs) == 1  # 不创建新记录
    assert runs[0].id == "pre-existing-run"
    assert runs[0].status == "success"  # 复用记录被更新


# ---------- 时区处理 ----------

@pytest.mark.asyncio
async def test_timezone_handling(fresh_manager):
    """时区处理:有效时区注册成功;无效时区回退 Asia/Shanghai 仍注册成功"""
    # 有效时区
    wf_valid = _make_workflow(wf_id="wf-tz-valid", cron="0 9 * * *", timezone_str="America/New_York")
    fresh_manager._add_job_from_workflow(wf_valid)
    job = fresh_manager.get_job("wf-tz-valid")
    assert job is not None
    assert job.trigger.timezone is not None

    # 无效时区 → 回退默认,仍注册成功(不抛异常)
    wf_invalid = _make_workflow(wf_id="wf-tz-invalid", cron="0 9 * * *", timezone_str="Invalid/Zone")
    fresh_manager._add_job_from_workflow(wf_invalid)
    job2 = fresh_manager.get_job("wf-tz-invalid")
    assert job2 is not None  # 回退后注册成功


# ---------- schedule_enabled 切换与 DB 同步 ----------

@pytest.mark.asyncio
async def test_load_all_jobs_respects_schedule_enabled(fresh_manager, test_db, patched_session_local):
    """_load_all_jobs 仅加载 schedule_enabled=True 的工作流"""
    wf_on = _make_workflow(wf_id="wf-load-on", cron="0 9 * * *", schedule_enabled=True)
    wf_off = _make_workflow(wf_id="wf-load-off", cron="0 10 * * *", schedule_enabled=False)
    test_db.add_all([wf_on, wf_off])
    test_db.commit()  # 释放连接供 scheduler session 使用

    fresh_manager._load_all_jobs()
    assert fresh_manager.get_job("wf-load-on") is not None   # enabled → 注册
    assert fresh_manager.get_job("wf-load-off") is None      # disabled → 跳过


@pytest.mark.asyncio
async def test_schedule_enable_disable_api_sync(client, test_db):
    """API 启用/禁用调度时调用 scheduler_manager 并同步 DB schedule_enabled"""
    # 创建含 schedule_trigger 的工作流
    create_resp = await client.post("/api/workflows", json={
        "name": "API调度同步",
        "scenario": "测试",
        "summary": "",
        "steps": [{"id": "s1", "name": "定时", "tool": "schedule_trigger",
                    "params": {"cron": "0 9 * * *", "timezone": "Asia/Shanghai"}}],
        "edges": [],
        "on_failure": "stop",
    })
    assert create_resp.status_code == 200
    wf_id = create_resp.json()["id"]

    with patch("scheduler.manager.scheduler_manager") as mock_sm:
        # 启用 → add_job 被调用 + DB schedule_enabled=True
        resp = await client.post(f"/api/workflows/{wf_id}/schedule/enable")
        assert resp.status_code == 200
        assert resp.json()["schedule_enabled"] is True
        mock_sm.add_job.assert_called_once_with(wf_id)

        # 禁用 → remove_job 被调用 + DB schedule_enabled=False
        resp = await client.post(f"/api/workflows/{wf_id}/schedule/disable")
        assert resp.status_code == 200
        assert resp.json()["schedule_enabled"] is False
        mock_sm.remove_job.assert_called_once_with(wf_id)

    # 验证 DB 最终状态
    test_db.expire_all()
    wf = test_db.query(Workflow).filter(Workflow.id == wf_id).first()
    assert wf.schedule_enabled is False
