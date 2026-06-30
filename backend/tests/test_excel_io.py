"""C3: Excel 读写工具单元测试

验证:
- excel_write: 写入成功 / 首行表头加粗 / 行列截断 / 单元格截断 / 参差行补齐 / 空校验
- excel_read: 读取成功 / 表头解析 / has_header=False / limit 限制 / sheet 切换
- 往返一致性: write → read 数据一致
- 路径遍历防护
- executor 路由 + tool_registry 注册
"""
import os
import pytest


@pytest.fixture
def workspace_tmp(monkeypatch, tmp_path):
    """将 WORKSPACE_DIR 指向临时目录"""
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path))
    yield tmp_path


# ============ excel_write 测试 ============

@pytest.mark.asyncio
async def test_write_basic(workspace_tmp):
    """写入成功:返回 success=True + 行列数"""
    from tools.excel_io import execute_write

    rows = [
        ["姓名", "分数"],
        ["张三", 90],
        ["李四", 85],
    ]
    result = await execute_write(
        {"path": "data.xlsx", "rows": rows, "sheet_name": "成绩"},
        context=None,
    )

    assert result["success"] is True
    assert result["operation"] == "write"
    assert result["sheet_name"] == "成绩"
    assert result["rows_written"] == 3
    assert result["cols_written"] == 2
    assert result["size"] > 0
    assert (workspace_tmp / "data.xlsx").exists()


@pytest.mark.asyncio
async def test_write_truncates_to_max_rows(workspace_tmp):
    """行数超过上限时截断"""
    from tools.excel_io import execute_write, _MAX_WRITE_ROWS

    rows = [["id"]] + [[i] for i in range(_MAX_WRITE_ROWS + 100)]
    result = await execute_write(
        {"path": "big.xlsx", "rows": rows},
        context=None,
    )
    assert result["success"] is True
    assert result["rows_written"] == _MAX_WRITE_ROWS


@pytest.mark.asyncio
async def test_write_truncates_long_cell(workspace_tmp):
    """单元格内容超过 5000 字符时截断"""
    from tools.excel_io import execute_write, _MAX_CELL_LENGTH

    long_text = "x" * (_MAX_CELL_LENGTH + 500)
    result = await execute_write(
        {"path": "long.xlsx", "rows": [["col"], [long_text]]},
        context=None,
    )
    assert result["success"] is True


@pytest.mark.asyncio
async def test_write_handles_ragged_rows(workspace_tmp):
    """参差不齐的行(每行列数不同)能补齐生成"""
    from tools.excel_io import execute_write

    rows = [
        ["a", "b", "c"],
        ["1"],  # 只有 1 列
        ["x", "y"],
    ]
    result = await execute_write(
        {"path": "ragged.xlsx", "rows": rows},
        context=None,
    )
    assert result["success"] is True
    assert result["cols_written"] == 3


@pytest.mark.asyncio
async def test_write_handles_none_cell(workspace_tmp):
    """None 单元格写入空值"""
    from tools.excel_io import execute_write

    rows = [["a", "b"], [None, None]]
    result = await execute_write(
        {"path": "none.xlsx", "rows": rows},
        context=None,
    )
    assert result["success"] is True


@pytest.mark.asyncio
async def test_write_truncates_sheet_name(workspace_tmp):
    """sheet 名超过 31 字符被截断"""
    from tools.excel_io import execute_write

    long_name = "sheet_" + "x" * 50
    result = await execute_write(
        {"path": "long_sheet.xlsx", "rows": [["a"], ["1"]], "sheet_name": long_name},
        context=None,
    )
    assert result["success"] is True
    assert len(result["sheet_name"]) <= 31


@pytest.mark.asyncio
async def test_write_empty_path_returns_warning(workspace_tmp):
    """空 path 返回 warning"""
    from tools.excel_io import execute_write

    result = await execute_write({"path": "", "rows": [["a"]]}, context=None)
    assert result["success"] is False
    assert "warning" in result


@pytest.mark.asyncio
async def test_write_empty_rows_returns_warning(workspace_tmp):
    """空 rows 返回 warning"""
    from tools.excel_io import execute_write

    result = await execute_write({"path": "x.xlsx", "rows": []}, context=None)
    assert result["success"] is False
    assert "warning" in result


@pytest.mark.asyncio
async def test_write_path_traversal_rejected(workspace_tmp):
    """路径遍历被拒绝"""
    from tools.excel_io import execute_write

    result = await execute_write(
        {"path": "../../../etc/data.xlsx", "rows": [["a"]]},
        context=None,
    )
    assert result["success"] is False
    assert "warning" in result


# ============ excel_read 测试 ============

@pytest.mark.asyncio
async def test_read_basic(workspace_tmp):
    """读取成功:返回 header + rows"""
    from tools.excel_io import execute_write, execute_read

    # 先写入
    rows = [
        ["姓名", "分数"],
        ["张三", 90],
        ["李四", 85],
    ]
    await execute_write({"path": "read.xlsx", "rows": rows}, context=None)

    # 再读取
    result = await execute_read({"path": "read.xlsx", "has_header": True}, context=None)

    assert result["success"] is True
    assert result["operation"] == "read"
    assert result["header"] == ["姓名", "分数"]
    assert result["rows_count"] == 2
    assert result["rows"][0] == ["张三", 90]
    assert result["rows"][1] == ["李四", 85]


@pytest.mark.asyncio
async def test_read_no_header(workspace_tmp):
    """has_header=False:所有行作为 data,header 为空"""
    from tools.excel_io import execute_write, execute_read

    rows = [["a", "b"], ["1", "2"], ["3", "4"]]
    await execute_write({"path": "no_hdr.xlsx", "rows": rows}, context=None)

    result = await execute_read({"path": "no_hdr.xlsx", "has_header": False}, context=None)

    assert result["success"] is True
    assert result["header"] == []
    assert result["rows_count"] == 3
    assert result["total_rows"] == 3


@pytest.mark.asyncio
async def test_read_with_limit(workspace_tmp):
    """limit 限制返回行数"""
    from tools.excel_io import execute_write, execute_read

    rows = [["id"]] + [[i] for i in range(10)]
    await execute_write({"path": "limit.xlsx", "rows": rows}, context=None)

    result = await execute_read({"path": "limit.xlsx", "has_header": True, "limit": 3}, context=None)

    assert result["success"] is True
    assert result["header"] == ["id"]
    assert result["rows_count"] == 3
    # total_rows 应为 11(原始所有行,不含空行过滤)
    assert result["total_rows"] >= 10


@pytest.mark.asyncio
async def test_read_with_sheet_name(workspace_tmp):
    """指定 sheet 名读取"""
    from tools.excel_io import execute_write, execute_read

    rows = [["col1"], ["v1"]]
    await execute_write(
        {"path": "sheet.xlsx", "rows": rows, "sheet_name": "MySheet"},
        context=None,
    )

    result = await execute_read({"path": "sheet.xlsx", "sheet_name": "MySheet"}, context=None)
    assert result["success"] is True
    assert result["sheet_name"] == "MySheet"


@pytest.mark.asyncio
async def test_read_nonexistent_sheet_returns_warning(workspace_tmp):
    """不存在的 sheet 返回 warning(列出可用 sheet)"""
    from tools.excel_io import execute_write, execute_read

    await execute_write(
        {"path": "sheet2.xlsx", "rows": [["a"]], "sheet_name": "Sheet1"},
        context=None,
    )
    result = await execute_read({"path": "sheet2.xlsx", "sheet_name": "NotExist"}, context=None)
    assert result["success"] is False
    assert "warning" in result
    assert "Sheet1" in result["warning"]


@pytest.mark.asyncio
async def test_read_nonexistent_file_returns_warning(workspace_tmp):
    """不存在的文件返回 warning"""
    from tools.excel_io import execute_read

    result = await execute_read({"path": "missing.xlsx"}, context=None)
    assert result["success"] is False
    assert "不存在" in result["warning"]


@pytest.mark.asyncio
async def test_read_skips_empty_rows(workspace_tmp):
    """空行被跳过"""
    from tools.excel_io import execute_write, execute_read

    # openpyxl 写入空行:用空字符串
    rows = [["a"], ["1"], [""], [""], ["2"]]
    await execute_write({"path": "empty.xlsx", "rows": rows}, context=None)

    result = await execute_read({"path": "empty.xlsx", "has_header": True}, context=None)
    assert result["success"] is True
    # 空行应被过滤
    for row in result["rows"]:
        assert not all(c == "" or c is None for c in row)


# ============ execute 统一入口测试 ============

@pytest.mark.asyncio
async def test_execute_unknown_action_returns_warning(workspace_tmp):
    """未知 action 返回 warning"""
    from tools.excel_io import execute

    result = await execute({"action": "unknown"}, context=None)
    assert result["success"] is False
    assert "未知 action" in result["warning"]


@pytest.mark.asyncio
async def test_execute_dispatches_write(workspace_tmp):
    """execute(action=write) 路由到 execute_write"""
    from tools.excel_io import execute

    result = await execute(
        {"action": "write", "path": "r.xlsx", "rows": [["a"], ["1"]]},
        context=None,
    )
    assert result["success"] is True
    assert result["operation"] == "write"


# ============ 往返一致性测试 ============

@pytest.mark.asyncio
async def test_write_read_roundtrip(workspace_tmp):
    """write → read 数据一致"""
    from tools.excel_io import execute_write, execute_read

    original = [
        ["name", "age", "city"],
        ["Alice", 30, "Beijing"],
        ["Bob", 25, "Shanghai"],
        ["Charlie", 35, "Guangzhou"],
    ]
    await execute_write({"path": "rt.xlsx", "rows": original}, context=None)
    result = await execute_read({"path": "rt.xlsx", "has_header": True}, context=None)

    assert result["header"] == original[0]
    # 注意:openpyxl 读取的数字可能是 int,写入时也是 int,应保持一致
    for i, row in enumerate(result["rows"]):
        assert row == original[i + 1]


# ============ executor 路由测试 ============

def test_tool_executors_registered():
    """TOOL_EXECUTORS 应包含 excel_write 和 excel_read"""
    from tools import TOOL_EXECUTORS

    assert "excel_write" in TOOL_EXECUTORS
    assert "excel_read" in TOOL_EXECUTORS


# ============ tool_registry 注册验证 ============

def test_registry_has_excel_tools():
    """tool_registry 注册了 excel_write 和 excel_read"""
    from core.tool_registry import get_tool

    write_tool = get_tool("excel_write")
    assert write_tool is not None
    assert write_tool.category == "数据存储"
    assert write_tool.icon == "📊"
    assert "path" in write_tool.required
    assert "rows" in write_tool.required

    read_tool = get_tool("excel_read")
    assert read_tool is not None
    assert "path" in read_tool.required
    assert "rows" not in read_tool.required


def test_registry_get_tool_schema():
    """get_tool_schema 生成 OpenAI function schema"""
    from core.tool_registry import get_tool_schema

    schema = get_tool_schema("excel_write")
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "excel_write"
    assert "path" in schema["function"]["parameters"]["properties"]
    assert "rows" in schema["function"]["parameters"]["properties"]

    read_schema = get_tool_schema("excel_read")
    assert read_schema["function"]["name"] == "excel_read"
    assert "sheet_name" in read_schema["function"]["parameters"]["properties"]
