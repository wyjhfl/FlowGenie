"""执行引擎单元测试 - mock 工具验证就绪队列/失败策略/变量插值/if_else 分支"""
import json
import pytest
from unittest.mock import patch
from sqlalchemy.orm import sessionmaker
from engine.executor import WorkflowExecutor
from engine.context import ExecutionContext
from db.models import Workflow


def _make_step(sid, tool="http_request", params=None, name=None):
    """构造步骤字典"""
    return {
        "id": sid,
        "name": name or f"步骤{sid}",
        "tool": tool,
        "params": params or {},
    }


def _make_edge(from_id, to_id, condition=None):
    """构造边字典"""
    edge = {"from": from_id, "to": to_id}
    if condition:
        edge["condition"] = condition
    return edge


def _make_executor():
    """构造独立 WorkflowExecutor(不污染全局单例)"""
    return WorkflowExecutor()


async def _mock_tool_returning(output):
    """返回固定输出的 mock 工具执行器"""
    async def _func(params, context):
        return output
    return _func


@pytest.mark.asyncio
async def test_simple_sequential():
    """两步顺序执行成功,status=success"""
    executor = _make_executor()
    executor.register_executor("http_request", await _mock_tool_returning({"status_code": 200, "body": "ok"}))
    executor.register_executor("llm_summary", await _mock_tool_returning({"summary": "摘要"}))

    steps = [
        _make_step("s1", "http_request", {"url": "https://example.com", "method": "GET"}),
        _make_step("s2", "llm_summary", {"text": "test"}),
    ]
    edges = [_make_edge("s1", "s2")]

    result = await executor.execute(steps, edges)

    assert result["status"] == "success"
    assert result["steps_result"]["s1"]["status"] == "success"
    assert result["steps_result"]["s2"]["status"] == "success"
    assert result["steps_result"]["s1"]["output"]["status_code"] == 200


@pytest.mark.asyncio
async def test_step_failure_records_error():
    """步骤抛异常 → status=failed,error 记录,不外抛"""
    executor = _make_executor()

    async def failing_tool(params, context):
        raise RuntimeError("连接超时")

    executor.register_executor("http_request", failing_tool)

    steps = [_make_step("s1", "http_request", {"url": "https://example.com", "method": "GET"})]
    edges = []

    result = await executor.execute(steps, edges)

    assert result["status"] == "failed"
    assert result["steps_result"]["s1"]["status"] == "failed"
    assert "连接超时" in result["steps_result"]["s1"]["error"]


@pytest.mark.asyncio
async def test_on_failure_stop():
    """失败即停,后续步骤 skipped"""
    executor = _make_executor()

    async def failing_tool(params, context):
        raise RuntimeError("失败")

    executor.register_executor("http_request", failing_tool)
    executor.register_executor("llm_summary", await _mock_tool_returning({"summary": "ok"}))

    steps = [
        _make_step("s1", "http_request", {"url": "x", "method": "GET"}),
        _make_step("s2", "llm_summary", {"text": "y"}),
    ]
    edges = [_make_edge("s1", "s2")]

    result = await executor.execute(steps, edges, on_failure="stop")

    assert result["status"] == "failed"
    assert result["steps_result"]["s1"]["status"] == "failed"
    # s2 应被跳过(前置失败)
    assert result["steps_result"]["s2"]["status"] == "skipped"


@pytest.mark.asyncio
async def test_on_failure_continue():
    """失败继续,后续步骤执行"""
    executor = _make_executor()

    async def failing_tool(params, context):
        raise RuntimeError("失败")

    executor.register_executor("http_request", failing_tool)
    executor.register_executor("llm_summary", await _mock_tool_returning({"summary": "ok"}))

    steps = [
        _make_step("s1", "http_request", {"url": "x", "method": "GET"}),
        _make_step("s2", "llm_summary", {"text": "y"}),
    ]
    edges = [_make_edge("s1", "s2")]

    result = await executor.execute(steps, edges, on_failure="continue")

    # 失败继续:整体 partial_success,s2 仍执行
    assert result["status"] in ("partial_success", "failed")
    assert result["steps_result"]["s1"]["status"] == "failed"
    assert result["steps_result"]["s2"]["status"] == "success"


@pytest.mark.asyncio
async def test_variable_interpolation():
    """上一步输出 {{step_1.field}} 引用到下一步参数"""
    executor = _make_executor()
    executor.register_executor("http_request", await _mock_tool_returning({"status_code": 200, "body": "内容"}))

    # 第二个工具接收上一步的 body
    received_params = {}

    async def capture_tool(params, context):
        received_params.update(params)
        return {"summary": "ok"}

    executor.register_executor("llm_summary", capture_tool)

    steps = [
        _make_step("s1", "http_request", {"url": "x", "method": "GET"}),
        _make_step("s2", "llm_summary", {"text": "{{s1.body}}"}),
    ]
    edges = [_make_edge("s1", "s2")]

    result = await executor.execute(steps, edges)

    assert result["status"] == "success"
    # 验证变量被插值:s2 的 text 参数应为 s1.body 的值
    assert received_params["text"] == "内容"


@pytest.mark.asyncio
async def test_if_else_branch_true():
    """条件为真走 true 分支,假分支 skipped"""
    executor = _make_executor()
    executor.register_executor("http_request", await _mock_tool_returning({"status_code": 200}))

    true_executed = {"flag": False}
    false_executed = {"flag": False}

    async def true_tool(params, context):
        true_executed["flag"] = True
        return {"result": "true_branch"}

    async def false_tool(params, context):
        false_executed["flag"] = True
        return {"result": "false_branch"}

    executor.register_executor("llm_summary", true_tool)
    executor.register_executor("llm_analysis", false_tool)

    steps = [
        _make_step("s1", "http_request", {"url": "x", "method": "GET"}),
        # if_else: s1.status_code == 200 → true
        _make_step("s2", "if_else", {"field": "{{s1.status_code}}", "operator": "eq", "value": 200}),
        _make_step("s3", "llm_summary", {"text": "true 分支"}),
        _make_step("s4", "llm_analysis", {"data": "false 分支"}),
    ]
    edges = [
        _make_edge("s1", "s2"),
        _make_edge("s2", "s3", condition="true"),
        _make_edge("s2", "s4", condition="false"),
    ]

    result = await executor.execute(steps, edges)

    assert result["status"] == "success"
    assert true_executed["flag"] is True
    assert false_executed["flag"] is False
    assert result["steps_result"]["s3"]["status"] == "success"
    assert result["steps_result"]["s4"]["status"] == "skipped"


@pytest.mark.asyncio
async def test_if_else_branch_false():
    """条件为假走 false 分支,true 分支 skipped"""
    executor = _make_executor()
    executor.register_executor("http_request", await _mock_tool_returning({"status_code": 404}))

    true_executed = {"flag": False}
    false_executed = {"flag": False}

    async def true_tool(params, context):
        true_executed["flag"] = True
        return {"result": "true_branch"}

    async def false_tool(params, context):
        false_executed["flag"] = True
        return {"result": "false_branch"}

    executor.register_executor("llm_summary", true_tool)
    executor.register_executor("llm_analysis", false_tool)

    steps = [
        _make_step("s1", "http_request", {"url": "x", "method": "GET"}),
        # if_else: s1.status_code == 200 → false (实际 404)
        _make_step("s2", "if_else", {"field": "{{s1.status_code}}", "operator": "eq", "value": 200}),
        _make_step("s3", "llm_summary", {"text": "true 分支"}),
        _make_step("s4", "llm_analysis", {"data": "false 分支"}),
    ]
    edges = [
        _make_edge("s1", "s2"),
        _make_edge("s2", "s3", condition="true"),
        _make_edge("s2", "s4", condition="false"),
    ]

    result = await executor.execute(steps, edges)

    assert result["status"] == "success"
    assert true_executed["flag"] is False
    assert false_executed["flag"] is True
    assert result["steps_result"]["s3"]["status"] == "skipped"
    assert result["steps_result"]["s4"]["status"] == "success"


@pytest.mark.asyncio
async def test_total_time_ms_positive():
    """总耗时 > 0"""
    executor = _make_executor()
    executor.register_executor("http_request", await _mock_tool_returning({"status_code": 200}))

    import asyncio
    async def slow_tool(params, context):
        await asyncio.sleep(0.05)  # 50ms
        return {"summary": "ok"}

    executor.register_executor("llm_summary", slow_tool)

    steps = [
        _make_step("s1", "http_request", {"url": "x", "method": "GET"}),
        _make_step("s2", "llm_summary", {"text": "y"}),
    ]
    edges = [_make_edge("s1", "s2")]

    result = await executor.execute(steps, edges)

    assert result["total_time_ms"] > 0
    assert result["status"] == "success"


@pytest.mark.asyncio
async def test_step_timeout():
    """B1: 单步超时,step.params.timeout=0.5,慢工具 sleep 10s → step 状态 failed 且 error 含"超时" """
    import asyncio
    executor = _make_executor()

    async def slow_tool(params, context):
        await asyncio.sleep(10)  # 远超 0.5s 超时
        return {"should_not_reach": True}

    executor.register_executor("llm_summary", slow_tool)

    steps = [
        _make_step("s1", "llm_summary", {"text": "x", "timeout": 0.5}),
    ]
    edges = []

    result = await executor.execute(steps, edges)

    assert result["status"] == "failed"
    assert result["steps_result"]["s1"]["status"] == "failed"
    assert "超时" in result["steps_result"]["s1"]["error"]
    assert result["steps_result"]["s1"]["output"] is None


@pytest.mark.asyncio
async def test_loop_break_on_success():
    """B2: break_on="success",首项成功后提前终止,results 长度为 1 且 broken=True"""
    executor = _make_executor()
    executor.register_executor("http_request", await _mock_tool_returning({"status_code": 200}))

    sub_steps = [_make_step("sub_1", "http_request", {"url": "{{item}}", "method": "GET"})]
    steps = [
        _make_step("s1", "loop", {
            "input_array": ["a", "b", "c"],
            "sub_steps": sub_steps,
            "sub_edges": [],
            "break_on": "success",
        }),
    ]
    edges = []

    result = await executor.execute(steps, edges)

    assert result["status"] == "success"
    loop_output = result["steps_result"]["s1"]["output"]
    assert loop_output["count"] == 1
    assert loop_output["broken"] is True


@pytest.mark.asyncio
async def test_loop_max_iterations():
    """B2: max_iterations=2,input_array 长度 5,results 长度为 2 且 broken=False"""
    executor = _make_executor()
    executor.register_executor("http_request", await _mock_tool_returning({"status_code": 200}))

    sub_steps = [_make_step("sub_1", "http_request", {"url": "{{item}}", "method": "GET"})]
    steps = [
        _make_step("s1", "loop", {
            "input_array": [1, 2, 3, 4, 5],
            "sub_steps": sub_steps,
            "sub_edges": [],
            "max_iterations": 2,
        }),
    ]
    edges = []

    result = await executor.execute(steps, edges)

    assert result["status"] == "success"
    loop_output = result["steps_result"]["s1"]["output"]
    assert loop_output["count"] == 2
    assert loop_output["broken"] is False


@pytest.mark.asyncio
async def test_preference_auto_fill():
    """A3: 偏好自动填充 — params 中 to 为空,偏好 email 回填到 to"""
    executor = _make_executor()
    received = {}

    async def capture(params, context):
        received.update(params)
        return {"success": True}

    executor.register_executor("send_email", capture)

    steps = [_make_step("s1", "send_email", {"to": "", "subject": "x", "content": "y"})]
    edges = []

    result = await executor.execute(steps, edges, preferences={"email": "test@example.com"})

    assert result["status"] == "success"
    # 偏好应回填空 to 参数
    assert received["to"] == "test@example.com"


@pytest.mark.asyncio
async def test_pref_variable_resolution():
    """A3: {{pref.email}} 变量解析 — params 中 to 显式引用偏好"""
    executor = _make_executor()
    received = {}

    async def capture(params, context):
        received.update(params)
        return {"success": True}

    executor.register_executor("send_email", capture)

    steps = [_make_step("s1", "send_email", {"to": "{{pref.email}}", "subject": "x", "content": "y"})]
    edges = []

    result = await executor.execute(steps, edges, preferences={"email": "pref@flowgenie.com"})

    assert result["status"] == "success"
    # {{pref.email}} 应被解析为偏好值
    assert received["to"] == "pref@flowgenie.com"


# ---------- A2: 子流程嵌套 ----------

def _make_subworkflow_target(test_db, wf_id, steps, edges, name="子流程目标"):
    """在测试 DB 中创建一个目标工作流(供 subworkflow 节点调用)"""
    wf = Workflow(
        id=wf_id,
        name=name,
        steps=json.dumps(steps, ensure_ascii=False),
        edges=json.dumps(edges, ensure_ascii=False),
    )
    test_db.add(wf)
    test_db.commit()
    return wf


def _patch_sessionlocal(test_engine):
    """构造 patch 上下文,将 db.database.SessionLocal 指向测试内存 DB。

    _execute_subworkflow 内部用 `from db.database import SessionLocal` 创建独立会话,
    需 patch 指向同一内存 DB,否则查询不到预置的 Workflow。
    """
    TestSession = sessionmaker(bind=test_engine, autocommit=False, autoflush=False)
    return patch("db.database.SessionLocal", TestSession)


@pytest.mark.asyncio
async def test_subworkflow_normal_execution(test_db, test_engine):
    """A2: 子流程正常执行 — 父流程 subworkflow 节点调用目标工作流,返回末步输出

    断言:
    - 父流程 status == "success"
    - subworkflow 节点 status == "success", output 含 sub_steps_result / sub_workflow_id
    - output.output 为子流程末步(llm_summary)输出 {"summary": "ok"}
    """
    executor = _make_executor()

    async def _fake_llm_summary(params, context):
        return {"summary": "ok"}

    executor.register_executor("llm_summary", _fake_llm_summary)

    # 子流程目标:manual_trigger → llm_summary
    sub_steps = [
        _make_step("sub_1", "manual_trigger", {}, "子触发"),
        _make_step("sub_2", "llm_summary", {"text": "子流程输入"}, "子摘要"),
    ]
    sub_edges = [_make_edge("sub_1", "sub_2")]
    _make_subworkflow_target(test_db, "wf-sub-normal", sub_steps, sub_edges, "正常子流程")

    # 父流程:manual_trigger → subworkflow(指向 wf-sub-normal)
    parent_steps = [
        _make_step("p1", "manual_trigger", {}, "父触发"),
        _make_step("p2", "subworkflow", {"workflow_id": "wf-sub-normal"}, "调用子流程"),
    ]
    parent_edges = [_make_edge("p1", "p2")]

    with _patch_sessionlocal(test_engine):
        result = await executor.execute(parent_steps, parent_edges)

    assert result["status"] == "success"
    assert result["steps_result"]["p2"]["status"] == "success"
    sub_output = result["steps_result"]["p2"]["output"]
    assert sub_output["status"] == "success"
    assert sub_output["sub_workflow_id"] == "wf-sub-normal"
    # 末步输出为子流程的 llm_summary 结果
    assert sub_output["output"] == {"summary": "ok"}
    # sub_steps_result 含子流程两步
    assert "sub_1" in sub_output["sub_steps_result"]
    assert "sub_2" in sub_output["sub_steps_result"]
    assert sub_output["sub_steps_result"]["sub_2"]["status"] == "success"


@pytest.mark.asyncio
async def test_subworkflow_circular_reference():
    """A2: 循环引用检测 — 目标 workflow_id 已在调用链中时抛 ValueError

    构造 call_stack=("wf_a",) 模拟已在 wf_a 中执行,再调用 wf_a 应被拒绝。
    """
    executor = _make_executor()

    context = ExecutionContext(trigger_data={})
    context.subworkflow_call_stack = ("wf_a",)  # 模拟当前已在 wf_a 中
    step = _make_step("s_sub", "subworkflow", {"workflow_id": "wf_a"})

    with pytest.raises(ValueError, match="循环引用"):
        await executor._execute_subworkflow(step, context)


@pytest.mark.asyncio
async def test_subworkflow_depth_limit():
    """A2: 嵌套深度上限 — call_stack 长度 >= 5 时抛 ValueError

    构造 call_stack 含 5 个 wf_id,调用第 6 层应被拒绝。
    """
    executor = _make_executor()

    context = ExecutionContext(trigger_data={})
    context.subworkflow_call_stack = ("wf_1", "wf_2", "wf_3", "wf_4", "wf_5")
    step = _make_step("s_sub", "subworkflow", {"workflow_id": "wf_6"})

    with pytest.raises(ValueError, match="深度超限"):
        await executor._execute_subworkflow(step, context)


@pytest.mark.asyncio
async def test_subworkflow_missing_workflow_id():
    """A2: 缺少 workflow_id 参数 — 抛 ValueError 含'缺少 workflow_id'"""
    executor = _make_executor()

    context = ExecutionContext(trigger_data={})
    # workflow_id 为空字符串
    step = _make_step("s_sub", "subworkflow", {"workflow_id": ""})

    with pytest.raises(ValueError, match="缺少 workflow_id"):
        await executor._execute_subworkflow(step, context)


@pytest.mark.asyncio
async def test_subworkflow_nonexistent_workflow(test_db, test_engine):
    """A2: 目标工作流不存在 — 抛 ValueError 含'目标工作流不存在'

    patch SessionLocal 指向测试 DB(空表),查询目标 wf 返回 None。
    """
    executor = _make_executor()

    context = ExecutionContext(trigger_data={})
    step = _make_step("s_sub", "subworkflow", {"workflow_id": "wf-not-exist"})

    with _patch_sessionlocal(test_engine):
        with pytest.raises(ValueError, match="目标工作流不存在"):
            await executor._execute_subworkflow(step, context)


@pytest.mark.asyncio
async def test_subworkflow_token_aggregation(test_db, test_engine):
    """A2: 子流程 token_usage 聚合回父 context

    子流程含一个 mock LLM 工具,执行时调用 context.add_token_usage 注入 token。
    执行后父流程 result["token_usage"] 应包含子流程注入的 token。
    """
    executor = _make_executor()

    # mock LLM 工具:执行时注入 token 用量
    async def _fake_llm_with_token(params, context):
        context.add_token_usage({
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150,
            "model": "test-model",
        })
        return {"summary": "with-token"}

    executor.register_executor("llm_summary", _fake_llm_with_token)

    # 子流程目标:manual_trigger → llm_summary
    sub_steps = [
        _make_step("sub_1", "manual_trigger", {}, "子触发"),
        _make_step("sub_2", "llm_summary", {"text": "子流程"}, "子LLM"),
    ]
    sub_edges = [_make_edge("sub_1", "sub_2")]
    _make_subworkflow_target(test_db, "wf-sub-token", sub_steps, sub_edges, "Token子流程")

    # 父流程:manual_trigger → subworkflow
    parent_steps = [
        _make_step("p1", "manual_trigger", {}, "父触发"),
        _make_step("p2", "subworkflow", {"workflow_id": "wf-sub-token"}, "调用子流程"),
    ]
    parent_edges = [_make_edge("p1", "p2")]

    with _patch_sessionlocal(test_engine):
        result = await executor.execute(parent_steps, parent_edges)

    assert result["status"] == "success"
    # 子流程的 token 应聚合到父流程
    token_usage = result["token_usage"]
    assert token_usage["prompt_tokens"] == 100
    assert token_usage["completion_tokens"] == 50
    assert token_usage["total_tokens"] == 150
    assert token_usage["calls"] == 1
    assert "test-model" in token_usage["by_model"]
    assert token_usage["by_model"]["test-model"]["total_tokens"] == 150
