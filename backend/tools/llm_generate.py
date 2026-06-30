"""LLM 内容生成工具 - 调用 LLM 生成报告/邮件/文章/文案"""
import json
from core.llm import chat_with_streaming


async def execute(params: dict, context) -> dict:
    """
    LLM 内容生成
    :param params: { content_type, topic, tone, language, length }
    :return: { content, content_type }
    """
    content_type = params.get("content_type", "report")
    topic = params.get("topic", "")
    tone = params.get("tone", "professional")
    language = params.get("language", "zh")
    length = params.get("length", "")

    # 空数据容错
    if topic is None or topic == "" or topic == []:
        return {"content": "无主题内容", "content_type": content_type}

    # topic 可能是变量插值后的对象（如 list/dict），转为字符串
    if not isinstance(topic, str):
        topic = json.dumps(topic, ensure_ascii=False, default=str)

    if not topic.strip() or topic.strip() == "[]":
        return {"content": "无主题内容", "content_type": content_type}

    # 语言提示
    lang_hint = "中文" if language == "zh" else "English"

    # 内容类型描述
    type_desc = {
        "report": "结构化报告（含标题、概述、要点、结论）",
        "email": "邮件（含主题行、称呼、正文、落款）",
        "article": "文章（含标题、引言、正文段落、结语）",
        "copywriting": "营销文案（吸引眼球、突出卖点、含行动号召）",
    }.get(content_type, "结构化内容")

    # 语气描述
    tone_desc = {
        "professional": "专业",
        "casual": "轻松",
        "formal": "正式",
    }.get(tone, "专业")

    # 长度约束
    length_hint = f"字数约 {length}。" if length else ""

    system_prompt = (
        f"你是内容创作助手。请用{lang_hint}生成{tone_desc}风格的{type_desc}。"
        f"{length_hint}只输出最终内容，不要附加解释。"
    )
    user_prompt = f"请围绕以下主题生成{type_desc}：\n\n{topic}"

    # B1: 若 context.token_callback 存在则流式调用,否则同步
    # B3: 支持节点级 model 参数覆盖默认模型
    # B4: 传入 usage_callback 累积 token 用量到 context
    token_cb = getattr(context, "token_callback", None)
    usage_cb = getattr(context, "add_token_usage", None)
    model = params.get("model", "")
    content = await chat_with_streaming(system_prompt, user_prompt, model, 0.7, token_callback=token_cb, usage_callback=usage_cb)

    return {"content": content.strip(), "content_type": content_type}
