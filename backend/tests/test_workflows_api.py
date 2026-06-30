"""workflows API 集成测试 - CRUD + compare_runs 对比"""
import json
import pytest
from datetime import datetime, timezone, timedelta
from db.models import Workflow, RunRecord


def _wf_payload(name="测试工作流", steps=None):
    """构造创建工作流的请求体"""
    return {
        "name": name,
        "scenario": "测试场景",
        "summary": "测试摘要",
        "steps": steps or [{"id": "s1", "name": "步骤1", "tool": "http_request", "params": {"url": "x", "method": "GET"}}],
        "edges": [],
        "on_failure": "stop",
    }


@pytest.mark.asyncio
async def test_create_workflow(client):
    """创建工作流返回完整数据"""
    resp = await client.post("/api/workflows", json=_wf_payload("新工作流"))
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "新工作流"
    assert data["scenario"] == "测试场景"
    assert "id" in data
    assert len(data["steps"]) == 1


@pytest.mark.asyncio
async def test_get_workflow_not_found(client):
    """不存在的工作流 id 返回 404"""
    resp = await client.get("/api/workflows/nonexistent-id")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_workflows(client):
    """列表返回工作流(含字段)"""
    # 先创建 2 个工作流
    for i in range(2):
        await client.post("/api/workflows", json=_wf_payload(f"工作流{i}"))

    resp = await client.get("/api/workflows")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 2


@pytest.mark.asyncio
async def test_update_workflow(client):
    """更新后字段正确"""
    create_resp = await client.post("/api/workflows", json=_wf_payload("原名"))
    wf_id = create_resp.json()["id"]

    update_resp = await client.put(f"/api/workflows/{wf_id}", json={"name": "新名"})
    assert update_resp.status_code == 200
    assert update_resp.json()["name"] == "新名"

    # 验证持久化
    get_resp = await client.get(f"/api/workflows/{wf_id}")
    assert get_resp.json()["name"] == "新名"


@pytest.mark.asyncio
async def test_delete_workflow(client):
    """删除后查询返回 404"""
    create_resp = await client.post("/api/workflows", json=_wf_payload("待删除"))
    wf_id = create_resp.json()["id"]

    del_resp = await client.delete(f"/api/workflows/{wf_id}")
    assert del_resp.status_code == 200

    get_resp = await client.get(f"/api/workflows/{wf_id}")
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_compare_runs_not_found(client, test_db):
    """run 不存在返回 404"""
    wf = Workflow(id="wf-cmp", name="对比测试", steps="[]", edges="[]")
    test_db.add(wf)
    test_db.commit()

    resp = await client.get("/api/workflows/wf-cmp/runs/run-a/compare/run-b")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_compare_runs_success(client, test_db):
    """返回步骤级 diff"""
    # 工作流含 1 个步骤
    wf = Workflow(
        id="wf-cmp2",
        name="对比测试",
        steps=json.dumps([{"id": "s1", "name": "步骤1", "tool": "http_request"}]),
        edges="[]",
    )
    test_db.add(wf)
    test_db.commit()

    # 两次执行:s1 都成功
    now = datetime.now(timezone.utc)
    for i, rid in enumerate(["run-1", "run-2"]):
        test_db.add(RunRecord(
            id=rid,
            workflow_id="wf-cmp2",
            trigger_type="manual",
            status="success",
            total_time_ms=100 + i * 50,
            started_at=now,
            finished_at=now,
            steps_result=json.dumps({"s1": {"status": "success", "time_ms": 100 + i * 50}}),
        ))
    test_db.commit()

    resp = await client.get("/api/workflows/wf-cmp2/runs/run-1/compare/run-2")
    assert resp.status_code == 200
    data = resp.json()
    assert "run1" in data
    assert "run2" in data
    assert "steps" in data
    assert isinstance(data["steps"], list)
    assert len(data["steps"]) >= 1
    # s1 在两次执行中都存在
    s1_diff = next(s for s in data["steps"] if s["step_id"] == "s1")
    assert s1_diff["name"] == "步骤1"


@pytest.mark.asyncio
async def test_compare_runs_changed_detection(client, test_db):
    """状态变化时 changed=True"""
    wf = Workflow(
        id="wf-chg",
        name="变化检测",
        steps=json.dumps([{"id": "s1", "name": "步骤1", "tool": "http_request"}]),
        edges="[]",
    )
    test_db.add(wf)
    test_db.commit()

    now = datetime.now(timezone.utc)
    # run-1: s1 成功;run-2: s1 失败
    test_db.add(RunRecord(
        id="run-ok",
        workflow_id="wf-chg",
        trigger_type="manual",
        status="success",
        total_time_ms=100,
        started_at=now,
        finished_at=now,
        steps_result=json.dumps({"s1": {"status": "success", "time_ms": 100}}),
    ))
    test_db.add(RunRecord(
        id="run-fail",
        workflow_id="wf-chg",
        trigger_type="manual",
        status="failed",
        total_time_ms=200,
        started_at=now,
        finished_at=now,
        steps_result=json.dumps({"s1": {"status": "failed", "time_ms": 200, "error": "超时"}}),
    ))
    test_db.commit()

    resp = await client.get("/api/workflows/wf-chg/runs/run-ok/compare/run-fail")
    assert resp.status_code == 200
    data = resp.json()
    s1_diff = next(s for s in data["steps"] if s["step_id"] == "s1")
    # 状态从 success → failed,应标记为变化
    assert s1_diff.get("changed") is True
    assert s1_diff["status1"] == "success"
    assert s1_diff["status2"] == "failed"


@pytest.mark.asyncio
async def test_list_runs_order(client, test_db):
    """按 started_at 降序(最新在前)"""
    wf = Workflow(id="wf-order", name="排序测试", steps="[]", edges="[]")
    test_db.add(wf)
    test_db.commit()

    now = datetime.now(timezone.utc)
    # 故意乱序插入,run-new 时间最新
    for rid, hours_ago in [("run-old", 2), ("run-new", 0), ("run-mid", 1)]:
        test_db.add(RunRecord(
            id=rid,
            workflow_id="wf-order",
            trigger_type="manual",
            status="success",
            total_time_ms=100,
            started_at=now - timedelta(hours=hours_ago),
            finished_at=now,
        ))
    test_db.commit()

    resp = await client.get("/api/workflows/wf-order/runs")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3
    # 最新(run-new)应排第一
    assert data[0]["id"] == "run-new"
    assert data[-1]["id"] == "run-old"
