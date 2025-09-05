"""Media processing package for Telegram Meme Autoposter.

This module exposes helpers shared by the individual media processing
implementations.  In particular it provides a utility for uploading the
processed media to MinIO while preserving the submission metadata associated
with the original file.
"""

from __future__ import annotations

import os

from loguru import logger

from telegram_auto_poster.utils.general import MinioError
from telegram_auto_poster.utils.storage import storage


async def upload_processed_media(
    file_path: str,
    *,
    bucket: str,
    object_name: str,
    user_metadata: dict | None = None,
    original_name: str | None = None,
    media_hash: str | None = None,
    group_id: str | None = None,
    media_label: str = "file",
) -> None:
    """Upload processed media to MinIO, keeping submission metadata.

    Args:
        file_path: Local path to the processed file.
        bucket: MinIO bucket to upload to.
        object_name: Destination object name in MinIO.
        user_metadata: Optional pre-fetched submission metadata.
        original_name: Name of the original source file (used to look up
            metadata if ``user_metadata`` is not provided).
        media_hash: Optional hash used for deduplication.
        group_id: Optional identifier for media groups/albums.
        media_label: Human readable label for logging and error messages.
    """

    meta = user_metadata
    if meta is None:
        lookup = os.path.basename(original_name or file_path)
        meta = await storage.get_submission_metadata(lookup)

    uploaded = await storage.upload_file(
        file_path,
        bucket,
        object_name,
        user_id=(meta or {}).get("user_id"),
        chat_id=(meta or {}).get("chat_id"),
        message_id=(meta or {}).get("message_id"),
        media_hash=media_hash,
        group_id=group_id,
    )

    if not uploaded:
        raise MinioError(
            f"Failed to upload processed {media_label} to MinIO: {object_name}"
        )

    logger.debug(f"Uploaded processed {media_label} to MinIO: {bucket}/{object_name}")


__all__ = ["upload_processed_media"]
