"""F2: 多轮对话 / 会话记忆工具

提供三个会话管理工具,供工作流节点使用:
- conversation_start: 创建新会话(设定 system_prompt,可选指定 session_id)
- conversation_continue: 向会话追加用户消息并获取 LLM 回复(自动持久化历史)
- conversation_list: 查看会话历史消息

会话过期策略:默认 7 天,每次 continue 续期 7 天;scheduler 每日 3:00 清理过期会话。
"""
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Any

from db.database import SessionLocal
from db.models import ConversationSession
from core.llm import chat_with_session

logger = logging.getLogger(__name__)

# 会话默认过期天数
_DEFAULT_EXPIRE_DAYS = 7


async def execute(params: dict, context: Any) -> dict:
    """会话管理工具统一入口(按 action 分派)

    :param params: {action: "start"|"continue"|"list", ...}
    :param context: ExecutionContext(提供 add_token_usage 等)
    :return: 工具输出 dict
    """
    action = params.get("action", "")

    if action == "start":
        return await _start(params, context)
    if action == "continue":
        return await _continue(params, context)
    if action == "list":
        return await _list(params, context)

    return {
        "warning": f"未知 action: {action}(支持 start / continue / list)",
        "session_id": "",
        "messages": [],
        "message_count": 0,
    }


# 各工具的独立执行器(executor 通过 tool_name 查找,需各自独立的入口函数)
async def execute_start(params: dict, context: Any) -> dict:
    """conversation_start 工具执行器"""
    return await _start(params, context)


async def execute_continue(params: dict, context: Any) -> dict:
    """conversation_continue 工具执行器"""
    return await _continue(params, context)


async def execute_list(params: dict, context: Any) -> dict:
    """conversation_list 工具执行器"""
    return await _list(params, context)


async def _start(params: dict, context: Any) -> dict:
    """创建新会话

    :param params: {system_prompt, session_id?, model?}
    :return: {session_id, message_count, created_at}
    """
    system_prompt = params.get("system_prompt", "")
    # 业务 session_id 可由用户指定;缺省自动生成 UUID(取前 8 位便于显示)
    session_id = params.get("session_id", "") or f"sess_{uuid.uuid4().hex[:8]}"
    model = params.get("model", "")

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=_DEFAULT_EXPIRE_DAYS)

    db = SessionLocal()
    try:
        # 检查 session_id 是否已存在(避免重复创建覆盖旧会话)
        existing = db.query(ConversationSession).filter(
            ConversationSession.session_id == session_id
        ).first()
        if existing is not None:
            return {
                "warning": f"会话已存在: {session_id}(请使用 continue 续聊或更换 session_id)",
                "session_id": session_id,
                "message_count": len(existing.get_messages()),
                "created_at": existing.created_at.isoformat() if existing.created_at else None,
            }

        session = ConversationSession(
            session_id=session_id,
            system_prompt=system_prompt,
            messages_json="[]",
            model=model,
            created_at=now,
            updated_at=now,
            expires_at=expires_at,
        )
        db.add(session)
        db.commit()
        db.refresh(session)

        logger.info(f"创建会话: {session_id}")

        return {
            "session_id": session_id,
            "message_count": 0,
            "created_at": session.created_at.isoformat() if session.created_at else None,
            "expires_at": session.expires_at.isoformat() if session.expires_at else None,
        }
    finally:
        db.close()


async def _continue(params: dict, context: Any) -> dict:
    """向会话追加用户消息并获取 LLM 回复

    :param params: {session_id, user_message, model?, temperature?, max_tokens?}
    :return: {reply, session_id, message_count, warning?}
    """
    session_id = params.get("session_id", "")
    user_message = params.get("user_message", "")

    if not session_id:
        return {"reply": "", "session_id": "", "message_count": 0,
                "warning": "session_id 不能为空"}
    if not user_message:
        return {"reply": "", "session_id": session_id, "message_count": 0,
                "warning": "user_message 不能为空"}

    model = params.get("model", "")
    try:
        temperature = float(params.get("temperature", 0.3))
    except (TypeError, ValueError):
        temperature = 0.3
    try:
        max_tokens = int(params.get("max_tokens", 2000))
    except (TypeError, ValueError):
        max_tokens = 2000

    usage_cb = getattr(context, "add_token_usage", None)

    result = await chat_with_session(
        session_id=session_id,
        user_message=user_message,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        usage_callback=usage_cb,
    )
    return result


async def _list(params: dict, context: Any) -> dict:
    """查看会话历史消息

    :param params: {session_id}
    :return: {session_id, messages, message_count, warning?}
    """
    session_id = params.get("session_id", "")
    if not session_id:
        return {"session_id": "", "messages": [], "message_count": 0,
                "warning": "session_id 不能为空"}

    db = SessionLocal()
    try:
        session = db.query(ConversationSession).filter(
            ConversationSession.session_id == session_id
        ).first()
        if session is None:
            return {"session_id": session_id, "messages": [], "message_count": 0,
                    "warning": f"会话不存在: {session_id}"}

        messages = session.get_messages()
        return {
            "session_id": session_id,
            "messages": messages,
            "message_count": len(messages),
            "system_prompt": session.system_prompt,
            "updated_at": session.updated_at.isoformat() if session.updated_at else None,
        }
    finally:
        db.close()
