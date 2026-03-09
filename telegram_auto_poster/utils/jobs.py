"""Background job management for administrative tasks."""

from __future__ import annotations

import asyncio
import datetime
import json
import mimetypes
import os
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from loguru import logger
from telegram_auto_poster.config import (
    BUCKET_MAIN,
    CONFIG,
    PHOTOS_PATH,
    TRASH_PATH,
    VIDEOS_PATH,
)
from telegram_auto_poster.utils.caption import extract_ocr_text, get_tesseract_info
from telegram_auto_poster.utils.db import (
    add_trashed_post,
    _redis_key,
    get_async_redis_client,
    get_scheduled_posts,
    remove_scheduled_post,
)
from telegram_auto_poster.utils.general import cleanup_temp_file, download_from_minio
from telegram_auto_poster.utils.storage import storage
from telegram_auto_poster.utils.timezone import now_utc
from telegram_auto_poster.utils.trash import purge_expired_trash

JobRunner = Callable[["JobRunContext"], Awaitable[None]]
JobRuntimeBuilder = Callable[[], dict[str, Any]]

DEFAULT_JOB_STATE: dict[str, Any] = {
    "status": "idle",
    "status_detail": None,
    "pause_requested": False,
    "current_run_started_at": None,
    "current_stats": {},
    "last_run_started_at": None,
    "last_run_finished_at": None,
    "last_run_duration_seconds": None,
    "last_run_status": None,
    "last_run_stats": {},
    "last_error": None,
}


def _default_job_state() -> dict[str, Any]:
    """Return a fresh default job state."""

    return {
        **DEFAULT_JOB_STATE,
        "current_stats": {},
        "last_run_stats": {},
    }


@dataclass(slots=True)
class JobDefinition:
    """Static job definition exposed to the dashboard."""

    name: str
    title: str
    description: str
    runner: JobRunner
    runtime_builder: JobRuntimeBuilder | None = None


class JobRunContext:
    """Mutable state exposed to a running background job."""

    def __init__(self, manager: "JobManager", definition: JobDefinition) -> None:
        self.manager = manager
        self.definition = definition

    async def replace_stats(self, stats: dict[str, int | float | str]) -> None:
        """Replace the current stats payload for the active job."""

        await self.manager._update_state(self.definition.name, current_stats=stats)

    async def set_stat(self, key: str, value: int | float | str) -> None:
        """Set one stat value for the active job."""

        state = await self.manager._read_state(self.definition.name)
        current_stats = dict(state.get("current_stats") or {})
        current_stats[key] = value
        await self.manager._update_state(
            self.definition.name, current_stats=current_stats
        )

    async def increment(self, key: str, amount: int = 1) -> None:
        """Increment a numeric stat for the active job."""

        state = await self.manager._read_state(self.definition.name)
        current_stats = dict(state.get("current_stats") or {})
        current_stats[key] = int(current_stats.get(key, 0)) + amount
        await self.manager._update_state(
            self.definition.name, current_stats=current_stats
        )

    async def set_status_detail(self, detail: str | None) -> None:
        """Update the live status detail text."""

        await self.manager._update_state(self.definition.name, status_detail=detail)

    async def wait_if_paused(self) -> None:
        """Block the job loop while a pause has been requested."""

        was_paused = False
        while True:
            state = await self.manager._read_state(self.definition.name)
            if not state.get("pause_requested"):
                if was_paused:
                    await self.manager._update_state(
                        self.definition.name,
                        status="running",
                        status_detail="Resumed",
                    )
                return
            was_paused = True
            if state.get("status") != "paused":
                await self.manager._update_state(
                    self.definition.name,
                    status="paused",
                    status_detail="Paused",
                )
            await asyncio.sleep(0.5)


class JobManager:
    """Persisted background job registry for the admin dashboard."""

    def __init__(self) -> None:
        self._definitions: dict[str, JobDefinition] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def register(self, definition: JobDefinition) -> None:
        """Register a job definition."""

        self._definitions[definition.name] = definition
        self._locks.setdefault(definition.name, asyncio.Lock())

    async def initialize(self) -> None:
        """Mark interrupted jobs from previous process lifetimes as failed."""

        try:
            for name in self._definitions:
                state = await self._read_state(name)
                if state["status"] not in {"running", "paused"}:
                    continue
                started_at = state.get("current_run_started_at")
                finished_at = now_utc().isoformat()
                await self._write_state(
                    name,
                    {
                        "status": "failed",
                        "status_detail": None,
                        "pause_requested": False,
                        "current_run_started_at": None,
                        "current_stats": {},
                        "last_run_started_at": started_at,
                        "last_run_finished_at": finished_at,
                        "last_run_duration_seconds": _duration_seconds(
                            started_at, finished_at
                        ),
                        "last_run_status": "failed",
                        "last_run_stats": state.get("current_stats") or {},
                        "last_error": "Interrupted by application restart",
                    },
                )
        except Exception:
            logger.exception("Failed to initialize background job state")

    async def list_jobs(self) -> list[dict[str, Any]]:
        """Return job definitions merged with persisted runtime state."""

        items: list[dict[str, Any]] = []
        for definition in self._definitions.values():
            state = await self._read_state(definition.name)
            runtime = _build_runtime_payload(definition)
            current_started_at = state.get("current_run_started_at")
            items.append(
                {
                    "name": definition.name,
                    "title": definition.title,
                    "description": definition.description,
                    "status": state["status"],
                    "status_detail": state.get("status_detail"),
                    "pause_requested": bool(state.get("pause_requested")),
                    "current_run_started_at": current_started_at,
                    "current_run_duration_seconds": _duration_seconds(
                        current_started_at, now_utc().isoformat()
                    )
                    if state["status"] in {"running", "paused"}
                    else None,
                    "current_stats": state.get("current_stats") or {},
                    "last_run_started_at": state.get("last_run_started_at"),
                    "last_run_finished_at": state.get("last_run_finished_at"),
                    "last_run_duration_seconds": state.get("last_run_duration_seconds"),
                    "last_run_status": state.get("last_run_status"),
                    "last_run_stats": state.get("last_run_stats") or {},
                    "last_error": state.get("last_error"),
                    "can_run": state["status"] not in {"running", "paused"}
                    and runtime["can_run"],
                    "can_pause": state["status"] == "running",
                    "can_resume": state["status"] == "paused",
                    "runtime": runtime,
                }
            )
        return items

    async def run_job(self, name: str) -> dict[str, Any]:
        """Start a registered job unless it is already running."""

        definition = self._definitions.get(name)
        if definition is None:
            raise KeyError(name)

        runtime = _build_runtime_payload(definition)
        if not runtime["can_run"]:
            raise RuntimeError(runtime.get("reason") or "Job prerequisites are not met")

        async with self._locks[name]:
            state = await self._read_state(name)
            if state["status"] == "running":
                raise RuntimeError("Job is already running")

            task = asyncio.create_task(
                self._execute_job(definition),
                name=f"telegram-auto-poster-job:{name}",
            )
            self._tasks[name] = task

        await asyncio.sleep(0)
        return await self.get_job(name)

    async def get_job(self, name: str) -> dict[str, Any]:
        """Return one job payload by name."""

        for item in await self.list_jobs():
            if item["name"] == name:
                return item
        raise KeyError(name)

    async def pause_job(self, name: str) -> dict[str, Any]:
        """Pause a running job cooperatively."""

        definition = self._definitions.get(name)
        if definition is None:
            raise KeyError(name)

        async with self._locks[name]:
            state = await self._read_state(name)
            if state["status"] == "paused":
                raise RuntimeError("Job is already paused")
            if state["status"] != "running":
                raise RuntimeError("Only running jobs can be paused")
            await self._update_state(
                name,
                status="paused",
                status_detail="Paused",
                pause_requested=True,
            )

        return await self.get_job(name)

    async def resume_job(self, name: str) -> dict[str, Any]:
        """Resume a paused job."""

        definition = self._definitions.get(name)
        if definition is None:
            raise KeyError(name)

        async with self._locks[name]:
            state = await self._read_state(name)
            if state["status"] != "paused":
                raise RuntimeError("Only paused jobs can be resumed")
            await self._update_state(
                name,
                status="running",
                status_detail="Resuming",
                pause_requested=False,
            )

        return await self.get_job(name)

    async def _execute_job(self, definition: JobDefinition) -> None:
        started_at = now_utc().isoformat()
        await self._write_state(
            definition.name,
            {
                "status": "running",
                "status_detail": "Preparing run",
                "pause_requested": False,
                "current_run_started_at": started_at,
                "current_stats": {},
                "last_error": None,
            },
        )
        context = JobRunContext(self, definition)
        try:
            await definition.runner(context)
            final_status = "succeeded"
            last_error = None
        except Exception as exc:
            logger.exception("Background job %s failed", definition.name)
            final_status = "failed"
            last_error = str(exc)

        finished_at = now_utc().isoformat()
        state = await self._read_state(definition.name)
        await self._write_state(
            definition.name,
            {
                "status": final_status,
                "status_detail": None,
                "pause_requested": False,
                "current_run_started_at": None,
                "current_stats": {},
                "last_run_started_at": started_at,
                "last_run_finished_at": finished_at,
                "last_run_duration_seconds": _duration_seconds(started_at, finished_at),
                "last_run_status": final_status,
                "last_run_stats": state.get("current_stats") or {},
                "last_error": last_error,
            },
        )
        self._tasks.pop(definition.name, None)

    async def _read_state(self, name: str) -> dict[str, Any]:
        try:
            data = await get_async_redis_client().hgetall(_job_state_key(name))
        except Exception:
            logger.exception("Failed to read background job state for %s", name)
            return _default_job_state()
        if not data:
            return _default_job_state()

        state = _default_job_state()
        state.update(
            {
                "status": data.get("status", state["status"]),
                "status_detail": data.get("status_detail") or None,
                "pause_requested": data.get("pause_requested") in {"True", "true", "1"},
                "current_run_started_at": data.get("current_run_started_at") or None,
                "last_run_started_at": data.get("last_run_started_at") or None,
                "last_run_finished_at": data.get("last_run_finished_at") or None,
                "last_run_duration_seconds": (
                    float(data["last_run_duration_seconds"])
                    if data.get("last_run_duration_seconds")
                    else None
                ),
                "last_run_status": data.get("last_run_status") or None,
                "last_error": data.get("last_error") or None,
                "current_stats": _json_field_to_dict(data.get("current_stats")),
                "last_run_stats": _json_field_to_dict(data.get("last_run_stats")),
            }
        )
        return state

    async def _update_state(self, name: str, **fields: Any) -> None:
        state = await self._read_state(name)
        state.update(fields)
        await self._write_state(name, state)

    async def _write_state(self, name: str, state: dict[str, Any]) -> None:
        mapping: dict[str, str] = {}
        for key, value in state.items():
            if key in {"current_stats", "last_run_stats"}:
                mapping[key] = json.dumps(
                    value or {}, ensure_ascii=True, sort_keys=True
                )
            elif value is None:
                mapping[key] = ""
            else:
                mapping[key] = str(value)
        try:
            await get_async_redis_client().hset(_job_state_key(name), mapping=mapping)
        except Exception:
            logger.exception("Failed to write background job state for %s", name)


def _job_state_key(name: str) -> str:
    """Return the redis key used to store a job state."""

    return _redis_key("jobs", name)


def _json_field_to_dict(value: str | None) -> dict[str, Any]:
    """Deserialize a JSON object from a redis hash field."""

    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _duration_seconds(started_at: str | None, finished_at: str | None) -> float | None:
    """Return the run duration in seconds when both timestamps are valid."""

    if not started_at or not finished_at:
        return None
    try:
        start = datetime.datetime.fromisoformat(started_at)
        end = datetime.datetime.fromisoformat(finished_at)
    except ValueError:
        return None
    return max(0.0, (end - start).total_seconds())


def _is_image_path(path: str) -> bool:
    """Return whether the object path points to an image."""

    mime_type = mimetypes.guess_type(path)[0]
    return bool(mime_type and mime_type.startswith("image/"))


def _ocr_lookup_key(path: str) -> str:
    """Return the metadata lookup key for a stored image path."""

    if path.startswith(("photos/", "videos/", "downloads/")):
        return os.path.basename(path)
    return os.path.basename(path)


def _needs_ocr(meta: dict[str, Any] | None) -> bool:
    """Return whether OCR has not been recorded for a media item yet."""

    if not meta:
        return True
    return not any(
        meta.get(field) is not None
        for field in ("ocr_checked_at", "ocr_status", "ocr_text")
    )


def _build_runtime_payload(definition: JobDefinition) -> dict[str, Any]:
    """Return runtime details for one job definition."""

    if definition.runtime_builder is None:
        return {"can_run": True}
    payload = definition.runtime_builder()
    payload.setdefault("can_run", True)
    return payload


def _ocr_missing_images_runtime() -> dict[str, Any]:
    """Return runtime details for the OCR backfill job."""

    tesseract = get_tesseract_info()
    enabled = CONFIG.ocr.enabled
    can_run = enabled and tesseract.available
    reason = None
    if not enabled:
        reason = "OCR is disabled in configuration"
    elif not tesseract.available:
        reason = tesseract.error or "Tesseract is unavailable"
    return {
        "can_run": can_run,
        "reason": reason,
        "progress": {
            "current_key": "images_checked",
            "total_key": "images_missing_ocr",
            "label": "OCR progress",
        },
        "details": [
            {
                "label": "Tesseract",
                "value": (
                    tesseract.version
                    if tesseract.available
                    else tesseract.error or "Unavailable"
                ),
            },
            {
                "label": "OCR languages",
                "value": CONFIG.ocr.languages or "—",
            },
        ],
        "ocr_enabled": enabled,
        "languages": CONFIG.ocr.languages,
        "tesseract_available": tesseract.available,
        "tesseract_version": tesseract.version,
        "tesseract_error": tesseract.error,
    }


async def _run_ocr_missing_images(context: JobRunContext) -> None:
    """Extract OCR text for every stored image missing OCR metadata."""

    objects = await storage.list_files(BUCKET_MAIN)
    image_paths = [path for path in objects if _is_image_path(path)]
    pending_paths: list[tuple[str, str]] = []
    skipped = 0

    for path in image_paths:
        lookup_key = _ocr_lookup_key(path)
        meta = await storage.get_submission_metadata(lookup_key)
        if _needs_ocr(meta):
            pending_paths.append((path, lookup_key))
        else:
            skipped += 1

    await context.replace_stats(
        {
            "images_total": len(image_paths),
            "images_missing_ocr": len(pending_paths),
            "images_skipped": skipped,
            "images_checked": 0,
            "images_ocred": 0,
            "images_with_text": 0,
            "images_without_text": 0,
            "images_failed": 0,
        }
    )

    total_pending = len(pending_paths)
    if total_pending == 0:
        await context.set_status_detail("No images need OCR")
        return

    for index, (path, lookup_key) in enumerate(pending_paths, start=1):
        await context.wait_if_paused()
        await context.set_status_detail(
            f"OCR {index}/{total_pending}: {os.path.basename(path)}"
        )
        await context.increment("images_checked")
        try:
            temp_path, _mime = await download_from_minio(path, BUCKET_MAIN)
        except Exception as exc:
            await context.increment("images_failed")
            await storage.update_submission_metadata(
                lookup_key,
                ocr_text="",
                ocr_status="failed",
                ocr_error=str(exc),
                ocr_checked_at=now_utc().isoformat(),
                ocr_languages=CONFIG.ocr.languages,
            )
            continue
        if not temp_path:
            await context.increment("images_failed")
            continue

        try:
            result = await asyncio.to_thread(
                extract_ocr_text, temp_path, CONFIG.ocr.languages
            )
        finally:
            cleanup_temp_file(temp_path)

        await storage.update_submission_metadata(
            lookup_key,
            ocr_text=result.text,
            ocr_status=result.status,
            ocr_error=result.error,
            ocr_checked_at=now_utc().isoformat(),
            ocr_duration_seconds=result.duration_seconds,
            ocr_languages=CONFIG.ocr.languages,
        )
        await context.increment("images_ocred")
        if result.status != "completed":
            await context.increment("images_failed")
        elif result.text:
            await context.increment("images_with_text")
        else:
            await context.increment("images_without_text")

    await context.set_status_detail(f"Completed OCR for {total_pending} images")


async def _run_refresh_search_text(context: JobRunContext) -> None:
    """Rebuild cached search text in Redis from stored metadata and OCR results."""

    objects = await storage.list_files(BUCKET_MAIN)
    await context.replace_stats(
        {
            "objects_total": len(objects),
            "objects_checked": 0,
            "objects_indexed": 0,
            "objects_changed": 0,
            "objects_without_metadata": 0,
        }
    )

    total = len(objects)
    if total == 0:
        await context.set_status_detail("No objects found")
        return

    for index, path in enumerate(objects, start=1):
        lookup_key = _ocr_lookup_key(path)
        await context.increment("objects_checked")
        meta = await storage.get_submission_metadata(lookup_key)
        if not meta:
            await context.increment("objects_without_metadata")
            continue

        await context.set_status_detail(
            f"Refresh {index}/{total}: {os.path.basename(path)}"
        )
        before = str(meta.get("search_text") or "")
        refreshed = await storage.refresh_submission_search_text(lookup_key)
        after = str((refreshed or {}).get("search_text") or "")
        await context.increment("objects_indexed")
        if before != after:
            await context.increment("objects_changed")

    await context.set_status_detail(f"Refreshed search text for {total} objects")


def _refresh_search_text_runtime() -> dict[str, Any]:
    """Return runtime details for the search text refresh job."""

    return {
        "can_run": True,
        "progress": {
            "current_key": "objects_checked",
            "total_key": "objects_total",
            "label": "Checked objects",
        },
        "details": [
            {
                "label": "Source",
                "value": "MinIO metadata + OCR cache",
            }
        ],
    }


def _reconcile_scheduled_queue_runtime() -> dict[str, Any]:
    """Return runtime details for the scheduled queue reconciliation job."""

    return {
        "can_run": True,
        "progress": {
            "current_key": "items_checked",
            "total_key": "scheduled_total",
            "label": "Checked scheduled items",
        },
        "details": [
            {
                "label": "Queue source",
                "value": "Valkey scheduled_posts + MinIO objects",
            }
        ],
    }


async def _run_reconcile_scheduled_queue(context: JobRunContext) -> None:
    """Remove stale scheduled entries whose storage object no longer exists."""

    scheduled_posts = await asyncio.to_thread(get_scheduled_posts)
    now_ts = int(now_utc().timestamp())
    await context.replace_stats(
        {
            "scheduled_total": len(scheduled_posts),
            "items_checked": 0,
            "kept_valid": 0,
            "overdue_items": 0,
            "missing_objects": 0,
            "removed_stale": 0,
            "failed": 0,
        }
    )

    if not scheduled_posts:
        await context.set_status_detail("No scheduled posts found")
        return

    total = len(scheduled_posts)
    for index, (path, scheduled_ts) in enumerate(scheduled_posts, start=1):
        await context.wait_if_paused()
        await context.set_status_detail(
            f"Check {index}/{total}: {os.path.basename(path)}"
        )
        await context.increment("items_checked")
        if int(scheduled_ts) <= now_ts:
            await context.increment("overdue_items")

        try:
            exists = await storage.file_exists(path, BUCKET_MAIN)
        except Exception:
            await context.increment("failed")
            logger.exception("Failed to inspect scheduled object %s", path)
            continue

        if exists:
            await context.increment("kept_valid")
            continue

        await context.increment("missing_objects")
        try:
            await asyncio.to_thread(remove_scheduled_post, path)
            await context.increment("removed_stale")
        except Exception:
            await context.increment("failed")
            logger.exception("Failed to remove stale scheduled entry %s", path)

    await context.set_status_detail(f"Checked {total} scheduled items")


def _purge_expired_trash_runtime() -> dict[str, Any]:
    """Return runtime details for the trash purge job."""

    return {
        "can_run": True,
        "details": [
            {
                "label": "Scope",
                "value": "Trash objects whose Valkey expiration has passed",
            }
        ],
    }


async def _run_purge_expired_trash(context: JobRunContext) -> None:
    """Delete expired trash objects immediately."""

    trash_before = await _count_trash_objects()
    await context.replace_stats(
        {
            "trash_objects_before": trash_before,
            "removed": 0,
            "trash_objects_after": trash_before,
        }
    )
    await context.set_status_detail("Purging expired trash")
    removed = await purge_expired_trash()
    trash_after = await _count_trash_objects()
    await context.replace_stats(
        {
            "trash_objects_before": trash_before,
            "removed": len(removed),
            "trash_objects_after": trash_after,
        }
    )
    await context.set_status_detail(f"Removed {len(removed)} expired trash items")


def _sync_trash_registry_runtime() -> dict[str, Any]:
    """Return runtime details for the trash registry sync job."""

    return {
        "can_run": True,
        "progress": {
            "current_key": "items_checked",
            "total_key": "trash_objects",
            "label": "Checked trash objects",
        },
        "details": [
            {
                "label": "Queue source",
                "value": "MinIO trash paths + metadata expiration timestamps",
            }
        ],
    }


async def _run_sync_trash_registry(context: JobRunContext) -> None:
    """Rebuild trash expiration entries in Valkey from stored metadata."""

    trash_objects = await _list_trash_objects()
    now = now_utc()
    await context.replace_stats(
        {
            "trash_objects": len(trash_objects),
            "items_checked": 0,
            "registry_synced": 0,
            "missing_metadata": 0,
            "invalid_expiration": 0,
            "already_expired": 0,
        }
    )

    if not trash_objects:
        await context.set_status_detail("No trash objects found")
        return

    total = len(trash_objects)
    for index, path in enumerate(trash_objects, start=1):
        await context.wait_if_paused()
        await context.set_status_detail(
            f"Sync {index}/{total}: {os.path.basename(path)}"
        )
        await context.increment("items_checked")
        meta = await storage.get_submission_metadata(os.path.basename(path))
        if not meta:
            await context.increment("missing_metadata")
            continue

        expires_at = _parse_iso_datetime(meta.get("trash_expires_at"))
        if expires_at is None:
            await context.increment("invalid_expiration")
            continue
        if expires_at <= now:
            await context.increment("already_expired")
            continue

        await add_trashed_post(path, int(expires_at.timestamp()))
        await context.increment("registry_synced")

    await context.set_status_detail(f"Synced {total} trash objects")


def _reconcile_batch_count_runtime() -> dict[str, Any]:
    """Return runtime details for the batch count reconciliation job."""

    return {
        "can_run": True,
        "details": [
            {
                "label": "Counter",
                "value": _redis_key("batch", "size"),
            }
        ],
    }


async def _run_reconcile_batch_count(context: JobRunContext) -> None:
    """Reset the stored batch counter to match MinIO contents."""

    redis = get_async_redis_client()
    key = _redis_key("batch", "size")
    stored_raw = await redis.get(key)
    stored_count = int(stored_raw) if stored_raw is not None else 0
    actual_count = await _count_batch_objects()
    await redis.set(key, str(actual_count))
    await context.replace_stats(
        {
            "stored_count": stored_count,
            "actual_count": actual_count,
            "delta": actual_count - stored_count,
            "updated": 1 if actual_count != stored_count else 0,
        }
    )
    await context.set_status_detail(
        "Batch counter updated"
        if actual_count != stored_count
        else "Batch counter already matched storage"
    )


async def _list_trash_objects() -> list[str]:
    """Return all current trash object paths."""

    photo_files, video_files = await asyncio.gather(
        storage.list_files(BUCKET_MAIN, prefix=f"{TRASH_PATH}/{PHOTOS_PATH}/"),
        storage.list_files(BUCKET_MAIN, prefix=f"{TRASH_PATH}/{VIDEOS_PATH}/"),
    )
    return list(photo_files) + list(video_files)


async def _count_trash_objects() -> int:
    """Return the total number of trash objects in storage."""

    return len(await _list_trash_objects())


async def _count_batch_objects() -> int:
    """Return the total number of batch objects in storage."""

    photo_files, video_files = await asyncio.gather(
        storage.list_files(BUCKET_MAIN, prefix=f"{PHOTOS_PATH}/batch_"),
        storage.list_files(BUCKET_MAIN, prefix=f"{VIDEOS_PATH}/batch_"),
    )
    return len(photo_files) + len(video_files)


def _parse_iso_datetime(value: object) -> datetime.datetime | None:
    """Parse an ISO datetime string into an aware UTC datetime when possible."""

    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=datetime.UTC)
    return parsed.astimezone(datetime.UTC)


job_manager = JobManager()
job_manager.register(
    JobDefinition(
        name="ocr_missing_images",
        title="OCR missing images",
        description="Extract OCR text for stored images that do not have OCR metadata yet.",
        runner=_run_ocr_missing_images,
        runtime_builder=_ocr_missing_images_runtime,
    )
)
job_manager.register(
    JobDefinition(
        name="refresh_search_text",
        title="Refresh search text",
        description="Rebuild Redis search text from captions, source names, filenames, and OCR results.",
        runner=_run_refresh_search_text,
        runtime_builder=_refresh_search_text_runtime,
    )
)
job_manager.register(
    JobDefinition(
        name="reconcile_scheduled_queue",
        title="Reconcile scheduled queue",
        description="Remove scheduled queue entries that no longer have a corresponding object in storage.",
        runner=_run_reconcile_scheduled_queue,
        runtime_builder=_reconcile_scheduled_queue_runtime,
    )
)
job_manager.register(
    JobDefinition(
        name="purge_expired_trash",
        title="Purge expired trash",
        description="Delete trash objects whose retention period has already expired.",
        runner=_run_purge_expired_trash,
        runtime_builder=_purge_expired_trash_runtime,
    )
)
job_manager.register(
    JobDefinition(
        name="sync_trash_registry",
        title="Sync trash registry",
        description="Rebuild Valkey trash expiration entries from stored trash metadata.",
        runner=_run_sync_trash_registry,
        runtime_builder=_sync_trash_registry_runtime,
    )
)
job_manager.register(
    JobDefinition(
        name="reconcile_batch_count",
        title="Reconcile batch count",
        description="Reset the stored batch counter to match the actual number of batch objects in storage.",
        runner=_run_reconcile_batch_count,
        runtime_builder=_reconcile_batch_count_runtime,
    )
)
