"""图表生成工具 - HTML 表格 / ASCII 柱状图 / ASCII 饼图"""
import json
from html import escape


async def execute(params: dict, context) -> dict:
    """
    根据数据生成图表
    :param params: { data, chart_type, title, x_field, y_field }
    :return: { chart_html, chart_type, data_points }
    """
    data = params.get("data")
    chart_type = params.get("chart_type", "table")
    title = params.get("title", "数据图表")
    x_field = params.get("x_field", "")
    y_field = params.get("y_field", "")

    if data is None:
        raise ValueError("data 参数不能为空")

    # data 可能是变量插值后的字符串（JSON），尝试解析
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            raise ValueError("data 为字符串但无法解析为 JSON，期望 list[dict]")

    if not isinstance(data, list):
        raise ValueError("data 必须是 list[dict]")

    data_points = len(data)

    if chart_type == "table":
        chart_html = _generate_table(data, title)
    elif chart_type == "bar":
        chart_html = _generate_bar(data, title, x_field, y_field)
    elif chart_type == "pie":
        chart_html = _generate_pie(data, title, x_field, y_field)
    else:
        raise ValueError(f"不支持的 chart_type: {chart_type}（支持 table/bar/pie）")

    return {"chart_html": chart_html, "chart_type": chart_type, "data_points": data_points}


def _generate_table(data: list, title: str) -> str:
    """生成 HTML 表格"""
    if not data:
        return f"<div><h3>{escape(title)}</h3><p>无数据</p></div>"

    # 收集所有字段（保持顺序）
    columns = []
    seen = set()
    for row in data:
        for k in row.keys():
            if k not in seen:
                seen.add(k)
                columns.append(k)

    rows_html = []
    for row in data:
        cells = []
        for col in columns:
            val = row.get(col, "")
            if isinstance(val, (dict, list)):
                val = json.dumps(val, ensure_ascii=False)
            cells.append(f"<td>{escape(str(val))}</td>")
        rows_html.append(f"<tr>{''.join(cells)}</tr>")

    header = "".join(f"<th>{escape(c)}</th>" for c in columns)
    return (
        f'<div class="chart-table">'
        f"<h3>{escape(title)}</h3>"
        f'<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;">'
        f"<thead><tr>{header}</tr></thead>"
        f"<tbody>{''.join(rows_html)}</tbody>"
        f"</table></div>"
    )


def _generate_bar(data: list, title: str, x_field: str, y_field: str) -> str:
    """生成 ASCII 柱状图（纯文本）"""
    if not data:
        return f"{title}\n无数据"

    if not x_field or not y_field:
        # 无字段指定时，用第一条记录的键
        first = data[0]
        if isinstance(first, dict):
            keys = list(first.keys())
            x_field = x_field or (keys[0] if keys else "")
            y_field = y_field or (keys[1] if len(keys) > 1 else keys[0] if keys else "")

    # 提取数值
    points = []
    for row in data:
        label = str(row.get(x_field, "")) if x_field else ""
        val = row.get(y_field, 0) if y_field else 0
        try:
            val = float(val)
        except (ValueError, TypeError):
            val = 0
        points.append((label, val))

    if not points:
        return f"{title}\n无数据"

    max_val = max(abs(v) for _, v in points) or 1
    max_label = max(len(label) for label, _ in points) if points else 0
    bar_width = 40

    lines = [title, ""]
    for label, val in points:
        bar_len = int(abs(val) / max_val * bar_width)
        bar = "█" * bar_len
        lines.append(f"{label.ljust(max_label)} | {bar} {val}")

    return "\n".join(lines)


def _generate_pie(data: list, title: str, x_field: str, y_field: str) -> str:
    """生成 ASCII 饼图描述（纯文本）"""
    if not data:
        return f"{title}\n无数据"

    if not x_field or not y_field:
        first = data[0]
        if isinstance(first, dict):
            keys = list(first.keys())
            x_field = x_field or (keys[0] if keys else "")
            y_field = y_field or (keys[1] if len(keys) > 1 else keys[0] if keys else "")

    # 提取数值
    points = []
    for row in data:
        label = str(row.get(x_field, "")) if x_field else ""
        val = row.get(y_field, 0) if y_field else 0
        try:
            val = float(val)
        except (ValueError, TypeError):
            val = 0
        points.append((label, val))

    if not points:
        return f"{title}\n无数据"

    total = sum(v for _, v in points) or 1
    lines = [title, ""]

    # 用不同字符表示扇区
    symbols = "●▲■◆★♥♣♠"
    for i, (label, val) in enumerate(points):
        pct = val / total * 100
        sym = symbols[i % len(symbols)]
        lines.append(f"{sym} {label}: {val} ({pct:.1f}%)")

    lines.append("")
    lines.append(f"总计: {total}")
    return "\n".join(lines)
