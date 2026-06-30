"""FlowGenie 后端入口 - FastAPI 应用"""
import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# 日志配置必须在其他模块导入前初始化，确保所有模块使用统一日志配置
from core.logging_config import setup_logging
setup_logging()

from routers import parse, match, export, execute, workflows, webhooks, credentials, preferences, stats, run_export, ws
from db.database import init_db
from scheduler.manager import init_scheduler
from core.request_context import RequestContextMiddleware
from core.auth import APIKeyMiddleware

logger = logging.getLogger(__name__)

scheduler_manager = init_scheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动：初始化数据库表 + 启动调度器
    init_db()
    scheduler_manager.start()
    yield
    # 关闭：优雅关闭调度器
    scheduler_manager.shutdown()


app = FastAPI(
    title="FlowGenie API",
    description="自然语言驱动的 AI 智能工作流生成器",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS 配置(收紧 methods/headers,缩小风险面;保留 credentials 供前端携带 X-API-Key 头)
_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://flowgenie.vercel.app",
    "https://flow-genie-eight.vercel.app",  # Vercel 实际部署地址
    "https://flowgenie.hfl.asia",  # 自有域名(绑定后生效)
]
_frontend_url = os.getenv("FRONTEND_URL", "")
if _frontend_url and _frontend_url not in _origins:
    _origins.append(_frontend_url)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=[
        "Content-Type",
        "Authorization",
        "X-API-Key",
        "X-Admin-Token",
        "X-Request-Id",
    ],
)

# 中间件注册顺序(Starlette:后添加=最外层)
# 执行链:RequestContextMiddleware(最外) → APIKeyMiddleware → CORS → 路由
# - RequestContextMiddleware 最外层:确保所有后续中间件/异常处理器能取到 request_id
# - APIKeyMiddleware:env 开关启用时校验 X-API-Key,放行健康检查/文档/webhook
# - CORS:处理跨域预检
app.add_middleware(APIKeyMiddleware)
# 请求追踪中间件:注入 X-Request-Id,写入 contextvars 供日志关联
app.add_middleware(RequestContextMiddleware)


# 全局异常处理器:捕获所有未处理异常,统一返回 {code, message, request_id},不泄露堆栈
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", "unknown")
    logger.exception(f"[{request_id}] 未捕获异常: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "code": "INTERNAL_ERROR",
            "message": "服务器内部错误,请联系管理员",
            "request_id": request_id,
        },
    )


app.include_router(parse.router, prefix="/api", tags=["parse"])
app.include_router(match.router, prefix="/api", tags=["match"])
app.include_router(export.router, prefix="/api", tags=["export"])
app.include_router(execute.router, prefix="/api/workflows", tags=["execute"])
# run_export 必须在 workflows 之前注册:避免 /workflows/{id}/runs/export 被
# workflows 的 /workflows/{id}/runs/{run_id} 路径参数路由抢占
app.include_router(run_export.router, prefix="/api", tags=["run_export"])
app.include_router(workflows.router, prefix="/api", tags=["workflows"])
app.include_router(webhooks.router, prefix="/api", tags=["webhooks"])
app.include_router(credentials.router, prefix="/api/credentials", tags=["credentials"])
app.include_router(preferences.router, tags=["preferences"])
app.include_router(stats.router, prefix="/api", tags=["stats"])
# A4: WebSocket 端点 /ws(无 prefix,根路径挂载)
app.include_router(ws.router, tags=["websocket"])


@app.get("/api/health")
async def health():
    """健康检查接口"""
    return {"status": "ok", "service": "flowgenie-backend"}
