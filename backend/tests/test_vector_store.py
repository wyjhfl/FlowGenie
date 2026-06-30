"""C5: 向量存储与相似度检索工具单元测试

验证:
- vector_upsert: 直接传 vector / 自动向量化 / 同 id 覆盖 / 维度一致性 / 上限保护 / 路径遍历
- vector_search: 文本查询 / 向量查询 / Top-K / 维度校验 / 空存储 / 不存在文件
- vector_delete: 删除成功 / 不存在 id / 空 ids
- 往返一致性: upsert → search → delete
- 持久化:pickle 文件可重新加载
- executor 路由 + tool_registry 注册
"""
import os
import pickle
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def workspace_tmp(monkeypatch, tmp_path):
    """将 WORKSPACE_DIR 指向临时目录"""
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path))
    yield tmp_path


# ============ vector_upsert 测试 ============

@pytest.mark.asyncio
async def test_upsert_with_explicit_vectors(workspace_tmp):
    """直接传入 vector 字段:无需 LLM API"""
    from tools.vector_store import execute_upsert

    items = [
        {"id": "doc_1", "text": "hello", "vector": [1.0, 0.0, 0.0]},
        {"id": "doc_2", "text": "world", "vector": [0.0, 1.0, 0.0]},
    ]
    result = await execute_upsert(
        {"store_path": "kb.pkl", "items": items},
        context=None,
    )

    assert result["success"] is True
    assert result["operation"] == "upsert"
    assert result["count"] == 2
    assert result["dim"] == 3
    assert result["upserted"] == 2
    assert (workspace_tmp / "kb.pkl").exists()


@pytest.mark.asyncio
async def test_upsert_auto_embed(workspace_tmp):
    """items 未提供 vector 时自动调用 embedding"""
    from tools.vector_store import execute_upsert

    items = [
        {"id": "doc_1", "text": "hello world"},
        {"id": "doc_2", "text": "foo bar"},
    ]
    fake_vectors = [[0.1, 0.2], [0.3, 0.4]]

    with patch("core.llm.has_api_key", return_value=True), \
         patch("core.llm.embed", return_value=fake_vectors):
        result = await execute_upsert(
            {"store_path": "kb.pkl", "items": items, "model": "text-embedding-3-small"},
            context=None,
        )

    assert result["success"] is True
    assert result["count"] == 2
    assert result["dim"] == 2


@pytest.mark.asyncio
async def test_upsert_same_id_overwrites(workspace_tmp):
    """同 id 的记录被覆盖(不重复)"""
    from tools.vector_store import execute_upsert

    items1 = [{"id": "doc_1", "text": "v1", "vector": [1.0, 0.0]}]
    items2 = [{"id": "doc_1", "text": "v2-updated", "vector": [0.5, 0.5]}]

    await execute_upsert({"store_path": "kb.pkl", "items": items1}, context=None)
    result = await execute_upsert({"store_path": "kb.pkl", "items": items2}, context=None)

    assert result["success"] is True
    assert result["count"] == 1  # 仍是 1 条(覆盖)
    assert result["upserted"] == 1

    # 验证内容被覆盖:加载 store 检查
    from tools.vector_store import _load_store
    store = _load_store(str(workspace_tmp / "kb.pkl"))
    assert store["items"][0]["text"] == "v2-updated"
    assert store["items"][0]["vector"] == [0.5, 0.5]


@pytest.mark.asyncio
async def test_upsert_dim_mismatch(workspace_tmp):
    """维度不一致返回错误"""
    from tools.vector_store import execute_upsert

    items1 = [{"id": "doc_1", "text": "v1", "vector": [1.0, 0.0]}]
    items2 = [{"id": "doc_2", "text": "v2", "vector": [1.0, 0.0, 0.0]}]

    await execute_upsert({"store_path": "kb.pkl", "items": items1}, context=None)
    result = await execute_upsert({"store_path": "kb.pkl", "items": items2}, context=None)

    assert result["success"] is False
    assert "维度不一致" in result["warning"]


@pytest.mark.asyncio
async def test_upsert_empty_items(workspace_tmp):
    """空 items 返回错误"""
    from tools.vector_store import execute_upsert

    result = await execute_upsert({"store_path": "kb.pkl", "items": []}, context=None)
    assert result["success"] is False
    assert "items" in result["warning"]


@pytest.mark.asyncio
async def test_upsert_missing_store_path(workspace_tmp):
    """store_path 为空返回错误"""
    from tools.vector_store import execute_upsert

    result = await execute_upsert({"items": [{"id": "x", "vector": [1.0]}]}, context=None)
    assert result["success"] is False
    assert "store_path" in result["warning"]


@pytest.mark.asyncio
async def test_upsert_invalid_vector_type(workspace_tmp):
    """vector 非列表返回错误"""
    from tools.vector_store import execute_upsert

    items = [{"id": "doc_1", "text": "v1", "vector": "not a list"}]
    result = await execute_upsert({"store_path": "kb.pkl", "items": items}, context=None)
    assert result["success"] is False
    assert "vector" in result["warning"]


@pytest.mark.asyncio
async def test_upsert_auto_embed_no_api_key(workspace_tmp, monkeypatch):
    """自动向量化但未配置 LLM_API_KEY 返回错误"""
    from tools.vector_store import execute_upsert

    monkeypatch.setenv("LLM_API_KEY", "")
    items = [{"id": "doc_1", "text": "hello"}]
    with patch("core.llm.has_api_key", return_value=False):
        result = await execute_upsert({"store_path": "kb.pkl", "items": items}, context=None)

    assert result["success"] is False
    assert "LLM_API_KEY" in result["warning"]


@pytest.mark.asyncio
async def test_upsert_auto_embed_empty_text(workspace_tmp):
    """自动向量化但 text 为空返回错误"""
    from tools.vector_store import execute_upsert

    items = [{"id": "doc_1", "text": ""}]
    result = await execute_upsert({"store_path": "kb.pkl", "items": items}, context=None)
    assert result["success"] is False
    assert "text" in result["warning"]


@pytest.mark.asyncio
async def test_upsert_truncates_text(workspace_tmp):
    """text > 8000 字符自动截断"""
    from tools.vector_store import execute_upsert, _MAX_TEXT_LENGTH

    long_text = "x" * (_MAX_TEXT_LENGTH + 500)
    items = [{"id": "doc_1", "text": long_text, "vector": [1.0, 0.0]}]
    result = await execute_upsert({"store_path": "kb.pkl", "items": items}, context=None)

    assert result["success"] is True
    from tools.vector_store import _load_store
    store = _load_store(str(workspace_tmp / "kb.pkl"))
    assert len(store["items"][0]["text"]) == _MAX_TEXT_LENGTH


@pytest.mark.asyncio
async def test_upsert_path_traversal_rejected(workspace_tmp):
    """路径遍历防护:../ 被拒绝"""
    from tools.vector_store import execute_upsert

    items = [{"id": "doc_1", "text": "v1", "vector": [1.0]}]
    result = await execute_upsert(
        {"store_path": "../../etc/passwd.pkl", "items": items},
        context=None,
    )
    assert result["success"] is False
    assert "越界" in result["warning"] or "warning" in result


@pytest.mark.asyncio
async def test_upsert_metadata_normalized(workspace_tmp):
    """metadata 非 dict 时被规范化"""
    from tools.vector_store import execute_upsert

    items = [{"id": "doc_1", "text": "v1", "vector": [1.0], "metadata": "not a dict"}]
    result = await execute_upsert({"store_path": "kb.pkl", "items": items}, context=None)

    assert result["success"] is True
    from tools.vector_store import _load_store
    store = _load_store(str(workspace_tmp / "kb.pkl"))
    assert store["items"][0]["metadata"] == {"value": "not a dict"}


# ============ vector_search 测试 ============

@pytest.mark.asyncio
async def test_search_with_query_vector(workspace_tmp):
    """使用 query_vector 检索:返回 Top-K 结果"""
    from tools.vector_store import execute_upsert, execute_search

    # 构造 3 个向量,query 与 doc_1 最相似
    items = [
        {"id": "doc_1", "text": "alpha", "vector": [1.0, 0.0, 0.0]},
        {"id": "doc_2", "text": "beta", "vector": [0.0, 1.0, 0.0]},
        {"id": "doc_3", "text": "gamma", "vector": [0.0, 0.0, 1.0]},
    ]
    await execute_upsert({"store_path": "kb.pkl", "items": items}, context=None)

    result = await execute_search(
        {"store_path": "kb.pkl", "query_vector": [0.9, 0.1, 0.0], "top_k": 2},
        context=None,
    )

    assert result["success"] is True
    assert result["operation"] == "search"
    assert result["count"] == 2
    # Top-1 应是 doc_1(余弦相似度最高)
    assert result["results"][0]["id"] == "doc_1"
    assert result["results"][0]["score"] > 0.9
    # score 降序
    assert result["results"][0]["score"] >= result["results"][1]["score"]


@pytest.mark.asyncio
async def test_search_with_text_query(workspace_tmp):
    """文本查询:自动向量化后检索"""
    from tools.vector_store import execute_upsert, execute_search

    items = [
        {"id": "doc_1", "text": "alpha", "vector": [1.0, 0.0]},
        {"id": "doc_2", "text": "beta", "vector": [0.0, 1.0]},
    ]
    await execute_upsert({"store_path": "kb.pkl", "items": items}, context=None)

    # embed 返回的向量接近 doc_1
    with patch("core.llm.has_api_key", return_value=True), \
         patch("core.llm.embed", return_value=[[0.95, 0.05]]):
        result = await execute_search(
            {"store_path": "kb.pkl", "query": "alpha-like", "top_k": 1},
            context=None,
        )

    assert result["success"] is True
    assert result["count"] == 1
    assert result["results"][0]["id"] == "doc_1"


@pytest.mark.asyncio
async def test_search_top_k_limit(workspace_tmp):
    """top_k 超过 _MAX_TOP_K(100)时被截断"""
    from tools.vector_store import execute_search, _MAX_TOP_K

    # 先 upsert 一个 store
    from tools.vector_store import execute_upsert
    await execute_upsert(
        {"store_path": "kb.pkl", "items": [{"id": "x", "vector": [1.0]}]},
        context=None,
    )

    result = await execute_search(
        {"store_path": "kb.pkl", "query_vector": [1.0], "top_k": 500},
        context=None,
    )
    assert result["success"] is True
    assert result["top_k"] == _MAX_TOP_K


@pytest.mark.asyncio
async def test_search_dim_mismatch(workspace_tmp):
    """查询向量维度与 store 不一致返回错误"""
    from tools.vector_store import execute_upsert, execute_search

    await execute_upsert(
        {"store_path": "kb.pkl", "items": [{"id": "x", "vector": [1.0, 0.0]}]},
        context=None,
    )
    result = await execute_search(
        {"store_path": "kb.pkl", "query_vector": [1.0, 0.0, 0.0]},
        context=None,
    )
    assert result["success"] is False
    assert "维度" in result["warning"]


@pytest.mark.asyncio
async def test_search_store_not_exist(workspace_tmp):
    """store 文件不存在返回错误"""
    from tools.vector_store import execute_search

    result = await execute_search(
        {"store_path": "missing.pkl", "query_vector": [1.0]},
        context=None,
    )
    assert result["success"] is False
    assert "不存在" in result["warning"]


@pytest.mark.asyncio
async def test_search_empty_store(workspace_tmp):
    """store 为空时返回错误"""
    from tools.vector_store import execute_search, _save_store

    # 手动构造一个空 store
    _save_store(str(workspace_tmp / "kb.pkl"), {"dim": 0, "model": "", "items": []})

    result = await execute_search(
        {"store_path": "kb.pkl", "query_vector": [1.0]},
        context=None,
    )
    assert result["success"] is False
    assert "空" in result["warning"]


@pytest.mark.asyncio
async def test_search_missing_both_query_and_vector(workspace_tmp):
    """query 和 query_vector 都未提供返回错误"""
    from tools.vector_store import execute_upsert, execute_search

    await execute_upsert(
        {"store_path": "kb.pkl", "items": [{"id": "x", "vector": [1.0]}]},
        context=None,
    )

    result = await execute_search({"store_path": "kb.pkl"}, context=None)
    assert result["success"] is False
    assert "query" in result["warning"].lower() or "query_vector" in result["warning"].lower()


@pytest.mark.asyncio
async def test_search_path_traversal_rejected(workspace_tmp):
    """路径遍历防护"""
    from tools.vector_store import execute_search

    result = await execute_search(
        {"store_path": "../../etc/passwd.pkl", "query_vector": [1.0]},
        context=None,
    )
    assert result["success"] is False


# ============ vector_delete 测试 ============

@pytest.mark.asyncio
async def test_delete_basic(workspace_tmp):
    """删除指定 id 的记录"""
    from tools.vector_store import execute_upsert, execute_delete

    items = [
        {"id": "doc_1", "text": "a", "vector": [1.0]},
        {"id": "doc_2", "text": "b", "vector": [0.5]},
        {"id": "doc_3", "text": "c", "vector": [0.3]},
    ]
    await execute_upsert({"store_path": "kb.pkl", "items": items}, context=None)

    result = await execute_delete(
        {"store_path": "kb.pkl", "ids": ["doc_1", "doc_3"]},
        context=None,
    )

    assert result["success"] is True
    assert result["operation"] == "delete"
    assert result["deleted"] == 2
    assert result["remaining"] == 1


@pytest.mark.asyncio
async def test_delete_nonexistent_id(workspace_tmp):
    """删除不存在的 id:deleted=0"""
    from tools.vector_store import execute_upsert, execute_delete

    await execute_upsert(
        {"store_path": "kb.pkl", "items": [{"id": "doc_1", "vector": [1.0]}]},
        context=None,
    )

    result = await execute_delete(
        {"store_path": "kb.pkl", "ids": ["nonexistent"]},
        context=None,
    )

    assert result["success"] is True
    assert result["deleted"] == 0
    assert result["remaining"] == 1


@pytest.mark.asyncio
async def test_delete_empty_ids(workspace_tmp):
    """空 ids 返回错误"""
    from tools.vector_store import execute_delete

    result = await execute_delete({"store_path": "kb.pkl", "ids": []}, context=None)
    assert result["success"] is False
    assert "ids" in result["warning"]


@pytest.mark.asyncio
async def test_delete_store_not_exist(workspace_tmp):
    """store 不存在返回错误"""
    from tools.vector_store import execute_delete

    result = await execute_delete(
        {"store_path": "missing.pkl", "ids": ["x"]},
        context=None,
    )
    assert result["success"] is False
    assert "不存在" in result["warning"]


# ============ 往返一致性:upsert → search → delete ============

@pytest.mark.asyncio
async def test_roundtrip_upsert_search_delete(workspace_tmp):
    """完整往返:写入 → 检索 → 删除 → 检索为空"""
    from tools.vector_store import execute_upsert, execute_search, execute_delete, _load_store

    # 1. upsert 3 条
    items = [
        {"id": "d1", "text": "apple", "vector": [1.0, 0.0, 0.0]},
        {"id": "d2", "text": "banana", "vector": [0.0, 1.0, 0.0]},
        {"id": "d3", "text": "cherry", "vector": [0.0, 0.0, 1.0]},
    ]
    await execute_upsert({"store_path": "kb.pkl", "items": items}, context=None)

    # 2. 检索 Top-2
    r = await execute_search(
        {"store_path": "kb.pkl", "query_vector": [0.9, 0.1, 0.0], "top_k": 2},
        context=None,
    )
    assert r["success"] is True
    assert r["count"] == 2
    assert r["results"][0]["id"] == "d1"

    # 3. 删除 d1
    r = await execute_delete({"store_path": "kb.pkl", "ids": ["d1"]}, context=None)
    assert r["success"] is True
    assert r["deleted"] == 1
    assert r["remaining"] == 2

    # 4. 再检索:d1 应已消失,Top-1 应是 d2 或 d3
    r = await execute_search(
        {"store_path": "kb.pkl", "query_vector": [1.0, 0.0, 0.0], "top_k": 1},
        context=None,
    )
    assert r["success"] is True
    assert r["results"][0]["id"] != "d1"

    # 5. 验证 store 持久化:d1 不在 items 中
    store = _load_store(str(workspace_tmp / "kb.pkl"))
    ids = [it["id"] for it in store["items"]]
    assert "d1" not in ids
    assert set(ids) == {"d2", "d3"}


# ============ 持久化:pickle 文件可重新加载 ============

@pytest.mark.asyncio
async def test_store_persisted_as_pickle(workspace_tmp):
    """store 文件以 pickle 格式持久化,可被 _load_store 重新加载"""
    from tools.vector_store import execute_upsert, _load_store

    items = [{"id": "d1", "text": "v1", "vector": [1.0, 2.0, 3.0]}]
    await execute_upsert({"store_path": "kb.pkl", "items": items}, context=None)

    store_path = workspace_tmp / "kb.pkl"
    assert store_path.exists()

    # 直接用 pickle 加载验证格式
    with open(store_path, "rb") as f:
        raw_store = pickle.load(f)
    assert raw_store["dim"] == 3
    assert len(raw_store["items"]) == 1
    assert raw_store["items"][0]["id"] == "d1"
    assert raw_store["items"][0]["vector"] == [1.0, 2.0, 3.0]

    # 用 _load_store 加载
    store = _load_store(str(store_path))
    assert store["dim"] == 3
    assert store["items"][0]["id"] == "d1"


# ============ execute 分派 ============

@pytest.mark.asyncio
async def test_execute_dispatch_upsert(workspace_tmp):
    """execute 入口按 action=upsert 分派"""
    from tools.vector_store import execute

    items = [{"id": "d1", "vector": [1.0]}]
    result = await execute(
        {"action": "upsert", "store_path": "kb.pkl", "items": items},
        context=None,
    )
    assert result["success"] is True
    assert result["operation"] == "upsert"


@pytest.mark.asyncio
async def test_execute_dispatch_search(workspace_tmp):
    """execute 入口按 action=search 分派"""
    from tools.vector_store import execute, execute_upsert

    await execute_upsert(
        {"store_path": "kb.pkl", "items": [{"id": "d1", "vector": [1.0]}]},
        context=None,
    )
    result = await execute(
        {"action": "search", "store_path": "kb.pkl", "query_vector": [1.0]},
        context=None,
    )
    assert result["success"] is True
    assert result["operation"] == "search"


@pytest.mark.asyncio
async def test_execute_dispatch_delete(workspace_tmp):
    """execute 入口按 action=delete 分派"""
    from tools.vector_store import execute, execute_upsert

    await execute_upsert(
        {"store_path": "kb.pkl", "items": [{"id": "d1", "vector": [1.0]}]},
        context=None,
    )
    result = await execute(
        {"action": "delete", "store_path": "kb.pkl", "ids": ["d1"]},
        context=None,
    )
    assert result["success"] is True
    assert result["operation"] == "delete"


@pytest.mark.asyncio
async def test_execute_unknown_action(workspace_tmp):
    """未知 action 返回错误"""
    from tools.vector_store import execute

    result = await execute({"action": "invalid"}, context=None)
    assert result["success"] is False
    assert "action" in result["warning"]


# ============ tool_registry 注册验证 ============

def test_vector_store_tools_registered():
    """3 个 vector_store 工具已注册到 tool_registry"""
    from core.tool_registry import get_tool, TOOL_REGISTRY

    tool_names = {t.name for t in TOOL_REGISTRY}
    assert "vector_store_upsert" in tool_names
    assert "vector_store_search" in tool_names
    assert "vector_store_delete" in tool_names

    upsert = get_tool("vector_store_upsert")
    assert upsert is not None
    assert upsert.category == "AI 处理"
    assert "store_path" in upsert.required
    assert "items" in upsert.required

    search = get_tool("vector_store_search")
    assert search is not None
    assert "store_path" in search.required
    assert "results" in search.output_schema

    delete = get_tool("vector_store_delete")
    assert delete is not None
    assert "ids" in delete.required
    assert "deleted" in delete.output_schema


def test_vector_store_tools_in_executors():
    """3 个 vector_store 工具已在 TOOL_EXECUTORS 注册"""
    from tools import TOOL_EXECUTORS

    assert "vector_store_upsert" in TOOL_EXECUTORS
    assert "vector_store_search" in TOOL_EXECUTORS
    assert "vector_store_delete" in TOOL_EXECUTORS
    assert callable(TOOL_EXECUTORS["vector_store_upsert"])
    assert callable(TOOL_EXECUTORS["vector_store_search"])
    assert callable(TOOL_EXECUTORS["vector_store_delete"])


# ============ RAG 模板验证 ============

def test_rag_qa_template_registered():
    """RAG 模板已注册到 TEMPLATES 列表"""
    from templates import TEMPLATES

    scenarios = [t.get("scenario", "") for t in TEMPLATES]
    assert "知识库问答" in scenarios


def test_rag_qa_template_structure():
    """RAG 模板结构完整:steps/edges/工具引用"""
    from templates.rag_qa import get_template

    template = get_template()
    assert template["scenario"] == "知识库问答"
    assert len(template["steps"]) == 3

    # 验证工具引用
    tools = [s["tool"] for s in template["steps"]]
    assert "manual_trigger" in tools
    assert "vector_store_search" in tools
    assert "llm_analysis" in tools

    # 验证向量检索步骤引用 trigger_data.question
    search_step = next(s for s in template["steps"] if s["tool"] == "vector_store_search")
    assert "{{trigger_data.question}}" in search_step["params"]["query"]

    # 验证 LLM 步骤引用检索结果
    llm_step = next(s for s in template["steps"] if s["tool"] == "llm_analysis")
    assert "{{step_2.results}}" in llm_step["params"]["data"]


def test_rag_qa_match_keywords():
    """RAG 模板关键词匹配"""
    from templates.rag_qa import match_keywords
    from routers.parse import match_template

    keywords = match_keywords()
    assert "rag" in keywords
    assert "知识库" in keywords

    # 验证 match_template 能匹配 RAG 场景
    template = match_template("帮我做一个 RAG 知识库问答系统")
    assert template is not None
    assert template["scenario"] == "知识库问答"
