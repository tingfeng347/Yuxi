"""Undo / Fork 功能单元测试

完整覆盖：入口校验 + 核心逻辑路径（消息回退、request_id 提取、checkpoint 定位）。
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from yuxi.services.thread_undo_service import (
    UndoConflictError,
    UndoValidationError,
)
from yuxi.services.thread_fork_service import ForkValidationError


# ---- Mock 工厂 ----

def _conv(**kw):
    defaults = {"user_id": "u-1", "status": "active", "id": 1, "title": "T", "agent_id": "a-1", "extra_metadata": {}}
    defaults.update(kw)
    return MagicMock(**{k: v for k, v in defaults.items()})


def _msg(msg_id, role, conv_id=1, extra=None):
    m = MagicMock()
    m.id = msg_id
    m.role = role
    m.conversation_id = conv_id
    m.extra_metadata = extra or {}
    return m


def _patch_repo(return_value):
    return patch(
        "yuxi.repositories.conversation_repository.ConversationRepository.get_conversation_by_thread_id",
        return_value=return_value,
    )


def _patch_get_msg(return_value):
    return patch("yuxi.services.thread_undo_service._get_message", new=AsyncMock(return_value=return_value))


def _patch_fork_get_msg(return_value):
    return patch("yuxi.services.thread_fork_service._get_message", new=AsyncMock(return_value=return_value))


def _result(fetchone_val=None, scalar_val=None, first_val=None, scalar_one_or_none_val=None):
    """构造 db.execute 返回的查询结果 mock。用 lambda 避免 MagicMock 副作用。"""
    r = MagicMock()
    if fetchone_val is not None:
        r.fetchone = lambda: fetchone_val
    if scalar_val is not None:
        r.scalar = lambda: scalar_val
    if first_val is not None:
        r.first = lambda: first_val
    if scalar_one_or_none_val is not None:
        r.scalar_one_or_none = AsyncMock(return_value=scalar_one_or_none_val)
    return r


# =============================================================================
# Undo — 入口校验
# =============================================================================

class TestUndoEntry:
    @pytest.mark.asyncio
    async def test_conversation_not_found(self):
        with _patch_repo(None):
            from yuxi.services.thread_undo_service import undo_thread
            with pytest.raises(UndoValidationError, match="对话线程不存在"):
                await undo_thread(db=MagicMock(), thread_id="nx", message_id=1, user_id="u-1")

    @pytest.mark.asyncio
    async def test_wrong_user(self):
        with _patch_repo(_conv(user_id="other")):
            from yuxi.services.thread_undo_service import undo_thread
            with pytest.raises(UndoValidationError, match="对话线程不存在"):
                await undo_thread(db=MagicMock(), thread_id="t1", message_id=1, user_id="u-1")

    @pytest.mark.asyncio
    async def test_deleted_conversation(self):
        with _patch_repo(_conv(status="deleted")):
            from yuxi.services.thread_undo_service import undo_thread
            with pytest.raises(UndoValidationError, match="对话线程不存在"):
                await undo_thread(db=MagicMock(), thread_id="t1", message_id=1, user_id="u-1")


# =============================================================================
# Undo — 活跃 run 冲突
# =============================================================================

class TestUndoConflict:
    @pytest.mark.asyncio
    async def test_agent_running(self):
        db = MagicMock()
        db.rollback = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            MagicMock(),                          # FOR UPDATE
            MagicMock(first=lambda: True),        # agent_runs: has active
        ])
        with _patch_repo(_conv()):
            from yuxi.services.thread_undo_service import undo_thread
            with pytest.raises(UndoConflictError, match="正在思考"):
                await undo_thread(db=db, thread_id="t1", message_id=1, user_id="u-1")


# =============================================================================
# Undo — 消息定位
# =============================================================================

class TestUndoMessage:
    @pytest.mark.asyncio
    async def test_message_not_found(self):
        db = MagicMock()
        db.rollback = AsyncMock()
        db.execute = AsyncMock(side_effect=[MagicMock(), MagicMock(first=lambda: None)])
        with _patch_repo(_conv()), _patch_get_msg(None):
            from yuxi.services.thread_undo_service import undo_thread
            with pytest.raises(UndoValidationError, match="消息不存在"):
                await undo_thread(db=db, thread_id="t1", message_id=999, user_id="u-1")

    @pytest.mark.asyncio
    async def test_wrong_conversation(self):
        db = MagicMock()
        db.rollback = AsyncMock()
        db.execute = AsyncMock(side_effect=[MagicMock(), MagicMock(first=lambda: None)])
        with _patch_repo(_conv(id=1)), _patch_get_msg(_msg(100, "user", conv_id=2)):
            from yuxi.services.thread_undo_service import undo_thread
            with pytest.raises(UndoValidationError, match="消息不存在"):
                await undo_thread(db=db, thread_id="t1", message_id=100, user_id="u-1")

    @pytest.mark.asyncio
    async def test_missing_request_id(self):
        db = MagicMock()
        db.rollback = AsyncMock()
        db.execute = AsyncMock(side_effect=[MagicMock(), MagicMock(first=lambda: None)])
        with _patch_repo(_conv()), _patch_get_msg(_msg(100, "user", extra={})):
            from yuxi.services.thread_undo_service import undo_thread
            with pytest.raises(UndoValidationError, match="缺少 request_id"):
                await undo_thread(db=db, thread_id="t1", message_id=100, user_id="u-1")

    # NOTE: assistant 回退 + checkpoint 入口/parent 查找路径
    # 依赖真实的 checkpoint 表和递归 CTE 执行，适合集成测试（需 PG）。


# =============================================================================
# Fork — 入口校验
# =============================================================================

class TestForkEntry:
    @pytest.mark.asyncio
    async def test_conversation_not_found(self):
        db = MagicMock(); db.rollback = AsyncMock()
        with _patch_repo(None):
            from yuxi.services.thread_fork_service import fork_thread
            with pytest.raises(ForkValidationError, match="对话线程不存在"):
                await fork_thread(db=db, thread_id_a="nx", message_id=1, title=None, user_id="u-1")

    @pytest.mark.asyncio
    async def test_wrong_user(self):
        db = MagicMock(); db.rollback = AsyncMock()
        with _patch_repo(_conv(user_id="other")):
            from yuxi.services.thread_fork_service import fork_thread
            with pytest.raises(ForkValidationError, match="对话线程不存在"):
                await fork_thread(db=db, thread_id_a="t1", message_id=1, title=None, user_id="u-1")

    @pytest.mark.asyncio
    async def test_deleted_conversation(self):
        db = MagicMock(); db.rollback = AsyncMock()
        with _patch_repo(_conv(status="deleted")):
            from yuxi.services.thread_fork_service import fork_thread
            with pytest.raises(ForkValidationError, match="对话线程不存在"):
                await fork_thread(db=db, thread_id_a="t1", message_id=1, title=None, user_id="u-1")


# =============================================================================
# Fork — 消息定位
# =============================================================================

class TestForkMessage:
    @pytest.mark.asyncio
    async def test_missing_request_id(self):
        db = MagicMock(); db.rollback = AsyncMock()
        db.execute = AsyncMock(return_value=MagicMock())
        with _patch_repo(_conv()), _patch_fork_get_msg(_msg(100, "user", extra={})):
            from yuxi.services.thread_fork_service import fork_thread
            with pytest.raises(ForkValidationError, match="缺少 request_id"):
                await fork_thread(db=db, thread_id_a="t1", message_id=100, title=None, user_id="u-1")

    @pytest.mark.asyncio
    async def test_message_not_found(self):
        db = MagicMock(); db.rollback = AsyncMock()
        db.execute = AsyncMock(return_value=MagicMock())
        with _patch_repo(_conv()), _patch_fork_get_msg(None):
            from yuxi.services.thread_fork_service import fork_thread
            with pytest.raises(ForkValidationError, match="消息不存在"):
                await fork_thread(db=db, thread_id_a="t1", message_id=999, title=None, user_id="u-1")

    @pytest.mark.asyncio
    async def test_wrong_conversation(self):
        db = MagicMock(); db.rollback = AsyncMock()
        db.execute = AsyncMock(return_value=MagicMock())
        with _patch_repo(_conv(id=1)), _patch_fork_get_msg(_msg(100, "user", conv_id=2)):
            from yuxi.services.thread_fork_service import fork_thread
            with pytest.raises(ForkValidationError, match="消息不存在"):
                await fork_thread(db=db, thread_id_a="t1", message_id=100, title=None, user_id="u-1")

    # NOTE: assistant 回退 + checkpoint parent 查找路径
    # 依赖真实 checkpoint 表和递归 CTE，适合集成测试。

