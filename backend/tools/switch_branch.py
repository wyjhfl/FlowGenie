"""多路分支工具 - 按 field 值路由到不同分支"""


async def execute(params: dict, context) -> dict:
    """
    多路分支
    :param params: {field, cases}
    :return: {matched_case, branch}
    """
    field = params.get("field", "")
    cases = params.get("cases", [])

    # field 转 str
    if field is None:
        field_str = ""
    elif isinstance(field, str):
        field_str = field
    else:
        field_str = str(field)

    # cases 容错
    if not isinstance(cases, list):
        cases = [str(cases)] if cases else []
    else:
        cases = [str(c) for c in cases if c is not None]

    # 精确匹配
    matched = "default"
    for case in cases:
        if field_str == case:
            matched = case
            break

    return {
        "matched_case": matched,
        "branch": matched,
    }
