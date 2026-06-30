"""校验器测试 - 验证 LLM 输出工作流结构的合法性校验逻辑。

覆盖:步骤唯一性、工具合法性、边引用、必填参数、变量引用、触发器豁免、澄清放行。
"""
from core.validator import validate_workflow, ValidationResult
from core.tool_registry import get_all_tools


# 所有合法工具名集合(从注册表实时读取,避免硬编码漂移)
ALL_TOOL_NAMES = {t["name"] for t in get_all_tools()}


def _make_step(sid, tool="http_request", params=None):
    """构造一个步骤字典"""
    return {"id": sid, "name": f"步骤{sid}", "tool": tool, "params": params or {}}


def test_valid_workflow():
    """合法工作流(两步顺序 + 合法变量引用)应通过校验"""
    result = {
        "steps": [
            _make_step("step_1", "http_request", {"url": "https://x.com", "method": "GET"}),
            _make_step("step_2", "file_write", {"path": "/o.json", "content": "{{step_1.body}}"}),
        ],
        "edges": [{"from": "step_1", "to": "step_2"}],
    }
    res = validate_workflow(result, ALL_TOOL_NAMES)
    assert res.valid is True, f"应通过校验,错误: {res.errors}"


def test_empty_steps():
    """steps 为空数组应校验失败"""
    res = validate_workflow({"steps": [], "edges": []}, ALL_TOOL_NAMES)
    assert res.valid is False
    assert any("非空数组" in e for e in res.errors)


def test_duplicate_step_id():
    """步骤 id 重复应校验失败"""
    result = {
        "steps": [
            _make_step("step_1", "http_request", {"url": "https://x.com", "method": "GET"}),
            _make_step("step_1", "http_request", {"url": "https://y.com", "method": "GET"}),
        ],
        "edges": [],
    }
    res = validate_workflow(result, ALL_TOOL_NAMES)
    assert res.valid is False
    assert any("重复" in e for e in res.errors)


def test_unknown_tool():
    """tool 不在合法工具集合中应校验失败"""
    result = {
        "steps": [_make_step("step_1", "nonexistent_tool", {})],
        "edges": [],
    }
    res = validate_workflow(result, ALL_TOOL_NAMES)
    assert res.valid is False
    assert any("未知工具" in e for e in res.errors)


def test_edge_to_nonexistent_step():
    """edge.to 指向不存在的步骤应校验失败"""
    result = {
        "steps": [_make_step("step_1", "http_request", {"url": "https://x.com", "method": "GET"})],
        "edges": [{"from": "step_1", "to": "step_99"}],
    }
    res = validate_workflow(result, ALL_TOOL_NAMES)
    assert res.valid is False
    assert any("不存在的步骤" in e for e in res.errors)


def test_missing_required_param():
    """缺少必填参数(http_request 缺 url)应校验失败"""
    result = {
        "steps": [_make_step("step_1", "http_request", {"method": "GET"})],
        "edges": [],
    }
    res = validate_workflow(result, ALL_TOOL_NAMES)
    assert res.valid is False
    assert any("缺少必填参数" in e for e in res.errors)


def test_trigger_skips_required_check():
    """触发器类工具(schedule_trigger)应跳过必填参数检查"""
    result = {
        "steps": [_make_step("step_1", "schedule_trigger", {})],
        "edges": [],
    }
    res = validate_workflow(result, ALL_TOOL_NAMES)
    assert res.valid is True, f"触发器应豁免必填检查,错误: {res.errors}"


def test_valid_variable_ref():
    """合法变量引用 {{step_1.body}}(body 是 http_request 输出字段)应通过"""
    result = {
        "steps": [
            _make_step("step_1", "http_request", {"url": "https://x.com", "method": "GET"}),
            _make_step("step_2", "file_write", {"path": "/o.json", "content": "{{step_1.body}}"}),
        ],
        "edges": [{"from": "step_1", "to": "step_2"}],
    }
    res = validate_workflow(result, ALL_TOOL_NAMES)
    assert res.valid is True, f"合法引用应通过,错误: {res.errors}"


def test_invalid_variable_ref_step():
    """引用不存在的步骤 {{step_99.field}} 应校验失败"""
    result = {
        "steps": [
            _make_step("step_1", "http_request", {"url": "https://x.com", "method": "GET"}),
            _make_step("step_2", "file_write", {"path": "/o.json", "content": "{{step_99.body}}"}),
        ],
        "edges": [{"from": "step_1", "to": "step_2"}],
    }
    res = validate_workflow(result, ALL_TOOL_NAMES)
    assert res.valid is False
    assert any("不存在的步骤" in e for e in res.errors)


def test_invalid_variable_ref_field():
    """引用不存在的字段 {{step_1.nonexistent}} 应校验失败"""
    result = {
        "steps": [
            _make_step("step_1", "http_request", {"url": "https://x.com", "method": "GET"}),
            _make_step("step_2", "file_write", {"path": "/o.json", "content": "{{step_1.nonexistent_field}}"}),
        ],
        "edges": [{"from": "step_1", "to": "step_2"}],
    }
    res = validate_workflow(result, ALL_TOOL_NAMES)
    assert res.valid is False
    assert any("无效字段" in e for e in res.errors)


def test_need_clarification_passes():
    """need_clarification=True 时直接放行,不校验 steps"""
    res = validate_workflow({"need_clarification": True, "steps": []}, ALL_TOOL_NAMES)
    assert res.valid is True


def test_if_else_operator_without_value():
    """if_else 的 eq 操作符需要 value,但 value 为空应校验失败"""
    result = {
        "steps": [_make_step("step_1", "if_else", {"field": "{{trigger.x}}", "operator": "eq", "value": ""})],
        "edges": [],
    }
    res = validate_workflow(result, ALL_TOOL_NAMES)
    assert res.valid is False
    assert any("value" in e for e in res.errors)
