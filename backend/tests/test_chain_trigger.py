"""A3: 链式触发测试

覆盖:
- _status_matches 纯函数(状态过滤逻辑)
- maybe_trigger_chain 空配置跳过
- maybe_trigger_chain 深度上限拒绝
- maybe_trigger_chain 状态匹配触发(on=always/success/failed)
- maybe_trigger_chain 状态不匹配跳过
- maybe_trigger_chain 无事件循环静默跳过
- validate_on_complete_trigger 结构校验
"""
import json
import pytest
from unittest.mock import patch, AsyncMock
from sqlalchemy.orm import sessionmaker

from core.chain_trigger import (
    maybe_trigger_chain,
    _status_matches,
    MAX_CHAIN_DEPTH,
)
from core.validator import validate_on_complete_trigger
from db.models import Workflow


# ---------- 纯函数:状态过滤 ----------

def test_status_matches_always():
    """on=always 时任何状态都触发"""
    assert _status_matches("success", "always") is True
    assert _status_matches("failed", "always") is True
    assert _status_matches("aborted", "always") is True


def test_status_matches_success():
    """on=success 仅 success 触发"""
    assert _status_matches("success", "success") is True
    assert _status_matches("failed", "success") is False
    assert _status_matches("aborted", "success") is False


def test_status_matches_failed():
    """on=failed 时 failed 和 aborted 都触发"""
    assert _status_matches("failed", "failed") is True
    assert _status_matches("aborted", "failed") is True
    assert _status_matches("success", "failed") is False


def test_status_matches_invalid_on():
    """非法 on 值不触发"""
    assert _status_matches("success", "unknown") is False


# ---------- maybe_trigger_chain 行为 ----------

def _make_workflow_with_trigger(test_db, wf_id, triggers):
    """在测试 DB 创建含 on_complete_trigger 的工作流"""
    wf = Workflow(
        id=wf_id,
        name=f"测试工作流 {wf_id}",
        steps="[]",
        edges="[]",
        on_complete_trigger=json.dumps(triggers, ensure_ascii=False),
    )
    test_db.add(wf)
    test_db.commit()
    return wf


def _patch_sessionlocal(test_engine):
    """patch db.database.SessionLocal 指向测试内存 DB"""
    TestSession = sessionmaker(bind=test_engine, autocommit=False, autoflush=False)
    return patch("db.database.SessionLocal", TestSession)


@pytest.mark.asyncio
async def test_maybe_trigger_chain_empty_config(test_db, test_engine):
    """on_complete_trigger 为空列表时,不触发"""
    _make_workflow_with_trigger(test_db, "wf-empty", [])
    with _patch_sessionlocal(test_engine):
        with patch("core.chain_trigger._execute_chain_target", new_callable=AsyncMock) as mock_exec:
            maybe_trigger_chain("wf-empty", "success", {})
            await _drain_tasks()
    mock_exec.assert_not_called()


@pytest.mark.asyncio
async def test_maybe_trigger_chain_depth_limit(test_db, test_engine):
    """_chain_depth >= MAX_CHAIN_DEPTH 时拒绝触发"""
    _make_workflow_with_trigger(test_db, "wf-deep", [
        {"workflow_id": "wf-target", "on": "always"}
    ])
    # depth=MAX_CHAIN_DEPTH(3),应拒绝
    trigger_data = {"_chain_depth": MAX_CHAIN_DEPTH}
    with _patch_sessionlocal(test_engine):
        with patch("core.chain_trigger._execute_chain_target", new_callable=AsyncMock) as mock_exec:
            maybe_trigger_chain("wf-deep", "success", trigger_data)
            await _drain_tasks()
    mock_exec.assert_not_called()


@pytest.mark.asyncio
async def test_maybe_trigger_chain_depth_below_limit_triggers(test_db, test_engine):
    """_chain_depth < MAX_CHAIN_DEPTH 时允许触发"""
    _make_workflow_with_trigger(test_db, "wf-shallow", [
        {"workflow_id": "wf-target", "on": "always"}
    ])
    trigger_data = {"_chain_depth": 0}  # 首次执行
    with _patch_sessionlocal(test_engine):
        with patch("core.chain_trigger._execute_chain_target", new_callable=AsyncMock) as mock_exec:
            maybe_trigger_chain("wf-shallow", "success", trigger_data)
            await _drain_tasks()
    mock_exec.assert_called_once()
    # 验证传入的 chain_data 深度 +1
    call_args = mock_exec.call_args
    chain_data = call_args[0][1] if call_args[0] else call_args[1].get("chain_trigger_data")
    assert chain_data["_chain_depth"] == 1
    assert chain_data["_chain_from"] == "wf-shallow"


@pytest.mark.asyncio
async def test_maybe_trigger_chain_status_match_always(test_db, test_engine):
    """on=always 时无论 status 都触发"""
    _make_workflow_with_trigger(test_db, "wf-always", [
        {"workflow_id": "wf-target", "on": "always"}
    ])
    with _patch_sessionlocal(test_engine):
        with patch("core.chain_trigger._execute_chain_target", new_callable=AsyncMock) as mock_exec:
            maybe_trigger_chain("wf-always", "failed", {})
            await _drain_tasks()
    mock_exec.assert_called_once()


@pytest.mark.asyncio
async def test_maybe_trigger_chain_status_match_success(test_db, test_engine):
    """on=success + run_status=success 触发"""
    _make_workflow_with_trigger(test_db, "wf-succ", [
        {"workflow_id": "wf-target", "on": "success"}
    ])
    with _patch_sessionlocal(test_engine):
        with patch("core.chain_trigger._execute_chain_target", new_callable=AsyncMock) as mock_exec:
            maybe_trigger_chain("wf-succ", "success", {})
            await _drain_tasks()
    mock_exec.assert_called_once()


@pytest.mark.asyncio
async def test_maybe_trigger_chain_status_mismatch(test_db, test_engine):
    """on=success + run_status=failed 不触发"""
    _make_workflow_with_trigger(test_db, "wf-mismatch", [
        {"workflow_id": "wf-target", "on": "success"}
    ])
    with _patch_sessionlocal(test_engine):
        with patch("core.chain_trigger._execute_chain_target", new_callable=AsyncMock) as mock_exec:
            maybe_trigger_chain("wf-mismatch", "failed", {})
            await _drain_tasks()
    mock_exec.assert_not_called()


@pytest.mark.asyncio
async def test_maybe_trigger_chain_no_event_loop(test_db, test_engine):
    """无运行中的事件循环时静默跳过(不报错)

    maybe_trigger_chain 在同步上下文调用时,get_running_loop 抛 RuntimeError,应静默返回。
    """
    _make_workflow_with_trigger(test_db, "wf-noloop", [
        {"workflow_id": "wf-target", "on": "always"}
    ])
    with _patch_sessionlocal(test_engine):
        with patch("asyncio.get_running_loop", side_effect=RuntimeError("no loop")):
            with patch("core.chain_trigger._execute_chain_target", new_callable=AsyncMock) as mock_exec:
                # 在事件循环内但 mock get_running_loop 抛错
                maybe_trigger_chain("wf-noloop", "success", {})
                await _drain_tasks()
    mock_exec.assert_not_called()


@pytest.mark.asyncio
async def test_maybe_trigger_chain_multiple_targets(test_db, test_engine):
    """多个匹配目标工作流时,每个都触发"""
    _make_workflow_with_trigger(test_db, "wf-multi", [
        {"workflow_id": "wf-target-1", "on": "always"},
        {"workflow_id": "wf-target-2", "on": "success"},
        {"workflow_id": "wf-target-3", "on": "failed"},  # 不匹配 success
    ])
    with _patch_sessionlocal(test_engine):
        with patch("core.chain_trigger._execute_chain_target", new_callable=AsyncMock) as mock_exec:
            maybe_trigger_chain("wf-multi", "success", {})
            await _drain_tasks()
    # 应触发 target-1(always) 和 target-2(success),不触发 target-3(failed)
    assert mock_exec.call_count == 2


@pytest.mark.asyncio
async def test_maybe_trigger_chain_nonexistent_workflow(test_db, test_engine):
    """workflow_id 不存在时静默跳过(不报错)"""
    with _patch_sessionlocal(test_engine):
        with patch("core.chain_trigger._execute_chain_target", new_callable=AsyncMock) as mock_exec:
            maybe_trigger_chain("wf-not-exist", "success", {})
            await _drain_tasks()
    mock_exec.assert_not_called()


# ---------- validate_on_complete_trigger ----------

def test_validate_on_complete_trigger_none():
    """None 视为未设置,合法"""
    assert validate_on_complete_trigger(None) == []


def test_validate_on_complete_trigger_empty_list():
    """空列表合法"""
    assert validate_on_complete_trigger([]) == []


def test_validate_on_complete_trigger_valid():
    """合法配置无错误"""
    triggers = [
        {"workflow_id": "wf-1", "on": "success"},
        {"workflow_id": "wf-2", "on": "failed"},
        {"workflow_id": "wf-3", "on": "always"},
        {"workflow_id": "wf-4"},  # 缺省 on,默认 always
    ]
    errors = validate_on_complete_trigger(triggers)
    assert errors == []


def test_validate_on_complete_trigger_missing_workflow_id():
    """缺少 workflow_id 报错"""
    triggers = [{"on": "success"}]
    errors = validate_on_complete_trigger(triggers)
    assert len(errors) == 1
    assert "workflow_id" in errors[0]


def test_validate_on_complete_trigger_invalid_on():
    """非法 on 值报错"""
    triggers = [{"workflow_id": "wf-1", "on": "invalid"}]
    errors = validate_on_complete_trigger(triggers)
    assert len(errors) == 1
    assert "on" in errors[0]


def test_validate_on_complete_trigger_self_reference():
    """自引用报错"""
    triggers = [{"workflow_id": "wf-self", "on": "always"}]
    errors = validate_on_complete_trigger(triggers, self_workflow_id="wf-self")
    assert len(errors) == 1
    assert "自身" in errors[0]


def test_validate_on_complete_trigger_not_list():
    """非列表报错"""
    errors = validate_on_complete_trigger("not a list")
    assert len(errors) == 1
    assert "数组" in errors[0]


# ---------- 辅助函数 ----------

async def _drain_tasks():
    """让事件循环处理 pending 的 create_task 任务

    maybe_trigger_chain 用 loop.create_task 调度 _execute_chain_target,
    测试中 mock 了 _execute_chain_target,但仍需让 task 执行以避免 warning。
    """
    import asyncio
    # 让事件循环处理一个 tick,使 create_task 创建的 task 进入 pending
    await asyncio.sleep(0)
    # 取消所有未完成的 task(避免泄漏)
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    for t in tasks:
        t.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
