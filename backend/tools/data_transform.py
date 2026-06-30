"""数据转换工具 - 去重/字段映射/类型转换/过滤"""
import json


async def execute(params: dict, context) -> dict:
    """
    数据转换：支持去重、字段映射、类型转换、过滤
    :param params: { data, operations: [{type, ...}] }
    :return: { data, count }
    """
    data = params.get("data")
    operations = params.get("operations", [])

    if data is None:
        raise ValueError("data 参数不能为空")
    if not operations:
        raise ValueError("operations 参数不能为空")

    # data 可能是变量插值后的字符串（JSON），尝试解析
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            raise ValueError("data 为字符串但无法解析为 JSON，期望 list[dict] 或 dict")

    # 统一为 list 处理，记录是否原本为单 dict
    is_single = isinstance(data, dict)
    if is_single:
        rows = [data]
    elif isinstance(data, list):
        rows = data
    else:
        raise ValueError("data 必须是 list[dict] 或 dict")

    # 按顺序应用操作
    for op in operations:
        op_type = op.get("type", "")
        if op_type == "deduplicate":
            rows = _deduplicate(rows, op.get("key", ""))
        elif op_type == "map_fields":
            rows = _map_fields(rows, op.get("mapping", {}))
        elif op_type == "convert_type":
            rows = _convert_type(rows, op.get("fields", {}))
        elif op_type == "filter":
            rows = _filter_rows(rows, op)
        else:
            raise ValueError(f"不支持的操作类型: {op_type}")

    # 还原为单 dict（如果原本是），空列表则返回 None
    if is_single:
        result = rows[0] if rows else None
    else:
        result = rows

    return {"data": result, "count": len(rows)}


def _deduplicate(rows: list, key: str) -> list:
    """按 key 字段去重"""
    if not key:
        raise ValueError("deduplicate 操作需要 key 字段")
    seen = set()
    result = []
    for row in rows:
        val = row.get(key)
        # 不可哈希的值转为字符串
        if isinstance(val, (list, dict)):
            val = json.dumps(val, ensure_ascii=False, sort_keys=True)
        if val not in seen:
            seen.add(val)
            result.append(row)
    return result


def _map_fields(rows: list, mapping: dict) -> list:
    """字段重命名 {from: to}"""
    if not mapping:
        raise ValueError("map_fields 操作需要 mapping 字段")
    result = []
    for row in rows:
        new_row = {}
        for k, v in row.items():
            new_key = mapping.get(k, k)
            new_row[new_key] = v
        result.append(new_row)
    return result


def _convert_type(rows: list, fields: dict) -> list:
    """字段类型转换 {field: "int"|"float"|"str"}"""
    if not fields:
        raise ValueError("convert_type 操作需要 fields 字段")
    result = []
    for row in rows:
        new_row = dict(row)
        for field, target_type in fields.items():
            if field not in new_row:
                continue
            val = new_row[field]
            try:
                if target_type == "int":
                    new_row[field] = int(float(val)) if val != "" else 0
                elif target_type == "float":
                    new_row[field] = float(val) if val != "" else 0.0
                elif target_type == "str":
                    new_row[field] = str(val)
                else:
                    raise ValueError(f"不支持的类型: {target_type}")
            except (ValueError, TypeError) as e:
                raise ValueError(f"字段 {field} 无法转换为 {target_type}: {e}")
        result.append(new_row)
    return result


def _filter_rows(rows: list, op: dict) -> list:
    """按条件过滤 {field, operator, value}，operator: eq/ne/gt/lt/contains"""
    field = op.get("field", "")
    operator = op.get("operator", "eq")
    value = op.get("value")

    if not field:
        raise ValueError("filter 操作需要 field 字段")

    result = []
    for row in rows:
        val = row.get(field)
        if _match(val, operator, value):
            result.append(row)
    return result


def _match(val, operator: str, value) -> bool:
    """判断单个值是否匹配过滤条件"""
    if operator == "eq":
        return val == value
    elif operator == "ne":
        return val != value
    elif operator == "gt":
        try:
            return val is not None and val > value
        except TypeError:
            return False
    elif operator == "lt":
        try:
            return val is not None and val < value
        except TypeError:
            return False
    elif operator == "contains":
        if val is None:
            return False
        if isinstance(val, str):
            return str(value) in val
        if isinstance(val, (list, dict)):
            return value in val
        return str(value) in str(val)
    else:
        raise ValueError(f"不支持的 operator: {operator}")
