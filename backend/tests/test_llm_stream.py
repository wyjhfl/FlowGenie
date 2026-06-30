"""B1: LLM 流式输出单元测试 - 验证 chat_stream/chat_with_streaming/executor token_callback"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ============ chat_stream 测试 ============

async def _mock_async_stream(chunks):
    """模拟 AsyncOpenAI 流式响应的异步迭代器(yield chunk 对象,供 chat_stream 测试)"""
    for chunk_text in chunks:
        chunk = MagicMock()
        chunk.choices = [MagicMock()]
        chunk.choices[0].delta.content = chunk_text
        yield chunk


async def _mock_string_stream(chunks):
    """模拟 chat_stream 直接 yield 字符串(供 chat_with_streaming 测试,mock chat_stream 本身)"""
    for c in chunks:
        yield c


@pytest.mark.asyncio
async def test_chat_stream_yields_all_deltas():
    """chat_stream 逐 token yield 所有增量文本"""
    from core import llm

    chunks = ["你好", "，", "世界", "！"]
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_async_stream(chunks)
    )

    with patch.object(llm, "get_async_client", return_value=mock_client):
        result = []
        async for delta in llm.chat_stream("sys", "user"):
            result.append(delta)

    assert result == chunks


@pytest.mark.asyncio
async def test_chat_stream_skips_empty_content():
    """chat_stream 跳过 delta.content 为 None 的 chunk(如首尾控制 chunk)"""
    from core import llm

    async def _stream():
        # 第一个 chunk 无 content(角色信息)
        c1 = MagicMock()
        c1.choices = [MagicMock()]
        c1.choices[0].delta.content = None
        yield c1
        # 第二个 chunk 有 content
        c2 = MagicMock()
        c2.choices = [MagicMock()]
        c2.choices[0].delta.content = "Hello"
        yield c2
        # 第三个 chunk 无 content(结束标记)
        c3 = MagicMock()
        c3.choices = [MagicMock()]
        c3.choices[0].delta.content = None
        yield c3

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=_stream())

    with patch.object(llm, "get_async_client", return_value=mock_client):
        result = []
        async for delta in llm.chat_stream("sys", "user"):
            result.append(delta)

    assert result == ["Hello"]


# ============ chat_with_streaming 测试 ============

@pytest.mark.asyncio
async def test_chat_with_streaming_no_callback_uses_sync():
    """无 token_callback 时走同步 _chat_async 路径"""
    from core import llm

    with patch.object(llm, "_chat_async", AsyncMock(return_value="同步结果")) as mock_sync:
        with patch.object(llm, "chat_stream") as mock_stream:
            result = await llm.chat_with_streaming("sys", "user", "", 0.3, token_callback=None)

    assert result == "同步结果"
    mock_sync.assert_called_once_with("sys", "user", "", 0.3, 2000, None)
    mock_stream.assert_not_called()


@pytest.mark.asyncio
async def test_chat_with_streaming_with_callback_uses_stream():
    """有 token_callback 时走流式 chat_stream 路径,逐 token 回调,返回聚合文本"""
    from core import llm

    chunks = ["Hello", " ", "World"]
    # chat_stream 是 async generator function,用 MagicMock 返回 yield 字符串的 async generator
    mock_stream = MagicMock(return_value=_mock_string_stream(chunks))

    received_deltas = []
    def cb(delta):
        received_deltas.append(delta)

    with patch.object(llm, "chat_stream", mock_stream):
        with patch.object(llm, "_chat_async") as mock_sync:
            result = await llm.chat_with_streaming("sys", "user", "", 0.3, token_callback=cb)

    assert result == "Hello World"
    assert received_deltas == chunks
    mock_sync.assert_not_called()


@pytest.mark.asyncio
async def test_chat_with_streaming_passes_model_and_temperature():
    """chat_with_streaming 正确传递 model 和 temperature 到底层调用"""
    from core import llm

    mock_stream = MagicMock(return_value=_mock_string_stream(["ok"]))

    with patch.object(llm, "chat_stream", mock_stream):
        await llm.chat_with_streaming(
            "sys", "user", model="gpt-4o", temperature=0.7,
            max_tokens=500, token_callback=lambda d: None,
        )

    mock_stream.assert_called_once_with("sys", "user", "gpt-4o", 0.7, 500, None)


# ============ executor token_callback 集成测试 ============

def _make_step(sid, tool="llm_summary", params=None, name=None):
    return {
        "id": sid,
        "name": name or f"步骤{sid}",
        "tool": tool,
        "params": params or {},
    }


@pytest.mark.asyncio
async def test_executor_stream_sets_token_callback():
    """stream=true 时 executor 设置 context.token_callback,工具可读取"""
    from engine.executor import WorkflowExecutor
    from engine.context import ExecutionContext

    captured_callback = {"cb": None}

    async def mock_llm_tool(params, context):
        # 工具读取 context.token_callback
        captured_callback["cb"] = getattr(context, "token_callback", None)
        cb = context.token_callback
        if cb:
            cb("delta1")
            cb("delta2")
        return {"summary": "完整摘要"}

    executor = WorkflowExecutor()
    executor.register_executor("llm_summary", mock_llm_tool)

    progress_events = []
    def progress_cb(progress):
        progress_events.append(progress)

    steps = [_make_step("s1", "llm_summary", {"text": "test", "stream": True})]
    result = await executor.execute(steps, [], progress_callback=progress_cb)

    # 工具确实收到了 token_callback
    assert captured_callback["cb"] is not None
    # progress_callback 收到了 step_token 事件
    token_events = [e for e in progress_events if e.get("type") == "step_token"]
    assert len(token_events) == 2
    assert token_events[0] == {"type": "step_token", "step_id": "s1", "delta": "delta1"}
    assert token_events[1] == {"type": "step_token", "step_id": "s1", "delta": "delta2"}
    # 步骤执行成功
    assert result["status"] == "success"
    assert result["steps_result"]["s1"]["output"]["summary"] == "完整摘要"


@pytest.mark.asyncio
async def test_executor_no_stream_no_token_callback():
    """stream=false 时 executor 不设置 context.token_callback"""
    from engine.executor import WorkflowExecutor

    captured_callback = {"cb": "SENTINEL"}

    async def mock_llm_tool(params, context):
        captured_callback["cb"] = getattr(context, "token_callback", None)
        return {"summary": "摘要"}

    executor = WorkflowExecutor()
    executor.register_executor("llm_summary", mock_llm_tool)

    steps = [_make_step("s1", "llm_summary", {"text": "test"})]  # 无 stream 参数
    result = await executor.execute(steps, [], progress_callback=lambda e: None)

    assert captured_callback["cb"] is None
    assert result["status"] == "success"


@pytest.mark.asyncio
async def test_executor_stream_cleans_up_callback_after_step():
    """流式步骤执行后 token_callback 被清理,不影响后续步骤"""
    from engine.executor import WorkflowExecutor
    from engine.context import ExecutionContext

    callbacks_during_execution = []

    async def mock_llm_tool(params, context):
        callbacks_during_execution.append(getattr(context, "token_callback", None))
        cb = context.token_callback
        if cb:
            cb("tok")
        return {"summary": "ok"}

    executor = WorkflowExecutor()
    executor.register_executor("llm_summary", mock_llm_tool)

    # 步骤1 stream=true,步骤2 stream=false
    steps = [
        _make_step("s1", "llm_summary", {"text": "test", "stream": True}),
        _make_step("s2", "llm_summary", {"text": "test"}),
    ]
    edges = [{"from": "s1", "to": "s2"}]
    result = await executor.execute(steps, edges, progress_callback=lambda e: None)

    # 步骤1 执行时有 callback,步骤2 执行时无 callback
    assert callbacks_during_execution[0] is not None
    assert callbacks_during_execution[1] is None
    assert result["status"] == "success"


@pytest.mark.asyncio
async def test_executor_stream_without_progress_callback_no_token_callback():
    """stream=true 但无 progress_callback 时,不设置 token_callback(无回调通道)"""
    from engine.executor import WorkflowExecutor

    captured_callback = {"cb": "SENTINEL"}

    async def mock_llm_tool(params, context):
        captured_callback["cb"] = getattr(context, "token_callback", None)
        return {"summary": "ok"}

    executor = WorkflowExecutor()
    executor.register_executor("llm_summary", mock_llm_tool)

    steps = [_make_step("s1", "llm_summary", {"text": "test", "stream": True})]
    # 不传 progress_callback
    result = await executor.execute(steps, [])

    assert captured_callback["cb"] is None
    assert result["status"] == "success"


# ============ context token_callback 属性测试 ============

def test_context_has_token_callback_attribute():
    """ExecutionContext 默认 token_callback 为 None"""
    from engine.context import ExecutionContext

    ctx = ExecutionContext()
    assert ctx.token_callback is None


def test_context_token_callback_settable():
    """ExecutionContext.token_callback 可设置和读取"""
    from engine.context import ExecutionContext

    ctx = ExecutionContext()
    received = []
    def cb(delta):
        received.append(delta)

    ctx.token_callback = cb
    ctx.token_callback("hello")
    assert received == ["hello"]


# ============ B4: token 用量统计测试 ============

def test_context_add_token_usage_accumulates():
    """B4: add_token_usage 正确累积多次 LLM 调用的 token 用量"""
    from engine.context import ExecutionContext

    ctx = ExecutionContext()
    # 初始状态全 0
    assert ctx.token_usage["total_tokens"] == 0
    assert ctx.token_usage["calls"] == 0
    assert ctx.token_usage["by_model"] == {}

    ctx.add_token_usage({"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150, "model": "gpt-4o"})
    ctx.add_token_usage({"prompt_tokens": 200, "completion_tokens": 80, "total_tokens": 280, "model": "gpt-4o"})
    ctx.add_token_usage({"prompt_tokens": 50, "completion_tokens": 30, "total_tokens": 80, "model": "agnes-flash"})

    assert ctx.token_usage["prompt_tokens"] == 350
    assert ctx.token_usage["completion_tokens"] == 160
    assert ctx.token_usage["total_tokens"] == 510
    assert ctx.token_usage["calls"] == 3
    # 按模型聚合
    assert ctx.token_usage["by_model"]["gpt-4o"]["total_tokens"] == 430
    assert ctx.token_usage["by_model"]["gpt-4o"]["calls"] == 2
    assert ctx.token_usage["by_model"]["agnes-flash"]["total_tokens"] == 80
    assert ctx.token_usage["by_model"]["agnes-flash"]["calls"] == 1


def test_context_add_token_usage_ignores_empty():
    """B4: add_token_usage 忽略空/None 用量"""
    from engine.context import ExecutionContext

    ctx = ExecutionContext()
    ctx.add_token_usage(None)
    ctx.add_token_usage({})
    assert ctx.token_usage["calls"] == 0
    assert ctx.token_usage["total_tokens"] == 0


@pytest.mark.asyncio
async def test_chat_usage_callback_invoked():
    """B4: chat() 在 API 返回 usage 时调用 usage_callback"""
    from core import llm

    mock_usage = MagicMock()
    mock_usage.prompt_tokens = 120
    mock_usage.completion_tokens = 60
    mock_usage.total_tokens = 180

    mock_response = MagicMock()
    mock_response.usage = mock_usage
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "回复"

    mock_client = MagicMock()
    mock_client.chat.completions.create = MagicMock(return_value=mock_response)

    received = []
    def cb(usage):
        received.append(usage)

    with patch.object(llm, "get_client", return_value=mock_client):
        result = llm.chat("sys", "user", usage_callback=cb)

    assert result == "回复"
    assert len(received) == 1
    assert received[0]["prompt_tokens"] == 120
    assert received[0]["completion_tokens"] == 60
    assert received[0]["total_tokens"] == 180
    assert received[0]["model"] == "agnes-2.0-flash"  # 默认模型


@pytest.mark.asyncio
async def test_chat_stream_usage_callback_from_last_chunk():
    """B4: chat_stream() 从最后一个 chunk 的 usage 上报 token 用量"""
    from core import llm

    async def _stream_with_usage():
        # 文本 chunk
        c1 = MagicMock()
        c1.choices = [MagicMock()]
        c1.choices[0].delta.content = "Hello"
        c1.usage = None
        yield c1
        # 末尾 usage chunk(choices 空,usage 有值)
        c2 = MagicMock()
        c2.choices = []
        c2.usage = MagicMock(prompt_tokens=50, completion_tokens=20, total_tokens=70)
        yield c2

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=_stream_with_usage())

    received = []
    with patch.object(llm, "get_async_client", return_value=mock_client):
        result = []
        async for delta in llm.chat_stream("sys", "user", usage_callback=lambda u: received.append(u)):
            result.append(delta)

    assert result == ["Hello"]
    assert len(received) == 1
    assert received[0]["total_tokens"] == 70
    assert received[0]["prompt_tokens"] == 50


@pytest.mark.asyncio
async def test_executor_result_includes_token_usage():
    """B4: executor.execute 返回结果包含 token_usage 字段(初始全 0)"""
    from engine.executor import WorkflowExecutor

    async def mock_tool(params, context):
        # 模拟 LLM 工具上报 token 用量
        if hasattr(context, "add_token_usage"):
            context.add_token_usage({"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150, "model": "gpt-4o"})
        return {"summary": "ok"}

    executor = WorkflowExecutor()
    executor.register_executor("llm_summary", mock_tool)

    steps = [_make_step("s1", "llm_summary", {"text": "test"})]
    result = await executor.execute(steps, [])

    assert "token_usage" in result
    assert result["token_usage"]["total_tokens"] == 150
    assert result["token_usage"]["calls"] == 1
    assert result["token_usage"]["by_model"]["gpt-4o"]["total_tokens"] == 150
