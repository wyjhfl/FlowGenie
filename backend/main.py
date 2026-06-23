"""FlowGenie 后端入口 - FastAPI 应用"""
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import parse, match, export

app = FastAPI(
    title="FlowGenie API",
    description="自然语言驱动的 AI 智能工作流生成器",
    version="0.1.0",
)

# CORS 配置：允许前端本地开发与生产域名访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        # 生产环境前端域名（部署后替换为实际 Vercel 地址）
        os.getenv("FRONTEND_URL", "https://flowgenie.vercel.app"),
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(parse.router, prefix="/api", tags=["parse"])
app.include_router(match.router, prefix="/api", tags=["match"])
app.include_router(export.router, prefix="/api", tags=["export"])


@app.get("/api/health")
async def health():
    """健康检查接口"""
    return {"status": "ok", "service": "flowgenie-backend"}
