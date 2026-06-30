"""LLM 输出校验层 - 校验工作流结构合法性"""
import re

from core.tool_registry import get_tool
from core.preference_schema import PREFERENCE_ITEMS


# 触发器类工具无需校验必填参数
TRIGGER_TOOLS = {"schedule_trigger", "manual_trigger", "webhook_trigger"}

# if_else 操作符中不需要 value 参数的 operator
OPERATORS_NOT_NEED_VALUE = {"is_null", "is_not_null", "is_empty", "is_not_empty"}

# 合法的偏好 key 集合(用于 {{pref.xxx}} 变量引用校验)
_PREF_KEYS = {item["key"] for item in PREFERENCE_ITEMS}


class ValidationResult:
    """校验结果"""

    def __init__(self, valid: bool, errors: list[str] = None):
        self.valid = valid
        self.errors = errors if errors is not None else []

    def __repr__(self) -> str:
        return f"ValidationResult(valid={self.valid}, errors={self.errors})"


def validate_workflow(result: dict, tool_names: set[str]) -> ValidationResult:
    """
    校验 LLM 输出的工作流结构。

    :param result: LLM 返回的字典
    :param tool_names: 合法工具名集合
    :return: ValidationResult
    """
    errors: list[str] = []

    # a. 澄清场景直接放行
    if result.get("need_clarification") is True:
        return ValidationResult(valid=True)

    # b. steps 必须是非空数组
    steps = result.get("steps")
    if not isinstance(steps, list) or len(steps) == 0:
        errors.append("steps 必须是非空数组")
        return ValidationResult(valid=False, errors=errors)

    # d. 步骤 id 唯一性
    step_ids: set[str] = set()
    for step in steps:
        sid = step.get("id") if isinstance(step, dict) else None
        if sid in step_ids:
            errors.append(f"步骤 id 重复: {sid}")
        step_ids.add(sid)

    # c. tool 必须在合法工具名集合中
    for step in steps:
        if not isinstance(step, dict):
            errors.append(f"步骤格式非法（非对象）: {step}")
            continue
        tool = step.get("tool")
        if tool not in tool_names:
            errors.append(f"步骤 {step.get('id')} 使用了未知工具: {tool}")

    # e. edges 的 from/to 必须指向存在的 step id
    edges = result.get("edges", [])
    if not isinstance(edges, list):
        edges = []
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        frm = edge.get("from")
        to = edge.get("to")
        if frm not in step_ids:
            errors.append(f"边的 from 指向不存在的步骤: {frm}")
        if to not in step_ids:
            errors.append(f"边的 to 指向不存在的步骤: {to}")

    # f. 必填参数检查（触发器类跳过）
    for step in steps:
        if not isinstance(step, dict):
            continue
        tool_name = step.get("tool")
        if tool_name in TRIGGER_TOOLS:
            continue
        tool = get_tool(tool_name) if tool_name else None
        if tool is None:
            continue  # 未知工具已在上面报错
        params = step.get("params", {})
        if not isinstance(params, dict):
            params = {}
        sid = step.get("id")
        for req in tool.required:
            if req not in params:
                errors.append(
                    f"步骤 {sid} 缺少必填参数: {req}（工具 {tool_name}）"
                )
        # 额外检查：if_else 的 operator 需要 value 时，value 不能为空
        operator = params.get("operator", "")
        if operator and operator not in OPERATORS_NOT_NEED_VALUE:
            value = params.get("value", "")
            if not value and "value" not in tool.required:
                errors.append(f"步骤 {sid} 的操作符 {operator} 需要 value 参数")
        # A2: subworkflow 的 workflow_id 必须是非空字符串
        # (required 检查只验证 key 存在,不验证值非空;LLM 可能传空字符串)
        # 真正的存在性校验与循环引用检测在 executor 运行时完成(validator 无 DB 访问)
        if tool_name == "subworkflow":
            wf_id = params.get("workflow_id", "")
            if not wf_id or not isinstance(wf_id, str) or not wf_id.strip():
                errors.append(
                    f"步骤 {sid} 的 subworkflow 缺少有效的 workflow_id 参数"
                )

    # g. 变量引用校验 {{step_x.field}}
    errors.extend(_validate_variable_refs(steps, edges))

    return ValidationResult(valid=(len(errors) == 0), errors=errors)


def _validate_variable_refs(steps: list, edges: list) -> list:
    """校验 params 值中的变量引用 {{step_x.field}} 的有效性"""
    errors = []

    # 构建 step_id -> tool_name 映射
    step_tools = {}
    for step in steps:
        sid = step.get("id")
        tool_name = step.get("tool")
        if sid and tool_name:
            step_tools[sid] = tool_name

    # 正则匹配变量引用 {{step_x.field.path}} 或 {{trigger.xxx}} 或 {{item}} 或 {{index}}
    var_pattern = re.compile(r'\{\{\s*(\w+)\.(\w[\w.]*)\s*(?:\|\s*default\s*:\s*["\']([^"\']*)["\'])?\s*\}\}')
    # 也匹配无点的特殊变量 {{item}} {{index}} {{trigger}}
    simple_var_pattern = re.compile(r'\{\{\s*(item|index|trigger)\s*\}\}')

    for step in steps:
        sid = step.get("id", "?")
        params = step.get("params", {})
        if not isinstance(params, dict):
            continue

        for param_name, param_value in params.items():
            if not isinstance(param_value, str):
                continue

            # 检查 {{step_x.field}} 形式的引用
            for match in var_pattern.finditer(param_value):
                ref_step_id = match.group(1)
                ref_field = match.group(2)

                # 豁免 trigger
                if ref_step_id == "trigger":
                    continue

                # 豁免并校验 pref(用户偏好,如 {{pref.email}})
                if ref_step_id == "pref":
                    pref_key = ref_field.split(".")[0]
                    if pref_key not in _PREF_KEYS:
                        available = ", ".join(sorted(_PREF_KEYS))
                        errors.append(
                            f"步骤 {sid} 的参数 {param_name} 引用了未知的偏好项 pref.{pref_key},"
                            f"可用偏好键: {available}"
                        )
                    continue

                # 校验 step_x 是否存在
                if ref_step_id not in step_tools:
                    errors.append(f"步骤 {sid} 的参数 {param_name} 引用了不存在的步骤 {ref_step_id}")
                    continue

                # 校验 field 是否为该工具的输出字段
                tool_name = step_tools[ref_step_id]
                tool = get_tool(tool_name)
                if tool and tool.output_schema:
                    field_root = ref_field.split(".")[0]  # 取第一段，如 items.0.title -> items
                    if field_root not in tool.output_schema:
                        available = ", ".join(tool.output_schema.keys())
                        errors.append(f"步骤 {sid} 的参数 {param_name} 引用了 {ref_step_id} 的无效字段 {field_root}，{tool_name} 的输出字段为: {available}")

    # 递归校验 loop 的 sub_steps（{{item}}/{{index}} 不匹配 var_pattern，天然豁免）
    for step in steps:
        if not isinstance(step, dict):
            continue
        if step.get("tool") == "loop":
            params = step.get("params", {})
            if not isinstance(params, dict):
                continue
            sub_steps = params.get("sub_steps", [])
            sub_edges = params.get("sub_edges", [])
            if isinstance(sub_steps, list) and sub_steps:
                sub_errors = _validate_variable_refs(sub_steps, sub_edges)
                errors.extend(sub_errors)

    return errors


# A3: on_complete_trigger 结构校验(工作流级配置,非 LLM 输出)
# 在 routers/workflows.py 的 create/update 端点调用,返回错误列表(空表示合法)
_VALID_ON_VALUES = {"success", "failed", "always"}


def validate_on_complete_trigger(triggers, self_workflow_id: str = "") -> list[str]:
    """校验 on_complete_trigger 配置结构

    :param triggers: list[dict],每项 {workflow_id, on}
    :param self_workflow_id: 当前工作流 ID(用于检测自引用,空字符串则跳过)
    :return: 错误信息列表(空表示合法)
    """
    errors: list[str] = []
    if triggers is None:
        return errors  # None 视为未设置,合法
    if not isinstance(triggers, list):
        errors.append("on_complete_trigger 必须是数组")
        return errors

    for i, t in enumerate(triggers):
        if not isinstance(t, dict):
            errors.append(f"on_complete_trigger[{i}] 必须是对象")
            continue
        wf_id = t.get("workflow_id", "")
        if not wf_id or not isinstance(wf_id, str) or not wf_id.strip():
            errors.append(f"on_complete_trigger[{i}] 缺少有效的 workflow_id")
        elif self_workflow_id and wf_id == self_workflow_id:
            errors.append(f"on_complete_trigger[{i}] 不能引用自身工作流(会导致立即循环)")
        on_val = t.get("on", "always")
        if on_val not in _VALID_ON_VALUES:
            errors.append(
                f"on_complete_trigger[{i}] 的 on 值非法: {on_val},"
                f"必须为 {', '.join(sorted(_VALID_ON_VALUES))} 之一"
            )
    return errors
