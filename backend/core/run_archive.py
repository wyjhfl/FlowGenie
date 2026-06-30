"""D4: RunRecord 归档与保留策略

提供:
- get_archive_retention_days(): 从 UserPreference 读取保留天数(默认 90,0=永久)
- cleanup_old_run_records(): 清理超期已完成的 RunRecord(保留 failed 供复盘)

设计要点:
- 仅清理 status in (success, partial_success) 的记录;failed 始终保留
- retention_days=0 表示永久保留,跳过清理
- 支持可选 workflow_id 过滤(用于按工作流手动清理)
- 支持可选 before_iso 参数(用于手动指定截止时间)
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session
from db.models import RunRecord, UserPreference

logger = logging.getLogger(__name__)

DEFAULT_RETENTION_DAYS = 90
# 仅清理这些状态的记录;failed 始终保留供复盘
CLEANABLE_STATUSES = ("success", "partial_success")


def get_archive_retention_days(db: Session) -> int:
    """从 UserPreference 读取 archive_retention_days,缺省 90,0=永久

    best-effort:读取失败或非法值时返回默认值,不影响主流程。
    """
    try:
        pref = db.query(UserPreference).filter(
            UserPreference.key == "archive_retention_days"
        ).first()
        if pref and pref.value:
            days = int(pref.value)
            if days >= 0:
                return days
    except (ValueError, TypeError) as e:
        logger.warning(f"archive_retention_days 偏好值非法,回退默认 {DEFAULT_RETENTION_DAYS}: {e}")
    return DEFAULT_RETENTION_DAYS


def cleanup_old_run_records(
    db: Session,
    retention_days: Optional[int] = None,
    workflow_id: Optional[str] = None,
    before_iso: Optional[str] = None,
) -> int:
    """清理超期已完成的 RunRecord,返回删除条数

    参数:
    - retention_days: 保留天数;None 则从偏好读取;0 表示永久保留(返回 0)
    - workflow_id: 仅清理指定工作流的记录;None 则清理全部
    - before_iso: 手动指定截止时间(ISO 格式字符串);None 则用 now - retention_days

    清理规则:
    - 仅清理 status in (success, partial_success) 的记录
    - failed 记录始终保留,不受保留天数限制
    """
    if retention_days is None:
        retention_days = get_archive_retention_days(db)
    if retention_days == 0:
        # 0 = 永久保留
        return 0

    if before_iso:
        try:
            cutoff = datetime.fromisoformat(before_iso)
            if cutoff.tzinfo is None:
                cutoff = cutoff.replace(tzinfo=timezone.utc)
        except ValueError as e:
            raise ValueError(f"before_iso 格式非法,需 ISO 8601: {e}")
    else:
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)

    query = db.query(RunRecord).filter(
        RunRecord.status.in_(CLEANABLE_STATUSES),
        RunRecord.started_at < cutoff,
    )
    if workflow_id:
        query = query.filter(RunRecord.workflow_id == workflow_id)

    deleted = query.delete(synchronize_session=False)
    if deleted > 0:
        db.commit()
        logger.info(
            f"清理超期执行记录: 删除 {deleted} 条"
            f" (retention_days={retention_days}, workflow_id={workflow_id or 'all'},"
            f" cutoff={cutoff.isoformat()})"
        )
    else:
        db.rollback()
    return deleted
