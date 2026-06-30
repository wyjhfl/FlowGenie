"""F2: 多轮对话 / 会话记忆单元测试

验证:
- conversation_start: 创建会话(自定义/自动 session_id、重复创建返回警告)
- conversation_continue: 追加消息、持久化历史、usage_callback、不存在/过期会话兜底
- conversation_list: 查看历史、不存在会话兜底
- chat_with_session: 底层 LLM 调用与消息持久化
- _cleanup_expired_conversations: 清理过期会话
- executor 路由 conversation_* 工具到对应执行器
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta

from db.models import ConversationSession
from db.database import SessionLocal


# ============ conversation_start 测试 ============

@pytest.mark.asyncio
async def test_conversation_start_creates_session_with_auto_id(test_db):
    """conversation_start 自动生成 session_id 并创建会话"""
    from tools.conversation import execute_start

    # 覆盖 SessionLocal 为测试 session
    with patch("tools.conversation.SessionLocal", return_value=test_db):
        result = await execute_start(
            {"system_prompt": "你是客服助手"},
            context=None,
        )

    assert "session_id" in result
    assert result["session_id"].startswith("sess_")
    assert result["message_count"] == 0
    assert "created_at" in result
    assert "expires_at" in result

    # 验证持久化
    session = test_db.query(ConversationSession).filter(
        ConversationSession.session_id == result["session_id"]
    ).first()
    assert session is not None
    assert session.system_prompt == "你是客服助手"
    assert session.get_messages() == []


@pytest.mark.asyncio
async def test_conversation_start_with_custom_session_id(test_db):
    """conversation_start 支持自定义 session_id"""
    from tools.conversation import execute_start

    with patch("tools.conversation.SessionLocal", return_value=test_db):
        result = await execute_start(
            {"system_prompt": "你是助手", "session_id": "customer_123"},
            context=None,
        )

    assert result["session_id"] == "customer_123"
    assert result["message_count"] == 0


@pytest.mark.asyncio
async def test_conversation_start_duplicate_returns_warning(test_db):
    """conversation_start 对已存在的 session_id 返回警告(不覆盖)"""
    from tools.conversation import execute_start

    with patch("tools.conversation.SessionLocal", return_value=test_db):
        # 第一次创建
        await execute_start(
            {"system_prompt": "你是助手", "session_id": "dup_001"},
            context=None,
        )
        # 第二次创建(重复)
        result = await execute_start(
            {"system_prompt": "你是助手", "session_id": "dup_001"},
            context=None,
        )

    assert "warning" in result
    assert "已存在" in result["warning"]
    assert result["session_id"] == "dup_001"


# ============ conversation_continue 测试 ============

@pytest.mark.asyncio
async def test_conversation_continue_appends_and_persists(test_db):
    """conversation_continue 追加 user/assistant 消息并持久化"""
    from tools.conversation import execute_start, execute_continue
    from core import llm

    # 先创建会话
    with patch("tools.conversation.SessionLocal", return_value=test_db):
        start_result = await execute_start(
            {"system_prompt": "你是助手", "session_id": "sess_persist"},
            context=None,
        )
    sid = start_result["session_id"]

    # mock LLM 客户端,让 chat_with_session 完整运行(加载历史→调用 LLM→持久化)
    mock_msg = MagicMock()
    mock_msg.content = "你好,有什么可以帮你?"
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message = mock_msg
    mock_response.usage = None

    mock_client = MagicMock()
    mock_client.chat.completions.create = MagicMock(return_value=mock_response)

    # 同时 patch tools.conversation 和 core.llm 的 SessionLocal 引用
    with patch("tools.conversation.SessionLocal", return_value=test_db), \
         patch("db.database.SessionLocal", return_value=test_db), \
         patch.object(llm, "get_client", return_value=mock_client):
        result = await execute_continue(
            {"session_id": sid, "user_message": "你好"},
            context=None,
        )

    assert result["reply"] == "你好,有什么可以帮你?"
    assert result["session_id"] == sid
    assert result["message_count"] == 2

    # 验证持久化
    session = test_db.query(ConversationSession).filter(
        ConversationSession.session_id == sid
    ).first()
    messages = session.get_messages()
    assert len(messages) == 2
    assert messages[0] == {"role": "user", "content": "你好"}
    assert messages[1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_conversation_continue_nonexistent_returns_warning():
    """conversation_continue 对不存在的会话返回警告(chat_with_session 兜底)"""
    from tools.conversation import execute_continue

    # mock chat_with_session 返回会话不存在警告
    with patch("tools.conversation.chat_with_session",
               return_value={"reply": "", "session_id": "nonexistent",
                             "message_count": 0, "warning": "会话不存在: nonexistent"}):
        result = await execute_continue(
            {"session_id": "nonexistent", "user_message": "你好"},
            context=None,
        )

    assert "warning" in result
    assert "不存在" in result["warning"]


@pytest.mark.asyncio
async def test_conversation_continue_empty_session_id_returns_warning():
    """conversation_continue 空 session_id 返回警告(不调用 LLM)"""
    from tools.conversation import execute_continue

    result = await execute_continue(
        {"session_id": "", "user_message": "你好"},
        context=None,
    )

    assert "warning" in result
    assert "session_id" in result["warning"]


@pytest.mark.asyncio
async def test_conversation_continue_empty_message_returns_warning():
    """conversation_continue 空 user_message 返回警告(不调用 LLM)"""
    from tools.conversation import execute_continue

    result = await execute_continue(
        {"session_id": "sess_x", "user_message": ""},
        context=None,
    )

    assert "warning" in result
    assert "user_message" in result["warning"]


# ============ conversation_list 测试 ============

@pytest.mark.asyncio
async def test_conversation_list_returns_messages(test_db):
    """conversation_list 返回会话历史消息"""
    from tools.conversation import execute_start, execute_list

    # 创建会话并手动写入消息
    with patch("tools.conversation.SessionLocal", return_value=test_db):
        start_result = await execute_start(
            {"system_prompt": "你是助手", "session_id": "sess_list"},
            context=None,
        )
    sid = start_result["session_id"]

    session = test_db.query(ConversationSession).filter(
        ConversationSession.session_id == sid
    ).first()
    session.set_messages([
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好,有什么可以帮你?"},
    ])
    test_db.commit()

    with patch("tools.conversation.SessionLocal", return_value=test_db):
        result = await execute_list({"session_id": sid}, context=None)

    assert result["session_id"] == sid
    assert result["message_count"] == 2
    assert len(result["messages"]) == 2
    assert result["system_prompt"] == "你是助手"


@pytest.mark.asyncio
async def test_conversation_list_nonexistent_returns_warning(test_db):
    """conversation_list 不存在的会话返回警告"""
    from tools.conversation import execute_list

    with patch("tools.conversation.SessionLocal", return_value=test_db):
        result = await execute_list({"session_id": "nonexistent"}, context=None)

    assert "warning" in result
    assert "不存在" in result["warning"]
    assert result["messages"] == []


@pytest.mark.asyncio
async def test_conversation_list_empty_session_id_returns_warning():
    """conversation_list 空 session_id 返回警告"""
    from tools.conversation import execute_list

    result = await execute_list({"session_id": ""}, context=None)

    assert "warning" in result
    assert "session_id" in result["warning"]


# ============ 统一入口 execute(action 分派)测试 ============

@pytest.mark.asyncio
async def test_conversation_execute_unknown_action_returns_warning():
    """execute 统一入口对未知 action 返回警告"""
    from tools.conversation import execute

    result = await execute({"action": "invalid"}, context=None)

    assert "warning" in result
    assert "未知 action" in result["warning"]


# ============ chat_with_session 测试 ============

@pytest.mark.asyncio
async def test_chat_with_session_nonexistent_returns_warning(test_db):
    """chat_with_session 对不存在的会话返回警告"""
    from core import llm

    # chat_with_session 内部 from db.database import SessionLocal,需 patch 源
    with patch("db.database.SessionLocal", return_value=test_db):
        result = await llm.chat_with_session(
            session_id="nonexistent_session",
            user_message="你好",
        )

    assert result["reply"] == ""
    assert "warning" in result
    assert "不存在" in result["warning"]


@pytest.mark.asyncio
async def test_chat_with_session_expired_returns_warning(test_db):
    """chat_with_session 对已过期会话返回警告"""
    from core import llm

    # 创建一个已过期的会话
    now = datetime.now(timezone.utc)
    session = ConversationSession(
        session_id="sess_expired",
        system_prompt="你是助手",
        messages_json="[]",
        model="",
        created_at=now - timedelta(days=10),
        updated_at=now - timedelta(days=10),
        expires_at=now - timedelta(days=1),  # 已过期
    )
    test_db.add(session)
    test_db.commit()

    with patch("db.database.SessionLocal", return_value=test_db):
        result = await llm.chat_with_session(
            session_id="sess_expired",
            user_message="你好",
        )

    assert result["reply"] == ""
    assert "warning" in result
    assert "过期" in result["warning"]


@pytest.mark.asyncio
async def test_chat_with_session_appends_and_renews_expiry(test_db):
    """chat_with_session 追加消息并续期过期时间"""
    from core import llm

    # 创建会话
    now = datetime.now(timezone.utc)
    session = ConversationSession(
        session_id="sess_renew",
        system_prompt="你是助手",
        messages_json="[]",
        model="",
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(days=1),  # 1 天后过期
    )
    test_db.add(session)
    test_db.commit()

    # mock LLM 客户端
    mock_msg = MagicMock()
    mock_msg.content = "你好,我是助手"
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message = mock_msg
    mock_response.usage = None

    mock_client = MagicMock()
    mock_client.chat.completions.create = MagicMock(return_value=mock_response)

    original_expires = session.expires_at
    with patch("db.database.SessionLocal", return_value=test_db), \
         patch.object(llm, "get_client", return_value=mock_client):
        result = await llm.chat_with_session(
            session_id="sess_renew",
            user_message="你好",
        )

    assert result["reply"] == "你好,我是助手"
    assert result["message_count"] == 2  # user + assistant

    # 验证持久化与续期
    test_db.expire_all()
    updated = test_db.query(ConversationSession).filter(
        ConversationSession.session_id == "sess_renew"
    ).first()
    assert len(updated.get_messages()) == 2
    # 续期后过期时间应晚于原过期时间
    assert updated.expires_at > original_expires


@pytest.mark.asyncio
async def test_chat_with_session_invokes_usage_callback(test_db):
    """chat_with_session 在 API 返回 usage 时调用 usage_callback"""
    from core import llm

    now = datetime.now(timezone.utc)
    session = ConversationSession(
        session_id="sess_usage",
        system_prompt="你是助手",
        messages_json="[]",
        model="",
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(days=7),
    )
    test_db.add(session)
    test_db.commit()

    mock_usage = MagicMock(prompt_tokens=80, completion_tokens=20, total_tokens=100)
    mock_msg = MagicMock()
    mock_msg.content = "ok"
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message = mock_msg
    mock_response.usage = mock_usage

    mock_client = MagicMock()
    mock_client.chat.completions.create = MagicMock(return_value=mock_response)

    received = []
    with patch("db.database.SessionLocal", return_value=test_db), \
         patch.object(llm, "get_client", return_value=mock_client):
        await llm.chat_with_session(
            session_id="sess_usage",
            user_message="你好",
            usage_callback=lambda u: received.append(u),
        )

    assert len(received) == 1
    assert received[0]["total_tokens"] == 100


# ============ 清理过期会话测试 ============

@pytest.mark.asyncio
async def test_cleanup_expired_conversations_deletes_expired(test_db):
    """_cleanup_expired_conversations 删除过期会话,保留未过期会话"""
    from scheduler.manager import _cleanup_expired_conversations

    now = datetime.now(timezone.utc)
    # 过期会话
    expired1 = ConversationSession(
        session_id="sess_expired1",
        system_prompt="", messages_json="[]", model="",
        created_at=now - timedelta(days=10), updated_at=now - timedelta(days=10),
        expires_at=now - timedelta(days=1),
    )
    expired2 = ConversationSession(
        session_id="sess_expired2",
        system_prompt="", messages_json="[]", model="",
        created_at=now - timedelta(days=10), updated_at=now - timedelta(days=10),
        expires_at=now - timedelta(hours=1),
    )
    # 未过期会话
    active = ConversationSession(
        session_id="sess_active",
        system_prompt="", messages_json="[]", model="",
        created_at=now, updated_at=now,
        expires_at=now + timedelta(days=7),
    )
    test_db.add_all([expired1, expired2, active])
    test_db.commit()

    with patch("scheduler.manager.SessionLocal", return_value=test_db):
        _cleanup_expired_conversations()

    test_db.expire_all()
    remaining = test_db.query(ConversationSession).all()
    remaining_ids = {s.session_id for s in remaining}
    assert remaining_ids == {"sess_active"}


@pytest.mark.asyncio
async def test_cleanup_expired_conversations_no_expired(test_db):
    """_cleanup_expired_conversations 无过期会话时不删除任何记录"""
    from scheduler.manager import _cleanup_expired_conversations

    now = datetime.now(timezone.utc)
    active = ConversationSession(
        session_id="sess_active_only",
        system_prompt="", messages_json="[]", model="",
        created_at=now, updated_at=now,
        expires_at=now + timedelta(days=7),
    )
    test_db.add(active)
    test_db.commit()

    with patch("scheduler.manager.SessionLocal", return_value=test_db):
        _cleanup_expired_conversations()

    test_db.expire_all()
    remaining = test_db.query(ConversationSession).all()
    assert len(remaining) == 1
    assert remaining[0].session_id == "sess_active_only"


# ============ executor 路由测试 ============

@pytest.mark.asyncio
async def test_executor_routes_conversation_start(test_db):
    """executor 将 conversation_start 工具路由到 conversation_start_execute"""
    from tools import TOOL_EXECUTORS

    assert "conversation_start" in TOOL_EXECUTORS
    assert "conversation_continue" in TOOL_EXECUTORS
    assert "conversation_list" in TOOL_EXECUTORS
    # 三个工具应是不同的执行器函数
    assert TOOL_EXECUTORS["conversation_start"] is not TOOL_EXECUTORS["conversation_continue"]
    assert TOOL_EXECUTORS["conversation_start"] is not TOOL_EXECUTORS["conversation_list"]


@pytest.mark.asyncio
async def test_executor_calls_conversation_continue(test_db):
    """executor 完整路由:conversation_continue → execute_continue → chat_with_session"""
    from engine.executor import WorkflowExecutor
    from tools.conversation import execute_start

    # 先创建会话
    with patch("tools.conversation.SessionLocal", return_value=test_db):
        start_result = await execute_start(
            {"system_prompt": "你是助手", "session_id": "sess_route"},
            context=None,
        )
    sid = start_result["session_id"]

    executor = WorkflowExecutor()
    # 注册所有工具执行器
    from tools import TOOL_EXECUTORS
    for name, func in TOOL_EXECUTORS.items():
        executor.register_executor(name, func)

    # mock chat_with_session 避免真实 LLM 调用
    with patch("tools.conversation.chat_with_session",
               return_value={"reply": "mock 回复", "session_id": sid, "message_count": 2}):
        # 直接调用执行器(绕过完整工作流,聚焦工具路由)
        result = await executor.tool_executors["conversation_continue"](
            {"session_id": sid, "user_message": "你好"},
            context=None,
        )

    assert result["reply"] == "mock 回复"
    assert result["session_id"] == sid
    assert result["message_count"] == 2


# ============ tool_registry 注册验证 ============

def test_conversation_tools_registered():
    """conversation_start/continue/list 三个工具已在 TOOL_REGISTRY 注册"""
    from core.tool_registry import get_tool, get_all_tools

    tool_names = {t["name"] for t in get_all_tools()}
    assert "conversation_start" in tool_names
    assert "conversation_continue" in tool_names
    assert "conversation_list" in tool_names

    # 验证工具元数据
    start = get_tool("conversation_start")
    assert start is not None
    assert start.category == "AI 处理"
    assert "system_prompt" in start.params_schema
    assert "system_prompt" in start.required

    continue_tool = get_tool("conversation_continue")
    assert continue_tool is not None
    assert "session_id" in continue_tool.required
    assert "user_message" in continue_tool.required

    list_tool = get_tool("conversation_list")
    assert list_tool is not None
    assert "session_id" in list_tool.required


def test_conversation_tool_schema_generated():
    """get_tool_schema 能为 conversation_continue 生成 OpenAI function schema"""
    from core.tool_registry import get_tool_schema

    schema = get_tool_schema("conversation_continue")
    assert schema is not None
    assert schema["function"]["name"] == "conversation_continue"
    props = schema["function"]["parameters"]["properties"]
    assert "session_id" in props
    assert "user_message" in props
    assert props["session_id"]["type"] == "string"
    # temperature 是 float → number
    assert props["temperature"]["type"] == "number"
    # max_tokens 是 int → number
    assert props["max_tokens"]["type"] == "number"
