"""C2: PDF 生成工具

使用 reportlab 生成 PDF 文档,支持两种内容模式:
- text: 纯文本(按段落换行)
- table: 表格数据(rows 为二维数组,首行视为表头)

输出:写入工作区文件系统(复用 file_write 的路径校验),返回路径 + 文件大小。

安全:
- 路径遍历防护:复用 file_write._validate_workspace_path
- 字段长度限制:单元格内容截断至 5000 字符,避免内存爆炸
- 表格行列上限:200 行 × 50 列
"""
import os
import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

# 安全上限
_MAX_CELL_LENGTH = 5000
_MAX_TABLE_ROWS = 200
_MAX_TABLE_COLS = 50


def _validate_workspace_path(path: str) -> str:
    """复用 file_write 的路径校验逻辑(避免重复实现)"""
    from tools.file_write import _validate_workspace_path as _validate
    return _validate(path)


def _truncate_cell(value: Any) -> str:
    """单元格值转字符串并截断"""
    text = str(value) if value is not None else ""
    if len(text) > _MAX_CELL_LENGTH:
        return text[:_MAX_CELL_LENGTH] + "...(截断)"
    return text


def _generate_pdf_sync(path: str, title: str, content_mode: str, text: str, rows: list) -> dict:
    """同步生成 PDF(放线程池执行)"""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

    # 确保目录存在
    os.makedirs(os.path.dirname(path), exist_ok=True)

    doc = SimpleDocTemplate(
        path,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title=title or "FlowGenie PDF",
    )

    styles = getSampleStyleSheet()
    title_style = styles["Title"]
    body_style = ParagraphStyle(
        "BodyCustom",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=11,
        leading=16,
        spaceAfter=6,
    )

    elements = []
    if title:
        elements.append(Paragraph(title, title_style))
        elements.append(Spacer(1, 0.5 * cm))

    if content_mode == "table":
        if not rows:
            raise ValueError("表格模式下 rows 不能为空")
        # 截断行列
        rows = rows[:_MAX_TABLE_ROWS]
        ncols = min(max(len(r) for r in rows), _MAX_TABLE_COLS)
        processed = []
        for r in rows:
            row = [_truncate_cell(c) for c in r[:ncols]]
            row += [""] * (ncols - len(row))
            processed.append(row)

        col_width = (A4[0] - 4 * cm) / ncols
        table = Table(processed, colWidths=[col_width] * ncols, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4f46e5")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f4f6")]),
        ]))
        elements.append(table)
    else:
        # text 模式:按段落渲染
        if not text:
            raise ValueError("text 模式下 text 不能为空")
        for line in text.split("\n"):
            # reportlab Paragraph 会自动换行;空行渲染为 Spacer
            if not line.strip():
                elements.append(Spacer(1, 0.3 * cm))
            else:
                # 转义 XML 特殊字符
                safe = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                elements.append(Paragraph(safe, body_style))

    doc.build(elements)

    size = os.path.getsize(path)
    return {
        "success": True,
        "path": path,
        "size": size,
        "title": title,
        "mode": content_mode,
        "rows_count": len(rows) if content_mode == "table" else 0,
    }


async def execute(params: dict, context: Any) -> dict:
    """C2: 生成 PDF 文档

    :param params: {
        path: 输出 PDF 路径(工作区内,如 reports/2026.pdf),
        title: 文档标题(可选),
        mode: "text" | "table"(默认 text),
        text: mode=text 时的正文内容,
        rows: mode=table 时的二维数组(首行表头),
    }
    :return: {success, path, size, title, mode, rows_count, warning}
    """
    path = params.get("path", "")
    title = params.get("title", "")
    mode = params.get("mode", "text")
    text = params.get("text", "")
    rows = params.get("rows", [])

    if not path:
        return {"success": False, "warning": "path 不能为空"}

    # 路径校验(工作区内,防止路径遍历)
    try:
        abs_path = _validate_workspace_path(path)
    except ValueError as e:
        return {"success": False, "warning": str(e)}

    if mode not in ("text", "table"):
        return {"success": False, "warning": f"mode 仅支持 text/table,当前: {mode}"}

    if mode == "text" and not text:
        return {"success": False, "warning": "text 模式下 text 不能为空"}
    if mode == "table" and not rows:
        return {"success": False, "warning": "table 模式下 rows 不能为空"}

    try:
        return await asyncio.to_thread(_generate_pdf_sync, abs_path, title, mode, text, rows)
    except Exception as e:
        logger.error(f"pdf_generator 失败: {e}")
        return {"success": False, "warning": f"PDF 生成失败: {e}"}
