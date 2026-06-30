"""C5: 文本向量化工具

调用 LLM 兼容 `/v1/embeddings` 接口将文本批量向量化,作为向量检索/RAG 的基础能力。

设计要点:
- 复用 `core/llm.embed()`,统一走 OpenAI 兼容 client(凭证面板配置 LLM_API_KEY/LLM_BASE_URL 后生效)
- 单次上限 100 条文本(由 core/llm.embed 强制截断);超长文本自动截断到 8000 字符
- 模型可由参数 `model` 指定,缺省用 env `LLM_EMBEDDING_MODEL`(默认 text-embedding-3-small)
- 未配置 LLM_API_KEY 时返回明确错误(而非抛异常),与其它 LLM 工具错误处理一致
- B4 token 用量通过 context.usage_callback 上报(若存在)

输出:
- {vectors: list[list[float]], dim: int, count: int, model: str}
"""
import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

# 单条文本最大长度(超出截断)
_MAX_TEXT_LENGTH = 8000
# 单次最大文本数(超出截断)
_MAX_TEXTS = 100


async def execute(params: dict, context: Any) -> dict:
    """embed: 将文本批量向量化

    :param params: {texts: list[str], model?: str}
    :return: {success, vectors, dim, count, model, warning?}
    """
    texts = params.get("texts", [])
    model = params.get("model", "")

    # 参数校验
    if not texts:
        return {"success": False, "warning": "texts 不能为空(需为字符串列表)"}
    if not isinstance(texts, list):
        return {"success": False, "warning": f"texts 必须为列表,当前类型: {type(texts).__name__}"}
    # 元素类型容错:非字符串统一转 str
    texts = [str(t) if not isinstance(t, str) else t for t in texts]
    # 上限截断
    if len(texts) > _MAX_TEXTS:
        logger.warning(f"embed 文本数 {len(texts)} 超过上限 {_MAX_TEXTS},已截断")
        texts = texts[:_MAX_TEXTS]

    try:
        from core.llm import embed, has_api_key
    except ImportError as e:
        return {"success": False, "warning": f"LLM 模块加载失败: {e}"}

    if not has_api_key():
        return {"success": False, "warning": "未配置 LLM_API_KEY(请在凭证面板配置 LLM 凭证)"}

    # 从 context 提取 usage_callback(B4 token 上报)
    usage_callback = getattr(context, "usage_callback", None) if context is not None else None

    try:
        # core/llm.embed 是同步函数,放线程池执行避免阻塞事件循环
        vectors = await asyncio.to_thread(embed, texts, model, usage_callback)
    except Exception as e:
        logger.error(f"embed 调用失败: {e}")
        return {"success": False, "warning": f"向量化失败: {e}"}

    if not vectors:
        return {"success": False, "warning": "API 返回空向量(请检查 embedding 模型名)"}

    dim = len(vectors[0]) if vectors else 0
    use_model = model or _resolve_default_model()

    return {
        "success": True,
        "vectors": vectors,
        "dim": dim,
        "count": len(vectors),
        "model": use_model,
    }


def _resolve_default_model() -> str:
    """解析实际使用的 embedding 模型名(用于回显)"""
    import os
    return os.getenv("LLM_EMBEDDING_MODEL", "text-embedding-3-small")
