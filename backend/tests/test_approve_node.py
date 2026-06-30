"""A1: approve_node 人工审批节点测试

覆盖暂停/恢复/拒绝/超时四条路径:
- approve_node 触发 PauseExecution 暂停工作流
- resume_execution(approved) 恢复执行后续步骤
- resume_execution(rejected) 标记失败并跳过后续步骤
- approve_node 作为末步,approved 时直接成功
- pause_run 序列化 context 到 RunRecord
- _cleanup_expired_approvals 超时清理(24h)
"""
import json
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
from sqlalchemy.orm import sessionmaker

from engine.executor import WorkflowExecutor
from tools import TOOL_EXECUTORS
from db.models import Workflow, RunRecord


# ---------- 辅助函数 ----------

def _make_step(sid, tool, params=None, name=None):
    """构造步骤字典"""
    return {
        "id": sid,
        "name": name or sid,
        "tool": tool,
        "params": params or {},
    }


def _make_edge(from_id, to_id):
    """构造边字典"""
    return {"from": from_id, "to": to_id}


def _make_approve_flow():
    """构造含 approve_node 的标准三步工作流:
    step_1: manual_trigger → step_2: approve_node → step_3: llm_summary
    """
    steps = [
        _make_step("step_1", "manual_trigger", {}, "触发"),
        _make_step("step_2", "approve_node", {
            "message": "请审批",
            "approvers": [],
            "timeout_hours": 24,
        }, "审批"),
        _make_step("step_3", "llm_summary", {"text": "{{step_2.decision}}"}, "摘要"),
    ]
    edges = [
        _make_edge("step_1", "step_2"),
        _make_edge("step_2", "step_3"),
    ]
    return steps, edges


def _make_executor_with_tools():
    """构造独立 executor 并注册全部 TOOL_EXECUTORS。

    approve_node 由 executor 内部拦截(抛出 PauseExecution),不会真正调用占位 execute。
    使用独立实例避免污染全局 executor 单例。
    """
    executor = WorkflowExecutor()
    for name, func in TOOL_EXECUTORS.items():
        executor.register_executor(name, func)
    return executor


def _mock_llm_summary(executor):
    """将 executor 的 llm_summary 替换为返回固定 dict 的 mock(避免真实 LLM 调用)。

    返回 mock 函数本身,便于测试断言调用情况。
    """
    async def _fake_llm_summary(params, context):
        return {"summary": "ok"}
    executor.tool_executors["llm_summary"] = _fake_llm_summary
    return _fake_llm_summary


def _build_paused_context(result, trigger_data=None):
    """从 execute 返回的 result 构造 resume_execution 所需的 paused_context。

    结构: {step_results, trigger_data, logs, token_usage}
    """
    return {
        "step_results": result["steps_result"],
        "trigger_data": trigger_data or {},
        "logs": result.get("logs", []),
        "token_usage": result.get("token_usage") or {
            "prompt_tokens": 0, "completion_tokens": 0,
            "total_tokens": 0, "calls": 0, "by_model": {},
        },
    }


# ---------- 暂停路径 ----------

@pytest.mark.asyncio
async def test_approve_node_pauses_execution():
    """approve_node 触发暂停:status==paused, paused_step_id==step_2, step_3 未执行(skipped)"""
    executor = _make_executor_with_tools()
    _mock_llm_summary(executor)
    steps, edges = _make_approve_flow()

    result = await executor.execute(steps, edges)

    assert result["status"] == "paused"
    assert result["paused_step_id"] == "step_2"
    assert result["paused_message"] == "请审批"
    # approve_node 自身记录为 paused 状态(供前端展示"待审批")
    assert result["steps_result"]["step_2"]["status"] == "paused"
    assert result["steps_result"]["step_2"]["output"]["status"] == "pending_approval"
    assert result["steps_result"]["step_2"]["output"]["message"] == "请审批"
    # step_3 未执行:被收尾逻辑标记为 skipped
    assert result["steps_result"]["step_3"]["status"] == "skipped"


# ---------- 恢复路径(批准) ----------

@pytest.mark.asyncio
async def test_resume_execution_approved():
    """approved:step_3 执行成功, approve_node 标记 success, output.decision==approved"""
    executor = _make_executor_with_tools()
    _mock_llm_summary(executor)
    steps, edges = _make_approve_flow()

    # 第一次执行触发暂停
    paused_result = await executor.execute(steps, edges)
    assert paused_result["status"] == "paused"

    # 构造 paused_context 并恢复执行
    paused_context = _build_paused_context(paused_result)
    resume_result = await executor.resume_execution(
        steps=steps,
        edges=edges,
        paused_context=paused_context,
        paused_step_id="step_2",
        decision="approved",
        comment="同意",
    )

    assert resume_result["status"] == "success"
    # approve_node 被注入审批结果:status=success, decision=approved
    assert resume_result["steps_result"]["step_2"]["status"] == "success"
    assert resume_result["steps_result"]["step_2"]["output"]["decision"] == "approved"
    assert resume_result["steps_result"]["step_2"]["output"]["comment"] == "同意"
    assert resume_result["steps_result"]["step_2"]["output"]["approved_by"] == "manual"
    # step_3 恢复后执行成功(llm_summary mock 返回 {"summary":"ok"})
    assert resume_result["steps_result"]["step_3"]["status"] == "success"
    assert resume_result["steps_result"]["step_3"]["output"]["summary"] == "ok"


# ---------- 恢复路径(拒绝) ----------

@pytest.mark.asyncio
async def test_resume_execution_rejected():
    """rejected:status==failed, step_3 被跳过, approve_node output.decision==rejected"""
    executor = _make_executor_with_tools()
    _mock_llm_summary(executor)
    steps, edges = _make_approve_flow()

    # 先触发暂停
    paused_result = await executor.execute(steps, edges)
    assert paused_result["status"] == "paused"

    # 拒绝恢复
    paused_context = _build_paused_context(paused_result)
    resume_result = await executor.resume_execution(
        steps=steps,
        edges=edges,
        paused_context=paused_context,
        paused_step_id="step_2",
        decision="rejected",
        comment="不同意",
    )

    assert resume_result["status"] == "failed"
    # approve_node 被标记失败,decision=rejected
    assert resume_result["steps_result"]["step_2"]["status"] == "failed"
    assert resume_result["steps_result"]["step_2"]["output"]["decision"] == "rejected"
    assert resume_result["steps_result"]["step_2"]["output"]["comment"] == "不同意"
    # step_3 被标记为 skipped(暂停时已被收尾逻辑跳过,恢复时保留 skipped 状态)
    assert resume_result["steps_result"]["step_3"]["status"] == "skipped"
    # 顶层 error 字段含拒绝信息(resume_execution 在拒绝路径显式设置)
    assert "审批被拒绝" in resume_result["error"]


# ---------- approve_node 作为末步 ----------

@pytest.mark.asyncio
async def test_approve_node_no_successors():
    """approve_node 作为最后一步:approved 时无后继,直接返回 success"""
    executor = _make_executor_with_tools()
    _mock_llm_summary(executor)
    # 仅两步:manual_trigger → approve_node(无后继)
    steps = [
        _make_step("step_1", "manual_trigger", {}, "触发"),
        _make_step("step_2", "approve_node", {
            "message": "请审批",
            "approvers": [],
            "timeout_hours": 24,
        }, "审批"),
    ]
    edges = [_make_edge("step_1", "step_2")]

    # 先触发暂停
    paused_result = await executor.execute(steps, edges)
    assert paused_result["status"] == "paused"
    assert paused_result["paused_step_id"] == "step_2"

    # 恢复(approved)——无后继步骤,直接返回 success
    paused_context = _build_paused_context(paused_result)
    resume_result = await executor.resume_execution(
        steps=steps,
        edges=edges,
        paused_context=paused_context,
        paused_step_id="step_2",
        decision="approved",
        comment="通过",
    )

    assert resume_result["status"] == "success"
    assert resume_result["steps_result"]["step_2"]["status"] == "success"
    assert resume_result["steps_result"]["step_2"]["output"]["decision"] == "approved"


# ---------- pause_run 序列化 context ----------

@pytest.mark.asyncio
async def test_pause_run_serializes_context(test_db):
    """pause_run 将 ExecutionContext 序列化到 RunRecord.paused_context。

    断言:
    - run.status == "paused"
    - run.paused_context 非空且含 step_results / trigger_data / logs / token_usage
    - run.paused_step_id 正确
    """
    from core.run_record_service import pause_run

    # 准备 Workflow + RunRecord(trigger_data 非空,验证序列化时回填 trigger_data)
    wf = Workflow(id="wf-pause", name="暂停测试", steps="[]", edges="[]")
    test_db.add(wf)
    test_db.commit()

    run = RunRecord(
        id="run-pause",
        workflow_id="wf-pause",
        trigger_type="manual",
        status="running",
        started_at=datetime.now(timezone.utc),
        trigger_data=json.dumps({"user": "alice", "amount": 100}, ensure_ascii=False),
    )
    test_db.add(run)
    test_db.commit()

    # 构造 executor 暂停结果(模拟真实 execute 返回的 paused result)
    paused_result = {
        "status": "paused",
        "steps_result": {
            "step_1": {"output": {"message": "触发器"}, "status": "success", "error": None},
            "step_2": {
                "output": {"status": "pending_approval", "message": "请审批", "approvers": []},
                "status": "paused",
                "error": None,
            },
        },
        "logs": [{"level": "INFO", "module": "executor", "message": "工作流暂停于审批节点 step_2"}],
        "token_usage": {
            "prompt_tokens": 0, "completion_tokens": 0,
            "total_tokens": 0, "calls": 0, "by_model": {},
        },
    }

    pause_run(test_db, run, paused_result, paused_step_id="step_2")

    # 刷新并断言
    test_db.refresh(run)
    assert run.status == "paused"
    assert run.paused_step_id == "step_2"
    assert run.paused_at is not None
    assert run.paused_context is not None

    # 解析 paused_context,验证四个关键字段
    ctx = json.loads(run.paused_context)
    assert "step_results" in ctx
    assert "trigger_data" in ctx
    assert "logs" in ctx
    assert "token_usage" in ctx
    # step_results 应含 step_1(success) 和 step_2(paused)
    assert ctx["step_results"]["step_1"]["status"] == "success"
    assert ctx["step_results"]["step_2"]["status"] == "paused"
    # trigger_data 从 run.trigger_data JSON 反序列化回填
    assert ctx["trigger_data"]["user"] == "alice"
    assert ctx["trigger_data"]["amount"] == 100
    # logs 含暂停日志
    assert len(ctx["logs"]) >= 1
    assert ctx["token_usage"]["calls"] == 0


# ---------- 超时清理 ----------

@pytest.mark.asyncio
async def test_cleanup_expired_approvals(test_db, test_engine):
    """_cleanup_expired_approvals 清理 paused_at 早于 24h 的 RunRecord。

    断言:
    - status 变为 "failed"
    - error 含 "超时"
    - finished_at 被设置
    """
    from scheduler.manager import _cleanup_expired_approvals

    # 准备 Workflow + 一条超期 paused RunRecord(paused_at = now - 25h)
    wf = Workflow(id="wf-timeout", name="超时测试", steps="[]", edges="[]")
    test_db.add(wf)
    test_db.commit()

    now = datetime.now(timezone.utc)
    expired_run = RunRecord(
        id="run-expired",
        workflow_id="wf-timeout",
        trigger_type="manual",
        status="paused",
        started_at=now - timedelta(hours=26),
        paused_at=now - timedelta(hours=25),  # 早于 24h 阈值
        paused_step_id="step_approve",
    )
    test_db.add(expired_run)

    # 再加一条未超期的 paused RunRecord(不应被清理)
    fresh_run = RunRecord(
        id="run-fresh",
        workflow_id="wf-timeout",
        trigger_type="manual",
        status="paused",
        started_at=now - timedelta(hours=1),
        paused_at=now - timedelta(hours=1),  # 1h 前,未超期
        paused_step_id="step_approve",
    )
    test_db.add(fresh_run)
    test_db.commit()  # 释放连接供 scheduler session 使用

    # 将 scheduler.manager.SessionLocal 替换为绑定到测试内存 DB 的 sessionmaker
    TestSession = sessionmaker(bind=test_engine, autocommit=False, autoflush=False)
    with patch("scheduler.manager.SessionLocal", TestSession):
        _cleanup_expired_approvals()

    # 验证超期记录被标记 failed
    test_db.expire_all()
    expired_after = test_db.query(RunRecord).filter(RunRecord.id == "run-expired").first()
    assert expired_after is not None
    assert expired_after.status == "failed"
    assert expired_after.error is not None
    assert "超时" in expired_after.error
    assert expired_after.finished_at is not None

    # 验证未超期记录仍为 paused
    fresh_after = test_db.query(RunRecord).filter(RunRecord.id == "run-fresh").first()
    assert fresh_after is not None
    assert fresh_after.status == "paused"
