"""飞书机器人推送工具 - 通过 webhook 发送消息"""
import os
import httpx
from core.ssrf_guard import validate_url


async def execute(params: dict, context) -> dict:
    """
    飞书推送
    :param params: {content, msg_type="text", webhook_url=""}
    :return: {success, response, message}
    """
    content = params.get("content", "")
    msg_type = params.get("msg_type", "text")
    webhook_url = params.get("webhook_url", "") or os.getenv("FEISHU_WEBHOOK_URL", "")

    if not webhook_url:
        return {"success": False, "response": {}, "message": "缺少飞书 webhook_url(请配置 FEISHU_WEBHOOK_URL 环境变量或传 webhook_url 参数)"}
    if not content:
        return {"success": False, "response": {}, "message": "缺少 content"}

    # SSRF 防护:校验 webhook URL 协议与目标 IP
    await validate_url(webhook_url)

    # 构造请求体
    if msg_type == "markdown":
        body = {
            "msg_type": "interactive",
            "card": {
                "elements": [{"tag": "markdown", "content": str(content)}],
            },
        }
    elif msg_type == "interactive":
        # content 已是完整 card JSON
        if isinstance(content, str):
            import json
            try:
                body = {"msg_type": "interactive", "card": json.loads(content)}
            except Exception:
                body = {"msg_type": "text", "content": {"text": str(content)}}
        else:
            body = {"msg_type": "interactive", "card": content}
    else:  # text
        body = {
            "msg_type": "text",
            "content": {"text": str(content)},
        }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(webhook_url, json=body)
        data = resp.json()
        # 飞书 webhook 成功返回 code=0
        if resp.status_code == 200 and data.get("code", data.get("StatusCode", -1)) in (0, 200):
            return {"success": True, "response": data, "message": "推送成功"}
        return {"success": False, "response": data, "message": f"飞书 API 错误: {data.get('msg', str(data)[:200])}"}
    except Exception as e:
        return {"success": False, "response": {}, "message": f"请求异常: {e}"}
