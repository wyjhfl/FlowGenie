"""工作流执行器 - 就绪队列模式异步执行步骤，支持条件分支与循环"""
import asyncio
import copy
import json
import logging
import os
import time
from typing import Any, Callable
from engine.context import ExecutionContext
from tools.if_else import execute as if_else_execute

logger = logging.getLogger(__name__)

# P2: 工具执行默认超时(秒),可通过环境变量 TOOL_TIMEOUT 覆盖;上限 300s 防止误配置
# 单步可通过 step.params.timeout 单独覆盖;流式 LLM 调用自动放宽至 300s
def _read_tool_timeout() -> int:
    raw = os.getenv("TOOL_TIMEOUT", "120")
    try:
        val = int(raw)
    except (TypeError, ValueError):
        return 120
    return max(1, min(val, 300))

DEFAULT_TOOL_TIMEOUT = _read_tool_timeout()


class PauseExecution(Exception):
    """A1: 审批节点触发的暂停异常。

    执行器遇到 approve_node 时抛出,由 _execute_internal_impl 捕获并返回 "paused" 状态。
    携带 step_id/message/approvers/timeout_hours 供调用方序列化到 RunRecord。
    """
    def __init__(self, step_id: str, message: str, approvers: list, timeout_hours: int = 24):
        self.step_id = step_id
        self.message = message
        self.approvers = approvers
        self.timeout_hours = timeout_hours
        super().__init__(f"工作流暂停于审批节点 {step_id}: {message}")


class WorkflowExecutor:
    """
    工作流执行器
    - 基于就绪队列的迭代执行（替代纯拓扑排序）
    - 支持变量插值（上一步输出 → 下一步输入）
    - 支持 if_else 条件分支（按 condition 路由出边）
    - 支持 loop 循环节点（对数组遍历执行子流程）
    - 支持失败策略（stop / continue）
    - 支持上下文恢复与单步重试（execute_with_context）
    - 捕获每步执行结果、耗时、错误
    """

    def __init__(self, debug_mode: bool = False, step_event: "asyncio.Event | None" = None):
        # 工具执行器映射表，由 tool_registry 注册
        self.tool_executors: dict[str, Any] = {}
        # 调试模式：每步完成后等待 step_event 被外部 set() 再继续
        self.debug_mode = debug_mode
        self.step_event = step_event
        # 中止标志：abort() 设为 True，每步前检查并抛异常中止执行
        self._aborted = False

    def register_executor(self, tool_name: str, executor_func):
        """注册工具执行函数"""
        self.tool_executors[tool_name] = executor_func

    def abort(self):
        """中止执行：设置标志位并释放可能的等待，让 executor 退出暂停"""
        self._aborted = True
        if self.step_event is not None:
            self.step_event.set()

    def set_debug_mode(self, enabled: bool):
        """运行时切换调试模式；关闭时释放可能的等待以全速执行剩余步骤"""
        self.debug_mode = enabled
        if not enabled and self.step_event is not None:
            self.step_event.set()

    async def execute(
        self,
        steps: list[dict],
        edges: list[dict],
        trigger_data: dict | None = None,
        on_failure: str = "stop",
        progress_callback: Callable | None = None,
        preferences: dict | None = None,
    ) -> dict:
        """
        执行工作流
        :param steps: 步骤列表 [{ id, name, tool, params }]
        :param edges: 边列表 [{ from, to, condition? }]
        :param trigger_data: 触发器传入的初始数据
        :param on_failure: 失败策略 "stop"（失败即停） | "continue"（失败继续）
        :param progress_callback: 进度回调函数，每步完成（成功/失败/跳过）后调用
        :param preferences: 用户偏好(用于 {{pref.x}} 变量解析与执行期自动填充)
        :return: { status, steps_result, total_time_ms, on_failure }
        """
        start_time = time.time()
        context = ExecutionContext(trigger_data=trigger_data, preferences=preferences or {})
        status = await self._execute_internal(
            steps, edges, context, on_failure=on_failure,
            progress_callback=progress_callback,
        )
        total_time = int((time.time() - start_time) * 1000)
        context.add_log("INFO", "executor", f"工作流执行完成，状态: {status}")

        return self._build_result(context, status, total_time, on_failure)

    async def execute_with_context(
        self,
        steps: list[dict],
        edges: list[dict],
        trigger_data: dict | None = None,
        on_failure: str = "stop",
        prev_context: dict | None = None,
        start_from: str | None = None,
        progress_callback: Callable | None = None,
        preferences: dict | None = None,
    ) -> dict:
        """
        带上下文恢复的执行（用于重试）
        :param prev_context: 之前已成功步骤的输出 {step_id: {output, status, ...}}
        :param start_from: 从该步骤开始执行（之前的成功步骤跳过但保留输出）
        :param progress_callback: 进度回调函数，每步完成（成功/失败/跳过）后调用
        :param preferences: 用户偏好(用于 {{pref.x}} 变量解析与执行期自动填充)
        :return: { status, steps_result, total_time_ms, on_failure }
        """
        start_time = time.time()
        context = ExecutionContext(trigger_data=trigger_data, preferences=preferences or {})
        status = await self._execute_internal(
            steps, edges, context,
            on_failure=on_failure,
            prev_context=prev_context,
            start_from=start_from,
            progress_callback=progress_callback,
        )
        total_time = int((time.time() - start_time) * 1000)
        context.add_log("INFO", "executor", f"工作流执行完成，状态: {status}")

        return self._build_result(context, status, total_time, on_failure)

    def _build_result(
        self,
        context: ExecutionContext,
        status: str,
        total_time: int,
        on_failure: str,
    ) -> dict:
        """构造执行返回结果。A1: status==paused 时附带 paused_step_id 等审批信息。"""
        result = {
            "status": status,
            "steps_result": context.step_results,
            "total_time_ms": total_time,
            "on_failure": on_failure,
            "warnings": context.warnings,
            "logs": context.logs,
            "token_usage": context.token_usage,
        }
        if status == "paused" and context.paused_info:
            result["paused_step_id"] = context.paused_info["step_id"]
            result["paused_message"] = context.paused_info["message"]
            result["paused_approvers"] = context.paused_info["approvers"]
        return result

    async def resume_execution(
        self,
        steps: list[dict],
        edges: list[dict],
        paused_context: dict,
        paused_step_id: str,
        decision: str,
        comment: str = "",
        on_failure: str = "stop",
        preferences: dict | None = None,
        progress_callback: Callable | None = None,
    ) -> dict:
        """A1: 审批后恢复工作流执行。

        :param paused_context: 暂停时序列化的 ExecutionContext {step_results, trigger_data, logs, token_usage}
        :param paused_step_id: 触发暂停的 approve_node 步骤 ID
        :param decision: "approved" | "rejected"
        :param comment: 审批评论
        :return: 与 execute 相同的返回结构 {status, steps_result, total_time_ms, ...}
        """
        start_time = time.time()
        # 1. 重建 ExecutionContext
        context = ExecutionContext(
            trigger_data=paused_context.get("trigger_data") or {},
            preferences=preferences or {},
        )
        # 恢复已完成步骤的结果(排除 approve_node 本身,下面单独注入审批结果)
        prev_step_results = paused_context.get("step_results") or {}
        for sid, sr in prev_step_results.items():
            if sid == paused_step_id:
                continue
            if isinstance(sr, dict):
                context.set_step_result(
                    sid, output=sr.get("output"), status=sr.get("status", "success"),
                    error=sr.get("error"),
                )
                if "time_ms" in sr:
                    context.step_results[sid]["time_ms"] = sr["time_ms"]
        # 恢复 token_usage 与 logs(累积,不覆盖)
        saved_usage = paused_context.get("token_usage")
        if isinstance(saved_usage, dict):
            context.token_usage = copy.deepcopy(saved_usage)
        saved_logs = paused_context.get("logs") or []
        context.logs = list(saved_logs)

        # 2. 注入 approve_node 的审批结果
        approve_output = {"decision": decision, "comment": comment, "approved_by": "manual"}
        if decision == "approved":
            context.set_step_result(paused_step_id, output=approve_output, status="success")
            context.add_log("INFO", "executor", f"审批节点 {paused_step_id} 已批准: {comment}")
        else:
            context.set_step_result(
                paused_step_id, output=approve_output, status="failed",
                error=f"审批被拒绝: {comment}",
            )
            context.add_log("WARN", "executor", f"审批节点 {paused_step_id} 已拒绝: {comment}")

        # 3. 拒绝:直接返回 failed(approve_node 失败,后续步骤按 on_failure 策略处理)
        if decision != "approved":
            # 标记 approve_node 后继为 skipped(on_failure=stop 时全部跳过)
            successors = [e.get("to") for e in edges if e.get("from") == paused_step_id]
            for succ in successors:
                if succ and succ not in context.step_results:
                    context.set_step_result(succ, output=None, status="skipped", error="审批被拒绝,后续步骤跳过")
                    context.add_log("WARN", "executor", f"步骤 {succ} 因审批拒绝已跳过")
            total_time = int((time.time() - start_time) * 1000)
            return {
                "status": "failed",
                "steps_result": context.step_results,
                "total_time_ms": total_time,
                "on_failure": on_failure,
                "warnings": context.warnings,
                "logs": context.logs,
                "token_usage": context.token_usage,
                "error": f"审批被拒绝: {comment}",
            }

        # 4. 批准:从 approve_node 的后继继续执行(复用 execute_with_context 机制)
        successors = [e.get("to") for e in edges if e.get("from") == paused_step_id]
        if not successors:
            # approve_node 是最后一步,直接返回成功
            total_time = int((time.time() - start_time) * 1000)
            context.add_log("INFO", "executor", "审批通过,工作流执行完成(无后续步骤)")
            return {
                "status": "success",
                "steps_result": context.step_results,
                "total_time_ms": total_time,
                "on_failure": on_failure,
                "warnings": context.warnings,
                "logs": context.logs,
                "token_usage": context.token_usage,
            }

        # start_from = 第一个后继;descendants 计算会包含后继及其所有后继,approve_node 不在其中(被恢复)
        start_from = successors[0]
        status = await self._execute_internal(
            steps, edges, context,
            on_failure=on_failure,
            prev_context=context.step_results,  # 用当前已恢复的结果作为 prev_context
            start_from=start_from,
            progress_callback=progress_callback,
        )
        total_time = int((time.time() - start_time) * 1000)
        context.add_log("INFO", "executor", f"审批恢复执行完成,状态: {status}")
        return {
            "status": status,
            "steps_result": context.step_results,
            "total_time_ms": total_time,
            "on_failure": on_failure,
            "warnings": context.warnings,
            "logs": context.logs,
            "token_usage": context.token_usage,
        }

    def _apply_preferences(self, params: dict, tool_name: str, context: ExecutionContext) -> dict:
        """
        执行期偏好自动填充:遍历偏好 schema,若 applicable_tools 包含当前工具,
        且参数中对应字段为空字符串/None,则用偏好值回填。
        不覆盖用户显式设置的值。
        """
        if not params or not isinstance(params, dict):
            return params
        if not context.preferences:
            return params

        from core.preference_schema import PREFERENCE_ITEMS

        for item in PREFERENCE_ITEMS:
            applicable = item.get("applicable_tools") or {}
            if tool_name not in applicable:
                continue
            param_names = applicable[tool_name]
            pref_value = context.preferences.get(item["key"])
            if not pref_value:
                continue
            for param_name in param_names:
                current = params.get(param_name)
                if current is None or current == "":
                    params[param_name] = pref_value
        return params

    async def _execute_internal(
        self,
        steps: list[dict],
        edges: list[dict],
        context: ExecutionContext,
        on_failure: str = "stop",
        prev_context: dict | None = None,
        start_from: str | None = None,
        progress_callback: Callable | None = None,
        _acquire_lock: bool = True,
    ) -> str:
        """
        核心执行循环（就绪队列模式），供 execute / execute_with_context / loop 子流程复用
        :param on_failure: 失败策略 "stop" | "continue"
        :param prev_context: 重试时之前已执行步骤的结果（用于恢复上下文）
        :param start_from: 重试时从该步骤开始重新执行
        :param progress_callback: 进度回调函数，每步完成（成功/失败/跳过）后调用
        :param _acquire_lock: 是否获取全局并发信号量。loop 子流程递归调用时应传 False，
                              避免嵌套 acquire 导致死锁（父流程已持有槽位）。
        :return: overall_status ("success" | "failed" | "partial_success")
        """
        # 并发执行限制：在最外层执行入口获取信号量，控制同时执行的工作流数量。
        # loop 子流程复用父流程已持有的槽位（_acquire_lock=False），不重复 acquire。
        # 使用 acquired 标志确保仅在成功 acquire 后才 release，避免 CancelledError
        # 中断 acquire 时过度释放信号量。
        from core.concurrency import acquire_execution_slot, release_execution_slot
        acquired = False
        try:
            if _acquire_lock:
                await acquire_execution_slot()
                acquired = True
            return await self._execute_internal_impl(
                steps, edges, context,
                on_failure=on_failure,
                prev_context=prev_context,
                start_from=start_from,
                progress_callback=progress_callback,
                _acquire_lock=_acquire_lock,
            )
        finally:
            if acquired:
                release_execution_slot()

    async def _execute_internal_impl(
        self,
        steps: list[dict],
        edges: list[dict],
        context: ExecutionContext,
        on_failure: str = "stop",
        prev_context: dict | None = None,
        start_from: str | None = None,
        progress_callback: Callable | None = None,
        _acquire_lock: bool = True,
    ) -> str:
        """
        _execute_internal 的实际实现（已由外层持有信号量）。
        参数与 _execute_internal 一致，_acquire_lock 仅用于透传给递归调用。
        """
        # 过滤掉缺少 id 的步骤并记录警告
        valid_steps = []
        for s in steps:
            sid = s.get("id")
            if not sid:
                logger.warning(f"步骤缺少关键字段 id，已跳过: {s}")
                continue
            valid_steps.append(s)
        steps = valid_steps

        step_map = {s["id"]: s for s in steps}
        step_ids = set(step_map.keys())
        order_index = {s["id"]: i for i, s in enumerate(steps)}

        # 构建邻接表和入度
        out_edges_map: dict[str, list[dict]] = {sid: [] for sid in step_ids}
        in_degree: dict[str, int] = {sid: 0 for sid in step_ids}
        for edge in edges:
            from_id = edge.get("from")
            to_id = edge.get("to")
            if from_id in step_ids and to_id in step_ids:
                out_edges_map[from_id].append(edge)
                in_degree[to_id] += 1

        # 就绪队列状态追踪
        pending = dict(in_degree)               # 剩余未解析的入边数
        activated = {sid: False for sid in step_ids}  # 是否被激活边到达
        resolved: set[str] = set()              # 已执行或已跳过

        # 初始就绪队列：入度为 0 的节点
        ready: list[str] = []
        for s in steps:
            sid = s.get("id")
            if in_degree[sid] == 0:
                activated[sid] = True
                ready.append(sid)

        # 重试模式：计算 start_from 的后继节点集合（含自身），
        # 这些节点需重新执行，不从前次结果恢复；仅前驱/无关节点恢复输出
        descendants: set[str] = set()
        if start_from and prev_context:
            descendants = self._find_descendants(start_from, edges, out_edges_map) | {start_from}

        overall_status = "success"
        while ready:
            # 调试模式中止检查：abort() 置位后立即退出循环
            if self._aborted:
                raise RuntimeError("aborted by user")
            # 取出当前批次（同一层级的就绪节点，入度均为 0）
            batch = ready[:]
            ready.clear()
            # 过滤已解析的节点
            batch = [sid for sid in batch if sid not in resolved]
            if not batch:
                continue

            # 执行当前批次：多节点并发，单节点串行
            if len(batch) > 1:
                tasks = [
                    self._execute_step_only(
                        sid, step_map, context, on_failure,
                        progress_callback, prev_context, descendants, activated,
                    )
                    for sid in batch
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)
            else:
                sid = batch[0]
                try:
                    result = await self._execute_step_only(
                        sid, step_map, context, on_failure,
                        progress_callback, prev_context, descendants, activated,
                    )
                    results = [result]
                except Exception as e:
                    results = [e]

            # 串行处理结果：先处理成功/跳过（解析边更新 activated），
            # 再处理失败（_mark_remaining_skipped 依赖 activated 避免误跳并发节点）
            failed_items: list[tuple[str, Any]] = []
            paused_step_id: str | None = None  # A1: 审批暂停检测
            for sid, result in zip(batch, results):
                # A1: 审批节点暂停——PauseExecution 由 _execute_step_only 抛出
                # step_result 已在抛出前设为 paused 状态,此处仅记录并退出循环
                if isinstance(result, PauseExecution):
                    paused_step_id = sid
                    resolved.add(sid)  # 审批节点本身视为已处理(不参与循环检测收尾)
                    context.paused_info = {
                        "step_id": sid,
                        "message": result.message,
                        "approvers": result.approvers,
                        "timeout_hours": result.timeout_hours,
                    }
                    context.add_log("INFO", "executor", f"工作流暂停于审批节点 {sid}: {result.message}")
                    continue
                if isinstance(result, Exception):
                    # 协程异常（不应发生，_execute_step_only 内部已捕获）
                    context.set_step_result(
                        sid, output=None, status="failed", error=str(result)
                    )
                    context.step_results[sid]["time_ms"] = 0
                    self._notify_progress(sid, context, progress_callback)
                    failed_items.append((sid, result))
                    continue

                status = result.get("status")
                if status == "failed":
                    failed_items.append((sid, result.get("error")))
                else:
                    resolved.add(sid)
                    self._resolve_edges(
                        sid, out_edges_map, pending, activated, resolved,
                        ready, order_index,
                        branch=result.get("branch"),
                        was_skipped=result.get("was_skipped", False),
                    )

            # A1: 审批暂停——检测到 PauseExecution 后立即退出 while 循环,返回 "paused"
            if paused_step_id is not None:
                overall_status = "paused"
                break

            # 处理失败节点的边路由
            should_break = False
            for sid, error in failed_items:
                status, break_flag = self._handle_failure(
                    sid, error, context, on_failure,
                    step_map, out_edges_map, pending, activated,
                    resolved, ready, order_index, steps, edges,
                    progress_callback=progress_callback,
                )
                if status == "failed":
                    overall_status = "failed"
                elif overall_status != "failed":
                    overall_status = status
                if break_flag:
                    should_break = True

            if should_break:
                break

            # 调试模式：单步执行，每批完成后等待用户触发下一步（无后续步骤时不暂停）
            if self.debug_mode and self.step_event is not None and not self._aborted and ready:
                await self.step_event.wait()
                self.step_event.clear()

        # 循环检测与收尾:未解析节点标记 skipped,更新 overall_status
        return self._finalize_execution(
            step_ids, resolved, activated, context, overall_status, progress_callback
        )

    def _finalize_execution(
        self,
        step_ids: set,
        resolved: set,
        activated: dict,
        context: ExecutionContext,
        overall_status: str,
        progress_callback: Callable | None = None,
    ) -> str:
        """循环检测与执行收尾:未解析节点(循环引用/前置失败)标记为 skipped"""
        unresolved = step_ids - resolved
        if unresolved:
            warning_msg = f"检测到循环引用，以下节点无法到达已跳过: {sorted(unresolved)}"
            logger.warning(warning_msg)
            context.warnings.append(warning_msg)
            context.add_log("WARN", "executor", warning_msg)
            for sid in unresolved:
                if sid not in context.step_results:
                    # 区分：被激活但未执行（前置失败）vs 未激活（循环引用）
                    if activated.get(sid, False):
                        error_msg = "前置步骤失败，已跳过"
                    else:
                        error_msg = "检测到循环引用，节点无法到达"
                    context.set_step_result(
                        sid, output=None, status="skipped", error=error_msg
                    )
                    context.add_log("WARN", "executor", f"步骤 {sid} 已跳过: {error_msg}")
                    self._notify_progress(sid, context, progress_callback)
            if overall_status == "success":
                overall_status = "partial_success"

        return overall_status

    def _notify_progress(
        self, step_id: str, context: ExecutionContext, progress_callback
    ):
        """步骤完成（成功/失败/跳过）后推送进度回调"""
        if progress_callback:
            sr = context.step_results.get(step_id, {})
            progress_callback({
                "step_id": step_id,
                "status": sr.get("status"),
                "output": sr.get("output"),
                "time_ms": sr.get("time_ms"),
                "error": sr.get("error"),
            })

    async def _execute_step_only(
        self,
        step_id: str,
        step_map: dict,
        context: ExecutionContext,
        on_failure: str,
        progress_callback: Callable | None,
        prev_context: dict | None,
        descendants: set,
        activated: dict,
    ) -> dict:
        """
        执行单个步骤（不含 resolved 更新和边解析），用于串行/并发复用。
        - 设置 step_result 到 context
        - 推送 SSE（progress_callback）——每个节点完成时立即推送
        :return: { status, branch, was_skipped, error }
        """
        step = step_map[step_id]
        step_start = time.time()
        tool_name = step.get("tool", "")

        # 重试模式：恢复前驱/无关节点的输出（后继节点重新执行）
        if prev_context and step_id in prev_context and step_id not in descendants:
            prev_sr = prev_context[step_id]
            if prev_sr.get("status") == "success":
                context.set_step_result(
                    step_id, output=prev_sr.get("output"), status="success"
                )
                if "time_ms" in prev_sr:
                    context.step_results[step_id]["time_ms"] = prev_sr["time_ms"]
                prev_output = prev_sr.get("output")
                branch = (
                    prev_output.get("branch")
                    if isinstance(prev_output, dict) and "branch" in prev_output
                    else None
                )
                context.add_log("INFO", "executor", f"步骤 {step_id} ({tool_name}) 已从历史上下文恢复")
                self._notify_progress(step_id, context, progress_callback)
                return {"status": "success", "branch": branch, "was_skipped": False}
            # skipped/failed 前驱：不恢复，由正常流程重新评估/执行

        # 非激活节点（条件分支未命中）：跳过并传播
        if not activated[step_id]:
            context.set_step_result(
                step_id, output=None, status="skipped", error="条件分支未命中"
            )
            context.add_log("WARN", "executor", f"步骤 {step_id} 已跳过: 条件分支未命中")
            self._notify_progress(step_id, context, progress_callback)
            return {"status": "skipped", "branch": None, "was_skipped": True}

        # 触发类工具跳过执行（仅作为流程起点标记）
        if tool_name in ("schedule_trigger", "webhook_trigger", "manual_trigger"):
            context.set_step_result(
                step_id,
                output={"message": f"触发器: {step.get('name', tool_name)}"},
                status="success",
            )
            context.add_log("INFO", "executor", f"步骤 {step_id} ({tool_name}) 执行成功 (触发器)")
            self._notify_progress(step_id, context, progress_callback)
            return {"status": "success", "branch": None, "was_skipped": False}

        # 推送 running 状态：步骤即将开始执行（跳过/触发器不需要）
        if progress_callback:
            progress_callback({
                "type": "step",
                "step_id": step_id,
                "step_name": step.get("name", step_id),
                "status": "running",
                "output": None,
            })
        context.add_log("INFO", "executor", f"步骤 {step_id} ({tool_name}) 开始执行")

        # if_else 节点：条件求值，返回 branch
        if tool_name == "if_else":
            branch = await self._execute_if_else(step, context, step_id, step_start)
            step_time = context.step_results.get(step_id, {}).get("time_ms", 0)
            context.add_log("INFO", "executor", f"步骤 {step_id} 执行成功 ({step_time}ms)")
            self._notify_progress(step_id, context, progress_callback)
            return {"status": "success", "branch": branch, "was_skipped": False}

        # loop 节点：遍历数组执行子流程
        if tool_name == "loop":
            try:
                output = await self._execute_loop(
                    step, context, on_failure=on_failure,
                    progress_callback=progress_callback,
                )
                step_time = int((time.time() - step_start) * 1000)
                context.set_step_result(step_id, output=output, status="success")
                context.step_results[step_id]["time_ms"] = step_time
                context.add_log("INFO", "executor", f"步骤 {step_id} 执行成功 ({step_time}ms)")
                self._notify_progress(step_id, context, progress_callback)
                return {"status": "success", "branch": None, "was_skipped": False}
            except Exception as e:
                step_time = int((time.time() - step_start) * 1000)
                context.set_step_result(step_id, output=None, status="failed", error=str(e))
                context.step_results[step_id]["time_ms"] = step_time
                context.add_log("ERROR", "executor", f"步骤 {step_id} 执行失败: {e}")
                self._notify_progress(step_id, context, progress_callback)
                return {"status": "failed", "branch": None, "was_skipped": False, "error": e}

        # A2: 子流程调用节点——从 DB 加载目标工作流并递归执行
        # 复刻 loop 模式:_acquire_lock=False 复用父流程并发槽位;子 context 继承父 step_results;
        # 循环引用检测通过 context.subworkflow_call_stack;token_usage/logs 聚合回父级
        if tool_name == "subworkflow":
            try:
                output = await self._execute_subworkflow(
                    step, context, on_failure=on_failure,
                    progress_callback=progress_callback,
                )
                step_time = int((time.time() - step_start) * 1000)
                # 子流程失败则本步骤标记 failed(走父流程 on_failure 策略)
                step_status = "failed" if output.get("status") == "failed" else "success"
                context.set_step_result(step_id, output=output, status=step_status)
                context.step_results[step_id]["time_ms"] = step_time
                level = "INFO" if step_status == "success" else "ERROR"
                context.add_log(level, "executor", f"步骤 {step_id} (子流程) 执行 {step_status} ({step_time}ms)")
                self._notify_progress(step_id, context, progress_callback)
                return {"status": step_status, "branch": None, "was_skipped": False}
            except Exception as e:
                step_time = int((time.time() - step_start) * 1000)
                context.set_step_result(step_id, output=None, status="failed", error=str(e))
                context.step_results[step_id]["time_ms"] = step_time
                context.add_log("ERROR", "executor", f"步骤 {step_id} (子流程) 执行失败: {e}")
                self._notify_progress(step_id, context, progress_callback)
                return {"status": "failed", "branch": None, "was_skipped": False, "error": e}

        # A1: 审批节点——不执行实际操作,抛出 PauseExecution 暂停工作流
        # 执行器捕获后序列化 context 到 DB,等待人工审批后调用 resume_execution 恢复
        if tool_name == "approve_node":
            raw_params = step.get("params", {})
            resolved_params = context.resolve_variables(raw_params)
            message = resolved_params.get("message", "请审批此步骤以继续执行")
            approvers = resolved_params.get("approvers", [])
            timeout_hours = int(resolved_params.get("timeout_hours", 24) or 24)
            # 记录 pending 状态到 step_result(供前端展示"待审批")
            step_time = int((time.time() - step_start) * 1000)
            context.set_step_result(
                step_id,
                output={"status": "pending_approval", "message": message, "approvers": approvers},
                status="paused",
            )
            context.step_results[step_id]["time_ms"] = step_time
            context.add_log("INFO", "executor", f"步骤 {step_id} (审批节点) 暂停工作流: {message}")
            self._notify_progress(step_id, context, progress_callback)
            raise PauseExecution(step_id, message, approvers, timeout_hours)

        # 普通节点：解析参数并调用工具执行器
        raw_params = step.get("params", {})
        resolved_params = context.resolve_variables(raw_params)
        # 偏好自动填充:空参数用偏好值回填(不覆盖显式设置的值)
        resolved_params = self._apply_preferences(resolved_params, tool_name, context)

        executor_func = self.tool_executors.get(tool_name)
        if not executor_func:
            error = f"工具 '{tool_name}' 未实现执行逻辑"
            step_time = int((time.time() - step_start) * 1000)
            context.set_step_result(step_id, output=None, status="failed", error=error)
            context.step_results[step_id]["time_ms"] = step_time
            context.add_log("ERROR", "executor", f"步骤 {step_id} 执行失败: {error}")
            self._notify_progress(step_id, context, progress_callback)
            return {"status": "failed", "branch": None, "was_skipped": False, "error": error}

        # F1: Function Calling —— LLM 节点配置了 tools 参数时,委托给 function_call 执行(agent 循环)
        fc_tools = resolved_params.get("tools")
        if fc_tools and tool_name.startswith("llm_") and tool_name != "function_call":
            fc_func = self.tool_executors.get("function_call")
            if fc_func is not None:
                executor_func = fc_func
                context.add_log("INFO", "executor", f"步骤 {step_id} ({tool_name}) 启用 Function Calling,委托给 function_call")

        # B1: LLM 流式输出——若 step.params.stream=true 且有 progress_callback,
        # 设置 context.token_callback;LLM 工具读取 callback 决定是否流式调用 chat_stream。
        # 回调内通过 progress_callback 推送 step_token 事件(delta 增量),前端实时显示。
        is_stream = bool(resolved_params.get("stream", False))
        if is_stream and progress_callback:
            def _token_cb(delta: str, _sid=step_id):
                progress_callback({
                    "type": "step_token",
                    "step_id": _sid,
                    "delta": delta,
                })
            context.token_callback = _token_cb

        try:
            # B1: 单步超时保护,P2 默认值从 TOOL_TIMEOUT 环境变量读取(默认 120s,上限 300s)
            # step.params.timeout 可单独覆盖;流式 LLM 调用自动放宽至 300s
            timeout = step.get("params", {}).get("timeout", DEFAULT_TOOL_TIMEOUT)
            try:
                timeout = int(timeout)
            except (TypeError, ValueError):
                timeout = DEFAULT_TOOL_TIMEOUT
            timeout = max(1, min(timeout, 300))
            # 流式输出放宽超时上限(token 持续到达说明 LLM 在工作,不算挂起)
            if is_stream:
                timeout = max(timeout, 300)
            output = await asyncio.wait_for(executor_func(resolved_params, context), timeout=timeout)
            step_time = int((time.time() - step_start) * 1000)
            context.set_step_result(step_id, output=output, status="success")
            context.step_results[step_id]["time_ms"] = step_time
            context.add_log("INFO", "executor", f"步骤 {step_id} 执行成功 ({step_time}ms)")
            self._notify_progress(step_id, context, progress_callback)
            return {"status": "success", "branch": None, "was_skipped": False}
        except asyncio.TimeoutError:
            step_time = int((time.time() - step_start) * 1000)
            error_msg = f"步骤执行超时({timeout}s)"
            context.set_step_result(step_id, output=None, status="failed", error=error_msg)
            context.step_results[step_id]["time_ms"] = step_time
            context.add_log("ERROR", "executor", f"步骤 {step_id} {error_msg}")
            self._notify_progress(step_id, context, progress_callback)
            return {"status": "failed", "branch": None, "was_skipped": False, "error": error_msg}
        except Exception as e:
            step_time = int((time.time() - step_start) * 1000)
            context.set_step_result(step_id, output=None, status="failed", error=str(e))
            context.step_results[step_id]["time_ms"] = step_time
            context.add_log("ERROR", "executor", f"步骤 {step_id} 执行失败: {e}")
            self._notify_progress(step_id, context, progress_callback)
            return {"status": "failed", "branch": None, "was_skipped": False, "error": e}
        finally:
            # 清理 token_callback,避免影响后续步骤
            if is_stream:
                context.token_callback = None

    def _find_descendants(
        self,
        step_id: str,
        edges: list,
        out_edges_map: dict[str, list[dict]] | None = None,
    ) -> set:
        """BFS 遍历计算 step_id 的所有后继节点集合

        :param out_edges_map: 邻接表 {from_id: [edge, ...]}。提供时 O(V+E) 查询;
                              未提供时从 edges 构建(兼容旧调用)。
        """
        descendants = set()
        queue = [step_id]
        while queue:
            current = queue.pop(0)
            if out_edges_map is not None:
                neighbors = (e.get("to") for e in out_edges_map.get(current, []))
            else:
                neighbors = (e.get("to") for e in edges if e.get("from") == current)
            for to_id in neighbors:
                if to_id not in descendants:
                    descendants.add(to_id)
                    queue.append(to_id)
        return descendants

    def _handle_failure(
        self,
        step_id: str,
        error: Any,
        context: ExecutionContext,
        on_failure: str,
        step_map: dict,
        out_edges_map: dict,
        pending: dict,
        activated: dict,
        resolved: set,
        ready: list,
        order_index: dict,
        steps: list[dict],
        edges: list[dict],
        progress_callback: Callable | None = None,
    ) -> tuple[str, bool]:
        """
        统一处理步骤执行失败后的边路由（结果已由 _execute_step_only 设置）
        支持步骤级 on_exception 参数（stop / continue / branch）
        :return: (overall_status, should_break)
        """
        resolved.add(step_id)

        # 读取步骤级 on_exception 参数（默认 None，回退到 on_failure）
        step = step_map.get(step_id, {})
        on_exception = step.get("params", {}).get("on_exception")

        if on_exception == "branch":
            # 异常分支：在 context 中设置 branch_id 为 "exception"，
            # 走 condition="exception" 的出边，后续步骤正常执行
            context.step_results[step_id]["branch"] = "exception"
            self._resolve_edges(
                step_id, out_edges_map, pending, activated, resolved,
                ready, order_index, branch="exception",
            )
            return "partial_success", False
        elif on_exception == "continue":
            # 失败继续：标记失败但不跳过后续步骤，继续正常执行
            self._resolve_edges(
                step_id, out_edges_map, pending, activated, resolved,
                ready, order_index, branch=None,
            )
            return "partial_success", False
        elif on_exception == "stop":
            # 显式停止：只跳过该节点的后继，不影响其他并发节点
            self._mark_remaining_skipped(step_id, steps, edges, context, activated, resolved, progress_callback=progress_callback, out_edges_map=out_edges_map)
            return "failed", False
        else:
            # on_exception 未设置：回退到 on_failure（保持向后兼容）
            if on_failure == "continue":
                self._resolve_edges(
                    step_id, out_edges_map, pending, activated, resolved,
                    ready, order_index, branch=None,
                )
                return "partial_success", False
            else:
                # 失败即停：将失败节点的后继步骤标记为 skipped
                self._mark_remaining_skipped(step_id, steps, edges, context, activated, resolved, progress_callback=progress_callback, out_edges_map=out_edges_map)
                return "failed", True

    def _mark_remaining_skipped(
        self, failed_step_id, steps, edges, context, activated=None, resolved=None,
        progress_callback=None, out_edges_map=None,
    ):
        """
        只跳过失败节点的后继集合（用于 on_failure=stop / on_exception=stop）
        - activated 检查：已被其他并发节点激活的后继不跳过（避免影响其他分支）
        """
        descendants = self._find_descendants(failed_step_id, edges, out_edges_map)
        for step in steps:
            sid = step.get("id")
            if sid in descendants and sid not in context.step_results:
                # 已被其他并发路径激活的后继不跳过
                if activated and activated.get(sid, False):
                    continue
                context.set_step_result(
                    sid, output=None, status="skipped",
                    error="前置步骤失败，已跳过",
                )
                context.add_log("WARN", "executor", f"步骤 {sid} 已跳过: 前置步骤失败")
                if progress_callback:
                    self._notify_progress(sid, context, progress_callback)
                if resolved is not None:
                    resolved.add(sid)

    def _resolve_edges(
        self,
        step_id: str,
        out_edges_map: dict[str, list[dict]],
        pending: dict[str, int],
        activated: dict[str, bool],
        resolved: set,
        ready: list[str],
        order_index: dict[str, int],
        branch: str | None = None,
        was_skipped: bool = False,
    ):
        """
        节点执行/跳过后，解析其出边：
        - 普通节点：所有出边激活（condition="exception" 的异常边除外）
        - if_else 节点：仅 condition == branch 的出边激活
        - 异常分支（branch="exception"）：仅 condition="exception" 的出边激活
        - 跳过节点：所有出边不激活（传播跳过）
        目标节点入边全部解析后加入就绪队列
        """
        for edge in out_edges_map[step_id]:
            to_id = edge.get("to")
            if to_id not in pending:
                continue

            condition = edge.get("condition", "")

            # 判断此边是否激活
            if was_skipped:
                is_active = False
            elif branch is not None:
                # 分支节点（if_else 的 true/false 或异常分支 exception）
                is_active = condition == branch
            elif condition == "exception":
                # 普通成功节点不激活异常分支边
                is_active = False
            else:
                is_active = True

            pending[to_id] -= 1
            if is_active:
                activated[to_id] = True

            if pending[to_id] == 0 and to_id not in resolved:
                ready.append(to_id)
                # 保持原始顺序稳定
                ready.sort(key=lambda sid: order_index.get(sid, 0))

    async def _execute_if_else(
        self,
        step: dict,
        context: ExecutionContext,
        step_id: str,
        step_start: float,
    ) -> str:
        """
        执行 if_else 节点：解析参数后调用 if_else 工具求值（支持全部 18 个操作符）
        :return: "true" | "false"
        """
        raw_params = step.get("params", {})
        resolved_params = context.resolve_variables(raw_params)

        field_val = resolved_params.get("field")
        operator = resolved_params.get("operator", "eq")
        target_val = resolved_params.get("value")

        # 直接调用 if_else.py 的 execute，支持全部 18 个操作符
        result = await if_else_execute(
            {"field": field_val, "operator": operator, "value": target_val},
            context,
        )

        branch = result.get("branch", "false")

        step_time = int((time.time() - step_start) * 1000)
        context.set_step_result(
            step_id,
            output=result,
            status="success",
        )
        context.step_results[step_id]["time_ms"] = step_time

        return branch

    async def _execute_loop(
        self,
        step: dict,
        context: ExecutionContext,
        on_failure: str = "stop",
        progress_callback: Callable | None = None,
    ) -> dict:
        """
        执行 loop 节点：对 input_array 每个元素执行 sub_steps 子流程
        - 每轮创建子 ExecutionContext，设置 loop_item / loop_index
        - sub_steps / sub_edges 不在父上下文中解析变量（保留 {{item}}/{{index}}）
        - 收集每轮最后一步输出，合并为数组返回
        - 透传 on_failure 和 progress_callback 给子流程
        - 子流程失败时在该 item 结果中标记 status=failed 和 error
        - B2: 支持 break_on(success/failed) 提前终止,支持 max_iterations 限制遍历数
        """
        raw_params = step.get("params", {})

        # 仅解析 input_array，不解析 sub_steps/sub_edges（含 {{item}} 等子流程变量）
        input_array = context.resolve_variables(raw_params.get("input_array", []))
        sub_steps = raw_params.get("sub_steps", [])
        sub_edges = raw_params.get("sub_edges", [])

        if not isinstance(input_array, list):
            input_array = [input_array] if input_array else []

        # B2: 读取 break_on / max_iterations(可选)
        break_on = raw_params.get("break_on")  # "success" | "failed" | None
        max_iterations = raw_params.get("max_iterations")
        try:
            max_iterations = int(max_iterations) if max_iterations is not None else len(input_array)
        except (TypeError, ValueError):
            max_iterations = len(input_array)
        # 不超过 input_array 长度(避免无限循环)
        max_iterations = max(0, min(max_iterations, len(input_array)))

        results = []
        broken = False
        for index, item in enumerate(input_array):
            # B2: 达到最大迭代数则停止
            if index >= max_iterations:
                break
            # 创建子上下文，继承父级 step_results（深拷贝避免子流程修改污染父级）
            sub_context = ExecutionContext(trigger_data=context.trigger_data)
            sub_context.step_results = copy.deepcopy(context.step_results)
            sub_context.loop_item = item
            sub_context.loop_index = index

            # 执行子流程（透传 on_failure 和 progress_callback）
            # _acquire_lock=False：子流程复用父流程已持有的并发槽位，避免嵌套 acquire 导致死锁
            sub_status = await self._execute_internal(
                sub_steps, sub_edges, sub_context,
                on_failure=on_failure,
                progress_callback=progress_callback,
                _acquire_lock=False,
            )

            # A2 修复:聚合子流程 token_usage / warnings 回父 context
            # (loop 此前缺失此步,导致子流程 LLM 调用 token 丢失,dashboard 统计不准)
            context.merge_token_usage(sub_context.token_usage)
            context.warnings.extend(sub_context.warnings)

            # 检查子流程状态，失败时标记该 item 结果
            if sub_status != "success":
                error_msg = f"loop 子流程第 {index} 项执行失败 (status={sub_status})"
                logger.warning(error_msg)
                results.append({
                    "status": "failed",
                    "error": error_msg,
                    "output": self._get_last_step_output(sub_steps, sub_edges, sub_context),
                })
                # B2: break_on="failed" 时,子流程失败则提前终止
                if break_on == "failed":
                    broken = True
                    break
            else:
                # 收集子流程最后一步输出
                last_output = self._get_last_step_output(sub_steps, sub_edges, sub_context)
                results.append(last_output)
                # B2: break_on="success" 时,子流程成功则提前终止
                if break_on == "success":
                    broken = True
                    break

        return {"results": results, "count": len(results), "broken": broken}

    async def _execute_subworkflow(
        self,
        step: dict,
        context: ExecutionContext,
        on_failure: str = "stop",
        progress_callback: Callable | None = None,
    ) -> dict:
        """A2: 执行子流程调用节点

        流程:
        1. 从 params.workflow_id 加载目标 Workflow 的 steps/edges(从 DB)
        2. 循环引用检测:target_wf_id 不能在 context.subworkflow_call_stack 中
        3. 深度限制:call_stack 长度 >= 5 时拒绝(防止嵌套过深)
        4. 创建子 ExecutionContext(继承父 step_results 深拷贝 + input_mapping 作为 trigger_data)
        5. 递归调用 _execute_internal(_acquire_lock=False 复用父流程并发槽位)
        6. 子流程 token_usage / logs / warnings 聚合回父 context
        7. 返回子流程状态 + 末步输出 + 全部步骤结果

        与 _execute_loop 的差异:
        - loop 对 input_array 每个元素执行同一套 sub_steps
        - subworkflow 对 input_mapping 执行一次引用的 workflow_id 的 steps/edges
        - subworkflow 支持循环引用检测与深度限制

        :param step: 子流程节点定义(含 params.workflow_id / params.input_mapping)
        :param context: 父流程执行上下文
        :param on_failure: 父流程失败策略(子流程用其自身 on_failure,默认继承父级)
        :param progress_callback: 进度回调
        :return: {status, output, sub_steps_result, sub_workflow_id}
        """
        # 延迟 import 避免循环依赖
        from db.database import SessionLocal
        from db.models import Workflow

        raw_params = step.get("params", {})
        resolved_params = context.resolve_variables(raw_params)
        target_wf_id = resolved_params.get("workflow_id") or ""
        input_mapping = resolved_params.get("input_mapping", {}) or {}

        if not target_wf_id:
            raise ValueError("subworkflow 缺少 workflow_id 参数")

        # 循环引用检测:目标 workflow_id 不能在调用链中
        if target_wf_id in context.subworkflow_call_stack:
            chain = " -> ".join(context.subworkflow_call_stack + (target_wf_id,))
            raise ValueError(f"检测到子流程循环引用: {chain}")

        # 深度限制:嵌套层数上限 5(最外层执行不计入,子流程第 1 层即 call_stack 长度 0 -> 1)
        if len(context.subworkflow_call_stack) >= 5:
            raise ValueError(
                f"子流程嵌套深度超限(当前 {len(context.subworkflow_call_stack)} 层,最大 5 层)"
            )

        # 从 DB 加载目标工作流
        db = SessionLocal()
        try:
            wf = db.query(Workflow).filter(Workflow.id == target_wf_id).first()
            if not wf:
                raise ValueError(f"子流程目标工作流不存在: {target_wf_id}")
            sub_steps = json.loads(wf.steps) if wf.steps else []
            sub_edges = json.loads(wf.edges) if wf.edges else []
            sub_on_failure = wf.on_failure or on_failure
            sub_wf_name = wf.name
        finally:
            db.close()

        context.add_log(
            "INFO", "executor",
            f"调用子流程: {sub_wf_name} (id={target_wf_id}, steps={len(sub_steps)})"
        )

        # 构造子上下文:继承父级 step_results(深拷贝避免污染)+ input_mapping 作为 trigger_data
        sub_trigger_data = (
            context.resolve_variables(input_mapping) if isinstance(input_mapping, dict) else {}
        )
        sub_context = ExecutionContext(
            trigger_data=sub_trigger_data,
            preferences=context.preferences,
        )
        sub_context.step_results = copy.deepcopy(context.step_results)
        # 传递调用链:子流程的 call_stack = 父流程 call_stack + 当前 target_wf_id
        sub_context.subworkflow_call_stack = context.subworkflow_call_stack + (target_wf_id,)

        # 递归执行子流程(复用父流程并发槽位,_acquire_lock=False 避免死锁)
        sub_status = await self._execute_internal(
            sub_steps, sub_edges, sub_context,
            on_failure=sub_on_failure,
            progress_callback=progress_callback,
            _acquire_lock=False,
        )

        # 聚合子流程的 token_usage / logs / warnings 回父 context
        context.merge_token_usage(sub_context.token_usage)
        context.logs.extend(sub_context.logs)
        context.warnings.extend(sub_context.warnings)

        # 提取子流程末步输出
        last_output = self._get_last_step_output(sub_steps, sub_edges, sub_context)

        return {
            "status": sub_status,
            "output": last_output,
            "sub_steps_result": sub_context.step_results,
            "sub_workflow_id": target_wf_id,
        }

    def _get_last_step_output(
        self,
        steps: list[dict],
        edges: list[dict],
        context: ExecutionContext,
    ) -> Any:
        """获取子流程最后一步（汇点节点）的输出"""
        if not steps:
            return None

        step_ids = {s.get("id") for s in steps if s.get("id")}
        has_outgoing = set()
        for edge in edges:
            from_id = edge.get("from")
            if from_id in step_ids:
                has_outgoing.add(from_id)

        sinks = [s for s in steps if s.get("id") and s.get("id") not in has_outgoing]
        if sinks:
            return context.get_step_output(sinks[-1].get("id"))

        return context.get_step_output(steps[-1].get("id"))


# 全局执行器单例
executor = WorkflowExecutor()
