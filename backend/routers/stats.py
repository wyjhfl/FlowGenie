"""执行统计路由 - 聚合 RunRecord 提供可观测性 Dashboard 数据"""
import io
import json
import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import func, case
from sqlalchemy.orm import Session

from db.database import get_db
from db.models import RunRecord, Workflow
from cachetools import TTLCache
import threading

router = APIRouter()
logger = logging.getLogger(__name__)

# Dashboard 聚合数据缓存(60s TTL,P2 优化:从 30s 扩展到 60s,降低全表扫描+JSON 解析频次)
_dashboard_cache: TTLCache = TTLCache(maxsize=4, ttl=60)
_stats_cache_lock = threading.Lock()


@router.get("/stats/dashboard")
def get_dashboard(days: int = Query(7, ge=1, le=90), db: Session = Depends(get_db)):
    """
    返回执行统计聚合数据：
    - total_runs / success_count / failed_count / partial_success_count / success_rate
    - avg_time_ms
    - trend: 最近 days 天每天的执行数与成功率(7/30/90 可选)
    - tool_usage: 按工具使用频率统计 Top 5（关联 Workflow.steps 解析 step_id→tool）
    - workflow_ranking: 按工作流聚合 Top 10（执行数/成功率/平均耗时）
    - failure_clusters: 失败原因关键词聚类 Top 5
    - duration_percentiles: 耗时分位数 {p50, p90, p95, max}
    """
    cache_key = f"dashboard:{days}"
    with _stats_cache_lock:
        cached = _dashboard_cache.get(cache_key)
        if cached is not None:
            logger.debug(f"dashboard 缓存命中 days={days}")
            return cached
    logger.info(f"dashboard 缓存未命中,开始聚合 days={days}")
    # 基础计数
    total_runs = db.query(func.count(RunRecord.id)).scalar() or 0
    success_count = db.query(func.count(RunRecord.id)).filter(
        RunRecord.status == "success"
    ).scalar() or 0
    failed_count = db.query(func.count(RunRecord.id)).filter(
        RunRecord.status == "failed"
    ).scalar() or 0
    partial_success_count = db.query(func.count(RunRecord.id)).filter(
        RunRecord.status == "partial_success"
    ).scalar() or 0

    success_rate = round(success_count / total_runs * 100, 1) if total_runs > 0 else 0.0

    # 平均耗时（仅统计已完成的执行，排除 running）
    avg_time_ms = db.query(func.avg(RunRecord.total_time_ms)).filter(
        RunRecord.status.in_(["success", "failed", "partial_success"])
    ).scalar()
    avg_time_ms = int(avg_time_ms) if avg_time_ms is not None else 0

    # 最近 days 天趋势：按日期聚合
    days_ago = datetime.now(timezone.utc) - timedelta(days=days - 1)
    trend_rows = (
        db.query(
            func.date(RunRecord.started_at).label("d"),
            func.count(RunRecord.id).label("total"),
            func.sum(
                case((RunRecord.status == "success", 1), else_=0)
            ).label("success"),
            func.sum(
                case((RunRecord.status == "failed", 1), else_=0)
            ).label("failed"),
        )
        .filter(RunRecord.started_at >= days_ago)
        .group_by(func.date(RunRecord.started_at))
        .order_by(func.date(RunRecord.started_at))
        .all()
    )
    # 构建日期→数据映射，补齐无执行的日期
    trend_map = {
        row.d: {
            "date": row.d,
            "total": int(row.total or 0),
            "success": int(row.success or 0),
            "failed": int(row.failed or 0),
        }
        for row in trend_rows
    }
    trend = []
    for i in range(days):
        day = (datetime.now(timezone.utc) - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d")
        if day in trend_map:
            trend.append(trend_map[day])
        else:
            trend.append({"date": day, "total": 0, "success": 0, "failed": 0})

    # 工具使用频率：关联 Workflow.steps 解析 step_id→tool，统计实际执行的步骤
    tool_counter: Counter = Counter()
    # 仅选取所需列，避免加载可能缺失的列（如历史 schema 漂移）
    runs_with_wf = (
        db.query(
            RunRecord.steps_result.label("run_steps_result"),
            Workflow.steps.label("wf_steps"),
        )
        .join(Workflow, RunRecord.workflow_id == Workflow.id)
        .all()
    )
    for row in runs_with_wf:
        try:
            steps_result = json.loads(row.run_steps_result) if row.run_steps_result else {}
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(f"解析 run_steps_result 失败,跳过: {e}")
            steps_result = {}
        if not steps_result:
            continue
        try:
            wf_steps = json.loads(row.wf_steps) if row.wf_steps else []
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(f"解析 wf_steps 失败,跳过: {e}")
            wf_steps = []
        # 构建 step_id→tool 映射
        step_tool_map = {
            s.get("id"): s.get("tool", "unknown")
            for s in wf_steps
            if isinstance(s, dict) and s.get("id")
        }
        # 统计实际执行（success/failed）的步骤工具
        for sid, sr in steps_result.items():
            if not isinstance(sr, dict):
                continue
            status = sr.get("status")
            if status in ("success", "failed"):
                tool = step_tool_map.get(sid, "unknown")
                # 触发器/控制节点不计入工具使用统计
                if tool in ("schedule_trigger", "webhook_trigger", "manual_trigger"):
                    continue
                tool_counter[tool] += 1

    tool_usage = [
        {"tool": tool, "count": count}
        for tool, count in tool_counter.most_common(5)
    ]

    # 工作流排名：按 workflow_id 聚合,join Workflow 取 name,按执行数降序 Top 10
    ranking_rows = (
        db.query(
            RunRecord.workflow_id.label("wf_id"),
            Workflow.name.label("wf_name"),
            func.count(RunRecord.id).label("total"),
            func.sum(case((RunRecord.status == "success", 1), else_=0)).label("success"),
            func.sum(case((RunRecord.status == "failed", 1), else_=0)).label("failed"),
            func.avg(RunRecord.total_time_ms).label("avg_time"),
        )
        .join(Workflow, RunRecord.workflow_id == Workflow.id)
        .group_by(RunRecord.workflow_id, Workflow.name)
        .order_by(func.count(RunRecord.id).desc())
        .limit(10)
        .all()
    )
    workflow_ranking = []
    for row in ranking_rows:
        total = int(row.total or 0)
        succ = int(row.success or 0)
        wf_avg = int(row.avg_time) if row.avg_time is not None else 0
        workflow_ranking.append({
            "workflow_id": row.wf_id,
            "name": row.wf_name or "(未命名)",
            "total": total,
            "success": succ,
            "failed": int(row.failed or 0),
            "success_rate": round(succ / total * 100, 1) if total > 0 else 0.0,
            "avg_time_ms": wf_avg,
        })

    # 失败原因聚类：取所有 failed 的 error 文本,按关键词匹配归类
    failure_rows = (
        db.query(RunRecord.error)
        .filter(RunRecord.status == "failed", RunRecord.error.isnot(None))
        .all()
    )
    # 聚类规则:关键词 → 聚类名(顺序敏感,首个匹配生效)
    cluster_rules = [
        (("smtp", "mail", "邮件"), "邮件推送失败"),
        (("timeout", "超时"), "网络超时"),
        (("429", "rate_limit", "限流"), "LLM 限流"),
        (("credential", "token", "凭证", "401", "403"), "凭证/认证失败"),
        (("webhook", "飞书", "telegram", "slack"), "推送渠道失败"),
    ]
    cluster_counter: Counter = Counter()
    cluster_samples: dict = {}
    for row in failure_rows:
        err = (row.error or "").strip()
        if not err:
            continue
        matched = "其他错误"
        err_lower = err.lower()
        for keywords, cluster_name in cluster_rules:
            if any(kw in err_lower or kw in err for kw in keywords):
                matched = cluster_name
                break
        cluster_counter[matched] += 1
        if matched not in cluster_samples:
            cluster_samples[matched] = err[:200]
    failure_clusters = [
        {"cluster": name, "count": count, "sample_error": cluster_samples.get(name, "")}
        for name, count in cluster_counter.most_common(5)
    ]

    # 耗时分位数：取全部已完成执行的 total_time_ms,排序后在 Python 端取分位
    duration_rows = (
        db.query(RunRecord.total_time_ms)
        .filter(RunRecord.status.in_(["success", "failed", "partial_success"]))
        .all()
    )
    durations = sorted([int(r.total_time_ms or 0) for r in duration_rows])
    if durations:
        def percentile(p: int) -> int:
            if not durations:
                return 0
            k = (len(durations) - 1) * (p / 100)
            f = int(k)
            c = min(f + 1, len(durations) - 1)
            if f == c:
                return durations[f]
            return int(durations[f] + (durations[c] - durations[f]) * (k - f))
        duration_percentiles = {
            "p50": percentile(50),
            "p90": percentile(90),
            "p95": percentile(95),
            "max": durations[-1],
        }
    else:
        duration_percentiles = {"p50": 0, "p90": 0, "p95": 0, "max": 0}

    # B4: LLM token 用量聚合——解析每条 RunRecord.token_usage,汇总总量与按模型分布
    token_rows = db.query(RunRecord.token_usage).filter(
        RunRecord.token_usage.isnot(None)
    ).all()
    token_stats = {
        "total_tokens": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "calls": 0,
        "by_model": {},
    }
    for row in token_rows:
        try:
            tu = json.loads(row.token_usage) if row.token_usage else None
        except (json.JSONDecodeError, TypeError):
            continue
        if not tu:
            continue
        token_stats["total_tokens"] += int(tu.get("total_tokens", 0) or 0)
        token_stats["prompt_tokens"] += int(tu.get("prompt_tokens", 0) or 0)
        token_stats["completion_tokens"] += int(tu.get("completion_tokens", 0) or 0)
        token_stats["calls"] += int(tu.get("calls", 0) or 0)
        for model, info in (tu.get("by_model") or {}).items():
            if model not in token_stats["by_model"]:
                token_stats["by_model"][model] = {
                    "total_tokens": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "calls": 0,
                }
            token_stats["by_model"][model]["total_tokens"] += int(info.get("total_tokens", 0) or 0)
            token_stats["by_model"][model]["prompt_tokens"] += int(info.get("prompt_tokens", 0) or 0)
            token_stats["by_model"][model]["completion_tokens"] += int(info.get("completion_tokens", 0) or 0)
            token_stats["by_model"][model]["calls"] += int(info.get("calls", 0) or 0)

    result = {
        "total_runs": total_runs,
        "success_count": success_count,
        "failed_count": failed_count,
        "partial_success_count": partial_success_count,
        "success_rate": success_rate,
        "avg_time_ms": avg_time_ms,
        "trend": trend,
        "tool_usage": tool_usage,
        "workflow_ranking": workflow_ranking,
        "failure_clusters": failure_clusters,
        "duration_percentiles": duration_percentiles,
        "token_stats": token_stats,
    }
    with _stats_cache_lock:
        _dashboard_cache[cache_key] = result
    return result


def invalidate_dashboard_cache():
    """供 execute.py 在工作流执行完成后调用,清空 dashboard 缓存"""
    with _stats_cache_lock:
        _dashboard_cache.clear()


def _style_header(ws, num_cols: int) -> None:
    """为工作表首行加粗 + 浅灰底色"""
    from openpyxl.styles import Font, PatternFill
    header_font = Font(bold=True)
    header_fill = PatternFill(start_color="DDDDDD", end_color="DDDDDD", fill_type="solid")
    for col_idx in range(1, num_cols + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.font = header_font
        cell.fill = header_fill


def _auto_width(ws, headers: list[str], rows: list[list]) -> None:
    """粗略按内容长度设置列宽(上限 60)"""
    for col_idx, header in enumerate(headers, 1):
        max_len = len(header)
        for row in rows:
            if col_idx <= len(row):
                val = str(row[col_idx - 1] if row[col_idx - 1] is not None else "")
                if len(val) > max_len:
                    max_len = len(val)
        col_letter = ws.cell(row=1, column=col_idx).column_letter
        ws.column_dimensions[col_letter].width = min(max_len + 2, 60)


def _build_dashboard_xlsx(stats: dict) -> bytes:
    """将 dashboard 聚合数据构建为多 sheet Excel 报表

    Sheets: 总览 / 趋势 / 工具排名 / 工作流排名 / 失败聚类 / Token用量 / 耗时分位数
    """
    from openpyxl import Workbook

    wb = Workbook()

    # Sheet 1: 总览(指标 key-value)
    ws1 = wb.active
    ws1.title = "总览"
    overview_rows = [
        ["指标", "值"],
        ["总执行数", stats.get("total_runs", 0)],
        ["成功数", stats.get("success_count", 0)],
        ["失败数", stats.get("failed_count", 0)],
        ["部分成功数", stats.get("partial_success_count", 0)],
        ["成功率(%)", stats.get("success_rate", 0)],
        ["平均耗时(ms)", stats.get("avg_time_ms", 0)],
    ]
    for row in overview_rows:
        ws1.append(row)
    _style_header(ws1, 2)
    _auto_width(ws1, overview_rows[0], overview_rows[1:])

    # Sheet 2: 趋势(每日执行数)
    ws2 = wb.create_sheet("趋势")
    trend_headers = ["日期", "总执行数", "成功数", "失败数"]
    ws2.append(trend_headers)
    trend_rows = []
    for t in stats.get("trend", []):
        row = [t.get("date", ""), t.get("total", 0), t.get("success", 0), t.get("failed", 0)]
        ws2.append(row)
        trend_rows.append(row)
    _style_header(ws2, len(trend_headers))
    _auto_width(ws2, trend_headers, trend_rows)

    # Sheet 3: 工具排名
    ws3 = wb.create_sheet("工具排名")
    tool_headers = ["工具", "使用次数"]
    ws3.append(tool_headers)
    tool_rows = []
    for t in stats.get("tool_usage", []):
        row = [t.get("tool", ""), t.get("count", 0)]
        ws3.append(row)
        tool_rows.append(row)
    _style_header(ws3, len(tool_headers))
    _auto_width(ws3, tool_headers, tool_rows)

    # Sheet 4: 工作流排名
    ws4 = wb.create_sheet("工作流排名")
    wf_headers = ["工作流ID", "名称", "执行数", "成功数", "失败数", "成功率(%)", "平均耗时(ms)"]
    ws4.append(wf_headers)
    wf_rows = []
    for w in stats.get("workflow_ranking", []):
        row = [w.get("workflow_id", ""), w.get("name", ""), w.get("total", 0),
               w.get("success", 0), w.get("failed", 0), w.get("success_rate", 0),
               w.get("avg_time_ms", 0)]
        ws4.append(row)
        wf_rows.append(row)
    _style_header(ws4, len(wf_headers))
    _auto_width(ws4, wf_headers, wf_rows)

    # Sheet 5: 失败聚类
    ws5 = wb.create_sheet("失败聚类")
    fc_headers = ["聚类", "次数", "示例错误"]
    ws5.append(fc_headers)
    fc_rows = []
    for c in stats.get("failure_clusters", []):
        row = [c.get("cluster", ""), c.get("count", 0), c.get("sample_error", "")]
        ws5.append(row)
        fc_rows.append(row)
    _style_header(ws5, len(fc_headers))
    _auto_width(ws5, fc_headers, fc_rows)

    # Sheet 6: Token 用量(仅有数据时添加)
    token_stats = stats.get("token_stats") or {}
    if token_stats.get("total_tokens", 0) > 0:
        ws6 = wb.create_sheet("Token用量")
        tk_headers = ["指标", "值"]
        ws6.append(tk_headers)
        tk_rows = [
            ["总 Token", token_stats.get("total_tokens", 0)],
            ["输入 Token", token_stats.get("prompt_tokens", 0)],
            ["输出 Token", token_stats.get("completion_tokens", 0)],
            ["调用次数", token_stats.get("calls", 0)],
        ]
        for r in tk_rows:
            ws6.append(r)
        # 按模型分布追加
        by_model = token_stats.get("by_model") or {}
        if by_model:
            ws6.append([])
            ws6.append(["按模型分布", ""])
            ws6.append(["模型", "总Token", "输入Token", "输出Token", "调用次数"])
            for model, info in by_model.items():
                ws6.append([model, info.get("total_tokens", 0), info.get("prompt_tokens", 0),
                            info.get("completion_tokens", 0), info.get("calls", 0)])
        _style_header(ws6, 2)

    # Sheet 7: 耗时分位数
    ws7 = wb.create_sheet("耗时分位数")
    dp_headers = ["分位数", "耗时(ms)"]
    ws7.append(dp_headers)
    dp = stats.get("duration_percentiles") or {}
    dp_rows = [
        ["P50", dp.get("p50", 0)],
        ["P90", dp.get("p90", 0)],
        ["P95", dp.get("p95", 0)],
        ["Max", dp.get("max", 0)],
    ]
    for r in dp_rows:
        ws7.append(r)
    _style_header(ws7, 2)
    _auto_width(ws7, dp_headers, dp_rows)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _build_content_disposition(filename: str) -> str:
    """构造 Content-Disposition 头,中文用 RFC 5987 filename*=UTF-8'' 编码"""
    import re
    ascii_fallback = re.sub(r"[^\x21-\x7e]", "_", filename).strip("_") or "export"
    encoded = quote(filename, safe="")
    return f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{encoded}"


@router.get("/stats/export")
def export_stats(
    format: str = Query("xlsx", description="导出格式:xlsx"),
    days: int = Query(7, ge=1, le=90, description="趋势天数"),
    db: Session = Depends(get_db),
):
    """D2: 导出 Dashboard 统计报表为多 sheet Excel

    Sheets: 总览 / 趋势 / 工具排名 / 工作流排名 / 失败聚类 / Token用量(可选) / 耗时分位数
    """
    if format != "xlsx":
        raise HTTPException(status_code=400, detail=f"不支持的格式: {format}(仅支持 xlsx)")

    # 复用 get_dashboard 聚合逻辑(含 30s 缓存)
    stats = get_dashboard(days=days, db=db)
    content = _build_dashboard_xlsx(stats)
    filename = f"FlowGenie报表_{days}天.xlsx"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": _build_content_disposition(filename)},
    )
