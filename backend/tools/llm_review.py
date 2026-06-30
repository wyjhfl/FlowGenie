"""LLM Code Review 工具 - 调用 LLM 对代码进行 Review"""
from core.llm import chat_with_streaming


async def execute(params: dict, context) -> dict:
    """
    LLM Code Review
    :param params: { code, focus }
    :return: { review, issues_count }
    """
    code = params.get("code", "")
    focus = params.get("focus", ["bug", "security", "performance", "style"])

    # 空数据容错
    if code is None or code == "" or code == []:
        return {"review": "无代码可审查", "issues_count": 0}

    # code 可能是变量插值后的对象，转为字符串
    if not isinstance(code, str):
        import json
        code = json.dumps(code, ensure_ascii=False, default=str)

    if not code.strip() or code.strip() == "[]":
        return {"review": "无代码可审查", "issues_count": 0}

    if isinstance(focus, list):
        focus_str = "、".join(focus)
    else:
        focus_str = str(focus)

    system_prompt = f"你是资深代码审查专家。请从以下维度审查代码：{focus_str}。输出格式：先列出发现的问题（编号），再给出改进建议。"
    user_prompt = f"请审查以下代码：\n\n```\n{code}\n```"

    # B1: 若 context.token_callback 存在则流式调用,否则同步
    # B3: 支持节点级 model 参数覆盖默认模型
    # B4: 传入 usage_callback 累积 token 用量到 context
    token_cb = getattr(context, "token_callback", None)
    usage_cb = getattr(context, "add_token_usage", None)
    model = params.get("model", "")
    review = await chat_with_streaming(system_prompt, user_prompt, model, 0.3, token_callback=token_cb, usage_callback=usage_cb)

    # 统计问题数量：按"数字."开头的行计数
    import re
    issues_count = len(re.findall(r'^\s*\d+[\.\)]\s', review, re.MULTILINE))

    return {"review": review.strip(), "issues_count": issues_count}
