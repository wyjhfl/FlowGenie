"""正则提取工具 - 从文本中按正则模式提取匹配内容"""
import re


async def execute(params: dict, context) -> dict:
    """
    正则提取
    :param params: { text, pattern, group }
    :return: { matches, count }
    """
    text = params.get("text", "")
    pattern = params.get("pattern", "")
    group = params.get("group", 0)

    if not pattern:
        raise ValueError("pattern 参数不能为空")

    # text 可能是非字符串(如 dict/list),转为字符串处理
    if not isinstance(text, str):
        text = str(text)

    # 编译正则,无效 pattern 抛 ValueError
    try:
        regex = re.compile(pattern)
    except re.error as e:
        raise ValueError(f"无效的正则表达式: {e}")

    # group 可以是分组名(str)或索引(int)
    try:
        group_idx = int(group)
    except (TypeError, ValueError):
        group_idx = group  # 分组名

    matches = []
    for m in regex.finditer(text):
        try:
            val = m.group(group_idx)
            if val is not None:
                matches.append(val)
        except (IndexError, re.error):
            # 指定分组不存在则跳过
            continue

    return {"matches": matches, "count": len(matches)}
