"""LLM 调用封装（OpenAI SDK 兼容）"""
import os
import json
import logging
from typing import AsyncGenerator, Callable, Optional
from openai import OpenAI, AsyncOpenAI
from dotenv import load_dotenv

try:
    from tenacity import (
        retry,
        stop_after_attempt,
        wait_exponential,
        retry_if_exception_type,
        before_sleep_log,
    )
    _HAS_TENACITY = True
except ImportError:
    _HAS_TENACITY = False

try:
    import openai
    # 瞬时错误:超时/限流/连接错误(重试有意义);不重试认证/请求格式错误
    _RETRYABLE = (
        openai.APITimeoutError,
        openai.RateLimitError,
        openai.APIConnectionError,
    )
except ImportError:
    _RETRYABLE = ()

load_dotenv()

logger = logging.getLogger(__name__)

# LLM 配置：支持任意 OpenAI 兼容 API
# 模块级常量作为默认值;get_client/chat 运行时读取 env,使凭证面板更新后立即生效
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://apihub.agnes-ai.com/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "agnes-2.0-flash")
# LLM 调用超时(秒);OpenAI SDK 默认 600s,会长期占用并发槽位
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "60"))
# C5: embedding 模型名(用于向量检索/RAG);空则用 LLM 兼容 API 的默认 embedding 模型
LLM_EMBEDDING_MODEL = os.getenv("LLM_EMBEDDING_MODEL", "text-embedding-3-small")

_client: Optional[OpenAI] = None
# 记录当前 client 使用的 api_key,凭证面板更新 env 后检测变化则重建 client
_client_api_key: str = ""

# 异步客户端单例(用于流式输出),同样支持热重建
_async_client: Optional[AsyncOpenAI] = None
_async_client_api_key: str = ""


def get_client() -> OpenAI:
    """获取 LLM 客户端单例(凭证面板更新 LLM_API_KEY/LLM_BASE_URL 后自动重建)"""
    global _client, _client_api_key
    api_key = os.getenv("LLM_API_KEY", "")
    base_url = os.getenv("LLM_BASE_URL", LLM_BASE_URL)
    if _client is None or _client_api_key != api_key:
        _client = OpenAI(api_key=api_key, base_url=base_url)
        _client_api_key = api_key
    return _client


def get_async_client() -> AsyncOpenAI:
    """获取异步 LLM 客户端单例(用于流式输出,凭证面板更新后自动重建)"""
    global _async_client, _async_client_api_key
    api_key = os.getenv("LLM_API_KEY", "")
    base_url = os.getenv("LLM_BASE_URL", LLM_BASE_URL)
    if _async_client is None or _async_client_api_key != api_key:
        _async_client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        _async_client_api_key = api_key
    return _async_client


def has_api_key() -> bool:
    """检查是否配置了 API Key(运行时读取 env,凭证面板更新后立即生效)"""
    return bool(os.getenv("LLM_API_KEY", ""))


def chat(
    system_prompt: str,
    user_prompt: str,
    model: str = "",
    temperature: float = 0.3,
    response_format_json: bool = False,
    max_tokens: int = 2000,
    usage_callback: Callable[[dict], None] | None = None,
) -> str:
    """
    调用 LLM 对话接口
    :param system_prompt: 系统提示词
    :param user_prompt: 用户提示词
    :param model: 模型名（空则用默认模型）
    :param temperature: 温度，越低越稳定
    :param response_format_json: 是否强制返回 JSON
    :param max_tokens: 最大生成 token 数
    :param usage_callback: B4 token 用量回调,接收 {prompt_tokens, completion_tokens, total_tokens, model}
    :return: 模型回复文本
    """
    client = get_client()
    use_model = model or os.getenv("LLM_MODEL", LLM_MODEL)
    kwargs = {
        "model": use_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if response_format_json:
        kwargs["response_format"] = {"type": "json_object"}

    # 设置超时,避免长尾请求长期占用并发槽位(运行时读取 env,凭证面板更新后生效)
    timeout = int(os.getenv("LLM_TIMEOUT", str(LLM_TIMEOUT)))
    kwargs.setdefault("timeout", timeout)

    response = _call_llm_with_retry(client, **kwargs)
    # B4: 提取 token 用量并通过回调上报(部分 OpenAI 兼容 API 可能不返回 usage)
    if usage_callback is not None and getattr(response, "usage", None) is not None:
        usage_callback({
            "prompt_tokens": getattr(response.usage, "prompt_tokens", 0) or 0,
            "completion_tokens": getattr(response.usage, "completion_tokens", 0) or 0,
            "total_tokens": getattr(response.usage, "total_tokens", 0) or 0,
            "model": use_model,
        })
    return response.choices[0].message.content or ""


async def chat_stream(
    system_prompt: str,
    user_prompt: str,
    model: str = "",
    temperature: float = 0.3,
    max_tokens: int = 2000,
    usage_callback: Callable[[dict], None] | None = None,
) -> AsyncGenerator[str, None]:
    """
    流式调用 LLM,逐 token yield 增量文本(B1 流式输出)
    :param system_prompt: 系统提示词
    :param user_prompt: 用户提示词
    :param model: 模型名（空则用默认模型）
    :param temperature: 温度
    :param max_tokens: 最大生成 token 数
    :param usage_callback: B4 token 用量回调,接收 {prompt_tokens, completion_tokens, total_tokens, model};
                            流式模式下需启用 stream_options.include_usage,usage 在最后一个 chunk 返回
    :yield: 增量文本片段(delta)
    """
    client = get_async_client()
    use_model = model or os.getenv("LLM_MODEL", LLM_MODEL)
    timeout = int(os.getenv("LLM_TIMEOUT", str(LLM_TIMEOUT)))
    # B4: 启用 stream_options.include_usage 以在流式末尾获取 token 用量
    # 部分 OpenAI 兼容 API 可能不支持此选项,usage 为 None 时不上报
    stream_kwargs: dict = {
        "model": use_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
        "timeout": timeout,
    }
    if usage_callback is not None:
        stream_kwargs["stream_options"] = {"include_usage": True}
    response = await client.chat.completions.create(**stream_kwargs)
    captured_usage = None
    async for chunk in response:
        # B4: 流式最后一个 chunk 可能携带 usage(choices 为空,usage 有值)
        if usage_callback is not None and getattr(chunk, "usage", None) is not None:
            captured_usage = chunk.usage
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content
    # B4: 流结束后上报 token 用量
    if usage_callback is not None and captured_usage is not None:
        usage_callback({
            "prompt_tokens": getattr(captured_usage, "prompt_tokens", 0) or 0,
            "completion_tokens": getattr(captured_usage, "completion_tokens", 0) or 0,
            "total_tokens": getattr(captured_usage, "total_tokens", 0) or 0,
            "model": use_model,
        })


async def chat_with_streaming(
    system_prompt: str,
    user_prompt: str,
    model: str = "",
    temperature: float = 0.3,
    max_tokens: int = 2000,
    token_callback: Callable[[str], None] | None = None,
    usage_callback: Callable[[dict], None] | None = None,
) -> str:
    """
    统一 LLM 调用入口:有 token_callback 时流式调用并逐 token 回调,无则同步调用。
    供 LLM 工具(llm_summary 等)使用,工具只需判断 context.token_callback 是否存在。
    :param token_callback: 流式 token 回调函数,每个 delta 调用一次;None 时走同步 chat()
    :param usage_callback: B4 token 用量回调,两种模式都会上报(若 API 返回 usage)
    :return: 完整回复文本
    """
    if token_callback is None:
        # 非流式:走原同步 chat()(放线程池由调用方处理)
        return await _chat_async(system_prompt, user_prompt, model, temperature, max_tokens, usage_callback)
    # 流式:调用 chat_stream,逐 token 回调,聚合完整文本
    full_text: list[str] = []
    async for delta in chat_stream(system_prompt, user_prompt, model, temperature, max_tokens, usage_callback):
        full_text.append(delta)
        token_callback(delta)
    return "".join(full_text)


async def _chat_async(
    system_prompt: str,
    user_prompt: str,
    model: str,
    temperature: float,
    max_tokens: int,
    usage_callback: Callable[[dict], None] | None = None,
) -> str:
    """异步包装同步 chat()——放线程池执行避免阻塞事件循环"""
    import asyncio
    return await asyncio.to_thread(
        chat, system_prompt, user_prompt, model, temperature, False, max_tokens, usage_callback
    )


async def chat_with_tools(
    messages: list[dict],
    tools: list[dict] | None = None,
    tool_choice: str = "auto",
    model: str = "",
    temperature: float = 0.3,
    max_tokens: int = 2000,
    usage_callback: Callable[[dict], None] | None = None,
) -> dict:
    """F1: 带 Function Calling 的 LLM 调用(异步,使用 AsyncOpenAI)

    :param messages: 消息列表 [{role, content} / {role, tool, content, tool_call_id}]
    :param tools: OpenAI function schema 列表(由 tool_registry.get_tool_schemas 生成)
    :param tool_choice: "auto"(默认)/"none"/指定函数
    :param model: 模型名,空则用默认
    :param temperature: 温度
    :param max_tokens: 最大生成 token 数
    :param usage_callback: B4 token 用量回调
    :return: {content: str, tool_calls: list[{id,name,arguments}], usage: dict|None}
    """
    client = get_async_client()
    use_model = model or os.getenv("LLM_MODEL", LLM_MODEL)
    timeout = int(os.getenv("LLM_TIMEOUT", str(LLM_TIMEOUT)))
    kwargs: dict = {
        "model": use_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "timeout": timeout,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = tool_choice

    response = await client.chat.completions.create(**kwargs)
    # B4: 提取 token 用量
    if usage_callback is not None and getattr(response, "usage", None) is not None:
        usage_callback({
            "prompt_tokens": getattr(response.usage, "prompt_tokens", 0) or 0,
            "completion_tokens": getattr(response.usage, "completion_tokens", 0) or 0,
            "total_tokens": getattr(response.usage, "total_tokens", 0) or 0,
            "model": use_model,
        })
    msg = response.choices[0].message
    # 解析 tool_calls(若有)
    tool_calls: list[dict] = []
    if getattr(msg, "tool_calls", None):
        for tc in msg.tool_calls:
            tool_calls.append({
                "id": tc.id,
                "name": tc.function.name,
                "arguments": tc.function.arguments,
            })
    return {
        "content": msg.content or "",
        "tool_calls": tool_calls,
    }


async def chat_with_session(
    session_id: str,
    user_message: str,
    system_prompt: str = "",
    model: str = "",
    temperature: float = 0.3,
    max_tokens: int = 2000,
    usage_callback: Callable[[dict], None] | None = None,
) -> dict:
    """F2: 带会话记忆的 LLM 调用(异步)

    从 DB 加载该 session_id 的历史消息,追加当前 user_message,调用 LLM,
    将 assistant 回复追加到历史并持久化。会话不存在时返回错误。

    :param session_id: 业务会话 ID(由 conversation_start 创建)
    :param user_message: 用户本轮输入
    :param system_prompt: 系统提示词(仅会话首次创建时使用;后续 continue 沿用会话内 system_prompt)
    :param model: 模型覆盖,空则用会话内记录的模型或默认模型
    :param temperature: 温度
    :param max_tokens: 最大生成 token 数
    :param usage_callback: B4 token 用量回调
    :return: {reply: str, session_id: str, message_count: int, warning?: str}
    """
    import asyncio
    from db.database import SessionLocal
    from db.models import ConversationSession
    from datetime import datetime, timezone, timedelta

    def _load_and_update_sync() -> dict:
        """同步加载会话、调用 LLM、持久化新消息(放线程池执行)"""
        db = SessionLocal()
        try:
            session = db.query(ConversationSession).filter(
                ConversationSession.session_id == session_id
            ).first()
            if session is None:
                return {"reply": "", "session_id": session_id, "message_count": 0,
                        "warning": f"会话不存在: {session_id}"}

            # 会话已过期:返回警告(由 scheduler 清理,这里不主动删除避免 race)
            now = datetime.now(timezone.utc)
            expires = session.expires_at
            if expires is not None:
                # SQLite 不保留时区信息,读取后为 naive datetime;统一转为 aware(UTC) 比较
                if expires.tzinfo is None:
                    expires = expires.replace(tzinfo=timezone.utc)
                if expires < now:
                    return {"reply": "", "session_id": session_id,
                            "message_count": len(session.get_messages()),
                            "warning": "会话已过期"}

            # 拼接消息:system(从会话记录)+ 历史 + 当前 user
            use_model = model or session.model or os.getenv("LLM_MODEL", LLM_MODEL)
            use_system = session.system_prompt or system_prompt or ""
            history = session.get_messages()
            messages: list[dict] = []
            if use_system:
                messages.append({"role": "system", "content": use_system})
            messages.extend(history)
            messages.append({"role": "user", "content": user_message})

            # chat() 内部固定拼 system+user 两条消息,无法直接传 messages 列表。
            # 此处改用底层 client 直接调用以支持完整 messages 列表(含历史)。
            client = get_client()
            timeout = int(os.getenv("LLM_TIMEOUT", str(LLM_TIMEOUT)))
            kwargs = {
                "model": use_model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "timeout": timeout,
            }
            response = _call_llm_with_retry(client, **kwargs)
            if usage_callback is not None and getattr(response, "usage", None) is not None:
                usage_callback({
                    "prompt_tokens": getattr(response.usage, "prompt_tokens", 0) or 0,
                    "completion_tokens": getattr(response.usage, "completion_tokens", 0) or 0,
                    "total_tokens": getattr(response.usage, "total_tokens", 0) or 0,
                    "model": use_model,
                })
            reply = response.choices[0].message.content or ""

            # 持久化新消息(追加 user + assistant)
            history.append({"role": "user", "content": user_message})
            history.append({"role": "assistant", "content": reply})
            session.set_messages(history)
            session.updated_at = now
            # 续期:每次活动延长 7 天过期
            session.expires_at = now + timedelta(days=7)
            db.commit()

            return {
                "reply": reply,
                "session_id": session_id,
                "message_count": len(history),
            }
        finally:
            db.close()

    return await asyncio.to_thread(_load_and_update_sync)


def _call_llm_with_retry(client: OpenAI, **kwargs):
    """带 tenacity 重试的 LLM 调用。
    仅对瞬时错误(超时/限流/连接)重试 3 次,指数退避 2-10s;
    认证/请求格式错误立即失败(重试无意义)。
    tenacity 未安装时降级为单次调用。
    """
    if not _HAS_TENACITY or not _RETRYABLE:
        return client.chat.completions.create(**kwargs)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(_RETRYABLE),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def _call():
        return client.chat.completions.create(**kwargs)

    return _call()


def chat_json(
    system_prompt: str,
    user_prompt: str,
    model: str = "",
    temperature: float = 0.3,
    max_tokens: int = 2000,
) -> dict:
    """
    调用 LLM 并解析为 JSON 字典
    :param max_tokens: 最大生成 token 数
    :return: 解析后的字典，失败时返回空字典
    """
    content = chat(system_prompt, user_prompt, model, temperature, response_format_json=True, max_tokens=max_tokens)
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # 兜底：尝试从文本中提取 JSON
        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(content[start:end])
            except json.JSONDecodeError:
                pass
        return {}


def embed(
    texts: list[str],
    model: str = "",
    usage_callback: Callable[[dict], None] | None = None,
) -> list[list[float]]:
    """C5: 调用 LLM 兼容 /v1/embeddings 接口,将文本批量向量化

    :param texts: 待向量化的文本列表(单次上限 100 条,超长自动截断)
    :param model: embedding 模型名,空则用 env LLM_EMBEDDING_MODEL
    :param usage_callback: B4 token 用量回调(若 API 返回 usage)
    :return: 向量列表 [[float, ...], ...],顺序与 texts 一致;失败抛 RuntimeError
    """
    if not texts:
        return []
    # 单次上限 100 条,避免请求体过大
    texts = list(texts)[:100]
    # 截断超长文本(单条 > 8000 字符截断,避免 token 爆炸)
    texts = [t[:8000] if isinstance(t, str) else str(t) for t in texts]

    client = get_client()
    use_model = model or os.getenv("LLM_EMBEDDING_MODEL", LLM_EMBEDDING_MODEL)
    timeout = int(os.getenv("LLM_TIMEOUT", str(LLM_TIMEOUT)))

    response = client.embeddings.create(
        model=use_model,
        input=texts,
        timeout=timeout,
    )
    # B4: 上报 token 用量(embedding API 同样返回 usage)
    if usage_callback is not None and getattr(response, "usage", None) is not None:
        usage_callback({
            "prompt_tokens": getattr(response.usage, "prompt_tokens", 0) or 0,
            "completion_tokens": 0,  # embedding 无 completion
            "total_tokens": getattr(response.usage, "total_tokens", 0) or 0,
            "model": use_model,
        })
    # 按 index 排序确保顺序与输入一致(API 保证但显式排序更稳健)
    sorted_data = sorted(response.data, key=lambda d: getattr(d, "index", 0))
    return [list(d.embedding) for d in sorted_data]
