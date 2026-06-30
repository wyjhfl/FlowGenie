"""C3: Excel 读写工具

使用 openpyxl 读写 .xlsx 文件,提供两个工具:
- excel_write: 将二维数组写入 Excel(首行作为表头,加粗)
- excel_read: 读取 Excel 文件,返回二维数组

输出/输入:工作区文件系统(复用 file_write 的路径校验)。

安全:
- 路径遍历防护:复用 file_write._validate_workspace_path
- 单元格长度上限:5000 字符
- 表格行列上限:写入 1000 行 × 50 列;读取 5000 行 × 100 列
"""
import os
import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

# 安全上限
_MAX_CELL_LENGTH = 5000
_MAX_WRITE_ROWS = 1000
_MAX_WRITE_COLS = 50
_MAX_READ_ROWS = 5000
_MAX_READ_COLS = 100


def _validate_workspace_path(path: str) -> str:
    """复用 file_write 的路径校验逻辑"""
    from tools.file_write import _validate_workspace_path as _validate
    return _validate(path)


def _truncate_cell(value: Any) -> Any:
    """单元格值截断(保留原始类型,仅对超长字符串截断)"""
    if isinstance(value, str) and len(value) > _MAX_CELL_LENGTH:
        return value[:_MAX_CELL_LENGTH] + "...(截断)"
    return value


def _write_sync(path: str, rows: list[list], sheet_name: str) -> dict:
    """同步写入 Excel(放线程池执行)"""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment

    os.makedirs(os.path.dirname(path), exist_ok=True)

    # 截断行列
    rows = rows[:_MAX_WRITE_ROWS]
    ncols = min(max(len(r) for r in rows) if rows else 1, _MAX_WRITE_COLS)

    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name[:31]  # Excel sheet 名上限 31 字符

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="4F46E5", end_color="4F46E5", fill_type="solid")
    align = Alignment(vertical="center", wrap_text=True)

    for row_idx, row in enumerate(rows, start=1):
        for col_idx in range(1, ncols + 1):
            value = _truncate_cell(row[col_idx - 1]) if col_idx <= len(row) else ""
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.alignment = align
            if row_idx == 1:
                cell.font = header_font
                cell.fill = header_fill

    # 自动调整列宽(根据表头长度,简化估算)
    for col_idx in range(1, ncols + 1):
        max_len = 0
        for row_idx in range(1, min(len(rows) + 1, 100)):  # 仅扫描前 100 行估宽
            v = ws.cell(row=row_idx, column=col_idx).value
            if v is not None:
                max_len = max(max_len, len(str(v)))
        ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width = min(max_len + 4, 50)

    wb.save(path)
    size = os.path.getsize(path)

    return {
        "success": True,
        "operation": "write",
        "path": path,
        "size": size,
        "sheet_name": ws.title,
        "rows_written": len(rows),
        "cols_written": ncols,
    }


def _read_sync(path: str, sheet_name: str, has_header: bool, limit: int) -> dict:
    """同步读取 Excel(放线程池执行)"""
    from openpyxl import load_workbook

    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        # 选取 sheet:指定名 → 默认 active
        if sheet_name:
            if sheet_name not in wb.sheetnames:
                return {
                    "success": False,
                    "warning": f"sheet 不存在: {sheet_name}(可用: {wb.sheetnames})",
                }
            ws = wb[sheet_name]
        else:
            ws = wb.active

        rows = []
        header = []
        row_count = 0
        for row in ws.iter_rows(values_only=True):
            row_count += 1
            if row_count > _MAX_READ_ROWS:
                break
            # 截断列数
            row_list = [_truncate_cell(c) for c in row[:_MAX_READ_COLS]]
            # 跳过完全空行
            if all(c is None or c == "" for c in row_list):
                continue
            rows.append(row_list)

        # 应用 limit
        total_rows = len(rows)
        if has_header and rows:
            header = rows[0]
            data_rows = rows[1:limit + 1] if limit > 0 else rows[1:]
        else:
            header = []
            data_rows = rows[:limit] if limit > 0 else rows

        return {
            "success": True,
            "operation": "read",
            "path": path,
            "sheet_name": ws.title,
            "header": header,
            "rows": data_rows,
            "rows_count": len(data_rows),
            "total_rows": total_rows,
        }
    finally:
        wb.close()


# ===== 异步执行器 =====

async def execute(params: dict, context: Any) -> dict:
    """Excel 工具统一入口(按 action 分派)

    :param params: {action: "write"|"read", ...}
    :return: 操作结果 dict
    """
    action = params.get("action", "")
    if action == "write":
        return await execute_write(params, context)
    if action == "read":
        return await execute_read(params, context)
    return {
        "success": False,
        "warning": f"未知 action: {action}(支持 write / read)",
    }


async def execute_write(params: dict, context: Any) -> dict:
    """excel_write: 将 rows 写入 Excel 文件

    :param params: {path, rows, sheet_name?}
    """
    path = params.get("path", "")
    rows = params.get("rows", [])
    sheet_name = params.get("sheet_name", "Sheet1")

    if not path:
        return {"success": False, "warning": "path 不能为空"}
    if not rows:
        return {"success": False, "warning": "rows 不能为空"}

    try:
        abs_path = _validate_workspace_path(path)
    except ValueError as e:
        return {"success": False, "warning": str(e)}

    try:
        return await asyncio.to_thread(_write_sync, abs_path, rows, sheet_name)
    except Exception as e:
        logger.error(f"excel_write 失败: {e}")
        return {"success": False, "warning": f"Excel 写入失败: {e}"}


async def execute_read(params: dict, context: Any) -> dict:
    """excel_read: 读取 Excel 文件内容

    :param params: {path, sheet_name?, has_header?, limit?}
    """
    path = params.get("path", "")
    sheet_name = params.get("sheet_name", "")
    has_header = params.get("has_header", True)
    try:
        limit = int(params.get("limit", 0))
    except (TypeError, ValueError):
        limit = 0

    if not path:
        return {"success": False, "warning": "path 不能为空"}

    try:
        abs_path = _validate_workspace_path(path)
    except ValueError as e:
        return {"success": False, "warning": str(e)}

    if not os.path.exists(abs_path):
        return {"success": False, "warning": f"文件不存在: {path}"}

    try:
        return await asyncio.to_thread(_read_sync, abs_path, sheet_name, has_header, limit)
    except Exception as e:
        logger.error(f"excel_read 失败: {e}")
        return {"success": False, "warning": f"Excel 读取失败: {e}"}
