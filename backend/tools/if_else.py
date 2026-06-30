"""条件分支工具 - 根据 field + operator + value 判断选择执行路径"""


async def execute(params: dict, context) -> dict:
    """
    条件分支：根据 field + operator + value 判断真假
    :param params: { field, operator, value }
    :return: { result: bool, branch: "true"|"false" }
    """
    field = params.get("field")
    operator = params.get("operator", "eq")
    value = params.get("value")

    try:
        result = _evaluate(field, operator, value)
    except Exception:
        result = False

    return {"result": result, "branch": "true" if result else "false"}


def _evaluate(field, operator: str, value) -> bool:
    """根据操作符评估条件"""
    if operator == "eq":
        return field == value
    elif operator == "ne":
        return field != value
    elif operator == "gt":
        try:
            return field is not None and field > value
        except TypeError:
            return False
    elif operator == "ge":
        try:
            return field is not None and field >= value
        except TypeError:
            return False
    elif operator == "lt":
        try:
            return field is not None and field < value
        except TypeError:
            return False
    elif operator == "le":
        try:
            return field is not None and field <= value
        except TypeError:
            return False
    elif operator == "is_empty":
        return field is None or field == "" or field == [] or field == {}
    elif operator == "is_not_empty":
        return not (field is None or field == "" or field == [] or field == {})
    elif operator == "is_null":
        return field is None or field == "" or field == []
    elif operator == "is_not_null":
        return not (field is None or field == "" or field == [])
    elif operator == "contain":
        if field is None:
            return False
        return str(value) in str(field)
    elif operator == "not_contain":
        if field is None:
            return True
        return str(value) not in str(field)
    elif operator == "len_gt":
        try:
            return len(field) > int(value)
        except (TypeError, ValueError):
            return False
    elif operator == "len_ge":
        try:
            return len(field) >= int(value)
        except (TypeError, ValueError):
            return False
    elif operator == "len_lt":
        try:
            return len(field) < int(value)
        except (TypeError, ValueError):
            return False
    elif operator == "len_le":
        try:
            return len(field) <= int(value)
        except (TypeError, ValueError):
            return False
    elif operator == "startwith":
        if field is None:
            return False
        return str(field).startswith(str(value))
    elif operator == "endwith":
        if field is None:
            return False
        return str(field).endswith(str(value))
    else:
        raise ValueError(f"不支持的 operator: {operator}")
