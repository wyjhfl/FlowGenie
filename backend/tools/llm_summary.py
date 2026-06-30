"""LLM 摘要工具 - 调用 LLM 生成文本摘要"""
from core.llm import chat_with_streaming


async def execute(params: dict, context) -> dict:
    """
    生成文本摘要
    :param params: { text, max_length, language }
    :return: { summary, original_length }
    """
    text = params.get("text", "")
    max_length = params.get("max_length", 500)
    language = params.get("language", "zh")

    # 空数据容错：空数组/空字符串/None 返回空结果而非抛异常
    if text is None or text == "" or text == []:
        return {"summary": "无内容可摘要", "original_length": 0}

    # text 可能是变量插值后的对象（如 list/dict），转为字符串
    if not isinstance(text, str):
        import json
        text = json.dumps(text, ensure_ascii=False, default=str)

    if not text.strip() or text.strip() == "[]":
        return {"summary": "无内容可摘要", "original_length": 0}

    lang_hint = "中文" if language == "zh" else "English"
    system_prompt = f"你是摘要生成助手。请用{lang_hint}生成不超过 {max_length} 字的摘要，只输出摘要内容。"
    user_prompt = f"请摘要以下内容：\n\n{text}"

    # B1: 若 context.token_callback 存在则流式调用,否则同步
    # B3: 支持节点级 model 参数覆盖默认模型
    # B4: 传入 usage_callback 累积 token 用量到 context
    token_cb = getattr(context, "token_callback", None)
    usage_cb = getattr(context, "add_token_usage", None)
    model = params.get("model", "")
    summary = await chat_with_streaming(system_prompt, user_prompt, model, 0.3, token_callback=token_cb, usage_callback=usage_cb)

    return {"summary": summary.strip(), "original_length": len(text)}
