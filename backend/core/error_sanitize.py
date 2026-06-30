"""错误信息脱敏与提取 - 统一共享模块

避免敏感信息(Bearer token/密码/密钥/内网 IP)泄露到 DB、API 响应、外部通知渠道。
所有写入 RunRecord.error、发送到通知渠道的错误文本,必须先经过 sanitize_error_text。
"""
import re

# 敏感模式正则:匹配 Bearer token、api_key/token/password/secret 等键值对
_SENSITIVE_PATTERNS = [
    re.compile(r"(Bearer\s+)[^\s,;'\"]+", re.IGNORECASE),
    re.compile(
        r"((?:api[_-]?key|token|password|passwd|secret|pwd|authorization)"
        r"\s*[=:]\s*)[^\s,;'\"]+",
        re.IGNORECASE,
    ),
]

# 内网/回环 IP 模式(避免在错误信息中泄露内网拓扑)
_IP_PATTERNS = [
    re.compile(r"\b(10\.\d{1,3}\.\d{1,3}\.\d{1,3})\b"),
    re.compile(r"\b(192\.168\.\d{1,3}\.\d{1,3})\b"),
    re.compile(r"\b(172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b"),
    re.compile(r"\b(127\.\d{1,3}\.\d{1,3}\.\d{1,3})\b"),
    re.compile(r"\b(169\.254\.\d{1,3}\.\d{1,3})\b"),
]

# 错误信息最大长度(超出截断,避免 DB 字段膨胀与日志噪音)
MAX_ERROR_LEN = 500


def sanitize_error_text(text: str) -> str:
    """脱敏错误文本

    1. 替换 Bearer token / api_key / password / secret 等敏感键值
    2. 替换内网/回环 IP 为 ***.***.***.***
    3. 截断超长文本(MAX_ERROR_LEN)

    详细堆栈仅写日志(logger.exception),不写 DB/不返回 API/不发送通知。
    """
    if not text:
        return ""
    result = str(text)
    for pattern in _SENSITIVE_PATTERNS:
        result = pattern.sub(r"\1***", result)
    for pattern in _IP_PATTERNS:
        result = pattern.sub("***.***.***.***", result)
    if len(result) > MAX_ERROR_LEN:
        result = result[:MAX_ERROR_LEN] + "...[truncated]"
    return result


def extract_error(steps_result: dict) -> str | None:
    """从 steps_result 中提取第一个失败步骤的错误信息(已脱敏)

    :param steps_result: {step_id: {status, error, output, ...}}
    :return: 脱敏后的错误字符串,或 None(无失败步骤)
    """
    if not steps_result:
        return None
    for sr in steps_result.values():
        if isinstance(sr, dict) and sr.get("status") == "failed":
            return sanitize_error_text(sr.get("error") or "")
    return None
