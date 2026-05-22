from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from server.utils.auth_middleware import get_db, get_required_user
from sqlalchemy.ext.asyncio import AsyncSession
from yuxi.repositories.conversation_repository import ConversationRepository
from yuxi.services.mention_search_service import search_mention_files_in_index
from yuxi.storage.postgres.models_business import User

mention_router = APIRouter(prefix="/mention", tags=["mention"])


class MentionFileItem(BaseModel):
    """提及文件搜索结果条目"""

    name: str
    path: str
    is_dir: bool


@mention_router.get("/search", response_model=list[MentionFileItem])
async def search_mention_files(
    thread_id: str = Query(..., description="当前聊天会话 ID"),
    query: str = Query("", description="模糊搜索关键字"),
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    """
    提及文件模糊搜索接口：使用 Redis 二进制缓存进行极速过滤，防止大文件递归卡死。
    调用前校验 thread 归属权，防止 IDOR 越权访问他人会话文件。
    """
    user_id = str(current_user.id)

    # NOTE: 校验 thread 归属权，防止恶意用户传入他人 thread_id 遍历文件
    conv_repo = ConversationRepository(db)
    conversation = await conv_repo.get_conversation_by_thread_id(thread_id)
    if conversation:
        if conversation.user_id != user_id or conversation.status == "deleted":
            raise HTTPException(status_code=404, detail="对话线程不存在")
    else:
        # NOTE: 如果是尚未在数据库记录的全新对话（还未发送首条消息），在格式校验安全的前提下放行。
        # 此时该 thread 专属的 uploads/outputs 目录还没创建或为空，
        # 用户仅能安全地搜索到自己全局的工作区 (workspace) 文件。
        try:
            from yuxi.agents.backends.sandbox.paths import validate_thread_id

            validate_thread_id(thread_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="非法的 thread_id 格式")

    return await search_mention_files_in_index(
        thread_id=thread_id,
        user_id=user_id,
        query=query,
    )
