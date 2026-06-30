"""API Key 认证中间件 - 通过 env 开关启用,保护所有业务端点"""
import os
import logging
from fastapi import Header, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)

# 放行路径:健康检查、API 文档、OpenAPI schema、webhook 回调端点
# webhook 端点由外部系统调用,无法携带自定义头,需单独放行
_PUBLIC_PATHS = frozenset({
    "/api/health",
    "/docs",
    "/openapi.json",
    "/redoc",
})


class APIKeyMiddleware(BaseHTTPMiddleware):
    """
    API Key 认证中间件
    - 从 env 读取 FLOWGENIE_API_KEY;未配置 → 本地开发模式,放行所有请求
    - 已配置 → 校验请求头 X-API-Key,不匹配返回 401
    - 放行健康检查/文档/webhook 端点(无需认证)
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        api_key = os.getenv("FLOWGENIE_API_KEY", "")
        # 未配置 key → 本地开发模式,放行
        if not api_key:
            return await call_next(request)

        path = request.url.path
        # 公开端点放行
        if path in _PUBLIC_PATHS or path.startswith("/api/webhooks/"):
            return await call_next(request)

        # 校验 X-API-Key
        provided = request.headers.get("X-API-Key", "")
        if provided != api_key:
            client = request.client.host if request.client else "unknown"
            logger.warning(f"无效 API Key 访问 path={path} client={client}")
            return JSONResponse(
                status_code=401,
                content={
                    "code": "UNAUTHORIZED",
                    "message": "Invalid or missing API key",
                },
            )
        return await call_next(request)


async def require_admin(x_admin_token: str = Header(default="", alias="X-Admin-Token")) -> None:
    """FastAPI 依赖:校验 admin token,保护 /api/credentials 写操作。
    未配置 FLOWGENIE_ADMIN_TOKEN 时放行(本地开发)。
    用法:在路由签名加 `_: None = Depends(require_admin)`
    """
    admin_token = os.getenv("FLOWGENIE_ADMIN_TOKEN", "")
    if not admin_token:
        # 未配置 → 本地开发放行(仍受 APIKeyMiddleware 保护)
        return
    if x_admin_token != admin_token:
        raise HTTPException(status_code=403, detail="Admin token required")
