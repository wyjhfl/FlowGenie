"""数组操作工具 - 排序/切片/展平/去重/抽样"""
import json
import random


async def execute(params: dict, context) -> dict:
    """
    数组操作
    :param params: {
        array: 列表或 JSON 字符串,
        operation: sort | slice | flatten | unique | sample,
        key: sort/unique 时按该字段(可选,对象数组用),
        start: slice 起始索引(可选),
        end: slice 结束索引(可选),
        count: sample 抽样数量(可选,默认 1),
        reverse: sort 是否倒序(可选,默认 False)
    }
    :return: { result, count }
    """
    array = params.get("array")
    operation = params.get("operation", "")
    key = params.get("key")
    start = params.get("start")
    end = params.get("end")
    count = params.get("count")
    reverse = params.get("reverse", False)

    if array is None:
        raise ValueError("array 参数不能为空")
    if not operation:
        raise ValueError("operation 参数不能为空")

    # array 为字符串时尝试 JSON 解析
    if isinstance(array, str):
        try:
            array = json.loads(array)
        except json.JSONDecodeError:
            raise ValueError("array 为字符串但无法解析为 JSON")
    if not isinstance(array, list):
        raise ValueError("array 必须是列表或 JSON 数组字符串")

    if operation == "sort":
        if key:
            result = sorted(array, key=lambda x: x.get(key) if isinstance(x, dict) else x, reverse=bool(reverse))
        else:
            result = sorted(array, reverse=bool(reverse))
    elif operation == "slice":
        s = int(start) if start is not None else None
        e = int(end) if end is not None else None
        result = array[s:e]
    elif operation == "flatten":
        # 嵌套列表展开一层
        result = [item for sub in array for item in (sub if isinstance(sub, list) else [sub])]
    elif operation == "unique":
        if key:
            seen = set()
            result = []
            for x in array:
                k = x.get(key) if isinstance(x, dict) else x
                # 不可哈希的值转为字符串比较
                try:
                    if k not in seen:
                        seen.add(k)
                        result.append(x)
                except TypeError:
                    k = str(k)
                    if k not in seen:
                        seen.add(k)
                        result.append(x)
        else:
            # 保序去重
            seen = set()
            result = []
            for x in array:
                try:
                    if x not in seen:
                        seen.add(x)
                        result.append(x)
                except TypeError:
                    # 不可哈希元素转字符串去重
                    xs = str(x)
                    if xs not in seen:
                        seen.add(xs)
                        result.append(x)
    elif operation == "sample":
        n = int(count) if count is not None else 1
        if n < 0:
            raise ValueError("count 不能为负数")
        n = min(n, len(array))
        result = random.sample(array, n) if n > 0 else []
    else:
        raise ValueError(f"不支持的 operation: {operation}(支持 sort/slice/flatten/unique/sample)")

    return {"result": result, "count": len(result)}
