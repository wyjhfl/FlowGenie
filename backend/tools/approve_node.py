"""A1: 人工审批节点工具

执行器在 _execute_step_only 中拦截 approve_node,抛出 PauseExecution 异常暂停工作流。
本模块的 execute 函数仅作为占位符注册到 TOOL_EXECUTORS,不会被实际调用。
实际暂停/恢复逻辑在 engine/executor.py 中实现。
"""
import logging

logger = logging.getLogger(__name__)


async def execute(params: dict, context) -> dict:
    """占位实现:实际不会被执行器调用。

    执行器在分发前拦截 approve_node 工具,抛出 PauseExecution 异常。
    此函数仅为保持 TOOL_EXECUTORS 注册一致性而存在。
    """
    message = params.get("message", "请审批此步骤以继续执行")
    approvers = params.get("approvers", [])
    timeout_hours = params.get("timeout_hours", 24)
    logger.warning(
        f"approve_node.execute 被意外调用(message={message}),"
        "应被 executor 拦截。返回 pending 状态作为兜底。"
    )
    return {
        "status": "pending_approval",
        "message": message,
        "approvers": approvers,
        "timeout_hours": timeout_hours,
    }
