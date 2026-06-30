"""文件读取工具"""
import os
import json
import asyncio


def _validate_workspace_path(path: str) -> str:
    """校验路径必须位于工作区目录内，防止路径遍历，返回绝对路径"""
    WORKSPACE_DIR = os.getenv(
        "WORKSPACE_DIR",
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "workspace"),
    )
    # 容错：LLM 常生成 /input/xxx 或 /output/xxx 绝对路径，自动转为相对路径
    if path.startswith("/input/") or path.startswith("/output/") or path in ("/input", "/output"):
        path = path.lstrip("/")
    # 相对路径基于 WORKSPACE_DIR 解析，绝对路径直接规范化
    if os.path.isabs(path):
        abs_path = os.path.realpath(path)
    else:
        abs_path = os.path.realpath(os.path.join(WORKSPACE_DIR, path))
    workspace_real = os.path.realpath(WORKSPACE_DIR)
    # 工作区目录不存在则创建
    if not os.path.exists(workspace_real):
        os.makedirs(workspace_real, exist_ok=True)
    # 越界检查：解析后的路径必须位于工作区目录内
    if os.path.commonpath([abs_path, workspace_real]) != workspace_real:
        raise ValueError("路径越界，必须在工作区目录内")
    return abs_path


def _read_sync(path: str, fmt: str) -> dict:
    """同步读取文件，在线程池中执行"""
    size = os.path.getsize(path)

    if fmt == "json":
        with open(path, "r", encoding="utf-8") as f:
            content = json.load(f)
    else:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

    return {"content": content, "size": size, "path": path}


async def execute(params: dict, context) -> dict:
    """
    读取本地文件
    :param params: { path, format }
    :return: { content, size }
    """
    path = params.get("path", "")
    fmt = params.get("format", "text")  # text | json

    if not path:
        raise ValueError("path 参数不能为空")

    # 路径遍历防护：校验并替换为工作区内绝对路径
    path = _validate_workspace_path(path)

    if not os.path.exists(path):
        raise FileNotFoundError(f"文件不存在: {path}")

    # 在线程池中执行同步文件读取，避免阻塞事件循环
    return await asyncio.to_thread(_read_sync, path, fmt)
