"""C5: 向量存储与相似度检索工具

基于 `numpy` + pickle 本地文件存储,提供 3 个操作:
- vector_upsert: 写入/更新向量记录(支持自动调用 embedding 向量化,或直接传入向量)
- vector_search: 余弦相似度 Top-K 检索
- vector_delete: 按 id 删除向量记录

存储格式(pickle 文件):
{
    "dim": int,
    "model": str,
    "items": [{"id": str, "text": str, "vector": list[float], "metadata": dict}, ...],
}

设计要点:
- 路径遍历防护:复用 file_write._validate_workspace_path
- upsert 自动去重(同 id 覆盖)
- 检索使用 numpy 余弦相似度(向量归一化后点积,O(n) 单次扫描)
- 上限保护:单 store 最大 10000 条记录,单次检索 top_k ≤ 100
- 无外部向量库依赖,适合个人/小团队场景(千级文档量);更大规模请接入专业向量数据库
"""
import os
import pickle
import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

# 安全上限
_MAX_ITEMS_PER_STORE = 10000
_MAX_TOP_K = 100
_MAX_TEXT_LENGTH = 8000


def _validate_workspace_path(path: str) -> str:
    """复用 file_write 的路径校验逻辑"""
    from tools.file_write import _validate_workspace_path as _validate
    return _validate(path)


def _load_store(store_path: str) -> dict:
    """加载向量存储文件,不存在则返回空 store"""
    if not os.path.exists(store_path):
        return {"dim": 0, "model": "", "items": []}
    try:
        with open(store_path, "rb") as f:
            store = pickle.load(f)
        # 容错:确保字段完整
        if not isinstance(store, dict):
            return {"dim": 0, "model": "", "items": []}
        store.setdefault("dim", 0)
        store.setdefault("model", "")
        store.setdefault("items", [])
        return store
    except Exception as e:
        logger.warning(f"加载向量存储失败({store_path}): {e},已重置为空 store")
        return {"dim": 0, "model": "", "items": []}


def _save_store(store_path: str, store: dict) -> None:
    """保存向量存储到文件(原子写:先写临时文件再 rename,避免半截写)"""
    os.makedirs(os.path.dirname(store_path), exist_ok=True)
    tmp_path = store_path + ".tmp"
    with open(tmp_path, "wb") as f:
        pickle.dump(store, f, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(tmp_path, store_path)


def _cosine_top_k(query_vector: list[float], items: list[dict], top_k: int) -> list[dict]:
    """numpy 余弦相似度 Top-K 检索

    :return: [{id, text, score, metadata}, ...] 按 score 降序
    """
    import numpy as np

    if not items:
        return []

    query = np.asarray(query_vector, dtype=np.float32)
    query_norm = np.linalg.norm(query)
    if query_norm == 0:
        return []

    # 构造向量矩阵 (N, D)
    matrix = np.asarray([it["vector"] for it in items], dtype=np.float32)
    # 归一化
    norms = np.linalg.norm(matrix, axis=1)
    # 避免除零
    safe_norms = np.where(norms == 0, 1.0, norms)
    matrix_normalized = matrix / safe_norms[:, None]
    query_normalized = query / query_norm

    # 余弦相似度 = 归一化后点积
    scores = matrix_normalized @ query_normalized  # (N,)

    # Top-K(限制 top_k 不超过 items 数)
    k = min(top_k, len(items))
    if k <= 0:
        return []
    # argpartition 取前 k 个最大值的索引(无序),再排序
    top_idx_unsorted = np.argpartition(scores, -k)[-k:]
    top_idx_sorted = top_idx_unsorted[np.argsort(scores[top_idx_unsorted])[::-1]]

    results = []
    for idx in top_idx_sorted:
        i = int(idx)
        results.append({
            "id": items[i].get("id", ""),
            "text": items[i].get("text", ""),
            "score": float(scores[i]),
            "metadata": items[i].get("metadata", {}) or {},
        })
    return results


# ===== 异步执行器 =====

async def execute(params: dict, context: Any) -> dict:
    """vector_store 工具统一入口(按 action 分派)

    :param params: {action: "upsert"|"search"|"delete", ...}
    :return: 操作结果 dict
    """
    action = params.get("action", "")
    if action == "upsert":
        return await execute_upsert(params, context)
    if action == "search":
        return await execute_search(params, context)
    if action == "delete":
        return await execute_delete(params, context)
    return {
        "success": False,
        "warning": f"未知 action: {action}(支持 upsert / search / delete)",
    }


async def execute_upsert(params: dict, context: Any) -> dict:
    """vector_upsert: 写入/更新向量记录

    :param params: {
        store_path: str,
        items: [{"id": str, "text": str, "vector"?: list[float], "metadata"?: dict}],
        model?: str,  # 当 items 未提供 vector 时,自动调用 embedding 向量化
    }
    :return: {success, operation, store_path, count, dim, model, warning?}
    """
    store_path = params.get("store_path", "")
    items = params.get("items", [])
    model = params.get("model", "")

    if not store_path:
        return {"success": False, "warning": "store_path 不能为空"}
    if not items:
        return {"success": False, "warning": "items 不能为空"}
    if not isinstance(items, list):
        return {"success": False, "warning": f"items 必须为列表,当前类型: {type(items).__name__}"}

    try:
        abs_path = _validate_workspace_path(store_path)
    except ValueError as e:
        return {"success": False, "warning": str(e)}

    # 上限截断
    if len(items) > _MAX_ITEMS_PER_STORE:
        logger.warning(f"upsert items 数 {len(items)} 超过上限 {_MAX_ITEMS_PER_STORE},已截断")
        items = items[:_MAX_ITEMS_PER_STORE]

    # 规范化 items:确保每项有 id/text,vector 可选
    need_embed_texts: list[str] = []
    need_embed_indices: list[int] = []
    normalized: list[dict] = []
    for idx, it in enumerate(items):
        if not isinstance(it, dict):
            return {"success": False, "warning": f"items[{idx}] 必须为 dict,当前类型: {type(it).__name__}"}
        item_id = str(it.get("id", f"auto_{idx}"))
        text = it.get("text", "")
        if not isinstance(text, str):
            text = str(text)
        if len(text) > _MAX_TEXT_LENGTH:
            text = text[:_MAX_TEXT_LENGTH]
        vector = it.get("vector", None)
        metadata = it.get("metadata", {}) or {}
        if not isinstance(metadata, dict):
            metadata = {"value": metadata}

        if vector is None:
            # 需要向量化:text 不能为空
            if not text:
                return {"success": False, "warning": f"items[{idx}] 缺少 vector 且 text 为空,无法自动向量化"}
            need_embed_texts.append(text)
            need_embed_indices.append(idx)
            normalized.append({"id": item_id, "text": text, "vector": None, "metadata": metadata})
        else:
            # 直接提供向量
            if not isinstance(vector, list) or not vector:
                return {"success": False, "warning": f"items[{idx}].vector 必须为非空 list[float]"}
            try:
                vector = [float(x) for x in vector]
            except (TypeError, ValueError) as e:
                return {"success": False, "warning": f"items[{idx}].vector 转 float 失败: {e}"}
            normalized.append({"id": item_id, "text": text, "vector": vector, "metadata": metadata})

    # 批量向量化(若需要)
    if need_embed_texts:
        try:
            from core.llm import embed, has_api_key
        except ImportError as e:
            return {"success": False, "warning": f"LLM 模块加载失败: {e}"}

        if not has_api_key():
            return {"success": False, "warning": "未配置 LLM_API_KEY(自动向量化需要,或直接传入 vector 字段)"}

        usage_callback = getattr(context, "usage_callback", None) if context is not None else None
        try:
            vectors = await asyncio.to_thread(embed, need_embed_texts, model, usage_callback)
        except Exception as e:
            logger.error(f"upsert 自动向量化失败: {e}")
            return {"success": False, "warning": f"自动向量化失败: {e}"}

        if len(vectors) != len(need_embed_indices):
            return {"success": False, "warning": "向量化返回数量与输入不一致"}

        for i, vec in zip(need_embed_indices, vectors):
            normalized[i]["vector"] = vec

    # 加载已有 store 并合并(id 去重覆盖)
    def _merge_and_save():
        store = _load_store(abs_path)
        # 维度一致性检查
        new_dim = len(normalized[0]["vector"]) if normalized else 0
        if new_dim == 0:
            return None, "无有效向量"
        if store["dim"] == 0:
            store["dim"] = new_dim
            store["model"] = model or store.get("model", "")
        elif store["dim"] != new_dim:
            return None, f"向量维度不一致:store={store['dim']}, new={new_dim}(请使用相同 embedding 模型)"

        # id 索引(同 id 覆盖)
        existing_index = {it["id"]: i for i, it in enumerate(store["items"])}
        for it in normalized:
            if it["id"] in existing_index:
                store["items"][existing_index[it["id"]]] = it
            else:
                store["items"].append(it)

        # 上限保护(合并后再截断,保留最新)
        if len(store["items"]) > _MAX_ITEMS_PER_STORE:
            store["items"] = store["items"][-_MAX_ITEMS_PER_STORE:]

        _save_store(abs_path, store)
        return store, None

    try:
        store, err = await asyncio.to_thread(_merge_and_save)
    except Exception as e:
        logger.error(f"vector_upsert 持久化失败: {e}")
        return {"success": False, "warning": f"持久化失败: {e}"}

    if err:
        return {"success": False, "warning": err}

    return {
        "success": True,
        "operation": "upsert",
        "store_path": abs_path,
        "count": len(store["items"]),
        "dim": store["dim"],
        "model": store["model"],
        "upserted": len(normalized),
    }


async def execute_search(params: dict, context: Any) -> dict:
    """vector_search: 余弦相似度 Top-K 检索

    :param params: {
        store_path: str,
        query: str,            # 文本查询(自动向量化),与 query_vector 二选一
        query_vector: list,    # 向量查询,与 query 二选一(优先)
        top_k: int,            # 默认 5
        model?: str,
    }
    :return: {success, operation, store_path, results: [{id, text, score, metadata}], count, warning?}
    """
    store_path = params.get("store_path", "")
    query_text = params.get("query", "")
    query_vector = params.get("query_vector", None)
    try:
        top_k = int(params.get("top_k", 5))
    except (TypeError, ValueError):
        top_k = 5
    model = params.get("model", "")

    if not store_path:
        return {"success": False, "warning": "store_path 不能为空"}
    if top_k <= 0:
        top_k = 5
    if top_k > _MAX_TOP_K:
        top_k = _MAX_TOP_K

    try:
        abs_path = _validate_workspace_path(store_path)
    except ValueError as e:
        return {"success": False, "warning": str(e)}

    if not os.path.exists(abs_path):
        return {"success": False, "warning": f"向量存储不存在: {store_path}"}

    # 加载 store(线程池)
    store = await asyncio.to_thread(_load_store, abs_path)
    if not store["items"]:
        return {"success": False, "warning": "向量存储为空,无法检索"}
    if not store["dim"]:
        return {"success": False, "warning": "向量存储维度为 0,数据异常"}

    # 解析查询向量
    if query_vector is None:
        # 文本查询:自动向量化
        if not query_text:
            return {"success": False, "warning": "query 和 query_vector 至少提供一个"}
        try:
            from core.llm import embed, has_api_key
        except ImportError as e:
            return {"success": False, "warning": f"LLM 模块加载失败: {e}"}

        if not has_api_key():
            return {"success": False, "warning": "未配置 LLM_API_KEY(文本查询需要,或直接传入 query_vector)"}

        usage_callback = getattr(context, "usage_callback", None) if context is not None else None
        try:
            vectors = await asyncio.to_thread(embed, [query_text], model, usage_callback)
        except Exception as e:
            logger.error(f"search 自动向量化失败: {e}")
            return {"success": False, "warning": f"查询向量化失败: {e}"}
        if not vectors:
            return {"success": False, "warning": "查询向量化返回空"}
        query_vec = vectors[0]
    else:
        # 直接提供向量
        if not isinstance(query_vector, list) or not query_vector:
            return {"success": False, "warning": "query_vector 必须为非空 list[float]"}
        try:
            query_vec = [float(x) for x in query_vector]
        except (TypeError, ValueError) as e:
            return {"success": False, "warning": f"query_vector 转 float 失败: {e}"}

    # 维度一致性检查
    if len(query_vec) != store["dim"]:
        return {
            "success": False,
            "warning": f"查询向量维度 {len(query_vec)} 与 store 维度 {store['dim']} 不一致(请使用相同 embedding 模型)",
        }

    # 检索(放线程池,numpy 计算可能耗时)
    try:
        results = await asyncio.to_thread(_cosine_top_k, query_vec, store["items"], top_k)
    except Exception as e:
        logger.error(f"vector_search 计算失败: {e}")
        return {"success": False, "warning": f"检索失败: {e}"}

    return {
        "success": True,
        "operation": "search",
        "store_path": abs_path,
        "results": results,
        "count": len(results),
        "top_k": top_k,
        "store_count": len(store["items"]),
    }


async def execute_delete(params: dict, context: Any) -> dict:
    """vector_delete: 按 id 删除向量记录

    :param params: {store_path: str, ids: [str, ...]}
    :return: {success, operation, store_path, deleted, remaining, warning?}
    """
    store_path = params.get("store_path", "")
    ids = params.get("ids", [])

    if not store_path:
        return {"success": False, "warning": "store_path 不能为空"}
    if not ids:
        return {"success": False, "warning": "ids 不能为空"}
    if not isinstance(ids, list):
        return {"success": False, "warning": f"ids 必须为列表,当前类型: {type(ids).__name__}"}

    ids_set = {str(i) for i in ids}

    try:
        abs_path = _validate_workspace_path(store_path)
    except ValueError as e:
        return {"success": False, "warning": str(e)}

    if not os.path.exists(abs_path):
        return {"success": False, "warning": f"向量存储不存在: {store_path}"}

    def _delete_sync():
        store = _load_store(abs_path)
        before = len(store["items"])
        store["items"] = [it for it in store["items"] if it.get("id", "") not in ids_set]
        after = len(store["items"])
        _save_store(abs_path, store)
        return before - after, after

    try:
        deleted, remaining = await asyncio.to_thread(_delete_sync)
    except Exception as e:
        logger.error(f"vector_delete 失败: {e}")
        return {"success": False, "warning": f"删除失败: {e}"}

    return {
        "success": True,
        "operation": "delete",
        "store_path": abs_path,
        "deleted": deleted,
        "remaining": remaining,
    }
