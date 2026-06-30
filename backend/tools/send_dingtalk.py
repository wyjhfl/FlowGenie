"""钉钉机器人推送工具 - Webhook"""
import os
import json
import httpx
from core.ssrf_guard import validate_url


async def execute(params: dict, context) -> dict:
    """
    钉钉机器人推送
    :param params: { webhook_url, content, msg_type, at_mobiles }
    :return: { success, response }
    """
    webhook_url = params.get("webhook_url", "") or os.getenv("DINGTALK_WEBHOOK", "") or os.getenv("DINGTALK_WEBHOOK_URL", "")
    content = params.get("content", params.get("message", ""))
    msg_type = params.get("msg_type", "text")
    at_mobiles = params.get("at_mobiles", [])

    if not webhook_url:
        raise ValueError("钉钉 Webhook 未配置，请在凭证面板配置 DINGTALK_WEBHOOK")

    # 空数据容错：空内容跳过发送，返回有意义的空结果
    if not content:
        return {"success": False, "response": {}}

    # SSRF 防护:校验 webhook URL 协议与目标 IP
    await validate_url(webhook_url)

    # content 可能是变量插值后的对象，转为字符串
    if not isinstance(content, str):
        content = json.dumps(content, ensure_ascii=False, default=str)

    # 构建 @ 人信息
    at = {}
    if at_mobiles:
        at = {
            "atMobiles": at_mobiles if isinstance(at_mobiles, list) else [at_mobiles],
            "isAtAll": False,
        }

    # 构建钉钉消息体
    if msg_type == "markdown":
        payload = {
            "msgtype": "markdown",
            "markdown": {"title": "FlowGenie 通知", "text": content},
        }
    else:
        # text 类型
        payload = {
            "msgtype": "text",
            "text": {"content": content},
        }

    if at:
        payload["at"] = at

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(webhook_url, json=payload)
        try:
            result = response.json()
        except Exception:
            result = None

    if not isinstance(result, dict):
        raise RuntimeError(f"钉钉推送失败: 响应非 JSON: {response.text}")

    if result.get("errcode", 0) != 0:
        raise RuntimeError(f"钉钉推送失败: {result.get('errmsg', '未知错误')}")

    return {"success": True, "response": result}
