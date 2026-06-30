"""APScheduler 调度器管理"""
import json
import logging
from datetime import datetime, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from db.database import SessionLocal
from db.models import Workflow, RunRecord
from engine.executor import executor
from core.preference_schema import load_preferences_from_db
from core.error_sanitize import sanitize_error_text, extract_error
from core.run_record_service import finalize, finalize_error, notify_failure_if_needed, pause_run

logger = logging.getLogger(__name__)

try:
    from zoneinfo import ZoneInfo
    def _get_tz(tz_name: str):
        return ZoneInfo(tz_name)
except ImportError:
    from pytz import timezone as _pytz_timezone
    def _get_tz(tz_name: str):
        return _pytz_timezone(tz_name)

# 全局调度器单例
scheduler_manager: "SchedulerManager" = None


class SchedulerManager:
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self._started = False

    def start(self):
        """启动调度器并加载所有已启用调度的工作流"""
        if self._started:
            return
        self.scheduler.start()
        self._started = True
        self._load_all_jobs()
        self._register_conversation_cleanup_job()
        self._register_archive_cleanup_job()
        self._register_approve_timeout_job()
        logger.info("调度器已启动")

    def _load_all_jobs(self):
        """从数据库加载所有 schedule_enabled=True 的工作流，注册定时任务"""
        db = SessionLocal()
        try:
            workflows = db.query(Workflow).filter(Workflow.schedule_enabled == True).all()
            for wf in workflows:
                self._add_job_from_workflow(wf)
            logger.info(f"已加载 {len(workflows)} 个定时任务")
        finally:
            db.close()

    def _add_job_from_workflow(self, workflow: Workflow):
        """从工作流定义中提取 cron 表达式并注册定时任务"""
        steps = json.loads(workflow.steps) if workflow.steps else []
        cron_expr = None
        tz_name = "Asia/Shanghai"
        for step in steps:
            if step.get("tool") == "schedule_trigger":
                params = step.get("params", {})
                cron_expr = params.get("cron")
                tz_name = params.get("timezone", "Asia/Shanghai")
                break

        if not cron_expr:
            logger.warning(f"工作流 {workflow.id} 无 cron 表达式，跳过调度")
            return

        try:
            # 解析 cron 表达式（5 字段：分 时 日 月 周）
            parts = cron_expr.split()
            if len(parts) != 5:
                raise ValueError(f"cron 表达式必须是 5 字段: {cron_expr}")

            # 解析时区，失败时回退默认时区
            try:
                tz = _get_tz(tz_name)
            except Exception as e:
                logger.warning(f"无法解析时区 '{tz_name}'，回退 Asia/Shanghai: {e}")
                tz = _get_tz("Asia/Shanghai")

            trigger = CronTrigger(
                minute=parts[0], hour=parts[1], day=parts[2],
                month=parts[3], day_of_week=parts[4],
                timezone=tz,
            )

            job_id = f"workflow_{workflow.id}"
            self.scheduler.add_job(
                func=_execute_scheduled_workflow,
                trigger=trigger,
                args=[workflow.id],
                id=job_id,
                replace_existing=True,
            )
            logger.info(f"已注册定时任务: {job_id} (cron={cron_expr})")
        except Exception as e:
            logger.error(f"注册定时任务失败 {workflow.id}: {e}")

    def add_job(self, workflow_id: str):
        """启用某工作流的调度"""
        db = SessionLocal()
        try:
            wf = db.query(Workflow).filter(Workflow.id == workflow_id).first()
            if wf:
                self._add_job_from_workflow(wf)
        finally:
            db.close()

    def remove_job(self, workflow_id: str):
        """移除某工作流的调度"""
        job_id = f"workflow_{workflow_id}"
        try:
            self.scheduler.remove_job(job_id)
            logger.info(f"已移除定时任务: {job_id}")
        except Exception:
            pass  # 任务不存在则忽略

    def get_job(self, workflow_id: str):
        """获取某工作流的调度任务，不存在返回 None"""
        job_id = f"workflow_{workflow_id}"
        try:
            return self.scheduler.get_job(job_id)
        except Exception:
            return None

    def shutdown(self):
        """优雅关闭调度器"""
        if self._started:
            self.scheduler.shutdown(wait=False)
            self._started = False
            logger.info("调度器已关闭")

    def _register_conversation_cleanup_job(self):
        """F2: 注册定时清理过期会话任务(每日 03:00 执行)

        删除 expires_at < now 的 ConversationSession 记录,避免会话表无限增长。
        """
        try:
            tz = _get_tz("Asia/Shanghai")
            trigger = CronTrigger(hour=3, minute=0, timezone=tz)
            self.scheduler.add_job(
                func=_cleanup_expired_conversations,
                trigger=trigger,
                id="conversation_cleanup",
                replace_existing=True,
            )
            logger.info("已注册会话清理定时任务: conversation_cleanup (每日 03:00)")
        except Exception as e:
            logger.error(f"注册会话清理任务失败: {e}")

    def _register_archive_cleanup_job(self):
        """D4: 注册定时清理超期执行记录任务(每日 04:00 执行)

        删除 started_at < now - retention_days 且 status in (success, partial_success) 的 RunRecord。
        failed 记录始终保留供复盘。retention_days=0 时跳过清理(永久保留)。
        """
        try:
            tz = _get_tz("Asia/Shanghai")
            trigger = CronTrigger(hour=4, minute=0, timezone=tz)
            self.scheduler.add_job(
                func=_cleanup_old_runs,
                trigger=trigger,
                id="archive_cleanup",
                replace_existing=True,
            )
            logger.info("已注册执行记录归档清理定时任务: archive_cleanup (每日 04:00)")
        except Exception as e:
            logger.error(f"注册归档清理任务失败: {e}")

    def _register_approve_timeout_job(self):
        """A1: 注册审批超时清理任务(每日 05:00 执行)

        扫描 status=paused 且 paused_at < now - 24h 的 RunRecord,
        标记为 failed(error=审批超时自动拒绝),失效 dashboard 缓存。
        """
        try:
            tz = _get_tz("Asia/Shanghai")
            trigger = CronTrigger(hour=5, minute=0, timezone=tz)
            self.scheduler.add_job(
                func=_cleanup_expired_approvals,
                trigger=trigger,
                id="approve_timeout_cleanup",
                replace_existing=True,
            )
            logger.info("已注册审批超时清理定时任务: approve_timeout_cleanup (每日 05:00)")
        except Exception as e:
            logger.error(f"注册审批超时清理任务失败: {e}")


def _cleanup_expired_conversations():
    """F2: 清理过期会话(由 scheduler 每日 03:00 触发)"""
    from db.models import ConversationSession
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        deleted = db.query(ConversationSession).filter(
            ConversationSession.expires_at < now
        ).delete(synchronize_session=False)
        if deleted > 0:
            db.commit()
            logger.info(f"清理过期会话: 删除 {deleted} 条")
        else:
            db.rollback()
    except Exception as e:
        db.rollback()
        logger.error(f"清理过期会话失败: {e}")
    finally:
        db.close()


def _cleanup_old_runs():
    """D4: 清理超期执行记录(由 scheduler 每日 04:00 触发)

    从 UserPreference 读取 archive_retention_days(默认 90,0=永久),
    删除 started_at < now - retention_days 且 status in (success, partial_success) 的记录。
    failed 记录始终保留。
    """
    from core.run_archive import cleanup_old_run_records
    db = SessionLocal()
    try:
        deleted = cleanup_old_run_records(db)
        if deleted > 0:
            logger.info(f"归档清理: 删除 {deleted} 条超期执行记录")
    except Exception as e:
        logger.error(f"归档清理失败: {e}")
    finally:
        db.close()


def _cleanup_expired_approvals():
    """A1: 清理超期审批(由 scheduler 每日 05:00 触发)

    扫描 status=paused 且 paused_at < now - 24h 的 RunRecord,
    标记为 failed(error=审批超时自动拒绝),失效 dashboard 缓存。
    通知不在超时路径触发(边缘场景,失败通知在 manual/schedule/webhook 执行路径已覆盖)。
    """
    from datetime import timedelta
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        threshold = now - timedelta(hours=24)
        expired = db.query(RunRecord).filter(
            RunRecord.status == "paused",
            RunRecord.paused_at < threshold,
        ).all()
        if not expired:
            return
        for run in expired:
            try:
                run.status = "failed"
                run.error = "审批超时自动拒绝"
                run.finished_at = now
                logger.info(f"审批超时自动拒绝: run_id={run.id} workflow_id={run.workflow_id}")
            except Exception as e:
                logger.error(f"处理超期审批 run_id={getattr(run, 'id', '?')} 失败: {e}")
        db.commit()
        # 失效 dashboard 缓存(与 run_record_service 一致)
        try:
            from core.run_record_service import _invalidate_dashboard_cache
            _invalidate_dashboard_cache()
        except Exception:
            pass
        logger.info(f"清理超期审批: 处理 {len(expired)} 条")
    except Exception as e:
        logger.error(f"清理超期审批失败: {e}")
        db.rollback()
    finally:
        db.close()


async def _execute_scheduled_workflow(workflow_id: str, run_id: str | None = None):
    """定时任务回调：加载工作流并执行。

    若提供 run_id，则复用已创建的 RunRecord（用于手动触发场景）；
    否则内部创建新的 RunRecord。返回 run_id，失败返回 None。
    """
    db = SessionLocal()
    try:
        run = None
        wf = db.query(Workflow).filter(Workflow.id == workflow_id).first()
        if not wf:
            logger.warning(f"定时任务触发但工作流不存在: {workflow_id}")
            return None

        steps = json.loads(wf.steps) if wf.steps else []
        edges = json.loads(wf.edges) if wf.edges else []

        # 创建或复用 RunRecord
        if run_id:
            run = db.query(RunRecord).filter(RunRecord.id == run_id).first()
        if not run:
            run = RunRecord(
                workflow_id=workflow_id,
                trigger_type="schedule",
                status="running",
                started_at=datetime.now(timezone.utc),
            )
            db.add(run)
            db.commit()
            db.refresh(run)

        # 执行工作流
        result = await executor.execute(
            steps=steps,
            edges=edges,
            trigger_data={},
            on_failure=wf.on_failure or "stop",
            preferences=load_preferences_from_db(),
        )

        # A1: 审批暂停——保存 context + 推送 WS(不调用 finalize,不触发失败通知)
        if result.get("status") == "paused":
            paused_step_id = result.get("paused_step_id", "")
            pause_run(db, run, result, paused_step_id)
            logger.info(f"定时执行工作流 {workflow_id} 暂停于审批节点: {paused_step_id}")
            try:
                from routers.ws import notify_workflow_paused
                await notify_workflow_paused(
                    run_id=run.id, workflow_id=workflow_id,
                    message=result.get("paused_message", "请审批此步骤以继续执行"),
                    approvers=result.get("paused_approvers", []),
                    paused_step_id=paused_step_id,
                )
            except Exception as e:
                logger.warning(f"推送审批 WS 通知失败: {e}")
            return run.id

        # 更新 RunRecord(统一走 RunRecordService,内置 dashboard 缓存失效)
        finalize(db, run, result)

        logger.info(f"定时执行工作流 {workflow_id} 完成: {result['status']}")

        # 失败通知（异常不影响主流程,error 已脱敏)
        await notify_failure_if_needed(
            db,
            workflow_name=wf.name,
            run_id=run.id,
            status=result["status"],
            error=run.error or "",
            steps_result=result.get("steps_result"),
        )
        return run.id
    except Exception as e:
        logger.error(f"定时执行工作流 {workflow_id} 失败: {e}")
        # 更新 RunRecord 为 failed（run 可能未创建，需判空避免 UnboundLocalError）
        if run is not None:
            try:
                finalize_error(db, run, str(e))
            except Exception:
                pass
        return None
    finally:
        db.close()


def init_scheduler():
    """初始化全局调度器（应用启动时调用）"""
    global scheduler_manager
    if scheduler_manager is None:
        scheduler_manager = SchedulerManager()
    return scheduler_manager


# 向后兼容别名(若有外部引用)
_extract_error = extract_error
