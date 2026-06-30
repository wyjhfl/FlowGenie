"""LLM 信息抽取工具 - 结构化字段抽取"""
import json
import re
from core.llm import chat_with_streaming


async def execute(params: dict, context) -> dict:
    """
    信息抽取
    :param params: {text, schema, instruction=""}
    :return: {entities, count, raw}
    """
    text = params.get("text", "")
    schema = params.get("schema", "")
    instruction = params.get("instruction", "")

    # 空数据容错
    if text is None or text == "" or text == []:
        return {"entities": {}, "count": 0, "raw": ""}

    if not isinstance(text, str):
        text = json.dumps(text, ensure_ascii=False, default=str)

    if not text.strip() or not schema:
        return {"entities": {}, "count": 0, "raw": ""}

    # schema 为逗号分隔字段名
    if isinstance(schema, list):
        fields = [str(s).strip() for s in schema if s]
    else:
        fields = [s.strip() for s in str(schema).split(",") if s.strip()]

    if not fields:
        return {"entities": {}, "count": 0, "raw": ""}

    # 检测输入是否为 JSON 数组(多条记录)
    is_array_input = False
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            is_array_input = True
    except (json.JSONDecodeError, TypeError):
        pass

    fields_desc = ", ".join(fields)
    if is_array_input:
        system_prompt = (
            f"你是信息抽取助手。输入是一个 JSON 数组(多条记录),请从每一条记录中抽取以下字段:{fields_desc}。\n"
            f"输出一个 JSON 数组,数组中每个元素是一个对象,对应输入的一条记录。\n"
            f"重要:key 必须严格使用上述字段名(英文标识符),不可翻译为中文字段名;value 为抽取到的值(找不到则为 null)。\n"
            f"数组长度必须与输入数组一致。只输出 JSON 数组,不要输出多余的解释。"
        )
    else:
        system_prompt = (
            f"你是信息抽取助手。请从文本中抽取以下字段:{fields_desc}。\n"
            f"重要:key 必须严格使用上述字段名(英文标识符),不可翻译为中文字段名;value 为抽取到的值(找不到则为 null)。\n"
            f"只输出 JSON 对象,不要输出多余的解释。"
        )
    if instruction:
        system_prompt += f"\n补充说明:{instruction}"

    user_prompt = f"请从以下内容抽取信息:\n\n{text}"

    # B1: 若 context.token_callback 存在则流式调用,否则同步
    # B3: 支持节点级 model 参数覆盖默认模型
    # B4: 传入 usage_callback 累积 token 用量到 context
    token_cb = getattr(context, "token_callback", None)
    usage_cb = getattr(context, "add_token_usage", None)
    model = params.get("model", "")
    raw = await chat_with_streaming(system_prompt, user_prompt, model, 0.2, token_callback=token_cb, usage_callback=usage_cb)

    # 容错解析 JSON(支持对象或数组)
    entities = {} if not is_array_input else []
    try:
        if is_array_input:
            # 尝试提取 JSON 数组
            arr_match = re.search(r'\[[\s\S]*\]', raw)
            if arr_match:
                arr = json.loads(arr_match.group())
                # 过滤每条记录只保留 schema 字段
                filtered = [
                    {k: v for k, v in item.items() if k in fields}
                    if isinstance(item, dict) else item
                    for item in arr
                ]
                # 容错:若过滤后所有记录均为空但原始有数据,保留原始结果
                if filtered and all(isinstance(f, dict) and not f for f in filtered):
                    entities = arr
                else:
                    entities = filtered
            else:
                # 降级:尝试提取单个对象包装成数组
                obj_match = re.search(r'\{[\s\S]*\}', raw)
                if obj_match:
                    obj = json.loads(obj_match.group())
                    filtered_obj = {k: v for k, v in obj.items() if k in fields}
                    entities = [filtered_obj if filtered_obj else obj]
        else:
            json_match = re.search(r'\{[\s\S]*\}', raw)
            if json_match:
                obj = json.loads(json_match.group())
                filtered_obj = {k: v for k, v in obj.items() if k in fields}
                # 容错:若过滤后为空但原始有数据,保留原始结果
                entities = filtered_obj if filtered_obj else obj
            else:
                raise ValueError("no json found")
    except Exception:
        entities = {} if not is_array_input else []

    count = len(entities) if is_array_input else len(entities)

    return {
        "entities": entities,
        "count": count,
        "raw": raw.strip(),
    }
