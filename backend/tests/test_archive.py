"""D4: RunRecord 归档与保留策略测试

覆盖:
- get_archive_retention_days:默认值 / 偏好读取 / 非法值回退
- cleanup_old_run_records:
  * 清理 success / partial_success 超期记录
  * failed 记录始终保留
  * retention_days=0 永久保留
  * before_iso 手动指定截止时间
  * workflow_id 过滤
  * retention_days 显式参数覆盖偏好值
- 手动清理 API 端点 DELETE /api/workflows/{id}/runs/cleanup
"""
import pytest
from datetime import datetime, timezone, timedelta
from urllib.parse import quote

from db.models import Workflow, RunRecord, UserPreference
from core.run_archive import (
    get_archive_retention_days,
    cleanup_old_run_records,
    DEFAULT_RETENTION_DAYS,
    CLEANABLE_STATUSES,
)


# ========== 辅助函数 ==========

def _make_run(
    db,
    workflow_id: str,
    status: str,
    started_at: datetime,
    run_id: str = None,
) -> RunRecord:
    """创建一条 RunRecord 并提交"""
    run = RunRecord(
        id=run_id or f"run-{workflow_id}-{status}-{started_at.timestamp()}",
        workflow_id=workflow_id,
        trigger_type="manual",
        status=status,
        total_time_ms=100,
        started_at=started_at,
        finished_at=started_at + timedelta(seconds=1),
    )
    db.add(run)
    db.commit()
    return run


def _make_workflow(db, workflow_id: str = "wf-1") -> Workflow:
    """创建一条 Workflow 并提交"""
    wf = Workflow(id=workflow_id, name=f"工作流-{workflow_id}", steps="[]", edges="[]")
    db.add(wf)
    db.commit()
    return wf


def _set_preference(db, key: str, value: str):
    """写入/更新 UserPreference 并提交"""
    existing = db.query(UserPreference).filter(UserPreference.key == key).first()
    if existing:
        existing.value = value
    else:
        db.add(UserPreference(key=key, value=value))
    db.commit()


# ========== get_archive_retention_days ==========

def test_get_archive_retention_days_default(test_db):
    """无偏好时返回默认值 90"""
    assert get_archive_retention_days(test_db) == DEFAULT_RETENTION_DAYS


def test_get_archive_retention_days_from_preference(test_db):
    """从偏好读取自定义值"""
    _set_preference(test_db, "archive_retention_days", "30")
    assert get_archive_retention_days(test_db) == 30


def test_get_archive_retention_days_zero_means_forever(test_db):
    """0 表示永久保留,合法返回"""
    _set_preference(test_db, "archive_retention_days", "0")
    assert get_archive_retention_days(test_db) == 0


def test_get_archive_retention_days_invalid_value_fallback(test_db):
    """非法值(非数字)回退默认"""
    _set_preference(test_db, "archive_retention_days", "abc")
    assert get_archive_retention_days(test_db) == DEFAULT_RETENTION_DAYS


def test_get_archive_retention_days_negative_fallback(test_db):
    """负数回退默认"""
    _set_preference(test_db, "archive_retention_days", "-1")
    assert get_archive_retention_days(test_db) == DEFAULT_RETENTION_DAYS


# ========== cleanup_old_run_records 核心逻辑 ==========

def test_cleanup_cleans_success_and_partial_success(test_db):
    """超期的 success / partial_success 被清理,failed 保留"""
    wf = _make_workflow(test_db, "wf-clean")
    cutoff = datetime.now(timezone.utc) - timedelta(days=10)
    old_success = _make_run(test_db, wf.id, "success", cutoff - timedelta(days=1))
    old_partial = _make_run(test_db, wf.id, "partial_success", cutoff - timedelta(days=2))
    old_failed = _make_run(test_db, wf.id, "failed", cutoff - timedelta(days=3))
    # 提前记录 ID,避免对象被 bulk delete 后访问触发 ObjectDeletedError
    success_id = old_success.id
    partial_id = old_partial.id
    failed_id = old_failed.id

    deleted = cleanup_old_run_records(test_db, retention_days=5)
    assert deleted == 2

    # expire_all 让 session 丢弃已删除对象的缓存,避免访问时报 ObjectDeletedError
    test_db.expire_all()
    remaining_ids = {r.id for r in test_db.query(RunRecord).all()}
    assert failed_id in remaining_ids
    assert success_id not in remaining_ids
    assert partial_id not in remaining_ids


def test_cleanup_keeps_failed_regardless_of_age(test_db):
    """无论多旧,failed 记录始终保留"""
    wf = _make_workflow(test_db, "wf-fail")
    very_old = datetime.now(timezone.utc) - timedelta(days=365)
    old_failed = _make_run(test_db, wf.id, "failed", very_old)
    old_success = _make_run(test_db, wf.id, "success", very_old)
    failed_id = old_failed.id
    success_id = old_success.id

    deleted = cleanup_old_run_records(test_db, retention_days=30)
    assert deleted == 1  # 只清理 success

    test_db.expire_all()
    remaining = {r.id for r in test_db.query(RunRecord).all()}
    assert failed_id in remaining
    assert success_id not in remaining


def test_cleanup_zero_retention_keeps_everything(test_db):
    """retention_days=0 表示永久保留,不清理任何记录"""
    wf = _make_workflow(test_db, "wf-zero")
    very_old = datetime.now(timezone.utc) - timedelta(days=365)
    old_success = _make_run(test_db, wf.id, "success", very_old)
    success_id = old_success.id

    deleted = cleanup_old_run_records(test_db, retention_days=0)
    assert deleted == 0

    test_db.expire_all()
    remaining = {r.id for r in test_db.query(RunRecord).all()}
    assert success_id in remaining


def test_cleanup_keeps_recent_records(test_db):
    """未超期的记录保留"""
    wf = _make_workflow(test_db, "wf-recent")
    now = datetime.now(timezone.utc)
    recent_success = _make_run(test_db, wf.id, "success", now - timedelta(days=1))
    success_id = recent_success.id

    deleted = cleanup_old_run_records(test_db, retention_days=30)
    assert deleted == 0

    test_db.expire_all()
    remaining = {r.id for r in test_db.query(RunRecord).all()}
    assert success_id in remaining


def test_cleanup_before_iso_overrides_retention(test_db):
    """before_iso 参数优先,手动指定截止时间"""
    wf = _make_workflow(test_db, "wf-before")
    now = datetime.now(timezone.utc)
    # 5 天前的 success(若用 retention_days=30 则不会被清理)
    old_success = _make_run(test_db, wf.id, "success", now - timedelta(days=5))
    # 1 天前的 success(before=2天前 时不会被清理)
    recent_success = _make_run(test_db, wf.id, "success", now - timedelta(days=1))
    old_id = old_success.id
    recent_id = recent_success.id

    # before = 2 天前:只清理 started_at < (now-2天) 的记录
    before_iso = (now - timedelta(days=2)).isoformat()
    deleted = cleanup_old_run_records(test_db, retention_days=30, before_iso=before_iso)
    assert deleted == 1

    test_db.expire_all()
    remaining = {r.id for r in test_db.query(RunRecord).all()}
    assert old_id not in remaining
    assert recent_id in remaining


def test_cleanup_before_iso_invalid_format_raises(test_db):
    """before_iso 非法格式抛 ValueError"""
    wf = _make_workflow(test_db, "wf-bad")
    with pytest.raises(ValueError):
        cleanup_old_run_records(test_db, retention_days=30, before_iso="not-a-date")


def test_cleanup_workflow_id_filter(test_db):
    """workflow_id 过滤:仅清理指定工作流的记录"""
    wf_a = _make_workflow(test_db, "wf-a")
    wf_b = _make_workflow(test_db, "wf-b")
    very_old = datetime.now(timezone.utc) - timedelta(days=365)
    run_a = _make_run(test_db, wf_a.id, "success", very_old, run_id="run-a-old")
    run_b = _make_run(test_db, wf_b.id, "success", very_old, run_id="run-b-old")
    a_id = run_a.id
    b_id = run_b.id

    deleted = cleanup_old_run_records(test_db, retention_days=30, workflow_id="wf-a")
    assert deleted == 1

    test_db.expire_all()
    remaining = {r.id for r in test_db.query(RunRecord).all()}
    assert a_id not in remaining
    assert b_id in remaining


def test_cleanup_reads_retention_from_preference_when_none(test_db):
    """retention_days=None 时从偏好读取"""
    wf = _make_workflow(test_db, "wf-pref")
    _set_preference(test_db, "archive_retention_days", "10")
    now = datetime.now(timezone.utc)
    # 20 天前的 success(按偏好 10 天应被清理)
    old_success = _make_run(test_db, wf.id, "success", now - timedelta(days=20))
    # 5 天前的 success(按偏好 10 天保留)
    recent_success = _make_run(test_db, wf.id, "success", now - timedelta(days=5))
    old_id = old_success.id
    recent_id = recent_success.id

    deleted = cleanup_old_run_records(test_db)  # retention_days=None
    assert deleted == 1

    test_db.expire_all()
    remaining = {r.id for r in test_db.query(RunRecord).all()}
    assert old_id not in remaining
    assert recent_id in remaining


def test_cleanup_no_matching_records_returns_zero(test_db):
    """无匹配记录时返回 0 且不报错"""
    wf = _make_workflow(test_db, "wf-empty")
    now = datetime.now(timezone.utc)
    _make_run(test_db, wf.id, "success", now - timedelta(days=1))  # 未超期

    deleted = cleanup_old_run_records(test_db, retention_days=30)
    assert deleted == 0


def test_cleanable_statuses_constant():
    """常量校验:仅 success / partial_success 可清理"""
    assert set(CLEANABLE_STATUSES) == {"success", "partial_success"}
    assert "failed" not in CLEANABLE_STATUSES
    assert "running" not in CLEANABLE_STATUSES


# ========== 手动清理 API 端点 ==========

@pytest.mark.asyncio
async def test_cleanup_api_default(client, test_db):
    """默认参数:按偏好 retention_days 清理"""
    wf = _make_workflow(test_db, "wf-api")
    _set_preference(test_db, "archive_retention_days", "10")
    now = datetime.now(timezone.utc)
    _make_run(test_db, wf.id, "success", now - timedelta(days=20), run_id="r1")
    _make_run(test_db, wf.id, "failed", now - timedelta(days=20), run_id="r2")

    resp = await client.delete(f"/api/workflows/{wf.id}/runs/cleanup")
    assert resp.status_code == 200
    data = resp.json()
    assert data["deleted"] == 1
    assert data["workflow_id"] == wf.id

    # failed 仍保留
    test_db.expire_all()
    remaining = {r.id for r in test_db.query(RunRecord).all()}
    assert "r2" in remaining
    assert "r1" not in remaining


@pytest.mark.asyncio
async def test_cleanup_api_with_before_param(client, test_db):
    """before 参数:手动指定截止时间"""
    wf = _make_workflow(test_db, "wf-before-api")
    now = datetime.now(timezone.utc)
    _make_run(test_db, wf.id, "success", now - timedelta(days=5), run_id="r-old")
    _make_run(test_db, wf.id, "success", now - timedelta(days=1), run_id="r-new")

    # ISO 8601 时间戳含 + 号,需 URL 编码(否则 + 在 query string 中被解码为空格)
    before_iso = (now - timedelta(days=2)).isoformat()
    resp = await client.delete(
        f"/api/workflows/{wf.id}/runs/cleanup?before={quote(before_iso, safe='')}"
    )
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 1

    test_db.expire_all()
    remaining = {r.id for r in test_db.query(RunRecord).all()}
    assert "r-old" not in remaining
    assert "r-new" in remaining


@pytest.mark.asyncio
async def test_cleanup_api_with_retention_days_param(client, test_db):
    """retention_days 参数:覆盖偏好值"""
    wf = _make_workflow(test_db, "wf-retention-api")
    _set_preference(test_db, "archive_retention_days", "90")
    now = datetime.now(timezone.utc)
    _make_run(test_db, wf.id, "success", now - timedelta(days=20), run_id="r-old")
    _make_run(test_db, wf.id, "success", now - timedelta(days=5), run_id="r-new")

    # 显式传 retention_days=10:5天前的保留,20天前的清理
    resp = await client.delete(
        f"/api/workflows/{wf.id}/runs/cleanup?retention_days=10"
    )
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 1

    test_db.expire_all()
    remaining = {r.id for r in test_db.query(RunRecord).all()}
    assert "r-old" not in remaining
    assert "r-new" in remaining


@pytest.mark.asyncio
async def test_cleanup_api_retention_zero_keeps_all(client, test_db):
    """retention_days=0 永久保留"""
    wf = _make_workflow(test_db, "wf-zero-api")
    now = datetime.now(timezone.utc)
    _make_run(test_db, wf.id, "success", now - timedelta(days=365), run_id="r-old")

    resp = await client.delete(
        f"/api/workflows/{wf.id}/runs/cleanup?retention_days=0"
    )
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 0

    test_db.expire_all()
    remaining = {r.id for r in test_db.query(RunRecord).all()}
    assert "r-old" in remaining


@pytest.mark.asyncio
async def test_cleanup_api_workflow_not_found(client):
    """工作流不存在返回 404"""
    resp = await client.delete("/api/workflows/nonexistent-id/runs/cleanup")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cleanup_api_invalid_before_returns_400(client, test_db):
    """before 参数非法返回 400"""
    wf = _make_workflow(test_db, "wf-bad-api")
    resp = await client.delete(
        f"/api/workflows/{wf.id}/runs/cleanup?before=not-a-date"
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_cleanup_api_only_targets_specified_workflow(client, test_db):
    """清理只影响指定工作流,其他工作流的超期记录不受影响"""
    wf_a = _make_workflow(test_db, "wf-target")
    wf_b = _make_workflow(test_db, "wf-other")
    now = datetime.now(timezone.utc)
    _make_run(test_db, wf_a.id, "success", now - timedelta(days=20), run_id="r-a")
    _make_run(test_db, wf_b.id, "success", now - timedelta(days=20), run_id="r-b")

    resp = await client.delete(
        f"/api/workflows/{wf_a.id}/runs/cleanup?retention_days=10"
    )
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 1

    test_db.expire_all()
    remaining = {r.id for r in test_db.query(RunRecord).all()}
    assert "r-a" not in remaining
    assert "r-b" in remaining


@pytest.mark.asyncio
async def test_cleanup_api_keeps_failed_runs(client, test_db):
    """清理 API 始终保留 failed 记录"""
    wf = _make_workflow(test_db, "wf-keep-failed")
    now = datetime.now(timezone.utc)
    _make_run(test_db, wf.id, "success", now - timedelta(days=20), run_id="r-success")
    _make_run(test_db, wf.id, "failed", now - timedelta(days=20), run_id="r-failed")

    resp = await client.delete(
        f"/api/workflows/{wf.id}/runs/cleanup?retention_days=10"
    )
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 1

    test_db.expire_all()
    remaining = {r.id for r in test_db.query(RunRecord).all()}
    assert "r-failed" in remaining
    assert "r-success" not in remaining
