"""JSON 路径提取工具 - 简化版 JSONPath,支持 $.a.b / $.a[*].c / $.a[0]"""
import json
import re


async def execute(params: dict, context) -> dict:
    """
    JSON 路径提取
    :param params: { data, path }
    :return: { values, count }
    """
    data = params.get("data")
    path = params.get("path", "")

    if data is None:
        raise ValueError("data 参数不能为空")
    if not path:
        raise ValueError("path 参数不能为空")

    # data 可能是变量插值后的字符串(JSON),尝试解析
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            raise ValueError("data 为字符串但无法解析为 JSON")

    # 解析 path 为段列表
    segments = _parse_path(path)

    # 递归提取
    values = _extract(data, segments)

    return {"values": values, "count": len(values)}


def _parse_path(path: str) -> list:
    """
    解析 JSONPath 为段列表
    支持: $.a.b / $.a[0] / $.a[*].c / $[0].a
    每段: {"type": "key"|"index"|"wildcard", "value": str|int|None}
    """
    # 去掉前导 $ 与 .
    path = path.strip()
    if path.startswith("$"):
        path = path[1:]
    if path.startswith("."):
        path = path[1:]

    # 若剩余 path 以 key 开头(非 [ 非 .),补前导 . 以统一 token 匹配
    if path and not path.startswith("[") and not path.startswith("."):
        path = "." + path

    segments = []
    # 匹配 .key 或 [n] 或 [*]
    token_pattern = re.compile(r"\.([^.\[\]]+)|\[(-?\d+)\]|\[(\*)\]")
    pos = 0
    while pos < len(path):
        m = token_pattern.match(path, pos)
        if not m:
            raise ValueError(f"无法解析路径段: {path[pos:]}")
        if m.group(1) is not None:
            segments.append({"type": "key", "value": m.group(1)})
        elif m.group(2) is not None:
            segments.append({"type": "index", "value": int(m.group(2))})
        else:  # m.group(3) == "*"
            segments.append({"type": "wildcard", "value": None})
        pos = m.end()

    return segments


def _extract(data, segments: list) -> list:
    """递归提取匹配值"""
    if not segments:
        return [data]

    seg = segments[0]
    rest = segments[1:]

    if seg["type"] == "key":
        if not isinstance(data, dict):
            return []
        if seg["value"] not in data:
            return []
        return _extract(data[seg["value"]], rest)

    elif seg["type"] == "index":
        if not isinstance(data, list):
            return []
        idx = seg["value"]
        # 支持负索引
        if idx < 0:
            idx += len(data)
        if idx < 0 or idx >= len(data):
            return []
        return _extract(data[idx], rest)

    elif seg["type"] == "wildcard":
        if not isinstance(data, list):
            return []
        results = []
        for item in data:
            results.extend(_extract(item, rest))
        return results

    return []
