"""Slack 推送工具 - Webhook"""
import os
import json
import httpx
from core.ssrf_guard import validate_url


async def execute(params: dict, context) -> dict:
    """
    Slack Webhook 推送
    :param params: { webhook_url, channel, text }
    :return: { success, response }
    """
    webhook_url = params.get("webhook_url", "") or os.getenv("SLACK_WEBHOOK", "") or os.getenv("SLACK_WEBHOOK_URL", "")
    text = params.get("text", params.get("content", params.get("message", "")))

    if not webhook_url:
        raise ValueError("Slack Webhook 未配置，请在凭证面板配置 SLACK_WEBHOOK")

    # 空数据容错：空内容跳过发送，返回有意义的空结果
    if not text:
        return {"success": False, "response": ""}

    # SSRF 防护:校验 webhook URL 协议与目标 IP
    await validate_url(webhook_url)

    # text 可能是变量插值后的对象，转为字符串
    if not isinstance(text, str):
        text = json.dumps(text, ensure_ascii=False, default=str)

    payload = {"text": text}

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(webhook_url, json=payload)

    if response.status_code != 200 or response.text != "ok":
        raise RuntimeError(f"Slack 推送失败: {response.status_code} {response.text}")

    return {"success": True, "response": response.text}
