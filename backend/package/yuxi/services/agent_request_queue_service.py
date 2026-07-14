"""Agent request queue service.

提供请求入队、FIFO 派发、取消和恢复扫描的完整事务逻辑。
不调用 agent_run_service 私有函数。
``recover_pending_dispatches`` 自管会话，提交后才调 ``enqueue_agent_run``。
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from yuxi.repositories.agent_run_repository import AgentRunRepository
from yuxi.repositories.agent_run_request_repository import AgentRunRequestRepository
from yuxi.repositories.conversation_repository import ConversationRepository
from yuxi.services.agent_run_service import (
    create_agent_run_input_message,
    enqueue_agent_run,
    resolve_agent_run_config,
)
from yuxi.services.input_message_service import AgentRunInputMessage
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import AgentRun, AgentRunRequest, Message
from yuxi.utils.datetime_utils import utc_now_naive
from yuxi.utils.logging_config import logger
from yuxi.utils.sse_utils import (
    SSE_HEARTBEAT_SECONDS,
    SSE_MAX_CONNECTION_MINUTES,
    SSE_POLL_INTERVAL_SECONDS,
    format_heartbeat,
    format_sse,
)

SUPPORTED_QUEUE_POLICIES = ("enqueue", "reject")
NOT_IMPLEMENTED_QUEUE_POLICIES = ("steer", "guided", "bridge")

# Request lifecycle states.
REQUEST_STATUS_QUEUED = "queued"
REQUEST_STATUS_DISPATCHED = "dispatched"
REQUEST_STATUS_CANCELLED = "cancelled"
REQUEST_STATUS_REJECTED = "rejected"
REQUEST_STATUS_FAILED = "failed"
REQUEST_TERMINAL_STATUSES = frozenset({REQUEST_STATUS_CANCELLED, REQUEST_STATUS_REJECTED, REQUEST_STATUS_FAILED})

# Message delivery states aligned with messages.delivery_status.
DELIVERY_STATUS_QUEUED = "queued"
DELIVERY_STATUS_DISPATCHED = "dispatched"
DELIVERY_STATUS_COMPLETE = "complete"
DELIVERY_STATUS_REJECTED = "rejected"
DELIVERY_STATUS_FAILED = "failed"
DELIVERY_STATUS_CANCELLED = "cancelled"

# AgentRun terminal status → Message.delivery_status. ``interrupted`` 不在内：
# 被中断的请求未真正完成，保留原 delivery_status 以便 UI 区分完成 / 中断。
RUN_STATUS_TO_DELIVERY_STATUS: dict[str, str] = {
    "completed": DELIVERY_STATUS_COMPLETE,
    "failed": DELIVERY_STATUS_FAILED,
    "cancelled": DELIVERY_STATUS_CANCELLED,
}


@dataclass(frozen=True)
class IntakeResult:
    """入队决策结果。"""

    request_id: str
    status: str  # queued / dispatched / rejected
    queue_policy: str
    message_id: int | None
    run_id: str | None = None
    # FIFO 队内位置；未在排队（dispatched/rejected/已存在）时为 None。
    queue_position: int | None = None


def validate_queue_policy(queue_policy: str) -> str:
    """校验 queue_policy，对未实现策略返回 422。"""
    if queue_policy in NOT_IMPLEMENTED_QUEUE_POLICIES:
        raise HTTPException(
            status_code=422,
            detail=f"queue_policy '{queue_policy}' 暂未实现",
        )
    if queue_policy not in SUPPORTED_QUEUE_POLICIES:
        raise HTTPException(status_code=422, detail=f"不支持的 queue_policy: {queue_policy}")
    return queue_policy


def _build_message_metadata(
    *, request_id: str, source: str, input_message: AgentRunInputMessage, meta: dict
) -> dict[str, Any]:
    """构建 Message.extra_metadata：request_id + source + raw_message + 附加上下文。"""
    metadata: dict[str, Any] = {"request_id": request_id}
    if source:
        metadata["source"] = source
    if raw_message := input_message.raw_message():
        metadata["raw_message"] = raw_message
    if attachment_file_ids := meta.get("attachment_file_ids"):
        metadata["attachment_file_ids"] = attachment_file_ids
    if isinstance(meta.get("agent_invocation_meta"), dict):
        metadata["agent_invocation_meta"] = meta["agent_invocation_meta"]
    if meta.get("tool_approval_mode") is not None:
        metadata["tool_approval_mode"] = meta["tool_approval_mode"]
    return metadata


async def intake_request(
    *,
    db: AsyncSession,
    request_id: str,
    uid: str,
    agent_slug: str,
    thread_id: str,
    source: str = "chat",
    queue_policy: str = "enqueue",
    input_message: AgentRunInputMessage,
    agent_item: Any,
    agent_backend: Any,
    model_spec: str | None = None,
    tool_approval_mode: str | None = None,
    meta: dict | None = None,
) -> IntakeResult:
    """创建 request + Message，尝试立即派发。

    全部 flush 在调用方事务内完成；不 commit。
    返回 IntakeResult：dispatched 时含 run_id（调用方需 commit 后 enqueue ARQ）。
    """
    policy = validate_queue_policy(queue_policy)
    meta = meta or {}
    uid_str = str(uid)
    repo = AgentRunRequestRepository(db)
    conv_repo = ConversationRepository(db)

    # 幂等：相同 request_id 已存在时直接返回既有 request/run 视图
    existing_request = await repo.get_by_request_id(request_id)
    if existing_request:
        if existing_request.uid != uid_str:
            raise HTTPException(status_code=409, detail="request_id 冲突")
        return IntakeResult(
            request_id=existing_request.request_id,
            status=existing_request.status,
            queue_policy=existing_request.queue_policy,
            message_id=existing_request.input_message_id,
            run_id=existing_request.dispatched_run_id,
        )

    conv = await conv_repo.get_conversation_by_thread_id(thread_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="对话线程不存在")

    active_run = await AgentRunRepository(db).get_active_run_by_thread_for_user(
        agent_slug=agent_slug, conversation_thread_id=thread_id, uid=uid_str
    )

    # reject 策略 + 线程忙 → 写 rejected request + rejected message；其他情况走 queued 分支
    rejected_by_active_run = policy == "reject" and active_run is not None
    if rejected_by_active_run:
        request_status = REQUEST_STATUS_REJECTED
        delivery_status = DELIVERY_STATUS_REJECTED
        input_payload = {}
    else:
        request_status = REQUEST_STATUS_QUEUED
        delivery_status = DELIVERY_STATUS_QUEUED
        resolved_model_spec, resolved_tool_approval_mode = resolve_agent_run_config(
            model_spec, tool_approval_mode, agent_item, agent_backend
        )
        input_payload = {
            "model_spec": resolved_model_spec,
            "tool_approval_mode": resolved_tool_approval_mode,
        }

    run_input_message = input_message.with_metadata(
        _build_message_metadata(request_id=request_id, source=source, input_message=input_message, meta=meta)
    )
    persisted_message = await create_agent_run_input_message(
        db=db,
        conversation_id=conv.id,
        request_id=request_id,
        input_message=run_input_message,
        delivery_status=delivery_status,
    )
    await repo.create(
        request_id=request_id,
        uid=uid_str,
        agent_slug=agent_slug,
        conversation_thread_id=thread_id,
        source=source,
        queue_policy=policy,
        input_message_id=persisted_message.id,
        input_payload=input_payload,
        status=request_status,
    )

    # 线程空闲且不是 reject 策略时尝试立即派发
    if not rejected_by_active_run and active_run is None:
        run_id = await _try_dispatch_head(
            db,
            uid=uid_str,
            agent_slug=agent_slug,
            thread_id=thread_id,
            conversation_id=conv.id,
        )
        if run_id:
            return IntakeResult(
                request_id=request_id,
                status=REQUEST_STATUS_DISPATCHED,
                queue_policy=policy,
                message_id=persisted_message.id,
                run_id=run_id,
            )

    if rejected_by_active_run:
        return IntakeResult(
            request_id=request_id,
            status=REQUEST_STATUS_REJECTED,
            queue_policy=policy,
            message_id=persisted_message.id,
        )

    return IntakeResult(
        request_id=request_id,
        status=REQUEST_STATUS_QUEUED,
        queue_policy=policy,
        message_id=persisted_message.id,
        queue_position=await repo.get_queue_position(request_id),
    )


async def finalize_intake(*, db: AsyncSession, intake: IntakeResult) -> None:
    """调用方在 intake_request 后提交事务，并条件性将派发的 run 投入 ARQ。"""
    await db.commit()
    if intake.status == REQUEST_STATUS_DISPATCHED and intake.run_id:
        await enqueue_agent_run(intake.run_id)


async def _try_dispatch_head(
    db: AsyncSession,
    *,
    uid: str,
    agent_slug: str,
    thread_id: str,
    conversation_id: int,
) -> str | None:
    """锁定 FIFO 队头，创建 AgentRun，标记 dispatched。不 commit。

    返回 run_id 或 None（队列空/约束冲突）。
    线程忙的场景由 ``uq_agent_runs_one_active_per_thread`` 唯一约束兜底。
    """
    repo = AgentRunRequestRepository(db)
    run_repo = AgentRunRepository(db)

    head = await repo.get_queue_head(uid=uid, agent_slug=agent_slug, conversation_thread_id=thread_id)
    if not head:
        return None

    run_id = str(uuid.uuid4())
    try:
        async with db.begin_nested():
            await run_repo.create_run(
                run_id=run_id,
                conversation_thread_id=thread_id,
                agent_slug=agent_slug,
                uid=uid,
                request_id=head.request_id,
                input_payload=head.input_payload or {},
                conversation_id=conversation_id,
                run_type="chat",
                input_message_id=head.input_message_id,
            )
            msg = await db.get(Message, head.input_message_id)
            if msg:
                msg.run_id = run_id
                msg.delivery_status = DELIVERY_STATUS_DISPATCHED
            await db.flush()
            await repo.mark_dispatched(head.request_id, run_id=run_id)
    except IntegrityError:
        # active-run 唯一约束冲突 → 保持请求为 queued
        logger.info(f"Dispatch conflict for request {head.request_id}, keeping queued")
        return None

    return run_id


async def dispatch_next_request(
    *,
    uid: str,
    agent_slug: str,
    thread_id: str,
) -> str | None:
    """派发线程队头请求。自管会话，提交后投递 ARQ。

    供 run 完成后的下一个请求派发和恢复扫描调用。
    """
    run_id = None
    async with pg_manager.get_async_session_context() as db:
        conv = await ConversationRepository(db).get_conversation_by_thread_id(thread_id)
        if not conv:
            return None
        run_id = await _try_dispatch_head(
            db,
            uid=str(uid),
            agent_slug=agent_slug,
            thread_id=thread_id,
            conversation_id=conv.id,
        )
        if run_id:
            await db.commit()

    if run_id:
        await enqueue_agent_run(run_id)
    return run_id


async def recover_pending_dispatches() -> None:
    """恢复扫描：找出 dispatched 但 run 仍 pending 的请求，重新投递 ARQ。

    覆盖"提交成功但进程在 enqueue 前退出"的窗口。
    """
    async with pg_manager.get_async_session_context() as db:
        result = await db.execute(
            select(AgentRun.id)
            .join(AgentRunRequest, AgentRunRequest.dispatched_run_id == AgentRun.id)
            .where(
                AgentRunRequest.status == REQUEST_STATUS_DISPATCHED,
                AgentRun.status == "pending",
            )
        )
        recovered = [row[0] for row in result.all()]

    if not recovered:
        return

    await asyncio.gather(*(enqueue_agent_run(run_id) for run_id in recovered))
    for run_id in recovered:
        logger.info(f"Recovered pending run: {run_id}")


async def cancel_queued_request(
    *,
    request_id: str,
    current_uid: str,
    db: AsyncSession,
) -> str:
    """取消一个 queued 请求；已 dispatched 的不可取消。

    返回最终状态字符串。请求不存在或越权返回 404。
    所有状态读取与状态写入在同一 ``SELECT ... FOR UPDATE`` 内完成，
    避免无锁读后再锁写之间被并发修改。
    """
    repo = AgentRunRequestRepository(db)
    request = await repo.lock_by_request_id(request_id)
    if request is None or request.uid != str(current_uid):
        raise HTTPException(status_code=404, detail="请求不存在")
    if request.status == REQUEST_STATUS_DISPATCHED:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "request_already_dispatched",
                "message": "请求已派发，请通过 run 取消接口取消正在进行的运行",
                "run_id": request.dispatched_run_id,
            },
        )
    if request.status in REQUEST_TERMINAL_STATUSES:
        return request.status
    request.status = REQUEST_STATUS_CANCELLED
    request.updated_at = utc_now_naive()
    await db.flush()
    return REQUEST_STATUS_CANCELLED


async def get_request(*, db: AsyncSession, request_id: str, uid: str) -> dict | None:
    """按 request_id 查询请求（含 uid 归属校验）。"""
    repo = AgentRunRequestRepository(db)
    request = await repo.get_by_request_id(request_id)
    if not request or request.uid != str(uid):
        return None
    return request.to_dict()


async def list_queued_requests(*, db: AsyncSession, uid: str, agent_slug: str, thread_id: str) -> list[dict]:
    """列出线程内所有 queued 请求。"""
    repo = AgentRunRequestRepository(db)
    items = await repo.list_queued(uid=str(uid), agent_slug=agent_slug, conversation_thread_id=thread_id)
    if not items:
        return []

    message_ids = [request.input_message_id for request in items if request.input_message_id is not None]
    contents: dict[int, str] = {}
    if message_ids:
        result = await db.execute(select(Message.id, Message.content).where(Message.id.in_(message_ids)))
        contents = {row[0]: row[1] for row in result.all()}

    requests = []
    for position, request in enumerate(items, start=1):
        data = request.to_dict()
        if request.input_message_id is not None:
            data["content"] = contents.get(request.input_message_id, "")
        data["queue_position"] = position
        requests.append(data)
    return requests


async def stream_request_events(
    *,
    request_id: str,
    uid: str,
    db_session_factory,
) -> AsyncIterator[str]:
    """Request SSE：发送 queued 心跳、位置变化，dispatched 时发送 run_created 并结束。"""
    started_at = utc_now_naive()
    last_heartbeat_ts = started_at
    last_position = -1

    try:
        while True:
            async with db_session_factory() as db:
                repo = AgentRunRequestRepository(db)
                request = await repo.get_by_request_id(request_id)
                if not request or request.uid != str(uid):
                    yield format_sse({"request_id": request_id, "message": "请求不存在"}, event="error")
                    return

                if request.status == REQUEST_STATUS_DISPATCHED:
                    yield format_sse(
                        {
                            "request_id": request_id,
                            "run_id": request.dispatched_run_id,
                            "stream_url": f"/api/agent/runs/{request.dispatched_run_id}/events",
                        },
                        event="run_created",
                    )
                    return

                if request.status in REQUEST_TERMINAL_STATUSES:
                    yield format_sse(
                        {"request_id": request_id, "status": request.status},
                        event=request.status,
                    )
                    return

                # queued: 用 COUNT 查询位置（O(1)），仅在变化时上报
                position = await repo.get_queue_position_for(request)
                if position != last_position:
                    last_position = position
                    yield format_sse(
                        {"request_id": request_id, "status": REQUEST_STATUS_QUEUED, "position": position},
                        event=REQUEST_STATUS_QUEUED,
                    )

            now = utc_now_naive()
            if (now - last_heartbeat_ts).total_seconds() >= SSE_HEARTBEAT_SECONDS:
                yield format_heartbeat()
                last_heartbeat_ts = now

            if (now - started_at).total_seconds() >= SSE_MAX_CONNECTION_MINUTES * 60:
                return

            await asyncio.sleep(SSE_POLL_INTERVAL_SECONDS)
    except asyncio.CancelledError:
        return
