"""D1/D3: 执行记录导出 API 集成测试

覆盖:
- 单次执行 CSV 导出:steps_result 展平为行,含表头 + UTF-8 BOM
- 单次执行 JSON 导出:完整 steps_result + logs + token_usage
- 工作流执行列表 CSV 导出:每行一次执行
- 404:run/workflow 不存在
- 400:不支持的格式
- 文件名安全化
- Content-Disposition 头
"""
import io
import json
from datetime import datetime, timezone
import pytest
from db.models import RunRecord, Workflow


# ========== 辅助构造 ==========

def _make_workflow(test_db, wf_id="wf-1", name="测试工作流"):
    wf = Workflow(
        id=wf_id,
        name=name,
        steps=json.dumps([{"id": "s1", "name": "步骤1", "tool": "http_request", "params": {}}]),
        edges=json.dumps([]),
    )
    test_db.add(wf)
    test_db.commit()
    return wf


def _make_run(test_db, run_id="run-1", workflow_id="wf-1", status="success",
              steps_result=None, logs=None, token_usage=None):
    # 显式区分"未传"(用默认)与"传 None/{}"(用空值)
    if steps_result is None:
        steps_result = {
            "s1": {
                "name": "请求",
                "tool": "http_request",
                "status": "success",
                "result": {"body": "ok"},
                "duration_ms": 150,
                "error": None,
            },
        }
    if logs is None:
        logs = [{"level": "INFO", "msg": "started"}]
    run = RunRecord(
        id=run_id,
        workflow_id=workflow_id,
        trigger_type="manual",
        status=status,
        total_time_ms=150,
        started_at=datetime(2026, 6, 28, 10, 0, 0, tzinfo=timezone.utc),
        finished_at=datetime(2026, 6, 28, 10, 0, 0, 150000, tzinfo=timezone.utc),
        steps_result=json.dumps(steps_result),
        logs=json.dumps(logs),
        token_usage=json.dumps(token_usage) if token_usage else None,
        error=None if status == "success" else "失败原因",
    )
    test_db.add(run)
    test_db.commit()
    return run


# ========== 单次执行 CSV 导出(D1)==========

@pytest.mark.asyncio
async def test_export_run_csv_success(client, test_db):
    """CSV 导出:返回 steps_result 展平后的 CSV,含表头"""
    _make_workflow(test_db)
    _make_run(test_db, run_id="run-csv-1")

    resp = await client.get("/api/runs/run-csv-1/export?format=csv")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    # Content-Disposition 包含文件名
    assert "attachment" in resp.headers["content-disposition"]
    assert "run-csv-1_steps.csv" in resp.headers["content-disposition"]

    content = resp.text
    # UTF-8 BOM(Excel 中文兼容)
    assert content.startswith("\ufeff")
    # 表头
    assert "step_id" in content
    assert "name" in content
    assert "tool" in content
    assert "status" in content
    assert "result" in content
    # 步骤数据
    assert "s1" in content
    assert "http_request" in content
    assert "success" in content


@pytest.mark.asyncio
async def test_export_run_csv_multiple_steps(client, test_db):
    """多步骤 CSV 导出:每步一行"""
    _make_workflow(test_db)
    _make_run(test_db, run_id="run-multi", steps_result={
        "s1": {"name": "请求", "tool": "http_request", "status": "success", "result": "ok", "duration_ms": 50},
        "s2": {"name": "摘要", "tool": "llm_summary", "status": "success", "result": "摘要内容", "duration_ms": 100},
        "s3": {"name": "写入", "tool": "file_write", "status": "failed", "result": "", "duration_ms": 5, "error": "权限不足"},
    })

    resp = await client.get("/api/runs/run-multi/export?format=csv")
    assert resp.status_code == 200

    lines = resp.text.strip().split("\n")
    # 1 表头 + 3 数据行
    assert len(lines) >= 4
    assert "s1" in resp.text
    assert "s2" in resp.text
    assert "s3" in resp.text
    assert "权限不足" in resp.text


@pytest.mark.asyncio
async def test_export_run_csv_result_truncated(client, test_db):
    """超长 result 被截断到 5000 字符"""
    _make_workflow(test_db)
    long_result = "x" * 10000
    _make_run(test_db, run_id="run-long", steps_result={
        "s1": {"name": "请求", "tool": "http_request", "status": "success", "result": long_result, "duration_ms": 10},
    })

    resp = await client.get("/api/runs/run-long/export?format=csv")
    assert resp.status_code == 200
    # 截断标记存在
    assert "(截断)" in resp.text


@pytest.mark.asyncio
async def test_export_run_csv_empty_steps(client, test_db):
    """空 steps_result 仍返回 CSV(仅表头)"""
    _make_workflow(test_db)
    _make_run(test_db, run_id="run-empty", steps_result={})

    resp = await client.get("/api/runs/run-empty/export?format=csv")
    assert resp.status_code == 200
    # 仅表头
    lines = resp.text.strip().split("\n")
    assert len(lines) == 1
    assert "step_id" in lines[0]


# ========== 单次执行 JSON 导出(D3)==========

@pytest.mark.asyncio
async def test_export_run_json_success(client, test_db):
    """JSON 导出:包含完整 steps_result + logs + token_usage"""
    _make_workflow(test_db)
    _make_run(
        test_db,
        run_id="run-json-1",
        logs=[{"level": "INFO", "msg": "started"}, {"level": "INFO", "msg": "done"}],
        token_usage={"total_tokens": 100, "by_model": {"gpt-4o": {"prompt": 50, "completion": 50}}},
    )

    resp = await client.get("/api/runs/run-json-1/export?format=json")
    assert resp.status_code == 200
    assert "application/json" in resp.headers["content-type"]
    assert "run-json-1.json" in resp.headers["content-disposition"]

    payload = json.loads(resp.text)
    assert payload["id"] == "run-json-1"
    assert payload["workflow_id"] == "wf-1"
    assert payload["status"] == "success"
    assert "s1" in payload["steps_result"]
    assert len(payload["logs"]) == 2
    assert payload["token_usage"]["total_tokens"] == 100


@pytest.mark.asyncio
async def test_export_run_json_without_logs_token(client, test_db):
    """JSON 导出:logs/token_usage 为空时仍正常"""
    _make_workflow(test_db)
    _make_run(test_db, run_id="run-min", logs=[], token_usage=None)

    resp = await client.get("/api/runs/run-min/export?format=json")
    assert resp.status_code == 200
    payload = json.loads(resp.text)
    assert payload["logs"] == []
    assert payload["token_usage"] is None


# ========== 单次执行 Markdown 导出 ==========

@pytest.mark.asyncio
async def test_export_run_markdown_success(client, test_db):
    """Markdown 导出:含标题、工作流名、步骤详情"""
    _make_workflow(test_db, name="监控流")
    _make_run(test_db, run_id="run-md-1")

    resp = await client.get("/api/runs/run-md-1/export?format=markdown")
    assert resp.status_code == 200
    assert "text/markdown" in resp.headers["content-type"]
    assert "run-md-1.md" in resp.headers["content-disposition"]

    content = resp.text
    # 报告标题
    assert "# 工作流执行报告" in content
    # 工作流名
    assert "监控流" in content
    # 执行 ID
    assert "run-md-1" in content
    # 步骤详情节
    assert "## 步骤详情" in content
    # 步骤项(包含工具名)
    assert "http_request" in content


@pytest.mark.asyncio
async def test_export_run_markdown_empty_steps(client, test_db):
    """Markdown 导出:空 steps_result 显示"无步骤数据" """
    _make_workflow(test_db)
    _make_run(test_db, run_id="run-md-empty", steps_result={})

    resp = await client.get("/api/runs/run-md-empty/export?format=markdown")
    assert resp.status_code == 200
    assert "无步骤数据" in resp.text


# ========== 单次执行 Excel 导出(D2)==========

@pytest.mark.asyncio
async def test_export_run_xlsx_success(client, test_db):
    """xlsx 导出:返回有效 Excel 文件,含表头与步骤数据"""
    _make_workflow(test_db)
    _make_run(test_db, run_id="run-xlsx-1")

    resp = await client.get("/api/runs/run-xlsx-1/export?format=xlsx")
    assert resp.status_code == 200
    assert "spreadsheet" in resp.headers["content-type"]
    assert "run-xlsx-1_steps.xlsx" in resp.headers["content-disposition"]
    # 响应体为二进制 xlsx(zip 格式,以 PK 开头)
    assert resp.content[:2] == b"PK"
    # 用 openpyxl 验证内容
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(resp.content))
    assert "步骤结果" in wb.sheetnames
    ws = wb["步骤结果"]
    # 表头
    assert ws.cell(1, 1).value == "step_id"
    assert ws.cell(1, 3).value == "tool"
    # 数据行(s1 步骤)
    assert ws.cell(2, 1).value == "s1"
    assert ws.cell(2, 3).value == "http_request"


@pytest.mark.asyncio
async def test_export_run_xlsx_empty_steps(client, test_db):
    """xlsx 导出:空 steps_result 仍返回有效 Excel(仅表头)"""
    _make_workflow(test_db)
    _make_run(test_db, run_id="run-xlsx-empty", steps_result={})

    resp = await client.get("/api/runs/run-xlsx-empty/export?format=xlsx")
    assert resp.status_code == 200
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(resp.content))
    ws = wb["步骤结果"]
    # 仅表头行
    assert ws.max_row == 1
    assert ws.cell(1, 1).value == "step_id"


# ========== 404 / 400 错误处理 ==========

@pytest.mark.asyncio
async def test_export_run_not_found(client, test_db):
    """run_id 不存在返回 404"""
    resp = await client.get("/api/runs/nonexistent/export?format=csv")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_export_run_unsupported_format(client, test_db):
    """不支持的格式返回 400"""
    _make_workflow(test_db)
    _make_run(test_db, run_id="run-bad-fmt")

    resp = await client.get("/api/runs/run-bad-fmt/export?format=xml")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_export_run_default_format_is_csv(client, test_db):
    """未传 format 参数时默认 csv"""
    _make_workflow(test_db)
    _make_run(test_db, run_id="run-default")

    resp = await client.get("/api/runs/run-default/export")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]


# ========== 工作流执行列表 CSV 导出(D1)==========

@pytest.mark.asyncio
async def test_export_workflow_runs_csv_success(client, test_db):
    """工作流执行列表 CSV 导出:每行一次执行"""
    _make_workflow(test_db, name="监控流")
    _make_run(test_db, run_id="r1", status="success")
    _make_run(test_db, run_id="r2", status="failed")
    _make_run(test_db, run_id="r3", status="success")

    resp = await client.get("/api/workflows/wf-1/runs/export?format=csv")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    # 文件名从工作流名称派生(中文通过 RFC 5987 编码,latin-1 头中只可见百分比编码)
    assert "_runs.csv" in resp.headers["content-disposition"]
    assert "filename*=UTF-8''" in resp.headers["content-disposition"]

    content = resp.text
    # UTF-8 BOM
    assert content.startswith("\ufeff")
    # 表头
    assert "run_id" in content
    assert "workflow_id" in content
    assert "status" in content
    assert "trigger_type" in content
    # 三次执行
    assert "r1" in content
    assert "r2" in content
    assert "r3" in content
    assert "success" in content
    assert "failed" in content


@pytest.mark.asyncio
async def test_export_workflow_runs_csv_empty(client, test_db):
    """工作流无执行记录时返回空 CSV(仅表头)"""
    _make_workflow(test_db, name="空流")

    resp = await client.get("/api/workflows/wf-1/runs/export?format=csv")
    assert resp.status_code == 200
    lines = resp.text.strip().split("\n")
    # 仅表头
    assert len(lines) == 1
    assert "run_id" in lines[0]


@pytest.mark.asyncio
async def test_export_workflow_runs_workflow_not_found(client, test_db):
    """工作流不存在返回 404"""
    resp = await client.get("/api/workflows/nonexistent/runs/export?format=csv")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_export_workflow_runs_unsupported_format(client, test_db):
    """工作流执行列表不支持 json 格式(只支持 csv/xlsx)"""
    _make_workflow(test_db)

    resp = await client.get("/api/workflows/wf-1/runs/export?format=json")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_export_workflow_runs_xlsx_success(client, test_db):
    """工作流执行列表 xlsx 导出:Excel 单 sheet 含多次执行"""
    _make_workflow(test_db, name="监控流")
    _make_run(test_db, run_id="rx1", status="success")
    _make_run(test_db, run_id="rx2", status="failed")

    resp = await client.get("/api/workflows/wf-1/runs/export?format=xlsx")
    assert resp.status_code == 200
    assert "spreadsheet" in resp.headers["content-type"]
    assert resp.content[:2] == b"PK"
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(resp.content))
    assert "执行列表" in wb.sheetnames
    ws = wb["执行列表"]
    # 表头
    assert ws.cell(1, 1).value == "run_id"
    assert ws.cell(1, 4).value == "status"
    # 两条数据
    assert ws.cell(2, 1).value == "rx1"
    assert ws.cell(3, 1).value == "rx2"


# ========== 文件名安全化 ==========

@pytest.mark.asyncio
async def test_export_run_csv_filename_sanitized(client, test_db):
    """run_id 含特殊字符(* ?)时文件名被安全化(URL 路径不允许 /)"""
    _make_workflow(test_db)
    _make_run(test_db, run_id="run-with*special")

    resp = await client.get("/api/runs/run-with*special/export?format=csv")
    assert resp.status_code == 200
    cd = resp.headers["content-disposition"]
    # filename*= 后的编码文件名中不应含 *(已被 _ 替换)
    # cd 形如:attachment; filename="run-with_special_steps.csv"; filename*=UTF-8''run-with_special_steps.csv
    encoded_part = cd.split("filename*=UTF-8''")[1] if "filename*=UTF-8''" in cd else ""
    assert "*" not in encoded_part
    assert "_" in encoded_part  # * 被替换为 _


@pytest.mark.asyncio
async def test_export_workflow_runs_filename_from_workflow_name(client, test_db):
    """工作流名含特殊字符时文件名安全化"""
    _make_workflow(test_db, name="我的监控流*名称")
    _make_run(test_db, run_id="r1")

    resp = await client.get("/api/workflows/wf-1/runs/export?format=csv")
    assert resp.status_code == 200
    cd = resp.headers["content-disposition"]
    # 编码后的文件名部分不应含 *(已被 _ 替换为 %5F 或保留 _)
    encoded_part = cd.split("filename*=UTF-8''")[1] if "filename*=UTF-8''" in cd else ""
    assert "*" not in encoded_part
    # 中文通过 RFC 5987 filename*=UTF-8'' 百分比编码
    assert "filename*=UTF-8''" in cd
    assert "%E6%88%91" in cd  # "我" 的 UTF-8 百分比编码
