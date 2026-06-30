"""Telegram Bot 推送工具"""
import os
import httpx
from core.ssrf_guard import validate_url


async def execute(params: dict, context) -> dict:
    """
    通过 Telegram Bot API 发送消息
    params:
      chat_id: str - 目标聊天 ID
      text: str - 消息内容
      parse_mode: str - 解析模式（text/markdown/HTML），默认 text
    """
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        raise ValueError("Telegram Bot Token 未配置，请在凭证面板中设置")

    chat_id = params.get("chat_id")
    text = params.get("text")
    if not chat_id:
        raise ValueError("chat_id 参数不能为空")

    # 空数据容错：空内容跳过发送，返回有意义的空结果
    if not text:
        return {"message_id": 0, "chat_id": str(chat_id), "date": 0}

    # text 可能是变量插值后的对象，转为字符串
    if not isinstance(text, str):
        import json
        text = json.dumps(text, ensure_ascii=False, default=str)

    parse_mode = params.get("parse_mode", "text")
    parse_mode_map = {"text": None, "markdown": "Markdown", "html": "HTML"}

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    # SSRF 防护:校验请求 URL 协议与目标 IP
    await validate_url(url)

    payload = {
        "chat_id": chat_id,
        "text": text,
    }
    tg_parse_mode = parse_mode_map.get(parse_mode)
    if tg_parse_mode:
        payload["parse_mode"] = tg_parse_mode

    async with httpx.AsyncClient(timeout=10) as client:
        try:
            response = await client.post(url, json=payload)
            result = response.json()
            if isinstance(result, dict) and result.get("ok"):
                return {
                    "message_id": result["result"]["message_id"],
                    "chat_id": str(chat_id),
                    "date": result["result"].get("date", 0),
                }
            else:
                error_desc = result.get("description", "未知错误") if isinstance(result, dict) else response.text
                raise RuntimeError(f"Telegram API 错误: {error_desc}")
        except httpx.HTTPError as e:
            raise RuntimeError(f"请求失败: {e}")
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"解析响应失败: {e}")
