"""Utilities for normalizing user input across DB and LangChain messages."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from typing import Any

from langchain.messages import HumanMessage


@dataclass(frozen=True)
class AgentRunInputMessage:
    content: str
    message_type: str
    image_content: str | None
    langchain_message: HumanMessage | None = None
    extra_metadata: dict[str, Any] = field(default_factory=dict)

    def raw_message(self) -> dict[str, Any] | None:
        return self.langchain_message.model_dump() if self.langchain_message else None

    def require_langchain_message(self) -> HumanMessage:
        if not self.langchain_message:
            raise ValueError("chat input message must include a LangChain HumanMessage")
        return self.langchain_message

    def with_metadata(self, metadata: dict[str, Any]) -> AgentRunInputMessage:
        return replace(self, extra_metadata=dict(metadata))


def build_chat_input_message(query: str, image_content: str | None = None) -> AgentRunInputMessage:
    if image_content:
        langchain_message = HumanMessage(
            content=[
                {"type": "text", "text": query},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_content}"}},
            ]
        )
        message_type = "multimodal_image"
    else:
        langchain_message = HumanMessage(content=query)
        message_type = "text"

    return AgentRunInputMessage(
        content=query,
        message_type=message_type,
        image_content=image_content,
        langchain_message=langchain_message,
    )


def build_resume_input_message(resume: object) -> AgentRunInputMessage:
    return AgentRunInputMessage(
        content=json.dumps(resume, ensure_ascii=False),
        message_type="resume",
        image_content=None,
    )


def restore_chat_input_message(*, content: str, image_content: str | None, metadata: dict) -> AgentRunInputMessage:
    raw_message = metadata.get("raw_message")
    if isinstance(raw_message, dict):
        try:
            langchain_message = HumanMessage.model_validate(raw_message)
        except Exception as exc:
            raise ValueError("invalid raw_message for chat input message") from exc
        message_type = "multimodal_image" if image_content else "text"
        return AgentRunInputMessage(
            content=content,
            message_type=message_type,
            image_content=image_content,
            langchain_message=langchain_message,
            extra_metadata=dict(metadata),
        )

    return build_chat_input_message(content, image_content)
