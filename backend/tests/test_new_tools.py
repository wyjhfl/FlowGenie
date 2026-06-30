"""新工具单元测试 - json_path/regex_extract/date_format/array_ops/math_calculate

直接调用工具 execute 函数,聚焦工具本身正确性(context 传 None)。
"""
import pytest
from tools.json_path import execute as json_path_execute
from tools.regex_extract import execute as regex_extract_execute
from tools.date_format import execute as date_format_execute
from tools.array_ops import execute as array_ops_execute
from tools.math_calculate import execute as math_calculate_execute


@pytest.mark.asyncio
async def test_json_path_basic():
    """$.a.b 提取"""
    out = await json_path_execute({"data": {"a": {"b": 1}}, "path": "$.a.b"}, None)
    assert out == {"values": [1], "count": 1}


@pytest.mark.asyncio
async def test_json_path_wildcard():
    """$.a[*].c 通配展开"""
    out = await json_path_execute(
        {"data": {"a": [{"c": 1}, {"c": 2}]}, "path": "$.a[*].c"}, None
    )
    assert out == {"values": [1, 2], "count": 2}


@pytest.mark.asyncio
async def test_regex_extract():
    """正则提取邮箱"""
    text = "联系: a@b.com 或 c@d.com"
    out = await regex_extract_execute(
        {"text": text, "pattern": r"[\w.]+@[\w.]+", "group": 0}, None
    )
    assert out["count"] == 2
    assert "a@b.com" in out["matches"]


@pytest.mark.asyncio
async def test_date_format_add_days():
    """日期格式化 + add_days 运算"""
    out = await date_format_execute(
        {
            "datetime": "2026-01-01",
            "input_format": "%Y-%m-%d",
            "output_format": "%Y-%m-%d",
            "add_days": 5,
        },
        None,
    )
    assert out["formatted"] == "2026-01-06"


@pytest.mark.asyncio
async def test_array_ops_sort_by_key():
    """对象数组按 key 排序"""
    arr = [{"id": 3}, {"id": 1}, {"id": 2}]
    out = await array_ops_execute({"array": arr, "operation": "sort", "key": "id"}, None)
    assert out["result"] == [{"id": 1}, {"id": 2}, {"id": 3}]
    assert out["count"] == 3


@pytest.mark.asyncio
async def test_array_ops_flatten():
    """嵌套数组展开一层"""
    out = await array_ops_execute({"array": [[1, 2], [3, 4]], "operation": "flatten"}, None)
    assert out["result"] == [1, 2, 3, 4]
    assert out["count"] == 4


@pytest.mark.asyncio
async def test_math_calculate_sum_by_field():
    """对象数组按 field 求 sum"""
    data = [{"value": 10}, {"value": 20}, {"value": 30}]
    out = await math_calculate_execute(
        {"data": data, "operation": "sum", "field": "value"}, None
    )
    assert out["result"] == 60
    assert out["operation"] == "sum"


@pytest.mark.asyncio
async def test_math_calculate_avg_precision():
    """avg 计算 + operation 字段返回"""
    out = await math_calculate_execute(
        {"data": [1, 2, 3], "operation": "avg", "precision": 2}, None
    )
    assert out["result"] == 2.0
    assert out["operation"] == "avg"
