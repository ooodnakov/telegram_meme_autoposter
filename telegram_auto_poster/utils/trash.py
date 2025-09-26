"""Helpers for moving media into and out of the trash."""

from __future__ import annotations

import os
from datetime import datetime, timedelta

from loguru import logger
from miniopy_async.commonconfig import CopySource

from telegram_auto_poster.config import (
    BUCKET_MAIN,
    CONFIG,
    PHOTOS_PATH,
    TRASH_PATH,
    VIDEOS_PATH,
)
from telegram_auto_poster.utils.db import (
    add_trashed_post,
    get_expired_trashed_posts,
    remove_trashed_post,
)
from telegram_auto_poster.utils.storage import storage
from telegram_auto_poster.utils.timezone import now_utc


def _detect_media_type(path: str) -> str:
    if path.startswith(f"{PHOTOS_PATH}/"):
        return "photo"
    if path.startswith(f"{VIDEOS_PATH}/"):
        return "video"
    if path.startswith(f"{TRASH_PATH}/{PHOTOS_PATH}/"):
        return "photo"
    if path.startswith(f"{TRASH_PATH}/{VIDEOS_PATH}/"):
        return "video"
    raise ValueError(f"Unable to detect media type for path: {path}")


def _trash_path_for(path: str) -> str:
    if path.startswith(f"{TRASH_PATH}/"):
        return path
    return f"{TRASH_PATH}/{path}"


def _processed_path_for(path: str) -> str:
    if path.startswith(f"{TRASH_PATH}/"):
        return path[len(f"{TRASH_PATH}/") :]
    return path


async def move_to_trash(path: str) -> tuple[str, datetime, datetime]:
    """Move ``path`` to the trash and return new path with timestamps."""

    _detect_media_type(path)
    processed_path = path if not path.startswith(f"{TRASH_PATH}/") else _processed_path_for(path)
    trash_path = _trash_path_for(processed_path)
    file_name = os.path.basename(processed_path)

    source = CopySource(BUCKET_MAIN, processed_path)
    await storage.client.copy_object(BUCKET_MAIN, trash_path, source)
    await storage.delete_file(processed_path, BUCKET_MAIN)

    trashed_at = now_utc()
    expires_at = trashed_at + timedelta(hours=CONFIG.trash.retention_hours)
    await storage.update_submission_metadata(
        file_name,
        trashed_at=trashed_at.isoformat(),
        trash_expires_at=expires_at.isoformat(),
    )
    await add_trashed_post(trash_path, int(expires_at.timestamp()))

    logger.info(f"Moved {processed_path} to trash at {trashed_at.isoformat()}")
    return trash_path, trashed_at, expires_at


async def restore_from_trash(path: str) -> str:
    """Restore ``path`` from the trash back into the processed area."""

    _detect_media_type(path)
    trash_path = _trash_path_for(path)
    processed_path = _processed_path_for(trash_path)
    file_name = os.path.basename(processed_path)

    source = CopySource(BUCKET_MAIN, trash_path)
    await storage.client.copy_object(BUCKET_MAIN, processed_path, source)
    await storage.delete_file(trash_path, BUCKET_MAIN)
    await remove_trashed_post(trash_path)
    await storage.update_submission_metadata(
        file_name, trashed_at=None, trash_expires_at=None
    )

    logger.info(f"Restored {processed_path} from trash")
    return processed_path


async def purge_expired_trash() -> list[str]:
    """Delete trashed objects whose retention period has expired."""

    expired = await get_expired_trashed_posts()
    removed: list[str] = []
    for path in expired:
        try:
            await storage.delete_file(path, BUCKET_MAIN)
            file_name = os.path.basename(_processed_path_for(path))
            await storage.update_submission_metadata(
                file_name, trashed_at=None, trash_expires_at=None
            )
            removed.append(path)
            logger.info(f"Purged expired trash item: {path}")
        except Exception as exc:  # pragma: no cover - best effort cleanup
            logger.error(f"Failed to purge trash item {path}: {exc}")
    return removed


async def delete_from_trash(path: str) -> None:
    """Permanently remove ``path`` from the trash."""

    trash_path = _trash_path_for(path)
    await storage.delete_file(trash_path, BUCKET_MAIN)
    await remove_trashed_post(trash_path)
    file_name = os.path.basename(_processed_path_for(trash_path))
    await storage.update_submission_metadata(
        file_name, trashed_at=None, trash_expires_at=None
    )
