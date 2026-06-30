"""执行上下文 - 管理步骤间数据传递与变量插值"""
import re
import time
from typing import Any, Callable


class ExecutionContext:
    """
    工作流执行上下文
    - 存储每个步骤的输入/输出
    - 支持 {{step_id.field}} 变量插值
    """

    def __init__(self, trigger_data: dict | None = None, preferences: dict | None = None):
        # 每步执行结果: { step_id: { "output": Any, "status": str, "error": str|None } }
        self.step_results: dict[str, dict] = {}
        # 触发器传入的初始数据（如 Webhook payload）
        self.trigger_data = trigger_data or {}
        # 用户偏好(用于 {{pref.key}} 变量解析与执行期自动填充)
        self.preferences: dict = preferences or {}
        # loop 子流程特殊变量（仅在子流程内有意义）
        self.loop_item: Any = None
        self.loop_index: Any = None
        # 执行过程中的警告信息（如循环引用检测）
        self.warnings: list[str] = []
        # 执行日志：[{ timestamp, level, module, message }]
        self.logs: list[dict] = []
        # B1: LLM 流式 token 回调(仅 stream=true 的 LLM 节点执行期间设置)
        # 签名: callback(delta: str) -> None;由 executor 设置,LLM 工具读取
        self.token_callback: Callable[[str], None] | None = None
        # B4: LLM token 用量统计(单次执行内累积所有 LLM 调用的 token 用量)
        # 结构: {prompt_tokens, completion_tokens, total_tokens, calls, by_model: {model: {...}}}
        self.token_usage: dict = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "calls": 0,
            "by_model": {},
        }
        # A1: 审批节点暂停信息(仅当执行暂停于 approve_node 时非 None)
        # 结构: {step_id, message, approvers, timeout_hours}
        self.paused_info: dict | None = None
        # A2: 子流程调用链(用于循环引用检测与深度限制)
        # 结构: (workflow_id_1, workflow_id_2, ...),最外层执行时为空 tuple
        # _execute_subworkflow 创建子 context 时追加目标 workflow_id
        self.subworkflow_call_stack: tuple[str, ...] = ()

    def add_token_usage(self, usage: dict) -> None:
        """B4: 累积一次 LLM 调用的 token 用量

        :param usage: {prompt_tokens, completion_tokens, total_tokens, model}
        """
        if not usage:
            return
        prompt = int(usage.get("prompt_tokens", 0) or 0)
        completion = int(usage.get("completion_tokens", 0) or 0)
        total = int(usage.get("total_tokens", 0) or 0)
        model = usage.get("model") or "unknown"
        self.token_usage["prompt_tokens"] += prompt
        self.token_usage["completion_tokens"] += completion
        self.token_usage["total_tokens"] += total
        self.token_usage["calls"] += 1
        by_model = self.token_usage["by_model"]
        if model not in by_model:
            by_model[model] = {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "calls": 0,
            }
        by_model[model]["prompt_tokens"] += prompt
        by_model[model]["completion_tokens"] += completion
        by_model[model]["total_tokens"] += total
        by_model[model]["calls"] += 1

    def merge_token_usage(self, other: dict | None) -> None:
        """A2: 合并另一个 context 的 token_usage 聚合字典(用于子流程结果回传父流程)

        与 add_token_usage 的区别:本方法接受的是已聚合的 token_usage 字典(含 calls 与 by_model),
        适用于子流程结束后将其全部 token 用量合并回父流程。

        :param other: 子 context 的 token_usage 字典
        """
        if not other:
            return
        self.token_usage["prompt_tokens"] += int(other.get("prompt_tokens", 0) or 0)
        self.token_usage["completion_tokens"] += int(other.get("completion_tokens", 0) or 0)
        self.token_usage["total_tokens"] += int(other.get("total_tokens", 0) or 0)
        self.token_usage["calls"] += int(other.get("calls", 0) or 0)
        by_model = self.token_usage["by_model"]
        for model, stats in (other.get("by_model") or {}).items():
            if model not in by_model:
                by_model[model] = {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "calls": 0,
                }
            by_model[model]["prompt_tokens"] += int(stats.get("prompt_tokens", 0) or 0)
            by_model[model]["completion_tokens"] += int(stats.get("completion_tokens", 0) or 0)
            by_model[model]["total_tokens"] += int(stats.get("total_tokens", 0) or 0)
            by_model[model]["calls"] += int(stats.get("calls", 0) or 0)

    def add_log(self, level: str, module: str, message: str) -> None:
        """追加一条执行日志
        :param level: INFO | WARN | ERROR
        :param module: 模块名（如 executor）
        :param message: 日志消息
        """
        self.logs.append({
            "timestamp": time.time(),
            "level": level.upper(),
            "module": module,
            "message": message,
        })

    def set_step_result(self, step_id: str, output: Any, status: str = "success", error: str | None = None):
        """记录某步骤的执行结果"""
        self.step_results[step_id] = {
            "output": output,
            "status": status,
            "error": error,
        }

    def get_step_output(self, step_id: str) -> Any:
        """获取某步骤的输出"""
        result = self.step_results.get(step_id)
        if result is None:
            return None
        # 兼容 {output: ...} 包装结构 和 直接存储输出值的情况
        if isinstance(result, dict) and "output" in result:
            return result["output"]
        return result

    def resolve_variables(self, value: Any) -> Any:
        """
        递归解析值中的 {{step_id.field}} 变量引用
        支持: 字符串、字典、列表
        """
        if isinstance(value, str):
            return self._resolve_string(value)
        elif isinstance(value, dict):
            return {k: self.resolve_variables(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [self.resolve_variables(item) for item in value]
        return value

    def _resolve_string(self, text: str) -> Any:
        """解析字符串中的变量引用，支持 default 过滤器和可选空格"""
        # 匹配 {{path}} 或 {{path|default:"value"}} 或 {{path|default:'value'}}
        # 支持变量名前后可选空格：{{ step.field }} 或 {{step.field}}
        pattern = r"\{\{\s*([\w_.]+)\s*(?:\|\s*default\s*:\s*[\"']([^\"']*)[\"'])?\s*\}\}"
        matches = list(re.finditer(pattern, text))

        if not matches:
            return text

        # 如果整个字符串就是一个变量引用，返回原始类型（非字符串）
        if len(matches) == 1 and text.strip() == matches[0].group(0):
            m = matches[0]
            return self._get_variable(m.group(1), m.group(2))

        # 否则做字符串替换
        for m in matches:
            full_match = m.group(0)
            replacement = self._get_variable(m.group(1), m.group(2))
            text = text.replace(full_match, str(replacement))
        return text

    def _get_variable(self, path: str, default_value: str | None = None) -> Any:
        """
        根据路径获取变量值
        路径格式: step_id 或 step_id.field 或 step_id.field.subfield
        特殊: trigger.xxx 获取触发器数据
              item / index 获取 loop 子流程变量
        未找到时返回 default_value（若提供）否则空字符串
        """
        parts = path.split(".")

        # 特殊变量: trigger
        if parts[0] == "trigger":
            value = self.trigger_data
            for part in parts[1:]:
                if isinstance(value, dict):
                    if part not in value:
                        return default_value if default_value is not None else ""
                    value = value[part]
                else:
                    return default_value if default_value is not None else ""
            return value

        # 特殊变量: pref (用户偏好,如 {{pref.email}})
        if parts[0] == "pref":
            if len(parts) < 2:
                return default_value if default_value is not None else ""
            pref_key = parts[1]
            if pref_key not in self.preferences:
                return default_value if default_value is not None else ""
            value = self.preferences[pref_key]
            # 支持 {{pref.key.field}} 嵌套取值(偏好值为 dict 时)
            for part in parts[2:]:
                if isinstance(value, dict):
                    if part not in value:
                        return default_value if default_value is not None else ""
                    value = value[part]
                else:
                    return default_value if default_value is not None else ""
            return value

        # 特殊变量: item (loop 子流程)
        if parts[0] == "item":
            if self.loop_item is None:
                return default_value if default_value is not None else ""
            if len(parts) == 1:
                return self.loop_item
            value = self.loop_item
            for part in parts[1:]:
                if isinstance(value, dict):
                    if part not in value:
                        return default_value if default_value is not None else ""
                    value = value[part]
                elif isinstance(value, list):
                    try:
                        idx = int(part)
                        if 0 <= idx < len(value):
                            value = value[idx]
                        else:
                            return default_value if default_value is not None else ""
                    except (ValueError, IndexError):
                        return default_value if default_value is not None else ""
                else:
                    return default_value if default_value is not None else ""
            return value

        # 特殊变量: index (loop 子流程)
        if parts[0] == "index":
            if self.loop_index is None:
                return default_value if default_value is not None else ""
            return self.loop_index

        # 步骤输出变量
        step_id = parts[0]
        output = self.get_step_output(step_id)

        if output is None:
            return default_value if default_value is not None else ""

        # 如果只有 step_id，返回整个输出
        if len(parts) == 1:
            return output

        # 按 field 路径取值
        value = output
        for part in parts[1:]:
            if isinstance(value, dict):
                if part not in value:
                    return default_value if default_value is not None else ""
                value = value[part]
            elif isinstance(value, list):
                try:
                    idx = int(part)
                    if 0 <= idx < len(value):
                        value = value[idx]
                    else:
                        return default_value if default_value is not None else ""
                except (ValueError, IndexError):
                    return default_value if default_value is not None else ""
            else:
                return default_value if default_value is not None else ""
        return value

    def to_dict(self) -> dict:
        """序列化为字典（用于 API 返回）"""
        return {
            "step_results": self.step_results,
            "trigger_data": self.trigger_data,
            "logs": self.logs,
        }
