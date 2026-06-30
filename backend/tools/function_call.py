"""F1: Function Calling 智能体工具

LLM 自主决策调用工具并循环推理,直到给出最终答案或达到迭代上限。
循环逻辑:
1. 从 tool_registry 提取所选工具的 OpenAI function schema
2. 调用 chat_with_tools 获取 LLM 决策
3. 若有 tool_calls:逐个执行对应工具,将结果作为 tool 角色消息回填
4. 若无 tool_calls(LLM 给出最终答案):返回 {answer, iterations, tool_calls_history}
硬上限 max_iterations=10 防止无限循环;工具执行失败时回填错误信息让 LLM 自行处理。
"""
import json
import logging
from typing import Any

from core.llm import chat_with_tools
from core.tool_registry import get_tool_schemas

logger = logging.getLogger(__name__)

# F1: 硬上限——即使用户设置更大的 max_iterations 也不超过此值,防止无限循环
_MAX_ITERATIONS_HARD_LIMIT = 10


async def execute(params: dict, context: Any) -> dict:
    """Function Calling 智能体执行入口

    :param params: {prompt, tools: list[str], max_iterations?, model?}
    :param context: ExecutionContext(提供 add_token_usage / step 变量等)
    :return: {answer, iterations, tool_calls_history, warning?}
    """
    prompt = params.get("prompt", "")
    if not prompt:
        return {"answer": "", "iterations": 0, "tool_calls_history": [], "warning": "prompt 为空"}

    tool_names = params.get("tools") or []
    if not tool_names:
        return {"answer": "", "iterations": 0, "tool_calls_history": [], "warning": "未选择可用工具"}

    # 迭代上限:用户可配,但不超过硬上限
    try:
        max_iter = int(params.get("max_iterations", 10))
    except (TypeError, ValueError):
        max_iter = 10
    max_iter = max(1, min(max_iter, _MAX_ITERATIONS_HARD_LIMIT))

    model = params.get("model", "")
    usage_cb = getattr(context, "add_token_usage", None)

    # 生成 OpenAI function schema 列表
    tools_schema = get_tool_schemas(tool_names)
    if not tools_schema:
        return {
            "answer": "",
            "iterations": 0,
            "tool_calls_history": [],
            "warning": f"所选工具均不存在: {tool_names}",
        }

    # 延迟导入 TOOL_EXECUTORS 避免循环依赖
    from tools import TOOL_EXECUTORS

    system_prompt = (
        "你是一个智能助手,可以通过调用工具来完成用户的任务。"
        "请根据用户需求自主决定是否需要调用工具、调用哪个工具、传入什么参数。"
        "调用工具后根据返回结果继续推理,直到能够给出最终答案。"
        "如果不需要工具即可回答,请直接给出答案。"
    )

    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": str(prompt)},
    ]

    tool_calls_history: list[dict] = []
    warning = ""
    answer = ""

    for iteration in range(1, max_iter + 1):
        result = await chat_with_tools(
            messages=messages,
            tools=tools_schema,
            tool_choice="auto",
            model=model,
            temperature=0.3,
            max_tokens=2000,
            usage_callback=usage_cb,
        )

        tool_calls = result.get("tool_calls", [])
        content = result.get("content", "")

        # 无 tool_calls → LLM 给出最终答案
        if not tool_calls:
            answer = content
            break

        # 有 tool_calls → 将 assistant 消息(含 tool_calls)加入历史,逐个执行工具
        messages.append({
            "role": "assistant",
            "content": content,
            "tool_calls": [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {"name": tc["name"], "arguments": tc["arguments"]},
                }
                for tc in tool_calls
            ],
        })

        # 逐个执行工具调用
        for tc in tool_calls:
            tc_name = tc["name"]
            tc_args_raw = tc["arguments"]
            try:
                tc_args = json.loads(tc_args_raw) if isinstance(tc_args_raw, str) else (tc_args_raw or {})
            except json.JSONDecodeError:
                tc_args = {}

            history_entry = {
                "iteration": iteration,
                "tool": tc_name,
                "arguments": tc_args,
            }

            executor_func = TOOL_EXECUTORS.get(tc_name)
            if executor_func is None:
                # 工具未实现:回填错误让 LLM 自行处理
                err_msg = f"工具 '{tc_name}' 未实现"
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps({"error": err_msg}, ensure_ascii=False),
                })
                history_entry["error"] = err_msg
                history_entry["result"] = None
                tool_calls_history.append(history_entry)
                logger.warning(f"function_call: {err_msg}")
                continue

            try:
                tool_output = await executor_func(tc_args, context)
                # 工具结果回填为 tool 角色消息
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(tool_output, ensure_ascii=False, default=str),
                })
                history_entry["result"] = tool_output
            except Exception as e:
                # 工具执行失败:回填错误信息让 LLM 自行处理(不中断循环)
                err_msg = f"工具 '{tc_name}' 执行失败: {e}"
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps({"error": err_msg}, ensure_ascii=False),
                })
                history_entry["error"] = err_msg
                history_entry["result"] = None
                logger.warning(f"function_call: {err_msg}")

            tool_calls_history.append(history_entry)

        # 达到上限:再调一次不带 tools 让 LLM 给最终答案(或用当前 content)
        if iteration == max_iter:
            warning = f"已达到最大迭代次数 {max_iter}"
            # 尝试最后一次无工具调用,让 LLM 基于已有信息给出答案
            try:
                final_result = await chat_with_tools(
                    messages=messages,
                    tools=None,
                    model=model,
                    temperature=0.3,
                    max_tokens=2000,
                    usage_callback=usage_cb,
                )
                answer = final_result.get("content", "") or content
            except Exception:
                answer = content
            break
    else:
        # for 循环正常结束未 break(理论上 range 不会走到这里,兜底)
        answer = answer or "未能生成答案"

    return {
        "answer": answer,
        "iterations": len(tool_calls_history),
        "tool_calls_history": tool_calls_history,
        **({"warning": warning} if warning else {}),
    }
