"""A2: 子流程调用节点工具(占位实现)

执行器在 _execute_step_only 中拦截 subworkflow 工具:
1. 从 params.workflow_id 加载目标 Workflow 的 steps/edges
2. 创建子 ExecutionContext(继承父 step_results + 注入 input_mapping 作为 trigger_data)
3. 递归调用 _execute_internal(_acquire_lock=False 复用父流程并发槽位)
4. 子流程 token_usage / logs / warnings 聚合回父 context
5. 循环引用检测通过 context.subworkflow_call_stack 实现

本模块的 execute 函数仅作为占位符注册到 TOOL_EXECUTORS,不会被实际调用。
真实逻辑在 engine/executor.py 的 _execute_subworkflow 方法中实现。
"""
import logging

logger = logging.getLogger(__name__)


async def execute(params: dict, context) -> dict:
    """占位实现:实际不会被执行器调用。

    执行器在分发前拦截 subworkflow 工具,从 DB 加载目标工作流并递归执行。
    此函数仅为保持 TOOL_EXECUTORS 注册一致性而存在。
    """
    workflow_id = params.get("workflow_id", "")
    logger.warning(
        f"subworkflow.execute 被意外调用(workflow_id={workflow_id}),"
        "应被 executor 拦截。返回 skipped 状态作为兜底。"
    )
    return {
        "status": "skipped",
        "output": None,
        "sub_steps_result": {},
        "sub_workflow_id": workflow_id,
    }
