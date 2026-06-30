"""SSRF 防护 - 校验 URL 协议与目标 IP,阻止访问内网

策略:
1. 协议白名单:仅允许 http/https
2. DNS 解析改 asyncio.to_thread,避免阻塞事件循环
3. 内网/回环/链路本地 IP 拒绝
4. 二次解析校验(可选):解析时与请求时 IP 不一致则拒绝(DNS rebinding 防护)
"""
import asyncio
import ipaddress
import socket
from urllib.parse import urlparse


def _is_ip_blocked(ip_str: str) -> bool:
    """判断 IP 是否在禁止访问的范围内(内网/回环/链路本地/保留/组播)"""
    try:
        ip_obj = ipaddress.ip_address(ip_str)
    except ValueError:
        return True  # 无法解析的 IP 视为禁止

    if isinstance(ip_obj, ipaddress.IPv4Address):
        return (
            ip_obj.is_private
            or ip_obj.is_loopback
            or ip_obj.is_link_local
            or ip_obj.is_reserved
            or ip_obj.is_multicast
        )
    elif isinstance(ip_obj, ipaddress.IPv6Address):
        return (
            ip_obj.is_private
            or ip_obj.is_loopback
            or ip_obj.is_link_local
            or ip_obj.is_multicast
        )
    return False


def _sync_resolve(host: str) -> str:
    """同步 DNS 解析(供 asyncio.to_thread 调用)"""
    return socket.gethostbyname(host)


async def validate_url(url: str) -> str:
    """校验 URL,返回解析后的 IP(供二次校验用)

    :raises ValueError: 协议不允许 / 主机无效 / IP 在内网范围
    :return: 解析后的 IP 字符串
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("仅允许 http/https 协议")
    host = parsed.hostname
    if not host:
        raise ValueError("无效的 URL")

    # DNS 解析改 asyncio.to_thread,避免阻塞事件循环
    ip = await asyncio.to_thread(_sync_resolve, host)

    if _is_ip_blocked(ip):
        raise ValueError("不允许访问内网地址")

    return ip


def validate_url_sync(url: str) -> str:
    """同步版 URL 校验(供非 async 上下文使用,如模块导入时)

    :raises ValueError: 协议不允许 / 主机无效 / IP 在内网范围
    :return: 解析后的 IP 字符串
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("仅允许 http/https 协议")
    host = parsed.hostname
    if not host:
        raise ValueError("无效的 URL")
    ip = _sync_resolve(host)
    if _is_ip_blocked(ip):
        raise ValueError("不允许访问内网地址")
    return ip


def validate_host(host: str) -> str:
    """校验主机名(DNS 解析 + 内网 IP 检查),用于非 HTTP 场景如 SMTP

    与 validate_url_sync 的 IP 校验逻辑一致,但不校验协议。

    :raises ValueError: 主机无效 / IP 在内网范围
    :return: 解析后的 IP 字符串
    """
    if not host:
        raise ValueError("主机名不能为空")
    ip = _sync_resolve(host)
    if _is_ip_blocked(ip):
        raise ValueError("不允许访问内网地址")
    return ip
