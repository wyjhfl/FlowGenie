"""HTTP 请求工具 - httpx 异步请求"""
import httpx
from core.ssrf_guard import validate_url

# 响应体大小限制:10MB
MAX_CONTENT_LENGTH = 10 * 1024 * 1024


async def execute(params: dict, context) -> dict:
    """
    发起 HTTP 请求
    :param params: { url, method, headers, body }
    :return: { status_code, headers, body }
    """
    url = params.get("url", "")
    method = params.get("method", "GET").upper()
    headers = params.get("headers", {})
    body = params.get("body")

    if not url:
        raise ValueError("url 参数不能为空")

    # SSRF 防护:校验 URL 协议与目标 IP(异步,DNS 解析不阻塞事件循环)
    await validate_url(url)

    async with httpx.AsyncClient(timeout=30) as client:
        kwargs = {"headers": headers}
        if body and method in ("POST", "PUT", "PATCH"):
            if isinstance(body, (dict, list)):
                kwargs["json"] = body
            else:
                kwargs["content"] = str(body)

        response = await client.request(method, url, **kwargs)

    # 响应体大小限制：先检查 Content-Length 头
    content_length = response.headers.get("Content-Length")
    if content_length:
        try:
            cl = int(content_length)
        except (TypeError, ValueError):
            cl = None
        if cl is not None and cl > MAX_CONTENT_LENGTH:
            raise ValueError("响应体超过 10MB 限制")
    # 无 Content-Length 头或解析失败时，检查实际内容大小
    if len(response.content) > MAX_CONTENT_LENGTH:
        raise ValueError("响应体超过 10MB 限制")

    return {
        "status_code": response.status_code,
        "headers": dict(response.headers),
        "body": _parse_body(response.text),
    }


def _parse_body(text: str):
    """尝试解析 JSON，失败则返回原始文本"""
    import json
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return text
