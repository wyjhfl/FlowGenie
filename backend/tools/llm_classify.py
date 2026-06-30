"""LLM 文本分类工具 - 情感分析/主题分类/意图识别/垃圾检测"""
import json
import re
from core.llm import chat_with_streaming


# 各任务的默认类别
_DEFAULT_CATEGORIES = {
    "sentiment": ["正面", "负面", "中性"],
    "topic": ["科技", "财经", "体育", "娱乐", "政治", "其他"],
    "intent": ["咨询", "投诉", "建议", "购买", "其他"],
    "spam": ["正常", "垃圾"],
}


async def execute(params: dict, context) -> dict:
    """
    文本分类
    :param params: {text, categories=None, task="sentiment"}
    :return: {category, confidence, all_scores, reason}
    """
    text = params.get("text", "")
    categories = params.get("categories")
    task = params.get("task", "sentiment")

    # 空数据容错
    if text is None or text == "" or text == []:
        return {"category": "unknown", "confidence": 0.0, "all_scores": {}, "reason": "无内容可分类"}

    if not isinstance(text, str):
        text = json.dumps(text, ensure_ascii=False, default=str)

    if not text.strip():
        return {"category": "unknown", "confidence": 0.0, "all_scores": {}, "reason": "无内容可分类"}

    # 解析 categories(逗号分隔字符串或列表)
    if categories is None:
        cats = _DEFAULT_CATEGORIES.get(task, _DEFAULT_CATEGORIES["sentiment"])
    elif isinstance(categories, str):
        cats = [c.strip() for c in categories.split(",") if c.strip()]
    elif isinstance(categories, list):
        cats = [str(c).strip() for c in categories if c]
    else:
        cats = _DEFAULT_CATEGORIES.get(task, _DEFAULT_CATEGORIES["sentiment"])

    if not cats:
        cats = _DEFAULT_CATEGORIES.get(task, _DEFAULT_CATEGORIES["sentiment"])

    task_desc = {
        "sentiment": "情感分析",
        "topic": "主题分类",
        "intent": "意图识别",
        "spam": "垃圾检测",
    }.get(task, "文本分类")

    system_prompt = (
        f"你是{task_desc}助手。请从以下类别中选择最匹配的一个:"
        f"{', '.join(cats)}。\n"
        f"只输出 JSON,格式为:{{\"category\": \"类别名\", \"confidence\": 0.0-1.0, \"reason\": \"简要原因\"}}"
    )
    user_prompt = f"请分类以下内容:\n\n{text}"

    # B1: 若 context.token_callback 存在则流式调用,否则同步
    # B3: 支持节点级 model 参数覆盖默认模型
    # B4: 传入 usage_callback 累积 token 用量到 context
    token_cb = getattr(context, "token_callback", None)
    usage_cb = getattr(context, "add_token_usage", None)
    model = params.get("model", "")
    raw = await chat_with_streaming(system_prompt, user_prompt, model, 0.3, token_callback=token_cb, usage_callback=usage_cb)

    # 容错解析 JSON
    try:
        # 尝试提取 JSON 块
        json_match = re.search(r'\{[^{}]*\}', raw)
        if json_match:
            data = json.loads(json_match.group())
            category = str(data.get("category", "unknown")).strip()
            confidence = float(data.get("confidence", 0.5))
            reason = str(data.get("reason", "")).strip()
        else:
            raise ValueError("no json found")
    except Exception:
        category = raw.strip()[:50] if raw.strip() else "unknown"
        confidence = 0.5
        reason = "解析失败,使用原始输出"

    return {
        "category": category,
        "confidence": confidence,
        "all_scores": {category: confidence},
        "reason": reason,
    }
