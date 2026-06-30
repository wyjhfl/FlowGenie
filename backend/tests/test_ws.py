"""A4: WebSocket 实时推送基础设施测试

覆盖 ConnectionManager 与通知函数:
- connect/disconnect/broadcast 基础流程(不依赖真实网络)
- 配置 FLOWGENIE_API_KEY 时鉴权失败返回 False 并调用 websocket.close
- broadcast 自动清理 send_text 失败的死连接
- notify_workflow_paused/notify_workflow_resumed 调用 ws_manager.broadcast 推送正确事件
"""
import json
import pytest
from unittest.mock import AsyncMock, patch

from routers.ws import (
    ConnectionManager,
    ws_manager,
    notify_workflow_paused,
    notify_workflow_resumed,
)


# ---------- mock WebSocket 工具 ----------

def _make_mock_ws():
    """构造 mock WebSocket,实现 accept/close/send_text 三个 awaitable 方法。"""
    ws = AsyncMock()
    ws.accept = AsyncMock()
    ws.close = AsyncMock()
    ws.send_text = AsyncMock()
    return ws


# ---------- connect / disconnect / broadcast 基础流程 ----------

@pytest.mark.asyncio
async def test_connection_manager_connect_disconnect():
    """connect 接受连接并加入 _connections;disconnect 移除连接"""
    mgr = ConnectionManager()
    ws = _make_mock_ws()

    # connect 鉴权通过(无 FLOWGENIE_API_KEY)→ 返回 True, 调用 accept, 加入连接列表
    ok = await mgr.connect(ws)
    assert ok is True
    ws.accept.assert_awaited_once()
    assert ws in mgr._connections
    assert len(mgr._connections) == 1

    # disconnect 移除连接
    mgr.disconnect(ws)
    assert ws not in mgr._connections
    assert len(mgr._connections) == 0


@pytest.mark.asyncio
async def test_connection_manager_broadcast_sends_to_all():
    """broadcast 向所有活跃连接发送 JSON 消息,事件类型与 payload 正确合并"""
    mgr = ConnectionManager()
    ws1 = _make_mock_ws()
    ws2 = _make_mock_ws()
    await mgr.connect(ws1)
    await mgr.connect(ws2)

    await mgr.broadcast("test:event", {"foo": "bar"})

    # 两个连接均收到消息
    assert ws1.send_text.await_count == 1
    assert ws2.send_text.await_count == 1
    # 消息体含 type 与 payload 字段
    msg = json.loads(ws1.send_text.await_args.args[0])
    assert msg["type"] == "test:event"
    assert msg["foo"] == "bar"


@pytest.mark.asyncio
async def test_connection_manager_broadcast_empty_noop():
    """无活跃连接时 broadcast 直接返回(不抛异常)"""
    mgr = ConnectionManager()
    # 不应抛异常
    await mgr.broadcast("any", {"x": 1})


# ---------- 鉴权路径 ----------

@pytest.mark.asyncio
async def test_connection_manager_auth_no_key(monkeypatch):
    """配置 FLOWGENIE_API_KEY 时,connect 传入错误 api_key 返回 False 并调用 websocket.close"""
    monkeypatch.setenv("FLOWGENIE_API_KEY", "secret-123")
    mgr = ConnectionManager()
    ws = _make_mock_ws()

    # 错误 key → 返回 False, close 被调用(code=4401), 不加入连接列表
    ok = await mgr.connect(ws, api_key="wrong-key")
    assert ok is False
    ws.close.assert_awaited_once()
    call_kwargs = ws.close.await_args.kwargs
    assert call_kwargs.get("code") == 4401
    assert ws not in mgr._connections

    # 缺省 api_key(None)同样失败
    ws2 = _make_mock_ws()
    ok2 = await mgr.connect(ws2, api_key=None)
    assert ok2 is False
    ws2.close.assert_awaited_once()
    assert ws2 not in mgr._connections


@pytest.mark.asyncio
async def test_connection_manager_auth_correct_key(monkeypatch):
    """配置 FLOWGENIE_API_KEY 时,connect 传入正确 api_key 返回 True"""
    monkeypatch.setenv("FLOWGENIE_API_KEY", "secret-123")
    mgr = ConnectionManager()
    ws = _make_mock_ws()

    ok = await mgr.connect(ws, api_key="secret-123")
    assert ok is True
    ws.accept.assert_awaited_once()
    assert ws in mgr._connections


# ---------- broadcast 清理死连接 ----------

@pytest.mark.asyncio
async def test_connection_manager_broadcast_cleans_dead():
    """broadcast 时 send_text 抛异常的连接被自动移除,健康连接保留"""
    mgr = ConnectionManager()

    # 死连接:send_text 抛 RuntimeError
    dead_ws = _make_mock_ws()
    dead_ws.send_text = AsyncMock(side_effect=RuntimeError("连接已断开"))
    # 健康连接
    healthy_ws = _make_mock_ws()

    await mgr.connect(dead_ws)
    await mgr.connect(healthy_ws)
    assert len(mgr._connections) == 2

    await mgr.broadcast("ev", {"k": "v"})

    # 死连接被移除,健康连接保留
    assert dead_ws not in mgr._connections
    assert healthy_ws in mgr._connections
    assert len(mgr._connections) == 1
    # 健康连接仍收到消息
    healthy_ws.send_text.assert_awaited_once()


# ---------- 通知函数调用 broadcast ----------

@pytest.mark.asyncio
async def test_notify_workflow_paused_calls_broadcast():
    """notify_workflow_paused 调用 ws_manager.broadcast,事件类型为 workflow:paused"""
    with patch.object(ws_manager, "broadcast", new=AsyncMock()) as mock_broadcast:
        await notify_workflow_paused(
            run_id="run-1",
            workflow_id="wf-1",
            message="请审批",
            approvers=["alice@example.com"],
            paused_step_id="step_approve",
        )

    mock_broadcast.assert_awaited_once()
    args, _ = mock_broadcast.await_args
    event_type = args[0]
    payload = args[1]
    assert event_type == "workflow:paused"
    assert payload["run_id"] == "run-1"
    assert payload["workflow_id"] == "wf-1"
    assert payload["message"] == "请审批"
    assert payload["paused_step_id"] == "step_approve"
    assert payload["approvers"] == ["alice@example.com"]


@pytest.mark.asyncio
async def test_notify_workflow_resumed_calls_broadcast():
    """notify_workflow_resumed 调用 ws_manager.broadcast,事件类型为 workflow:resumed"""
    with patch.object(ws_manager, "broadcast", new=AsyncMock()) as mock_broadcast:
        await notify_workflow_resumed(
            run_id="run-1",
            workflow_id="wf-1",
            decision="approved",
        )

    mock_broadcast.assert_awaited_once()
    args, _ = mock_broadcast.await_args
    event_type = args[0]
    payload = args[1]
    assert event_type == "workflow:resumed"
    assert payload["run_id"] == "run-1"
    assert payload["workflow_id"] == "wf-1"
    assert payload["decision"] == "approved"
