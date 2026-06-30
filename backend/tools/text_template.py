"""文本模板渲染工具 - 变量插值拼接"""


async def execute(params: dict, context) -> dict:
    """
    模板渲染
    :param params: {template, variables}
    :return: {rendered, length}
    """
    template = params.get("template", "")
    variables = params.get("variables", {})

    # template 容错
    if not isinstance(template, str):
        template = str(template) if template is not None else ""

    # variables 容错
    if not isinstance(variables, dict):
        variables = {}

    rendered = template
    # 按 key 长度降序替换,避免短 key 覆盖长 key 的前缀
    for key in sorted(variables.keys(), key=len, reverse=True):
        placeholder = "{{" + key + "}}"
        value = variables[key]
        # 值转 str
        if value is None:
            value_str = ""
        elif isinstance(value, str):
            value_str = value
        else:
            import json
            value_str = json.dumps(value, ensure_ascii=False, default=str)
        rendered = rendered.replace(placeholder, value_str)

    return {
        "rendered": rendered,
        "length": len(rendered),
    }
