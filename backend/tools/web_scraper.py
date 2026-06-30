"""网页抓取工具 - httpx + BeautifulSoup"""
import httpx
from bs4 import BeautifulSoup
from core.ssrf_guard import validate_url

# 响应体大小限制：10MB
MAX_CONTENT_LENGTH = 10 * 1024 * 1024


async def execute(params: dict, context) -> dict:
    """
    抓取网页内容
    :param params: { url, selector, fields }
    :return: { title, url, items, count, page_text }
    """
    url = params.get("url", "")
    selector = params.get("selector", "body")
    fields = params.get("fields", ["title"])

    if not url:
        raise ValueError("url 参数不能为空")

    # SSRF 防护:校验 URL 协议与目标 IP(异步,DNS 解析不阻塞事件循环)
    await validate_url(url)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        response = await client.get(url, headers=headers)

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

    if response.status_code != 200:
        raise RuntimeError(f"抓取失败: HTTP {response.status_code}")

    soup = BeautifulSoup(response.text, "html.parser")
    page_title = soup.title.string.strip() if soup.title and soup.title.string else ""

    # 始终提取页面纯文本作为兜底
    page_text = soup.get_text(separator="\n", strip=True)[:5000]  # 限制 5000 字符

    # 按选择器提取内容
    items = []
    elements = soup.select(selector)
    warning = None
    if not elements:
        warning = f"selector '{selector}' 未匹配到任何元素，已回退到 body"
        elements = soup.select("body")
    for elem in elements[:50]:  # 限制最多 50 条
        item = {}
        for field in fields:
            if field == "title":
                item[field] = elem.get_text(strip=True)[:200]
            elif field == "content":
                item[field] = elem.get_text(strip=True)[:500]
            elif field in ("href", "link", "url"):
                link = elem.find("a")
                item[field] = link.get("href", "") if link else ""
            elif field == "text":
                item[field] = elem.get_text(strip=True)[:200]
            else:
                item[field] = elem.get(field, "") or elem.get_text(strip=True)[:200]
        items.append(item)

    # 空数据兜底：items 为空但 page_text 非空时，用 page_text 作为兜底内容
    if not items and page_text:
        items = [{"title": page_title or "页面内容", "content": page_text[:500]}]

    result = {
        "title": page_title,
        "url": url,
        "items": items,
        "count": len(items),
        "page_text": page_text,
    }
    if warning:
        result["warning"] = warning
    return result
