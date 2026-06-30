"""请求上下文 - 为每个请求注入 request_id,供日志关联链路"""
import uuid
from contextvars import ContextVar
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# 跨协程传递的 request_id(日志 Filter 通过它取值)
request_id_var: ContextVar[str] = ContextVar("request_id", default="")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """
    请求追踪中间件
    - 优先透传客户端传来的 X-Request-Id,否则生成 8 位短 UUID
    - 写入 request.state.request_id(供异常处理器/路由取用)
    - 写入 contextvars(供日志 Filter 取用)
    - 回写到响应头 X-Request-Id
    """

    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("X-Request-Id") or uuid.uuid4().hex[:8]
        request_id_var.set(rid)
        request.state.request_id = rid
        try:
            response: Response = await call_next(request)
        except Exception:
            # 异常会由全局异常处理器接管,但仍需确保 contextvar 在当前调用栈可见
            raise
        response.headers["X-Request-Id"] = rid
        return response
