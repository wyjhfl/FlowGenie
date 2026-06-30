"""数学计算工具 - 聚合运算:求和/均值/最值/计数/四舍五入"""
import json


def _is_number(x) -> bool:
    """判断是否为数字(int/float,排除 bool)"""
    return isinstance(x, (int, float)) and not isinstance(x, bool)


async def execute(params: dict, context) -> dict:
    """
    数学计算
    :param params: {
        data: 数字数组或对象数组(可为 JSON 字符串),
        operation: sum | avg | min | max | count | round,
        field: 对象数组时取该字段(可选),
        precision: round 小数位(默认 2)
    }
    :return: { result, operation }
    """
    data = params.get("data")
    operation = params.get("operation", "")
    field = params.get("field")
    precision = params.get("precision", 2)

    if data is None:
        raise ValueError("data 参数不能为空")
    if not operation:
        raise ValueError("operation 参数不能为空")

    # data 为字符串时尝试 JSON 解析
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            raise ValueError("data 为字符串但无法解析为 JSON")

    # round 操作支持单个数字输入
    if operation == "round":
        try:
            p = int(precision)
        except (TypeError, ValueError):
            p = 2
        if _is_number(data):
            return {"result": round(data, p), "operation": operation}
        if not isinstance(data, list):
            raise ValueError("data 必须是数字、数字列表或 JSON 数组字符串")
        nums = [_extract_field(x, field) for x in data] if field else data
        nums = [n for n in nums if _is_number(n)]
        if not nums:
            raise ValueError("data 中无有效数字")
        return {"result": [round(n, p) for n in nums], "operation": operation}

    if not isinstance(data, list):
        raise ValueError("data 必须是数字列表或 JSON 数组字符串")

    # 对象数组按 field 提取数字
    if field:
        nums = []
        for x in data:
            v = _extract_field(x, field)
            if _is_number(v):
                nums.append(v)
    else:
        nums = [x for x in data if _is_number(x)]

    if not nums:
        raise ValueError("data 中无有效数字")

    if operation == "sum":
        result = sum(nums)
    elif operation == "avg":
        result = sum(nums) / len(nums)
    elif operation == "min":
        result = min(nums)
    elif operation == "max":
        result = max(nums)
    elif operation == "count":
        result = len(nums)
    else:
        raise ValueError(f"不支持的 operation: {operation}(支持 sum/avg/min/max/count/round)")

    return {"result": result, "operation": operation}


def _extract_field(x, field):
    """从对象中按 field 取值,非对象则返回原值"""
    if isinstance(x, dict) and field in x:
        return x[field]
    return x
