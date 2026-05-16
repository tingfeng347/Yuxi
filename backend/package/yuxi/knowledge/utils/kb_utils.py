import hashlib
import os
import time
import traceback

from yuxi import config
from yuxi.config.static.models import EmbedModelInfo
from yuxi.knowledge.chunking.ragflow_like.presets import resolve_chunk_processing_params
from yuxi.utils import hashstr, logger
from yuxi.utils.datetime_utils import utc_isoformat


_DROPPED_PROCESSING_PARAM_KEYS = {
    "_preprocessed_map",
    "auto_index",
    "content_hashes",
    "enable_ocr",
}


def sanitize_processing_params(params: dict | None) -> dict | None:
    """移除不应写入单文件元数据的参数。"""
    if not params:
        return None

    return {key: value for key, value in params.items() if key not in _DROPPED_PROCESSING_PARAM_KEYS}


def resolve_processing_params(
    kb_additional_params: dict | None,
    file_processing_params: dict | None,
    request_params: dict | None = None,
) -> dict:
    merged_params = sanitize_processing_params(merge_processing_params(file_processing_params, request_params)) or {}
    merged_params["ocr_engine"] = merged_params.get("ocr_engine") or "disable"
    if not isinstance(merged_params.get("ocr_engine_config"), dict):
        merged_params["ocr_engine_config"] = {}

    chunk_params = resolve_chunk_processing_params(
        kb_additional_params=kb_additional_params,
        file_processing_params=file_processing_params,
        request_params=request_params,
    )
    merged_params.update(chunk_params)
    return merged_params


async def calculate_content_hash(data: bytes | bytearray) -> str:
    """计算文件内容的 SHA-256 哈希值。"""
    sha256 = hashlib.sha256()
    sha256.update(data)
    return sha256.hexdigest()


async def prepare_item_metadata(item: str, content_type: str, db_id: str, params: dict | None = None) -> dict:
    """
    准备文件或URL的元数据，文件来源必须是 MinIO URL。

    Args:
        item: MinIO URL 或 URL
        content_type: 内容类型 ("file" 或 "url")
        db_id: 数据库ID
        params: 处理参数，可选
    """
    # 检查是否有预处理信息 (针对 URL 转 HTML 文件的情况)
    if params and "_preprocessed_map" in params and item in params["_preprocessed_map"]:
        pre_info = params["_preprocessed_map"][item]

        # 使用预处理信息
        filename = pre_info.get("filename", item)  # 通常是原始 URL

        # 截断文件名以适应数据库限制 (512 chars)，保留部分后缀信息如果可能
        if len(filename) > 500:
            filename_display = filename[:400] + "..." + filename[-90:]
        else:
            filename_display = filename

        file_type = "html"  # 强制转换为 html 类型，以便后续作为文件处理
        item_path = pre_info["path"]  # MinIO path
        content_hash = pre_info["content_hash"]

        # 使用 item(url) 生成 ID，保证同一 URL 即使多次添加 ID 也不同（配合 time）
        # 或者我们应该基于 hash？不，基于 time 更符合上传逻辑
        file_id = f"file_{hashstr(item + str(time.time()), 6)}"

        metadata = {
            "database_id": db_id,
            "filename": filename_display,
            "path": item_path,
            "file_type": file_type,
            "status": "processing",
            "created_at": utc_isoformat(),
            "file_id": file_id,
            "content_hash": content_hash,
            "parent_id": params.get("parent_id"),
        }

        if params:
            safe_params = sanitize_processing_params(params) or {}
            # 覆盖 content_type 为 file，确保后续解析走文件流程（MinIO 下载 -> HTML 解析）
            # 而不是再次尝试作为 URL 抓取
            safe_params["content_type"] = "file"
            safe_params["original_source"] = item  # 保存完整 URL 到 JSON 字段，避免数据库字段长度限制
            metadata["processing_params"] = safe_params

        return metadata

    if content_type == "file":
        if not is_minio_url(item):
            raise ValueError(f"File source must be a MinIO URL: {item}")

        logger.debug(f"Processing MinIO file: {item}")
        _, object_name = parse_minio_url(item)
        filename = object_name.rsplit("/", 1)[-1]

        import re

        timestamp_pattern = r"^(.+)_(\d{13})(\.[^.]+)$"
        match = re.match(timestamp_pattern, filename)
        filename_display = match.group(1) + match.group(3) if match else filename

        file_type = filename.split(".")[-1].lower() if "." in filename else ""
        item_path = item

        content_hash = None
        if params and "content_hashes" in params and isinstance(params["content_hashes"], dict):
            content_hash = params["content_hashes"].get(item)

        if not content_hash:
            raise ValueError(f"Missing content_hash for file: {item}")

        file_id = f"file_{hashstr(str(item_path) + str(time.time()), 6)}"

    elif content_type == "url":
        # URL 处理
        filename = item  # 使用完整 URL 作为文件名
        filename_display = item
        file_type = "url"
        item_path = item
        content_hash = None  # URL 没有 content_hash
        file_id = f"url_{hashstr(item + str(time.time()), 6)}"

    else:
        raise ValueError(f"Unsupported content_type: {content_type}")

    metadata = {
        "database_id": db_id,
        "filename": filename_display,  # 使用显示用的文件名
        "path": item_path,
        "file_type": file_type,
        "status": "processing",
        "created_at": utc_isoformat(),
        "file_id": file_id,
        "content_hash": content_hash,
        "parent_id": params.get("parent_id") if params else None,
    }

    # 保存处理参数到元数据
    if params:
        metadata["processing_params"] = sanitize_processing_params(params)

    return metadata


def merge_processing_params(metadata_params: dict | None, request_params: dict | None) -> dict:
    """
    合并处理参数：优先使用请求参数，缺失时使用元数据中的参数

    Args:
        metadata_params: 元数据中保存的参数
        request_params: 请求中提供的参数

    Returns:
        dict: 合并后的参数
    """
    merged_params = {}

    # 首先使用元数据中的参数作为默认值
    if metadata_params:
        merged_params.update(metadata_params)

    # 然后使用请求参数覆盖（如果提供）
    if request_params:
        merged_params.update(request_params)

    logger.debug(f"Merged processing params: {metadata_params=}, {request_params=}, {merged_params=}")
    return merged_params


def get_embedding_config(embed_info: dict) -> dict:
    """
    获取嵌入模型配置（兼容性入口，新代码请直接使用 get_embedding_model_info_by_id）。

    Args:
        embed_info: 嵌入信息字典

    Returns:
        dict: 标准化的嵌入配置
    """
    try:
        assert isinstance(embed_info, dict), f"embed_info must be a dict, got {type(embed_info)}"
        assert "model_id" in embed_info, f"embed_info must contain 'model_id', got {embed_info}"
        logger.warning(f"Using model_id: {embed_info['model_id']}")
        from yuxi.models.embed import get_embedding_model_info_by_id

        return get_embedding_model_info_by_id(embed_info["model_id"])

    except AssertionError as e:
        logger.error(f"AssertionError in get_embedding_config: {e}, embed_info={embed_info}")

    # 兼容性检查：旧版配置字段
    try:
        # 1. 检查 embed_info 是否有效
        if not embed_info or ("model" not in embed_info and "name" not in embed_info):
            logger.error(f"Invalid embed_info: {embed_info}, using default embedding model config")
            raise ValueError("Invalid embed_info: must be a non-empty dictionary")

        # 2. 检查是否是 EmbedModelInfo 对象（在某些情况下可能直接传入对象）
        if hasattr(embed_info, "name") and isinstance(embed_info, EmbedModelInfo):
            logger.debug(f"Using EmbedModelInfo object: {embed_info.name}, {traceback.format_exc()}")
            config_dict = embed_info.model_dump()
            config_dict["api_key"] = os.getenv(config_dict["api_key"]) or config_dict["api_key"]
            return config_dict

        raise ValueError(f"Unsupported embed_info format: {embed_info}")

    except Exception as e:
        logger.error(f"Error in get_embedding_config: {e}, embed_info={embed_info}")
        # 返回默认配置作为fallback
        logger.warning("Falling back to default embedding model config")
        try:
            config_dict = config.embed_model_names[config.embed_model].model_dump()
            config_dict["api_key"] = os.getenv(config_dict["api_key"]) or config_dict["api_key"]
            return config_dict
        except Exception as fallback_error:
            logger.error(f"Failed to get default embedding config: {fallback_error}")
            raise ValueError(f"Failed to get embedding config and fallback failed: {e}")


def is_minio_url(file_path: str) -> bool:
    """检测是否是本系统生成的 MinIO 存储 URL。"""
    from urllib.parse import urlparse

    parsed_url = urlparse(file_path)
    if parsed_url.scheme == "minio":
        return bool(parsed_url.netloc and parsed_url.path.lstrip("/"))

    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        return False

    path_parts = parsed_url.path.lstrip("/").split("/", 1)
    if len(path_parts) != 2:
        return False

    from yuxi.storage.minio.client import MinIOClient

    known_buckets = set(MinIOClient.KB_BUCKETS.values()) | MinIOClient.PUBLIC_READ_BUCKETS
    return path_parts[0] in known_buckets


def parse_minio_url(file_path: str) -> tuple[str, str]:
    """
    解析MinIO URL，提取bucket名称和对象名称

    支持标准 HTTP/HTTPS URL 格式：
    - http(s)://host/bucket-name/path/to/object

    Args:
        file_path: MinIO文件URL (http:// 或 https://)

    Returns:
        tuple[str, str]: (bucket_name, object_name)

    Raises:
        ValueError: 如果无法解析URL
    """
    try:
        from urllib.parse import urlparse

        # 解析URL
        parsed_url = urlparse(file_path)

        # 对于 minio:// 协议，bucket名称在netloc中
        if parsed_url.scheme == "minio":
            bucket_name = parsed_url.netloc
            object_name = parsed_url.path.lstrip("/")
        else:
            # 对于 http/https 协议，bucket名称在path的第一部分
            object_name = parsed_url.path.lstrip("/")
            path_parts = object_name.split("/", 1)
            if len(path_parts) > 1:
                bucket_name = path_parts[0]
                object_name = path_parts[1]
            else:
                raise ValueError(f"无法解析MinIO URL中的bucket名称: {file_path}")

        logger.debug(f"Parsed MinIO URL: bucket_name={bucket_name}, object_name={object_name}")
        return bucket_name, object_name

    except Exception as e:
        logger.error(f"Failed to parse MinIO URL {file_path}: {e}")
        raise ValueError(f"无法解析MinIO URL: {file_path}")
