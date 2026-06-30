"""LLM 翻译工具 - 多语言互译"""
import json
from core.llm import chat_with_streaming


async def execute(params: dict, context) -> dict:
    """
    翻译文本
    :param params: {text, source_lang="auto", target_lang="en"}
    :return: {translation, source_lang, target_lang, original_length}
    """
    text = params.get("text", "")
    source_lang = params.get("source_lang", "auto")
    target_lang = params.get("target_lang", "en")

    # 空数据容错
    if text is None or text == "" or text == []:
        return {"translation": "无内容可翻译", "source_lang": "", "target_lang": target_lang, "original_length": 0}

    # 非 str 转 str
    if not isinstance(text, str):
        text = json.dumps(text, ensure_ascii=False, default=str)

    if not text.strip():
        return {"translation": "无内容可翻译", "source_lang": "", "target_lang": target_lang, "original_length": 0}

    src_hint = source_lang if source_lang != "auto" else "原文"
    system_prompt = f"你是翻译助手。请将{src_hint}翻译为{target_lang},只输出译文,不要附加解释。"
    user_prompt = f"请翻译以下内容:\n\n{text}"

    # B1: 若 context.token_callback 存在则流式调用,否则同步
    # B3: 支持节点级 model 参数覆盖默认模型
    # B4: 传入 usage_callback 累积 token 用量到 context
    token_cb = getattr(context, "token_callback", None)
    usage_cb = getattr(context, "add_token_usage", None)
    model = params.get("model", "")
    translation = await chat_with_streaming(system_prompt, user_prompt, model, 0.3, token_callback=token_cb, usage_callback=usage_cb)

    return {
        "translation": translation.strip(),
        "source_lang": source_lang,
        "target_lang": target_lang,
        "original_length": len(text),
    }
