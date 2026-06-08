"""Checkpoint 查询 Repository

基于 checkpoint_tables 表定义构建具体查询（CTE / select），
供 undo / fork 服务层调用。
"""

from sqlalchemy import select

from yuxi.storage.postgres.checkpoint_tables import checkpoints


def build_descendants_cte(thread_id: str, start_checkpoint_id: str):
    """递归向下查找所有后代 checkpoint（undo 用）。"""
    ckpt = checkpoints

    base = (
        select(ckpt.c.checkpoint_id)
        .where(ckpt.c.thread_id == thread_id, ckpt.c.checkpoint_id == start_checkpoint_id)
        .cte(name="descendants", recursive=True)
    )

    recursive_part = (
        select(ckpt.c.checkpoint_id)
        .select_from(ckpt.join(base, ckpt.c.parent_checkpoint_id == base.c.checkpoint_id))
        .where(ckpt.c.thread_id == thread_id)
    )

    return base.union_all(recursive_part)


def build_ancestors_cte(thread_id: str, start_checkpoint_id: str):
    """递归向上查找所有祖先 checkpoint（fork 用）。"""
    ckpt = checkpoints

    base = (
        select(ckpt.c.checkpoint_id, ckpt.c.parent_checkpoint_id)
        .where(ckpt.c.thread_id == thread_id, ckpt.c.checkpoint_id == start_checkpoint_id)
        .cte(name="ancestors", recursive=True)
    )

    recursive_part = (
        select(ckpt.c.checkpoint_id, ckpt.c.parent_checkpoint_id)
        .select_from(ckpt.join(base, ckpt.c.checkpoint_id == base.c.parent_checkpoint_id))
        .where(ckpt.c.thread_id == thread_id)
    )

    return base.union_all(recursive_part)


def select_checkpoint_entry(thread_id: str, request_id: str):
    """查找 source='input' 的 checkpoint 入口记录。"""
    ckpt = checkpoints
    return (
        select(ckpt.c.checkpoint_id)
        .where(
            ckpt.c.thread_id == thread_id,
            ckpt.c.metadata["request_id"].astext == request_id,
            ckpt.c.metadata["source"].astext == "input",
        )
        .limit(1)
    )


def select_checkpoint_parent(thread_id: str, request_id: str):
    """查找 source='input' 的 checkpoint 的 parent_checkpoint_id（fork 回档点）。"""
    ckpt = checkpoints
    return (
        select(ckpt.c.parent_checkpoint_id)
        .where(
            ckpt.c.thread_id == thread_id,
            ckpt.c.metadata["request_id"].astext == request_id,
            ckpt.c.metadata["source"].astext == "input",
        )
        .limit(1)
    )
