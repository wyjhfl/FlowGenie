"""webhooks API 集成测试 - 签名校验/限流/202 异步执行

覆盖:
- 不存在的 webhook_id → 404
- 无 secret 配置时向后兼容(无签名也通过)→ 202
- 配置 secret 但缺少签名头 → 401
- 签名错误 → 401
- 签名正确 → 202
- 同一 webhook_id 超过限流阈值 → 429
"""
import json
import hmac
import hashlib
import pytest
from unittest.mock import patch
from sqlalchemy.orm import sessionmaker
from db.models import Workflow
from core.rate_limiter import webhook_limiter


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """每个测试前后重置限流器,避免跨用例污染(全局单例)"""
    webhook_limiter.reset()
    yield
    webhook_limiter.reset()


def _make_sig(secret: str, body: bytes) -> str:
    """生成 HMAC-SHA256 签名头,格式 sha256=<hex>"""
    mac = hmac.new(secret.encode(), body, hashlib.sha256)
    return f"sha256={mac.hexdigest()}"


def _wf_with_webhook(name="webhook测试流"):
    """构造含 webhook_trigger 的工作流请求体(创建后自动生成 webhook_id 和 webhook_secret)"""
    return {
        "name": name,
        "scenario": "测试",
        "summary": "",
        "steps": [
            {"id": "s1", "name": "webhook入口", "tool": "webhook_trigger", "params": {}},
            {"id": "s2", "name": "手动步骤", "tool": "manual_trigger", "params": {}},
        ],
        "edges": [],
        "on_failure": "stop",
    }


@pytest.mark.asyncio
async def test_webhook_not_found(client):
    """不存在的 webhook_id 返回 404"""
    resp = await client.post("/api/webhooks/nonexistent", json={"hello": "world"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_webhook_no_secret_passes(client, test_db, test_engine):
    """工作流未配置 webhook_secret 时,无签名也通过(向后兼容)→ 202"""
    # 直接插入有 webhook_id 但无 webhook_secret 的工作流(模拟旧数据)
    wf = Workflow(
        id="wf-nosec",
        name="无密钥",
        steps=json.dumps([{"id": "s1", "name": "手动", "tool": "manual_trigger", "params": {}}]),
        edges="[]",
        webhook_id="wh-nosec-001",
        webhook_secret=None,
    )
    test_db.add(wf)
    test_db.commit()

    # A1 修复:BackgroundTasks 中的 _run_workflow_background 直接用 SessionLocal() 创建独立会话,
    # 绕过 get_db 依赖注入。需要 patch 指向同一内存 DB,否则查询 RunRecord 时缺 paused_context 列报 OperationalError。
    TestSession = sessionmaker(bind=test_engine, autocommit=False, autoflush=False)
    with patch("routers.webhooks.SessionLocal", TestSession):
        resp = await client.post("/api/webhooks/wh-nosec-001", json={"event": "test"})
    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "running"
    assert "run_id" in data
    assert data["workflow_id"] == "wf-nosec"


@pytest.mark.asyncio
async def test_webhook_missing_signature_rejected(client):
    """配置了 webhook_secret 但未提供签名头 → 401"""
    create_resp = await client.post("/api/workflows", json=_wf_with_webhook("签名测试"))
    wf_data = create_resp.json()
    webhook_id = wf_data["webhook_id"]
    assert wf_data["webhook_secret"], "webhook_trigger 工作流应自动生成 secret"

    resp = await client.post(f"/api/webhooks/{webhook_id}", json={"event": "test"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_webhook_wrong_signature_rejected(client):
    """签名错误 → 401"""
    create_resp = await client.post("/api/workflows", json=_wf_with_webhook("错签测试"))
    wf_data = create_resp.json()
    webhook_id = wf_data["webhook_id"]

    resp = await client.post(
        f"/api/webhooks/{webhook_id}",
        json={"event": "test"},
        headers={"X-FlowGenie-Signature": "sha256=deadbeef"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_webhook_valid_signature_passes(client, test_engine):
    """正确签名 → 202,返回 run_id"""
    create_resp = await client.post("/api/workflows", json=_wf_with_webhook("正签测试"))
    wf_data = create_resp.json()
    webhook_id = wf_data["webhook_id"]
    secret = wf_data["webhook_secret"]

    # 签名基于原始 body 字节,用 content= 传原始字节避免 httpx 重新序列化导致不一致
    body = json.dumps({"event": "test"}).encode()
    sig = _make_sig(secret, body)

    # A1 修复:同 test_webhook_no_secret_passes,patch SessionLocal 指向测试内存 DB
    TestSession = sessionmaker(bind=test_engine, autocommit=False, autoflush=False)
    with patch("routers.webhooks.SessionLocal", TestSession):
        resp = await client.post(
            f"/api/webhooks/{webhook_id}",
            content=body,
            headers={"Content-Type": "application/json", "X-FlowGenie-Signature": sig},
        )
    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "running"
    assert "run_id" in data


@pytest.mark.asyncio
async def test_webhook_rate_limit(client):
    """同一 webhook_id 超过 10 次/30s → 429(限流在 workflow 查找之前)"""
    webhook_id = "wh-ratelimit-test"
    # 前 10 次:限流通过,但工作流不存在 → 404
    for i in range(10):
        resp = await client.post(f"/api/webhooks/{webhook_id}", json={"i": i})
        assert resp.status_code == 404, f"第 {i + 1} 次应通过限流返回 404"
    # 第 11 次:被限流 → 429
    resp = await client.post(f"/api/webhooks/{webhook_id}", json={"i": 11})
    assert resp.status_code == 429
