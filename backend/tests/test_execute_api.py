"""execute API 集成测试 - 工作流执行/SSE 流式/retry 重试/调试会话/export 导出

覆盖迭代计划 B4 关键路径:
- 普通执行(非流式):成功/失败/参数校验/工作流不存在
- SSE 流式执行:content-type=text/event-stream、start/done 事件序列
- retry from_failed 模式:从失败步骤恢复上下文重新执行
- retry from_start 模式:从头重新执行
- step_next / continue / abort 调试端点(含会话不存在 404)
- debug_session 生命周期(会话存在/不存在)
- export 导出 json 格式

执行器(executor.execute / execute_with_context)统一 mock,避免真实 LLM/HTTP 调用。
偏好加载(_load_preferences)统一 mock,避免 SessionLocal 触碰生产文件 DB。
"""
import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from db.models import RunRecord, Workflow
from routers.execute import _debug_sessions


# ========== 全局 fixture ==========

@pytest.fixture(autouse=True)
def _clear_debug_sessions():
    """每个测试前后清空调试会话表(模块级全局 dict,避免跨用例污染)"""
    _debug_sessions.clear()
    yield
    _debug_sessions.clear()


@pytest.fixture(autouse=True)
def _mock_preferences():
    """统一 mock 偏好加载,_load_preferences 内部用 SessionLocal 直连生产文件 DB,
    测试环境应返回空 dict,避免非确定性行为。"""
    with patch("routers.execute._load_preferences", return_value={}):
        yield


# ========== 辅助构造函数 ==========

def _wf_row(test_db, wf_id="wf-1", name="执行测试流", steps=None, edges=None, on_failure="stop"):
    """直接插入 Workflow 行(避免走创建 API 的额外副作用)"""
    wf = Workflow(
        id=wf_id,
        name=name,
        steps=json.dumps(steps or [
            {"id": "s1", "name": "步骤1", "tool": "http_request", "params": {"url": "x", "method": "GET"}}
        ]),
        edges=json.dumps(edges or []),
        on_failure=on_failure,
    )
    test_db.add(wf)
    test_db.commit()
    return wf


def _failed_run_row(test_db, run_id="run-fail-1", workflow_id="wf-1",
                    steps_result=None, trigger_data=None):
    """插入一个失败的 RunRecord(用于 retry 测试)"""
    run = RunRecord(
        id=run_id,
        workflow_id=workflow_id,
        trigger_type="manual",
        status="failed",
        total_time_ms=200,
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
        steps_result=json.dumps(steps_result or {
            "s1": {"status": "success", "output": "ok", "time_ms": 50},
            "s2": {"status": "failed", "error": "连接超时", "time_ms": 150},
        }),
        trigger_data=json.dumps(trigger_data) if trigger_data is not None else None,
        error="连接超时",
    )
    test_db.add(run)
    test_db.commit()
    return run


def _success_result(step_ids=("s1",)):
    """构造 executor.execute 的成功返回值"""
    return {
        "status": "success",
        "steps_result": {sid: {"status": "success", "output": "ok", "time_ms": 10} for sid in step_ids},
        "total_time_ms": 100,
        "on_failure": "stop",
        "logs": [{"level": "INFO", "msg": "done"}],
        "warnings": [],
    }


# ========== 普通执行(非流式)==========

@pytest.mark.asyncio
async def test_run_workflow_success(client, test_db):
    """正常执行:mock executor 返回 success,RunRecord 被创建并标记成功"""
    _wf_row(test_db, "wf-run-ok")
    with patch("routers.execute.executor.execute", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = _success_result(("s1",))
        resp = await client.post("/api/workflows/run", json={
            "steps": [{"id": "s1", "name": "步骤1", "tool": "http_request",
                       "params": {"url": "x", "method": "GET"}}],
            "edges": [],
            "workflow_id": "wf-run-ok",
            "on_failure": "stop",
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["total_time_ms"] == 100
    assert data["steps_result"]["s1"]["status"] == "success"
    # RunRecord 已持久化为 success
    run = test_db.query(RunRecord).filter(RunRecord.workflow_id == "wf-run-ok").first()
    assert run is not None
    assert run.status == "success"
    mock_exec.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_workflow_empty_steps_rejected(client):
    """空 steps 列表 → 400(在执行前校验)"""
    resp = await client.post("/api/workflows/run", json={"steps": [], "edges": []})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_run_workflow_unknown_workflow_id(client):
    """workflow_id 指向不存在的工作流 → 404"""
    resp = await client.post("/api/workflows/run", json={
        "steps": [{"id": "s1", "name": "步骤1", "tool": "http_request", "params": {}}],
        "workflow_id": "no-such-wf",
    })
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_run_workflow_failure_records_error(client, test_db):
    """executor 返回 failed → RunRecord.status=failed 且 error 被写入"""
    _wf_row(test_db, "wf-run-fail")
    failed_result = {
        "status": "failed",
        "steps_result": {"s1": {"status": "failed", "error": "连接超时", "time_ms": 50}},
        "total_time_ms": 50,
        "on_failure": "stop",
        "logs": [],
        "warnings": [],
    }
    with patch("routers.execute.executor.execute", new_callable=AsyncMock, return_value=failed_result):
        resp = await client.post("/api/workflows/run", json={
            "steps": [{"id": "s1", "name": "步骤1", "tool": "http_request", "params": {}}],
            "workflow_id": "wf-run-fail",
        })
    assert resp.status_code == 200
    assert resp.json()["status"] == "failed"
    run = test_db.query(RunRecord).filter(RunRecord.workflow_id == "wf-run-fail").first()
    assert run is not None
    assert run.status == "failed"
    assert run.error  # 非空错误信息


# ========== SSE 流式执行 ==========

@pytest.mark.asyncio
async def test_run_stream_content_type_and_events(client, test_db):
    """流式端点:content-type=text/event-stream,响应含 start/done 事件"""
    _wf_row(test_db, "wf-stream")
    with patch("routers.execute.executor.execute", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = _success_result(("s1",))
        resp = await client.post("/api/workflows/run/stream", json={
            "steps": [{"id": "s1", "name": "步骤1", "tool": "http_request", "params": {}}],
            "edges": [],
            "workflow_id": "wf-stream",
        })
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    body = resp.text
    assert "event: start" in body
    assert "event: done" in body
    # done 事件载荷中含 success 状态
    assert "success" in body
    # RunRecord 被流式 done 事件更新为 success
    run = test_db.query(RunRecord).filter(RunRecord.workflow_id == "wf-stream").first()
    assert run is not None
    assert run.status == "success"


@pytest.mark.asyncio
async def test_run_stream_empty_steps_rejected(client):
    """流式端点空 steps → 400(在 StreamingResponse 创建之前校验)"""
    resp = await client.post("/api/workflows/run/stream", json={"steps": []})
    assert resp.status_code == 400


# ========== retry 重试 ==========

@pytest.mark.asyncio
async def test_retry_from_failed_success(client, test_db):
    """from_failed 模式:有失败步骤 → mock execute_with_context 成功 → 新 RunRecord success"""
    _wf_row(test_db, "wf-retry", steps=[
        {"id": "s1", "name": "步骤1", "tool": "http_request", "params": {}},
        {"id": "s2", "name": "步骤2", "tool": "llm_summary", "params": {}},
    ])
    _failed_run_row(test_db, "run-failed", "wf-retry")
    with patch("routers.execute.executor.execute_with_context", new_callable=AsyncMock) as mock_ctx:
        mock_ctx.return_value = _success_result(("s1", "s2"))
        resp = await client.post(
            "/api/workflows/wf-retry/runs/run-failed/retry?mode=from_failed"
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["id"] != "run-failed"  # 新 RunRecord
    # execute_with_context 收到 start_from 与 prev_context 参数
    _, kwargs = mock_ctx.call_args
    assert kwargs["start_from"] == "s2"
    assert kwargs["prev_context"]["s2"]["status"] == "failed"


@pytest.mark.asyncio
async def test_retry_from_failed_no_failed_steps(client, test_db):
    """from_failed 模式:原 run 无失败步骤 → 400"""
    _wf_row(test_db, "wf-retry-ok", steps=[
        {"id": "s1", "name": "步骤1", "tool": "http_request", "params": {}}
    ])
    test_db.add(RunRecord(
        id="run-all-ok",
        workflow_id="wf-retry-ok",
        trigger_type="manual",
        status="success",
        total_time_ms=10,
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
        steps_result=json.dumps({"s1": {"status": "success", "output": "ok", "time_ms": 10}}),
    ))
    test_db.commit()
    resp = await client.post(
        "/api/workflows/wf-retry-ok/runs/run-all-ok/retry?mode=from_failed"
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_retry_from_start_success(client, test_db):
    """from_start 模式:从头重跑 → mock executor.execute 成功 → 新 RunRecord success"""
    _wf_row(test_db, "wf-restart", steps=[
        {"id": "s1", "name": "步骤1", "tool": "http_request", "params": {}}
    ])
    _failed_run_row(test_db, "run-restart-fail", "wf-restart",
                    steps_result={"s1": {"status": "failed", "error": "boom", "time_ms": 10}})
    with patch("routers.execute.executor.execute", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = _success_result(("s1",))
        resp = await client.post(
            "/api/workflows/wf-restart/runs/run-restart-fail/retry?mode=from_start"
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"
    # from_start 调用普通 execute(非 execute_with_context)
    mock_exec.assert_awaited_once()


@pytest.mark.asyncio
async def test_retry_run_not_found(client, test_db):
    """retry 不存在的 run_id → 404"""
    _wf_row(test_db, "wf-retry-404")
    resp = await client.post("/api/workflows/wf-retry-404/runs/no-such-run/retry")
    assert resp.status_code == 404


# ========== 调试端点(step_next / continue / abort)==========

@pytest.mark.asyncio
async def test_step_next_no_session_returns_404(client):
    """无调试会话时调用 step/next → 404(会话已结束或不存在)"""
    resp = await client.post("/api/workflows/wf-x/runs/run-x/step/next")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_step_next_releases_step_event(client):
    """有调试会话时 step/next → 200 且 step_event 被 set(释放等待的 executor)"""
    step_event = asyncio.Event()
    fake_exec = MagicMock()
    _debug_sessions["run-step"] = {
        "executor": fake_exec,
        "step_event": step_event,
        "workflow_id": "wf-step",
    }
    resp = await client.post("/api/workflows/wf-step/runs/run-step/step/next")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert step_event.is_set()


@pytest.mark.asyncio
async def test_step_continue_disables_debug_mode(client):
    """step/continue → 关闭 debug_mode 并释放等待(全速执行剩余步骤)"""
    step_event = asyncio.Event()
    fake_exec = MagicMock()
    _debug_sessions["run-cont"] = {
        "executor": fake_exec,
        "step_event": step_event,
        "workflow_id": "wf-cont",
    }
    resp = await client.post("/api/workflows/wf-cont/runs/run-cont/step/continue")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    fake_exec.set_debug_mode.assert_called_once_with(False)
    assert step_event.is_set()


@pytest.mark.asyncio
async def test_step_abort_calls_executor_abort(client):
    """step/abort → 调用 executor.abort()(置位 _aborted 并释放等待)"""
    step_event = asyncio.Event()
    fake_exec = MagicMock()
    _debug_sessions["run-abort"] = {
        "executor": fake_exec,
        "step_event": step_event,
        "workflow_id": "wf-abort",
    }
    resp = await client.post("/api/workflows/wf-abort/runs/run-abort/step/abort")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    fake_exec.abort.assert_called_once()


# ========== export 导出 ==========

@pytest.mark.asyncio
async def test_export_run_json(client, test_db):
    """导出 json 格式:content-type=application/json,含 Content-Disposition 附件头"""
    _wf_row(test_db, "wf-export")
    test_db.add(RunRecord(
        id="run-export",
        workflow_id="wf-export",
        trigger_type="manual",
        status="success",
        total_time_ms=42,
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
        steps_result=json.dumps({"s1": {"status": "success", "output": "ok", "time_ms": 42}}),
    ))
    test_db.commit()
    resp = await client.get("/api/workflows/runs/run-export/export?format=json")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")
    assert "attachment" in resp.headers["content-disposition"]
    data = resp.json()
    assert data["id"] == "run-export"
    assert data["status"] == "success"
    assert data["total_time_ms"] == 42


@pytest.mark.asyncio
async def test_export_run_not_found(client):
    """导出不存在的 run_id → 404"""
    resp = await client.get("/api/workflows/runs/no-such-run/export?format=json")
    assert resp.status_code == 404
