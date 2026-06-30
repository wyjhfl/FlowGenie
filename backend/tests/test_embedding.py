"""C5: 文本向量化工具单元测试

验证:
- embed 成功:返回 vectors + dim + count + model
- 空列表/非列表参数校验
- 元素类型容错(非字符串自动转 str)
- 文本数 > 100 自动截断
- 未配置 LLM_API_KEY 返回明确错误
- LLM 调用异常时返回 success=False
- B4 token 用量回调通过 context.usage_callback 上报
- executor 路由 + tool_registry 注册
"""
import os
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def workspace_tmp(monkeypatch, tmp_path):
    """将 WORKSPACE_DIR 指向临时目录"""
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path))
    yield tmp_path


# ============ embed 成功路径 ============

@pytest.mark.asyncio
async def test_embed_basic(workspace_tmp):
    """embed 成功:返回 vectors/dim/count/model"""
    from tools.embedding import execute

    fake_vectors = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
    with patch("core.llm.has_api_key", return_value=True), \
         patch("core.llm.embed", return_value=fake_vectors):
        result = await execute(
            {"texts": ["hello world", "foo bar"], "model": "text-embedding-3-small"},
            context=None,
        )

    assert result["success"] is True
    assert result["vectors"] == fake_vectors
    assert result["dim"] == 3
    assert result["count"] == 2
    assert result["model"] == "text-embedding-3-small"


@pytest.mark.asyncio
async def test_embed_default_model_from_env(workspace_tmp, monkeypatch):
    """未传 model 时从 env LLM_EMBEDDING_MODEL 读取"""
    from tools.embedding import execute

    monkeypatch.setenv("LLM_EMBEDDING_MODEL", "custom-embed-v1")
    fake_vectors = [[0.1, 0.2]]
    with patch("core.llm.has_api_key", return_value=True), \
         patch("core.llm.embed", return_value=fake_vectors) as mock_embed:
        result = await execute({"texts": ["x"]}, context=None)

    assert result["success"] is True
    assert result["model"] == "custom-embed-v1"
    # 验证 embed() 调用时传了空 model(由内部 _resolve_default_model 回显)
    mock_embed.assert_called_once()
    args = mock_embed.call_args[0]
    # embed(texts, model, usage_callback) - model 应为空字符串
    assert args[1] == ""


# ============ 参数校验 ============

@pytest.mark.asyncio
async def test_embed_empty_texts(workspace_tmp):
    """空 texts 列表返回错误"""
    from tools.embedding import execute

    result = await execute({"texts": []}, context=None)
    assert result["success"] is False
    assert "texts" in result["warning"]


@pytest.mark.asyncio
async def test_embed_non_list_texts(workspace_tmp):
    """texts 非列表返回错误"""
    from tools.embedding import execute

    result = await execute({"texts": "not a list"}, context=None)
    assert result["success"] is False
    assert "列表" in result["warning"]


@pytest.mark.asyncio
async def test_embed_non_string_items_coerced(workspace_tmp):
    """非字符串元素自动转 str 后调用 embed"""
    from tools.embedding import execute

    fake_vectors = [[0.1], [0.2], [0.3]]
    captured_texts = []

    def fake_embed(texts, model, usage_callback):
        captured_texts.extend(texts)
        return fake_vectors

    with patch("core.llm.has_api_key", return_value=True), \
         patch("core.llm.embed", side_effect=fake_embed):
        result = await execute(
            {"texts": [123, True, {"k": "v"}]},
            context=None,
        )

    assert result["success"] is True
    assert result["count"] == 3
    # 验证元素都被转成 str
    assert captured_texts == ["123", "True", "{'k': 'v'}"]


@pytest.mark.asyncio
async def test_embed_truncates_over_100_texts(workspace_tmp):
    """文本数 > 100 自动截断到 100"""
    from tools.embedding import execute, _MAX_TEXTS

    fake_vectors = [[0.1]] * _MAX_TEXTS
    captured_count = {"value": 0}

    def fake_embed(texts, model, usage_callback):
        captured_count["value"] = len(texts)
        return fake_vectors[:len(texts)]

    with patch("core.llm.has_api_key", return_value=True), \
         patch("core.llm.embed", side_effect=fake_embed):
        result = await execute(
            {"texts": [f"text_{i}" for i in range(_MAX_TEXTS + 50)]},
            context=None,
        )

    assert result["success"] is True
    assert result["count"] == _MAX_TEXTS
    assert captured_count["value"] == _MAX_TEXTS


# ============ 错误处理 ============

@pytest.mark.asyncio
async def test_embed_no_api_key(workspace_tmp, monkeypatch):
    """未配置 LLM_API_KEY 返回明确错误"""
    from tools.embedding import execute

    monkeypatch.setenv("LLM_API_KEY", "")
    with patch("core.llm.has_api_key", return_value=False):
        result = await execute({"texts": ["x"]}, context=None)

    assert result["success"] is False
    assert "LLM_API_KEY" in result["warning"]


@pytest.mark.asyncio
async def test_embed_api_exception(workspace_tmp):
    """LLM 调用异常时返回 success=False"""
    from tools.embedding import execute

    with patch("core.llm.has_api_key", return_value=True), \
         patch("core.llm.embed", side_effect=RuntimeError("API timeout")):
        result = await execute({"texts": ["x"]}, context=None)

    assert result["success"] is False
    assert "向量化失败" in result["warning"]
    assert "API timeout" in result["warning"]


@pytest.mark.asyncio
async def test_embed_empty_vectors_from_api(workspace_tmp):
    """API 返回空向量列表时返回错误"""
    from tools.embedding import execute

    with patch("core.llm.has_api_key", return_value=True), \
         patch("core.llm.embed", return_value=[]):
        result = await execute({"texts": ["x"]}, context=None)

    assert result["success"] is False
    assert "空向量" in result["warning"]


# ============ B4 token 用量回调 ============

@pytest.mark.asyncio
async def test_embed_usage_callback_invoked(workspace_tmp):
    """context.usage_callback 被透传给 core.llm.embed"""
    from tools.embedding import execute

    captured_callback = {"value": None}

    def fake_embed(texts, model, usage_callback):
        captured_callback["value"] = usage_callback
        return [[0.1, 0.2]]

    fake_context = MagicMock()
    fake_context.usage_callback = lambda x: None

    with patch("core.llm.has_api_key", return_value=True), \
         patch("core.llm.embed", side_effect=fake_embed):
        result = await execute({"texts": ["x"]}, context=fake_context)

    assert result["success"] is True
    assert captured_callback["value"] is not None
    # 验证回调可正常调用
    captured_callback["value"]({"prompt_tokens": 10, "total_tokens": 10})


@pytest.mark.asyncio
async def test_embed_no_context_no_callback(workspace_tmp):
    """context=None 时不传 usage_callback(embed 接收 None)"""
    from tools.embedding import execute

    captured_callback = {"value": "unset"}

    def fake_embed(texts, model, usage_callback):
        captured_callback["value"] = usage_callback
        return [[0.1, 0.2]]

    with patch("core.llm.has_api_key", return_value=True), \
         patch("core.llm.embed", side_effect=fake_embed):
        result = await execute({"texts": ["x"]}, context=None)

    assert result["success"] is True
    assert captured_callback["value"] is None


# ============ tool_registry 注册验证 ============

def test_embedding_registered_in_tool_registry():
    """embedding 工具已注册到 tool_registry"""
    from core.tool_registry import get_tool, TOOL_REGISTRY

    tool_names = {t.name for t in TOOL_REGISTRY}
    assert "embedding" in tool_names

    tool = get_tool("embedding")
    assert tool is not None
    assert tool.category == "AI 处理"
    assert "texts" in tool.required
    assert "vectors" in tool.output_schema
    assert "dim" in tool.output_schema


def test_embedding_in_tool_executors():
    """embedding 已在 TOOL_EXECUTORS 注册"""
    from tools import TOOL_EXECUTORS

    assert "embedding" in TOOL_EXECUTORS
    assert callable(TOOL_EXECUTORS["embedding"])


# ============ core/llm.embed 单元测试 ============

def test_llm_embed_basic():
    """core.llm.embed: 正常调用返回向量列表"""
    from core.llm import embed

    fake_response = MagicMock()
    fake_response.data = [
        MagicMock(index=0, embedding=[0.1, 0.2, 0.3]),
        MagicMock(index=1, embedding=[0.4, 0.5, 0.6]),
    ]
    fake_response.usage = None

    fake_client = MagicMock()
    fake_client.embeddings.create.return_value = fake_response

    with patch("core.llm.get_client", return_value=fake_client):
        vectors = embed(["a", "b"])

    assert vectors == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
    # 验证 create 被调用,且 input 为列表
    call_kwargs = fake_client.embeddings.create.call_args.kwargs
    assert call_kwargs["input"] == ["a", "b"]


def test_llm_embed_empty_list():
    """core.llm.embed: 空列表直接返回 []"""
    from core.llm import embed

    result = embed([])
    assert result == []


def test_llm_embed_truncates_long_text():
    """core.llm.embed: 单条文本 > 8000 字符自动截断"""
    from core.llm import embed

    long_text = "x" * 9000
    fake_response = MagicMock()
    fake_response.data = [MagicMock(index=0, embedding=[0.1, 0.2])]
    fake_response.usage = None

    fake_client = MagicMock()
    fake_client.embeddings.create.return_value = fake_response

    with patch("core.llm.get_client", return_value=fake_client):
        embed([long_text])

    call_kwargs = fake_client.embeddings.create.call_args.kwargs
    # 验证文本被截断到 8000
    assert len(call_kwargs["input"][0]) == 8000


def test_llm_embed_usage_callback():
    """core.llm.embed: usage_callback 被正确调用"""
    from core.llm import embed

    fake_response = MagicMock()
    fake_response.data = [MagicMock(index=0, embedding=[0.1, 0.2])]
    fake_response.usage = MagicMock(
        prompt_tokens=15,
        total_tokens=15,
    )

    fake_client = MagicMock()
    fake_client.embeddings.create.return_value = fake_response

    captured = {"value": None}
    def cb(usage):
        captured["value"] = usage

    with patch("core.llm.get_client", return_value=fake_client):
        embed(["x"], "custom-model", cb)

    assert captured["value"] is not None
    assert captured["value"]["prompt_tokens"] == 15
    assert captured["value"]["completion_tokens"] == 0  # embedding 无 completion
    assert captured["value"]["total_tokens"] == 15
    assert captured["value"]["model"] == "custom-model"


def test_llm_embed_sorts_by_index():
    """core.llm.embed: 按 index 排序确保顺序与输入一致"""
    from core.llm import embed

    # 故意打乱 index 顺序
    fake_response = MagicMock()
    fake_response.data = [
        MagicMock(index=1, embedding=[0.4, 0.5]),
        MagicMock(index=0, embedding=[0.1, 0.2]),
        MagicMock(index=2, embedding=[0.7, 0.8]),
    ]
    fake_response.usage = None

    fake_client = MagicMock()
    fake_client.embeddings.create.return_value = fake_response

    with patch("core.llm.get_client", return_value=fake_client):
        vectors = embed(["a", "b", "c"])

    # 验证按 index 排序后顺序正确
    assert vectors == [[0.1, 0.2], [0.4, 0.5], [0.7, 0.8]]
