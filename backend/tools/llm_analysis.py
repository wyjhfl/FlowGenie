"""LLM 分析工具 - 调用 LLM 进行数据分析"""
from core.llm import chat_with_streaming


async def execute(params: dict, context) -> dict:
    """
    LLM 数据分析
    :param params: { data, task }
    :return: { analysis }
    """
    data = params.get("data", "")
    task = params.get("task", "分析数据趋势并给出洞察")

    # 空数据容错
    if data is None or data == "" or data == []:
        return {"analysis": "无数据可分析"}

    # data 可能是变量插值后的对象（如 list/dict），转为字符串
    if not isinstance(data, str):
        import json
        data = json.dumps(data, ensure_ascii=False, default=str)

    if not data.strip() or data.strip() == "[]":
        return {"analysis": "无数据可分析"}

    system_prompt = "你是数据分析专家。请根据给定任务分析数据，给出结构化的分析结果。"
    user_prompt = f"任务：{task}\n\n数据：\n{data}"

    # B1: 若 context.token_callback 存在则流式调用,否则同步
    # B3: 支持节点级 model 参数覆盖默认模型
    # B4: 传入 usage_callback 累积 token 用量到 context
    token_cb = getattr(context, "token_callback", None)
    usage_cb = getattr(context, "add_token_usage", None)
    model = params.get("model", "")
    analysis = await chat_with_streaming(system_prompt, user_prompt, model, 0.3, token_callback=token_cb, usage_callback=usage_cb)

    return {"analysis": analysis.strip()}
