from __future__ import annotations

from copy import deepcopy
from typing import Any

from yuxi.utils import logger

CHUNK_PRESET_GENERAL = "general"
CHUNK_PRESET_QA = "qa"
CHUNK_PRESET_BOOK = "book"
CHUNK_PRESET_LAWS = "laws"
CHUNK_PRESET_SEMANTIC = "semantic"
CHUNK_PRESET_SEPARATOR = "separator"

CHUNK_PRESET_IDS = {
    CHUNK_PRESET_GENERAL,
    CHUNK_PRESET_QA,
    CHUNK_PRESET_BOOK,
    CHUNK_PRESET_LAWS,
    CHUNK_PRESET_SEMANTIC,
    CHUNK_PRESET_SEPARATOR,
}

CHUNK_PRESET_DESCRIPTIONS: dict[str, str] = {
    CHUNK_PRESET_GENERAL: "通用分块：按分隔符和长度切分，适合大多数普通文档。",
    CHUNK_PRESET_QA: "问答分块：优先抽取问题-回答结构，适合 FAQ、题库、问答手册。",
    CHUNK_PRESET_BOOK: "书籍分块：强化章节标题识别并做层级合并，适合教材、手册、长章节文档。",
    CHUNK_PRESET_LAWS: "法规分块：按法条层级组织与合并，适合法律法规、制度规范类文本。",
    CHUNK_PRESET_SEMANTIC: "语义分块：利用嵌入和聚类算法进行语义切分，并自动增强标题上下文。",
    CHUNK_PRESET_SEPARATOR: "严格分隔：命中分隔符即切分，仅超长片段内部继续按长度切分。",
}

CHUNK_ENGINE_VERSION = "ragflow_like_v1"
GENERAL_INTERNAL_PARSER_ID = "naive"

def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def normalize_chunk_preset_id(value: str | None) -> str:
    if not value:
        return CHUNK_PRESET_GENERAL

    normalized = str(value).strip().lower()
    if normalized == GENERAL_INTERNAL_PARSER_ID:
        return CHUNK_PRESET_GENERAL

    if normalized in CHUNK_PRESET_IDS:
        return normalized

    logger.warning(f"Unknown chunk preset id '{value}', fallback to general")
    return CHUNK_PRESET_GENERAL


def map_to_internal_parser_id(preset_id: str) -> str:
    normalized = normalize_chunk_preset_id(preset_id)
    if normalized == CHUNK_PRESET_GENERAL:
        return GENERAL_INTERNAL_PARSER_ID
    return normalized


def get_default_chunk_parser_config(preset_id: str) -> dict[str, Any]:
    normalize_chunk_preset_id(preset_id)
    return {}


def ensure_chunk_defaults_in_additional_params(additional_params: dict[str, Any] | None) -> dict[str, Any]:
    params = dict(additional_params or {})
    params["chunk_preset_id"] = normalize_chunk_preset_id(params.get("chunk_preset_id"))

    if "chunk_parser_config" in params and not isinstance(params.get("chunk_parser_config"), dict):
        logger.warning("Invalid chunk_parser_config in additional_params, fallback to empty dict")
        params["chunk_parser_config"] = {}

    return params


def resolve_chunk_processing_params(
    kb_additional_params: dict[str, Any] | None,
    file_processing_params: dict[str, Any] | None,
    request_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    kb_additional = ensure_chunk_defaults_in_additional_params(kb_additional_params)
    file_params = dict(file_processing_params or {})
    request = dict(request_params or {})

    preset_id = normalize_chunk_preset_id(
        request.get("chunk_preset_id") or file_params.get("chunk_preset_id") or kb_additional.get("chunk_preset_id")
    )

    parser_config = get_default_chunk_parser_config(preset_id)

    kb_parser_config = kb_additional.get("chunk_parser_config")
    if isinstance(kb_parser_config, dict):
        parser_config = deep_merge(parser_config, kb_parser_config)

    file_parser_config = file_params.get("chunk_parser_config")
    if isinstance(file_parser_config, dict):
        parser_config = deep_merge(parser_config, file_parser_config)

    req_parser_config = request.get("chunk_parser_config")
    if isinstance(req_parser_config, dict):
        parser_config = deep_merge(parser_config, req_parser_config)

    return {
        "chunk_preset_id": preset_id,
        "chunk_parser_config": parser_config,
        "chunk_engine_version": CHUNK_ENGINE_VERSION,
    }


def get_chunk_preset_options() -> list[dict[str, str]]:
    return [
        {
            "value": CHUNK_PRESET_GENERAL,
            "label": "General",
            "description": CHUNK_PRESET_DESCRIPTIONS[CHUNK_PRESET_GENERAL],
        },
        {
            "value": CHUNK_PRESET_QA,
            "label": "QA",
            "description": CHUNK_PRESET_DESCRIPTIONS[CHUNK_PRESET_QA],
        },
        {
            "value": CHUNK_PRESET_BOOK,
            "label": "Book",
            "description": CHUNK_PRESET_DESCRIPTIONS[CHUNK_PRESET_BOOK],
        },
        {
            "value": CHUNK_PRESET_LAWS,
            "label": "Laws",
            "description": CHUNK_PRESET_DESCRIPTIONS[CHUNK_PRESET_LAWS],
        },
        {
            "value": CHUNK_PRESET_SEMANTIC,
            "label": "Semantic",
            "description": CHUNK_PRESET_DESCRIPTIONS[CHUNK_PRESET_SEMANTIC],
        },
        {
            "value": CHUNK_PRESET_SEPARATOR,
            "label": "Separator",
            "description": CHUNK_PRESET_DESCRIPTIONS[CHUNK_PRESET_SEPARATOR],
        },
    ]
