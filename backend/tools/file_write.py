"""文件写入工具 - 写入本地文件"""
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
    # 仅处理形如 /input/... /output/... 的伪绝对路径，避免真实系统路径被误改
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


def _write_sync(path: str, text: str) -> dict:
    """同步写入文件，在线程池中执行"""
    # 确保目录存在（path 为校验后的绝对路径，dirname 必非空）
    os.makedirs(os.path.dirname(path), exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        f.write(text)

    size = os.path.getsize(path)
    return {"success": True, "path": path, "size": size}


async def execute(params: dict, context) -> dict:
    """
    将内容写入文件
    :param params: { path, content, format }
    :return: { success, path, size }
    """
    path = params.get("path", "")
    content = params.get("content", "")
    fmt = params.get("format", "text")  # text | json

    if not path:
        raise ValueError("path 参数不能为空")

    # 路径遍历防护：校验并替换为工作区内绝对路径
    path = _validate_workspace_path(path)

    # 空数据容错：空内容跳过写入，返回有意义的空结果
    if not content:
        return {"success": False, "path": path, "size": 0}

    # 按格式写入
    if fmt == "json":
        if isinstance(content, (dict, list)):
            text = json.dumps(content, ensure_ascii=False, indent=2)
        else:
            text = str(content)
    else:
        text = str(content)

    # 在线程池中执行同步文件写入，避免阻塞事件循环
    return await asyncio.to_thread(_write_sync, path, text)
