"""RSS/Atom 订阅读取工具 - httpx + xml.etree.ElementTree"""
import httpx
import xml.etree.ElementTree as ET
from core.ssrf_guard import validate_url


async def execute(params: dict, context) -> dict:
    """
    读取 RSS/Atom 订阅源
    :param params: { feed_url, limit }
    :return: { items: [{title, link, published, summary}], count }
    """
    feed_url = params.get("feed_url", "")
    limit = params.get("limit", 10)

    if not feed_url:
        raise ValueError("feed_url 参数不能为空")

    # SSRF 防护:校验 URL 协议与目标 IP(异步,DNS 解析不阻塞事件循环)
    await validate_url(feed_url)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 FlowGenie/1.0"
    }

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        response = await client.get(feed_url, headers=headers)

    if response.status_code != 200:
        raise RuntimeError(f"获取订阅源失败: HTTP {response.status_code}")

    # 解析 XML
    try:
        root = ET.fromstring(response.content)
    except ET.ParseError as e:
        raise RuntimeError(f"XML 解析失败: {e}")

    # 判断是 RSS 2.0 还是 Atom 1.0
    tag = _local_tag(root.tag)
    if tag == "rss":
        items = _parse_rss(root, limit)
    elif tag == "feed":
        items = _parse_atom(root, limit)
    elif tag == "rdf":
        # RDF (RSS 1.0)
        items = _parse_rdf(root, limit)
    else:
        # 尝试兼容：找 channel 或 feed 子元素
        channel = root.find("channel")
        if channel is not None:
            items = _parse_rss(root, limit)
        else:
            raise RuntimeError(f"无法识别的订阅格式: {root.tag}")

    return {"items": items, "count": len(items)}


def _local_tag(tag: str) -> str:
    """去除命名空间前缀，返回本地标签名"""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _find_all(elem, name: str):
    """按本地标签名查找所有子元素（忽略命名空间）"""
    return [e for e in elem.iter() if _local_tag(e.tag) == name]


def _find_text(elem, name: str, default: str = "") -> str:
    """按本地标签名查找第一个子元素的文本"""
    for e in elem:
        if _local_tag(e.tag) == name:
            return (e.text or "").strip()
    return default


def _parse_rss(root, limit: int) -> list:
    """解析 RSS 2.0"""
    channel = root.find("channel")
    if channel is None:
        # 某些 RSS 1.0 没有 channel 包裹
        items_xml = _find_all(root, "item")
    else:
        items_xml = _find_all(channel, "item")

    items = []
    for item in items_xml[:limit]:
        title = _find_text(item, "title", "")
        link = _find_text(item, "link", "")
        published = _find_text(item, "pubDate", "") or _find_text(item, "date", "")
        summary = _find_text(item, "description", "") or _find_text(item, "content", "")
        items.append({
            "title": title,
            "link": link,
            "published": published,
            "summary": summary,
        })
    return items


def _parse_atom(root, limit: int) -> list:
    """解析 Atom 1.0"""
    entries = _find_all(root, "entry")
    items = []
    for entry in entries[:limit]:
        title = _find_text(entry, "title", "")

        # link 可能有多个，优先取 rel="alternate" 或 href 属性
        link = ""
        for e in entry:
            if _local_tag(e.tag) != "link":
                continue
            rel = e.get("rel", "alternate")
            href = e.get("href", "")
            if rel == "alternate" and href:
                link = href
                break
            if not link and href:
                link = href
        # 兜底：link 的文本内容
        if not link:
            link = _find_text(entry, "link", "")

        published = _find_text(entry, "published", "") or _find_text(entry, "updated", "")
        summary = _find_text(entry, "summary", "") or _find_text(entry, "content", "")

        items.append({
            "title": title,
            "link": link,
            "published": published,
            "summary": summary,
        })
    return items


def _parse_rdf(root, limit: int) -> list:
    """解析 RSS 1.0 (RDF)"""
    items_xml = _find_all(root, "item")
    items = []
    for item in items_xml[:limit]:
        title = _find_text(item, "title", "")
        link = _find_text(item, "link", "")
        published = _find_text(item, "date", "")
        summary = _find_text(item, "description", "")
        items.append({
            "title": title,
            "link": link,
            "published": published,
            "summary": summary,
        })
    return items
