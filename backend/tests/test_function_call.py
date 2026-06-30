"""F1: Function Calling 单元测试

验证:
- get_tool_schema 从 Tool.params_schema 生成 OpenAI function schema
- chat_with_tools 解析 tool_calls
- function_call.execute 循环执行 + 结果回填 + 上限保护 + 空入参兜底
- executor 对 LLM 节点带 tools 参数时委托给 function_call
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ============ get_tool_schema 测试 ============

def test_get_tool_schema_returns_openai_format():
    """get_tool_schema 返回 OpenAI function calling 兼容格式"""
    from core.tool_registry import get_tool_schema

    schema = get_tool_schema("http_request")
    assert schema is not None
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "http_request"
    assert "description" in schema["function"]
    params = schema["function"]["parameters"]
    assert params["type"] == "object"
    assert "url" in params["properties"]
    assert params["properties"]["url"]["type"] == "string"
    assert "url" in params["required"]
    assert "method" in params["required"]


def test_get_tool_schema_infers_types_from_examples():
    """get_tool_schema 从示例值推断 JSON 类型"""
    from core.tool_registry import get_tool_schema

    schema = get_tool_schema("web_scraper")
    assert schema is not None
    props = schema["function"]["parameters"]["properties"]
    # url 是 str → string
    assert props["url"]["type"] == "string"
    # fields 是 list → array
    assert props["fields"]["type"] == "array"


def test_get_tool_schema_unknown_tool_returns_none():
    """get_tool_schema 对未知工具返回 None"""
    from core.tool_registry import get_tool_schema

    assert get_tool_schema("nonexistent_tool_xyz") is None


def test_get_tool_schemas_batch_skips_missing():
    """get_tool_schemas 批量获取时跳过不存在的工具"""
    from core.tool_registry import get_tool_schemas

    schemas = get_tool_schemas(["http_request", "nonexistent", "web_scraper"])
    assert len(schemas) == 2
    names = [s["function"]["name"] for s in schemas]
    assert "http_request" in names
    assert "web_scraper" in names


def test_get_tool_schema_function_call_itself():
    """function_call 工具自身也有 schema(可供嵌套调用,虽然不常见)"""
    from core.tool_registry import get_tool_schema

    schema = get_tool_schema("function_call")
    assert schema is not None
    assert schema["function"]["name"] == "function_call"
    props = schema["function"]["parameters"]["properties"]
    assert "prompt" in props
    assert "tools" in props
    assert "max_iterations" in props


# ============ chat_with_tools 测试 ============

@pytest.mark.asyncio
async def test_chat_with_tools_returns_tool_calls():
    """chat_with_tools 正确解析 tool_calls"""
    from core import llm

    # 模拟 LLM 返回 tool_calls
    mock_tc = MagicMock()
    mock_tc.id = "call_123"
    mock_tc.function.name = "http_request"
    mock_tc.function.arguments = '{"url": "https://example.com", "method": "GET"}'

    mock_msg = MagicMock()
    mock_msg.content = ""
    mock_msg.tool_calls = [mock_tc]

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message = mock_msg
    mock_response.usage = None

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    with patch.object(llm, "get_async_client", return_value=mock_client):
        result = await llm.chat_with_tools(
            messages=[{"role": "user", "content": "test"}],
            tools=[{"type": "function", "function": {"name": "http_request"}}],
        )

    assert result["content"] == ""
    assert len(result["tool_calls"]) == 1
    assert result["tool_calls"][0]["id"] == "call_123"
    assert result["tool_calls"][0]["name"] == "http_request"
    assert json.loads(result["tool_calls"][0]["arguments"])["url"] == "https://example.com"


@pytest.mark.asyncio
async def test_chat_with_tools_no_tool_calls():
    """chat_with_tools 无 tool_calls 时返回空列表"""
    from core import llm

    mock_msg = MagicMock()
    mock_msg.content = "这是最终答案"
    mock_msg.tool_calls = None

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message = mock_msg
    mock_response.usage = None

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    with patch.object(llm, "get_async_client", return_value=mock_client):
        result = await llm.chat_with_tools(
            messages=[{"role": "user", "content": "test"}],
            tools=None,
        )

    assert result["content"] == "这是最终答案"
    assert result["tool_calls"] == []


@pytest.mark.asyncio
async def test_chat_with_tools_invokes_usage_callback():
    """chat_with_tools 在 API 返回 usage 时调用 usage_callback"""
    from core import llm

    mock_usage = MagicMock(prompt_tokens=100, completion_tokens=50, total_tokens=150)
    mock_msg = MagicMock()
    mock_msg.content = "ok"
    mock_msg.tool_calls = None

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message = mock_msg
    mock_response.usage = mock_usage

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    received = []
    with patch.object(llm, "get_async_client", return_value=mock_client):
        await llm.chat_with_tools(
            messages=[{"role": "user", "content": "test"}],
            usage_callback=lambda u: received.append(u),
        )

    assert len(received) == 1
    assert received[0]["total_tokens"] == 150


# ============ function_call.execute 测试 ============

@pytest.mark.asyncio
async def test_function_call_empty_prompt_returns_warning():
    """function_call.execute prompt 为空时返回警告"""
    from tools.function_call import execute

    ctx = MagicMock()
    result = await execute({"prompt": "", "tools": ["http_request"]}, ctx)

    assert result["answer"] == ""
    assert "warning" in result
    assert result["tool_calls_history"] == []


@pytest.mark.asyncio
async def test_function_call_no_tools_returns_warning():
    """function_call.execute 未选择工具时返回警告"""
    from tools.function_call import execute

    ctx = MagicMock()
    result = await execute({"prompt": "测试", "tools": []}, ctx)

    assert "warning" in result
    assert "未选择" in result["warning"]


@pytest.mark.asyncio
async def test_function_call_invalid_tools_returns_warning():
    """function_call.execute 所选工具均不存在时返回警告"""
    from tools.function_call import execute

    ctx = MagicMock()
    result = await execute({"prompt": "测试", "tools": ["nonexistent_xyz"]}, ctx)

    assert "warning" in result
    assert "不存在" in result["warning"]


@pytest.mark.asyncio
async def test_function_call_direct_answer_no_tool_calls():
    """LLM 第一轮就给出最终答案(无 tool_calls)→ iterations=0"""
    from tools import function_call

    ctx = MagicMock()
    ctx.add_token_usage = MagicMock()

    # mock chat_with_tools: 第一轮直接返回答案,无 tool_calls
    async def mock_chat_with_tools(**kwargs):
        return {"content": "直接答案", "tool_calls": []}

    with patch.object(function_call, "chat_with_tools", side_effect=mock_chat_with_tools):
        result = await function_call.execute(
            {"prompt": "1+1=?", "tools": ["http_request"], "max_iterations": 5},
            ctx,
        )

    assert result["answer"] == "直接答案"
    assert result["iterations"] == 0
    assert result["tool_calls_history"] == []


@pytest.mark.asyncio
async def test_function_call_executes_tool_then_answers():
    """LLM 第一轮调用工具,第二轮给出最终答案"""
    from tools import function_call

    ctx = MagicMock()
    ctx.add_token_usage = MagicMock()

    call_count = {"n": 0}

    async def mock_chat_with_tools(**kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            # 第一轮:LLM 决定调用 http_request
            return {
                "content": "",
                "tool_calls": [{
                    "id": "call_1",
                    "name": "http_request",
                    "arguments": '{"url": "https://api.example.com", "method": "GET"}',
                }],
            }
        else:
            # 第二轮:基于工具结果给出最终答案
            return {"content": "根据 API 返回,答案是 42", "tool_calls": []}

    # mock TOOL_EXECUTORS 中的 http_request
    mock_http = AsyncMock(return_value={"status_code": 200, "body": {"value": 42}})

    with patch.object(function_call, "chat_with_tools", side_effect=mock_chat_with_tools):
        with patch("tools.TOOL_EXECUTORS", {"http_request": mock_http}):
            result = await function_call.execute(
                {"prompt": "查询 API 获取答案", "tools": ["http_request"], "max_iterations": 5},
                ctx,
            )

    assert result["answer"] == "根据 API 返回,答案是 42"
    assert result["iterations"] == 1
    assert len(result["tool_calls_history"]) == 1
    assert result["tool_calls_history"][0]["tool"] == "http_request"
    assert result["tool_calls_history"][0]["result"]["body"]["value"] == 42
    # http_request 被调用了一次,参数正确
    mock_http.assert_called_once()
    called_args = mock_http.call_args[0][0]
    assert called_args["url"] == "https://api.example.com"


@pytest.mark.asyncio
async def test_function_call_tool_error_does_not_break_loop():
    """工具执行失败时回填错误信息,不中断循环"""
    from tools import function_call

    ctx = MagicMock()
    ctx.add_token_usage = MagicMock()

    call_count = {"n": 0}

    async def mock_chat_with_tools(**kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return {
                "content": "",
                "tool_calls": [{
                    "id": "call_1",
                    "name": "http_request",
                    "arguments": '{"url": "bad-url"}',
                }],
            }
        else:
            return {"content": "工具失败了,但我知道答案是 0", "tool_calls": []}

    # mock http_request 抛异常
    mock_http = AsyncMock(side_effect=Exception("连接超时"))

    with patch.object(function_call, "chat_with_tools", side_effect=mock_chat_with_tools):
        with patch("tools.TOOL_EXECUTORS", {"http_request": mock_http}):
            result = await function_call.execute(
                {"prompt": "查询", "tools": ["http_request"], "max_iterations": 5},
                ctx,
            )

    assert result["answer"] == "工具失败了,但我知道答案是 0"
    assert result["iterations"] == 1
    assert "error" in result["tool_calls_history"][0]


@pytest.mark.asyncio
async def test_function_call_max_iterations_cap():
    """达到 max_iterations 上限时返回警告 + 最佳答案"""
    from tools import function_call

    ctx = MagicMock()
    ctx.add_token_usage = MagicMock()

    # 每轮都返回 tool_calls,模拟无限循环,验证上限保护
    async def mock_chat_with_tools(**kwargs):
        tools_arg = kwargs.get("tools")
        if tools_arg is None:
            # 最后一轮无 tools 调用(达上限后的收尾)
            return {"content": "达上限后的答案", "tool_calls": []}
        return {
            "content": "",
            "tool_calls": [{
                "id": f"call_{kwargs['messages'][-1].get('content', 'x')[:5]}",
                "name": "http_request",
                "arguments": '{"url": "https://x.com"}',
            }],
        }

    mock_http = AsyncMock(return_value={"status_code": 200, "body": "ok"})

    with patch.object(function_call, "chat_with_tools", side_effect=mock_chat_with_tools):
        with patch("tools.TOOL_EXECUTORS", {"http_request": mock_http}):
            result = await function_call.execute(
                {"prompt": "无限循环测试", "tools": ["http_request"], "max_iterations": 3},
                ctx,
            )

    assert "warning" in result
    assert "3" in result["warning"]
    assert result["answer"] == "达上限后的答案"
    # 3 轮工具调用
    assert result["iterations"] == 3


@pytest.mark.asyncio
async def test_function_call_hard_limit_enforced():
    """用户设置 max_iterations=100 但硬上限为 10"""
    from tools import function_call

    assert function_call._MAX_ITERATIONS_HARD_LIMIT == 10

    ctx = MagicMock()
    ctx.add_token_usage = MagicMock()

    call_count = {"n": 0}

    async def mock_chat_with_tools(**kwargs):
        call_count["n"] += 1
        tools_arg = kwargs.get("tools")
        if tools_arg is None:
            return {"content": "最终答案", "tool_calls": []}
        return {
            "content": "",
            "tool_calls": [{
                "id": "call_x",
                "name": "http_request",
                "arguments": '{"url": "https://x.com"}',
            }],
        }

    mock_http = AsyncMock(return_value={"status_code": 200})

    with patch.object(function_call, "chat_with_tools", side_effect=mock_chat_with_tools):
        with patch("tools.TOOL_EXECUTORS", {"http_request": mock_http}):
            result = await function_call.execute(
                {"prompt": "测试", "tools": ["http_request"], "max_iterations": 100},
                ctx,
            )

    # 硬上限 10 次后停止
    assert result["iterations"] == 10
    assert "10" in result["warning"]


# ============ executor 委托测试 ============

@pytest.mark.asyncio
async def test_executor_delegates_llm_with_tools_to_function_call():
    """LLM 节点带 tools 参数时,executor 委托给 function_call"""
    from engine.executor import WorkflowExecutor

    delegated = {"called": False, "args": None}

    async def mock_function_call(params, context):
        delegated["called"] = True
        delegated["args"] = params
        return {"answer": "Agent 答案", "iterations": 1, "tool_calls_history": []}

    async def mock_llm_summary(params, context):
        # 如果被调用说明委托失败
        return {"summary": "不应被调用"}

    executor = WorkflowExecutor()
    executor.register_executor("llm_summary", mock_llm_summary)
    executor.register_executor("function_call", mock_function_call)

    steps = [{
        "id": "s1",
        "name": "LLM 带 Function Calling",
        "tool": "llm_summary",
        "params": {
            "text": "测试文本",
            "tools": ["http_request", "web_scraper"],
        },
    }]
    result = await executor.execute(steps, [], progress_callback=lambda e: None)

    assert result["status"] == "success"
    assert delegated["called"] is True
    assert result["steps_result"]["s1"]["output"]["answer"] == "Agent 答案"


@pytest.mark.asyncio
async def test_executor_llm_without_tools_not_delegated():
    """LLM 节点不带 tools 参数时,正常执行不走 function_call"""
    from engine.executor import WorkflowExecutor

    fc_called = {"v": False}
    llm_called = {"v": False}

    async def mock_function_call(params, context):
        fc_called["v"] = True
        return {"answer": "不应被调用"}

    async def mock_llm_summary(params, context):
        llm_called["v"] = True
        return {"summary": "正常摘要"}

    executor = WorkflowExecutor()
    executor.register_executor("llm_summary", mock_llm_summary)
    executor.register_executor("function_call", mock_function_call)

    steps = [{
        "id": "s1",
        "name": "普通 LLM 摘要",
        "tool": "llm_summary",
        "params": {"text": "测试文本"},  # 无 tools 参数
    }]
    result = await executor.execute(steps, [], progress_callback=lambda e: None)

    assert result["status"] == "success"
    assert llm_called["v"] is True
    assert fc_called["v"] is False
