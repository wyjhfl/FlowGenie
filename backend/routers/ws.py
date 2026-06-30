"""A4: WebSocket 实时推送——审批节点暂停/恢复通知

SSE 仍保留用于执行流 token 推送;WebSocket 仅用于审批请求实时通知(避免前端轮询)。
前端建立单一 WS 连接,订阅 workflow:paused / workflow:resumed 事件。
"""
import json
import logging
import os
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)
router = APIRouter()


class ConnectionManager:
    """管理活跃 WebSocket 连接,支持广播事件。

    单例模式,全局共享。连接时鉴权(X-API-Key query 参数),断开时自动清理。
    """

    def __init__(self):
        self._connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket, api_key: str | None = None) -> bool:
        """接受连接并鉴权。鉴权失败返回 False(由调用方关闭连接)。

        :param api_key: 客户端通过 ?api_key=xxx 传入
        :return: True=鉴权通过已接受;False=鉴权失败
        """
        # 鉴权:配置了 FLOWGENIE_API_KEY 时校验 api_key(与 APIKeyMiddleware 一致)
        configured_key = os.getenv("FLOWGENIE_API_KEY", "")
        if configured_key:
            if not api_key or api_key != configured_key:
                logger.warning(f"WebSocket 连接鉴权失败(api_key={'有' if api_key else '无'})")
                await websocket.close(code=4401, reason="Unauthorized")
                return False
        await websocket.accept()
        self._connections.append(websocket)
        logger.info(f"WebSocket 连接已建立,当前活跃连接数: {len(self._connections)}")
        return True

    def disconnect(self, websocket: WebSocket):
        """移除断开的连接"""
        if websocket in self._connections:
            self._connections.remove(websocket)
        logger.debug(f"WebSocket 连接断开,当前活跃连接数: {len(self._connections)}")

    async def broadcast(self, event_type: str, payload: dict[str, Any]) -> None:
        """向所有活跃连接广播事件。

        事件格式: {"type": event_type, ...payload}
        发送失败的连接自动移除(视为已断开)。
        """
        if not self._connections:
            return
        message = json.dumps({"type": event_type, **payload}, ensure_ascii=False, default=str)
        dead: list[WebSocket] = []
        for ws in self._connections:
            try:
                await ws.send_text(message)
            except Exception as e:
                logger.debug(f"WebSocket 发送失败,标记为断开: {e}")
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


# 全局单例(供 execute.py 在审批暂停/恢复时调用 broadcast)
ws_manager = ConnectionManager()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, api_key: str | None = None):
    """WebSocket 端点 /ws

    鉴权:通过 query 参数 ?api_key=xxx 传入 API Key。
    若 API_KEY_ENABLED=False(默认),则无需鉴权,任何连接均可建立。
    """
    ok = await ws_manager.connect(websocket, api_key)
    if not ok:
        return
    try:
        # 保持连接,等待客户端消息(心跳/订阅);当前无需处理客户端消息
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.debug(f"WebSocket 异常断开: {e}")
        ws_manager.disconnect(websocket)


async def notify_workflow_paused(
    run_id: str,
    workflow_id: str,
    message: str,
    approvers: list,
    paused_step_id: str,
) -> None:
    """A1: 工作流暂停于审批节点时广播通知(供 execute.py 调用)"""
    await ws_manager.broadcast("workflow:paused", {
        "run_id": run_id,
        "workflow_id": workflow_id,
        "message": message,
        "approvers": approvers,
        "paused_step_id": paused_step_id,
    })


async def notify_workflow_resumed(run_id: str, workflow_id: str, decision: str) -> None:
    """A1: 工作流审批恢复后广播通知(供 execute.py 调用)"""
    await ws_manager.broadcast("workflow:resumed", {
        "run_id": run_id,
        "workflow_id": workflow_id,
        "decision": decision,
    })
