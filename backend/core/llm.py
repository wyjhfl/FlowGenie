"""LLM 调用封装（OpenAI SDK 兼容）"""
import os
import json
from typing import Optional
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# LLM 配置：支持任意 OpenAI 兼容 API
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://apihub.agnes-ai.com/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "agnes-2.0-flash")

_client: Optional[OpenAI] = None


def get_client() -> OpenAI:
    """获取 LLM 客户端单例"""
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=LLM_API_KEY,
            base_url=LLM_BASE_URL,
        )
    return _client


def has_api_key() -> bool:
    """检查是否配置了 API Key"""
    return bool(LLM_API_KEY)


def chat(
    system_prompt: str,
    user_prompt: str,
    model: str = "",
    temperature: float = 0.3,
    response_format_json: bool = False,
) -> str:
    """
    调用 LLM 对话接口
    :param system_prompt: 系统提示词
    :param user_prompt: 用户提示词
    :param model: 模型名（空则用默认模型）
    :param temperature: 温度，越低越稳定
    :param response_format_json: 是否强制返回 JSON
    :return: 模型回复文本
    """
    client = get_client()
    use_model = model or LLM_MODEL
    kwargs = {
        "model": use_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": 2000,
    }
    if response_format_json:
        kwargs["response_format"] = {"type": "json_object"}

    response = client.chat.completions.create(**kwargs)
    return response.choices[0].message.content or ""


def chat_json(
    system_prompt: str,
    user_prompt: str,
    model: str = "",
    temperature: float = 0.3,
) -> dict:
    """
    调用 LLM 并解析为 JSON 字典
    :return: 解析后的字典，失败时返回空字典
    """
    content = chat(system_prompt, user_prompt, model, temperature, response_format_json=True)
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
