"""D1/D3: 执行记录导出路由

提供两个端点:
- GET /api/runs/{run_id}/export?format=csv|json  — 导出单次执行的 steps_result/logs/token_usage
- GET /api/workflows/{workflow_id}/runs/export?format=csv  — 导出某工作流下的 RunRecord 列表

设计要点:
- CSV 用标准库 csv(无新依赖)
- JSON 包含完整 steps_result + logs + token_usage,便于离线分析/迁移
- 文件名安全化:特殊字符替换为 _,中文保留
- HTTP 头为 latin-1,中文文件名需用 RFC 5987 filename*=UTF-8''... 编码
- 404:run/workflow 不存在时返回
- 复用 workflows 路由的 db 依赖注入模式
"""
import csv
import io
import json
import logging
import re
from datetime import timezone
from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy.orm import Session

from db.database import get_db
from db.models import Workflow, RunRecord

router = APIRouter()
logger = logging.getLogger(__name__)


def _sanitize_filename(name: str) -> str:
    """文件名安全化:仅保留字母数字中文下划线连字符"""
    safe = re.sub(r"[^\w\u4e00-\u9fff\-]", "_", name).strip("_")
    return safe or "flowgenie"


def _build_content_disposition(filename: str) -> str:
    """构造 Content-Disposition 头,中文用 RFC 5987 filename*=UTF-8'' 编码

    返回形如: attachment; filename="fallback.csv"; filename*=UTF-8''%E6%88%91.csv
    """
    # fallback: ASCII 安全化(中文/特殊字符 → _),保证 latin-1 可编码
    ascii_fallback = re.sub(r"[^\x21-\x7e]", "_", filename).strip("_") or "export"
    # 主文件名:RFC 5987 UTF-8 百分比编码(支持中文)
    encoded = quote(filename, safe="")
    return f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{encoded}"


def _flatten_steps_result(steps_result: dict) -> list[dict]:
    """将 steps_result(dict)展平为行列表,每行代表一个步骤结果

    steps_result 结构示例:
    {
        "step_1": {"name": "...", "tool": "...", "status": "success", "result": {...}, "duration_ms": 123, "error": null},
        ...
    }
    """
    rows = []
    for step_id, info in steps_result.items():
        if not isinstance(info, dict):
            continue
        # result 可能是 dict/list/str,序列化为字符串便于 CSV 单元格
        result = info.get("result", info.get("output", ""))
        if isinstance(result, (dict, list)):
            result_str = json.dumps(result, ensure_ascii=False)
        else:
            result_str = str(result) if result is not None else ""
        # 截断超长结果(避免 CSV 单元格过大)
        if len(result_str) > 5000:
            result_str = result_str[:5000] + "...(截断)"
        rows.append({
            "step_id": step_id,
            "name": info.get("name", ""),
            "tool": info.get("tool", ""),
            "status": info.get("status", ""),
            "duration_ms": info.get("duration_ms", info.get("duration", 0)),
            "result": result_str,
            "error": info.get("error", "") or "",
        })
    return rows


def _runs_to_csv(runs: list) -> str:
    """将 RunRecord 列表序列化为 CSV 字符串(每行一次执行)"""
    output = io.StringIO()
    # UTF-8 BOM,确保 Excel 正确识别中文
    output.write("\ufeff")
    writer = csv.writer(output)
    writer.writerow([
        "run_id", "workflow_id", "trigger_type", "status",
        "total_time_ms", "started_at", "finished_at", "error",
    ])
    for r in runs:
        writer.writerow([
            r.id,
            r.workflow_id,
            r.trigger_type,
            r.status,
            r.total_time_ms or 0,
            r.started_at.isoformat() if r.started_at else "",
            r.finished_at.isoformat() if r.finished_at else "",
            r.error or "",
        ])
    return output.getvalue()


def _steps_to_csv(rows: list[dict]) -> str:
    """将步骤结果行列表序列化为 CSV 字符串"""
    output = io.StringIO()
    output.write("\ufeff")  # UTF-8 BOM
    writer = csv.DictWriter(
        output,
        fieldnames=["step_id", "name", "tool", "status", "duration_ms", "result", "error"],
    )
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return output.getvalue()


def _steps_to_xlsx(rows: list[dict]) -> bytes:
    """将步骤结果行列表序列化为 xlsx 字节(单 sheet "步骤结果")"""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = "步骤结果"
    headers = ["step_id", "name", "tool", "status", "duration_ms", "result", "error"]
    ws.append(headers)
    # 表头加粗 + 浅灰底色
    header_font = Font(bold=True)
    header_fill = PatternFill(start_color="DDDDDD", end_color="DDDDDD", fill_type="solid")
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.font = header_font
        cell.fill = header_fill
    for row in rows:
        ws.append([
            row.get("step_id", ""),
            row.get("name", ""),
            row.get("tool", ""),
            row.get("status", ""),
            row.get("duration_ms", 0),
            row.get("result", ""),
            row.get("error", ""),
        ])
    # 自动列宽(粗略按内容长度估算)
    for col_idx, header in enumerate(headers, 1):
        max_len = len(header)
        for row in rows:
            val = str(row.get(header, ""))
            if len(val) > max_len:
                max_len = len(val)
        ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width = min(max_len + 2, 60)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _runs_to_xlsx(runs: list) -> bytes:
    """将 RunRecord 列表序列化为 xlsx 字节(单 sheet "执行列表")"""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = "执行列表"
    headers = ["run_id", "workflow_id", "trigger_type", "status",
               "total_time_ms", "started_at", "finished_at", "error"]
    ws.append(headers)
    header_font = Font(bold=True)
    header_fill = PatternFill(start_color="DDDDDD", end_color="DDDDDD", fill_type="solid")
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.font = header_font
        cell.fill = header_fill
    for r in runs:
        ws.append([
            r.id, r.workflow_id, r.trigger_type, r.status,
            r.total_time_ms or 0,
            r.started_at.isoformat() if r.started_at else "",
            r.finished_at.isoformat() if r.finished_at else "",
            r.error or "",
        ])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _to_local_str(dt) -> str:
    """UTC datetime 转本地时区可读字符串;为空时返回"未记录" """
    if not dt:
        return "未记录"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _build_markdown(run: RunRecord, workflow_name: str = "") -> str:
    """生成 Markdown 执行报告(便于阅读和分享)"""
    steps_result = json.loads(run.steps_result) if run.steps_result else {}
    lines = [
        "# 工作流执行报告",
        "",
        f"- **工作流**: {workflow_name}",
        f"- **执行 ID**: {run.id}",
        f"- **触发类型**: {run.trigger_type}",
        f"- **状态**: {run.status}",
        f"- **开始时间**: {_to_local_str(run.started_at)}",
        f"- **结束时间**: {_to_local_str(run.finished_at)}",
        f"- **总耗时**: {run.total_time_ms} ms",
        "",
        "## 步骤详情",
        "",
    ]
    if not steps_result:
        lines.append("无步骤数据")
    else:
        for idx, (step_id, sr) in enumerate(steps_result.items(), 1):
            if not isinstance(sr, dict):
                continue
            output = sr.get("output", sr.get("result"))
            output_str = json.dumps(output, ensure_ascii=False, indent=2, default=str)
            if len(output_str) > 2000:
                output_str = output_str[:2000]
            error = sr.get("error") or "无"
            lines.extend([
                f"### {idx}. {sr.get('name', '')} (`{step_id}`)",
                f"- **工具**: {sr.get('tool', '')}",
                f"- **状态**: {sr.get('status', '')}",
                f"- **耗时**: {sr.get('duration_ms', sr.get('time_ms', ''))} ms",
                "- **输出**:",
                "```",
                output_str,
                "```",
                f"- **错误**: {error}",
                "",
            ])
    return "\n".join(lines)


@router.get("/runs/{run_id}/export")
def export_run(
    run_id: str,
    format: str = Query("csv", description="导出格式:csv | json | markdown | xlsx"),
    db: Session = Depends(get_db),
):
    """D1/D3/D2: 导出单次执行记录

    - format=csv: 导出 steps_result 为 CSV(每行一个步骤)
    - format=json: 导出完整 run(steps_result + logs + token_usage)
    - format=markdown: 生成可读的 Markdown 执行报告
    - format=xlsx: 导出 steps_result 为 Excel(单 sheet,含表头样式)
    """
    run = db.query(RunRecord).filter(RunRecord.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="执行记录不存在")

    if format == "csv":
        steps_result = json.loads(run.steps_result) if run.steps_result else {}
        rows = _flatten_steps_result(steps_result)
        content = _steps_to_csv(rows)
        filename = f"{_sanitize_filename(run_id)}_steps.csv"
        return PlainTextResponse(
            content,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": _build_content_disposition(filename)},
        )

    if format == "json":
        payload = run.to_dict()
        content = json.dumps(payload, ensure_ascii=False, indent=2)
        filename = f"{_sanitize_filename(run_id)}.json"
        return PlainTextResponse(
            content,
            media_type="application/json; charset=utf-8",
            headers={"Content-Disposition": _build_content_disposition(filename)},
        )

    if format == "markdown":
        workflow_name = run.workflow.name if run.workflow else ""
        content = _build_markdown(run, workflow_name)
        filename = f"{_sanitize_filename(run_id)}.md"
        return PlainTextResponse(
            content,
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": _build_content_disposition(filename)},
        )

    if format == "xlsx":
        steps_result = json.loads(run.steps_result) if run.steps_result else {}
        rows = _flatten_steps_result(steps_result)
        content = _steps_to_xlsx(rows)
        filename = f"{_sanitize_filename(run_id)}_steps.xlsx"
        return Response(
            content=content,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": _build_content_disposition(filename)},
        )

    raise HTTPException(status_code=400, detail=f"不支持的格式: {format}(支持 csv / json / markdown / xlsx)")


@router.get("/workflows/{workflow_id}/runs/export")
def export_workflow_runs(
    workflow_id: str,
    format: str = Query("csv", description="导出格式:csv | xlsx"),
    db: Session = Depends(get_db),
):
    """D1/D2: 导出工作流下的执行记录列表

    - format=csv: 每行一次执行(不含步骤详情)
    - format=xlsx: Excel 单 sheet(含表头样式)
    """
    # 工作流必须存在
    wf = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not wf:
        raise HTTPException(status_code=404, detail="工作流不存在")

    runs = (
        db.query(RunRecord)
        .filter(RunRecord.workflow_id == workflow_id)
        .order_by(RunRecord.started_at.desc())
        .limit(500)
        .all()
    )

    if format == "csv":
        content = _runs_to_csv(runs)
        filename = f"{_sanitize_filename(wf.name)}_runs.csv"
        return PlainTextResponse(
            content,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": _build_content_disposition(filename)},
        )

    if format == "xlsx":
        content = _runs_to_xlsx(runs)
        filename = f"{_sanitize_filename(wf.name)}_runs.xlsx"
        return Response(
            content=content,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": _build_content_disposition(filename)},
        )

    raise HTTPException(status_code=400, detail=f"不支持的格式: {format}(支持 csv / xlsx)")
