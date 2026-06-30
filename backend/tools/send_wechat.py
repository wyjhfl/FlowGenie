"""企业微信推送工具 - Webhook"""
import os
import json
import httpx
from core.ssrf_guard import validate_url


async def execute(params: dict, context) -> dict:
    """
    企业微信机器人推送
    :param params: { webhook_url, content, msg_type }
    :return: { success, response }
    """
    webhook_url = params.get("webhook_url", "") or os.getenv("WECHAT_WEBHOOK", "") or os.getenv("WECHAT_WEBHOOK_URL", "")
    content = params.get("content", params.get("message", ""))
    msg_type = params.get("msg_type", "markdown")

    if not webhook_url:
        raise ValueError("企业微信 Webhook 未配置，请在凭证面板配置 WECHAT_WEBHOOK")

    # 空数据容错：空内容跳过发送，返回有意义的空结果
    if not content:
        return {"success": False, "response": {}}

    # SSRF 防护:校验 webhook URL 协议与目标 IP
    await validate_url(webhook_url)

    # content 可能是变量插值后的对象，转为字符串
    if not isinstance(content, str):
        content = json.dumps(content, ensure_ascii=False, default=str)

    # 构建企业微信消息体
    if msg_type == "markdown":
        payload = {
            "msgtype": "markdown",
            "markdown": {"content": content},
        }
    elif msg_type == "text":
        payload = {
            "msgtype": "text",
            "text": {"content": content},
        }
    else:
        payload = {
            "msgtype": "text",
            "text": {"content": content},
        }

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(webhook_url, json=payload)
        try:
            result = response.json()
        except Exception:
            result = None

    if not isinstance(result, dict):
        raise RuntimeError(f"企业微信推送失败: 响应非 JSON: {response.text}")

    if result.get("errcode", 0) != 0:
        raise RuntimeError(f"企业微信推送失败: {result.get('errmsg', '未知错误')}")

    return {"success": True, "response": result}
