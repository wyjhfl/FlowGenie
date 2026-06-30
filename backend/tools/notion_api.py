"""Notion 集成工具 - 写入数据库记录"""
import os
import httpx
from core.ssrf_guard import validate_url


async def execute(params: dict, context) -> dict:
    """
    写入 Notion 数据库
    :param params: {database_id, properties, token=""}
    :return: {success, page_id, url, message}
    """
    database_id = params.get("database_id", "")
    properties = params.get("properties", {})
    token = params.get("token", "") or os.getenv("NOTION_TOKEN", "")

    if not database_id:
        return {"success": False, "page_id": "", "url": "", "message": "缺少 database_id"}
    if not token:
        return {"success": False, "page_id": "", "url": "", "message": "缺少 Notion token(请配置 NOTION_TOKEN 环境变量或传 token 参数)"}
    if not isinstance(properties, dict) or not properties:
        return {"success": False, "page_id": "", "url": "", "message": "缺少 properties"}

    # 转换 properties 为 Notion 格式
    notion_properties = {}
    for key, value in properties.items():
        if isinstance(value, bool):
            notion_properties[key] = {"checkbox": value}
        elif isinstance(value, (int, float)):
            notion_properties[key] = {"number": value}
        elif isinstance(value, str):
            # 第一个字符串字段用 title,其余用 rich_text
            if not any("title" in v for v in notion_properties.values()):
                notion_properties[key] = {"title": [{"text": {"content": value}}]}
            else:
                notion_properties[key] = {"rich_text": [{"text": {"content": value}}]}
        else:
            # 其他类型转为字符串
            import json
            notion_properties[key] = {"rich_text": [{"text": {"content": json.dumps(value, ensure_ascii=False, default=str)}}]}

    body = {
        "parent": {"database_id": database_id},
        "properties": notion_properties,
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }

    # SSRF 防护:校验实际请求的完整 URL
    notion_url = "https://api.notion.com/v1/pages"
    await validate_url(notion_url)

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(notion_url, json=body, headers=headers)
        data = resp.json()
        if resp.status_code in (200, 201):
            return {
                "success": True,
                "page_id": data.get("id", ""),
                "url": data.get("url", ""),
                "message": "写入成功",
            }
        return {
            "success": False,
            "page_id": "",
            "url": "",
            "message": f"Notion API 错误: {resp.status_code} - {data.get('message', str(data)[:200])}",
        }
    except Exception as e:
        return {"success": False, "page_id": "", "url": "", "message": f"请求异常: {e}"}
