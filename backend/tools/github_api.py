"""GitHub API 封装工具 - httpx 异步请求"""
import os
import json
import httpx
from core.ssrf_guard import validate_url


async def execute(params: dict, context) -> dict:
    """
    调用 GitHub REST API
    :param params: { endpoint, owner, repo, method, params, token }
    :return: { status_code, body, rate_limit_remaining }
    """
    endpoint = params.get("endpoint", "")
    owner = params.get("owner", "")
    repo = params.get("repo", "")
    method = params.get("method", "GET").upper()
    query_params = params.get("params", {})
    token = params.get("token", "") or os.getenv("GITHUB_TOKEN", "")

    if not endpoint:
        raise ValueError("endpoint 参数不能为空")

    # 填充 endpoint 中的 {owner}/{repo} 占位符
    if owner:
        endpoint = endpoint.replace("{owner}", owner)
    if repo:
        endpoint = endpoint.replace("{repo}", repo)

    # 确保以 / 开头
    if not endpoint.startswith("/"):
        endpoint = "/" + endpoint

    url = f"https://api.github.com{endpoint}"

    # SSRF 防护:校验拼接后的完整 URL(host 固定,主要防止 endpoint 注入异常协议/路径)
    await validate_url(url)

    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "FlowGenie/1.0",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    async with httpx.AsyncClient(timeout=30) as client:
        kwargs = {"headers": headers}
        if query_params and method == "GET":
            kwargs["params"] = query_params
        elif query_params and method in ("POST", "PUT", "PATCH"):
            kwargs["json"] = query_params

        response = await client.request(method, url, **kwargs)

    # 解析响应体
    try:
        body = response.json()
    except (json.JSONDecodeError, ValueError):
        body = response.text

    # 速率限制剩余次数
    rate_limit_remaining_raw = response.headers.get("X-RateLimit-Remaining", "")
    try:
        rate_limit_remaining = int(rate_limit_remaining_raw) if rate_limit_remaining_raw else 0
    except (ValueError, TypeError):
        rate_limit_remaining = 0

    return {
        "status_code": response.status_code,
        "body": body,
        "rate_limit_remaining": rate_limit_remaining,
    }
