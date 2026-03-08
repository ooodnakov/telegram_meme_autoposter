"""Administrative dashboard API and SPA entrypoint."""

from __future__ import annotations

import asyncio
import datetime
import mimetypes
import os
import pydoc
from pathlib import Path
from pydoc import locate
from typing import Any, Awaitable, Callable, Mapping, Sequence
from urllib.parse import urlparse

from fastapi import FastAPI, Form, HTTPException, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from miniopy_async.commonconfig import CopySource
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
from telegram import Bot

from telegram_auto_poster.config import (
    BUCKET_MAIN,
    CONFIG,
    PHOTOS_PATH,
    SCHEDULED_PATH,
    SUGGESTION_CAPTION,
    TRASH_PATH,
    VIDEOS_PATH,
)
from telegram_auto_poster.utils.db import (
    EVENT_HISTORY_LIMIT,
    add_event_history_entry,
    add_scheduled_post,
    clear_event_history,
    decrement_batch_count,
    get_event_history,
    get_scheduled_posts,
    get_scheduled_posts_count,
    increment_batch_count,
    remove_scheduled_post,
)
from telegram_auto_poster.utils.deduplication import (
    add_approved_hash,
    calculate_image_hash,
    calculate_video_hash,
)
from telegram_auto_poster.utils.general import (
    cleanup_temp_file,
    download_from_minio,
    prepare_group_items,
    send_group_media,
    send_media_to_telegram,
)
from telegram_auto_poster.utils.i18n import set_locale
from telegram_auto_poster.utils.scheduler import find_next_available_slot
from telegram_auto_poster.utils.stats import stats
from telegram_auto_poster.utils.storage import storage
from telegram_auto_poster.utils.timezone import UTC, now_utc, parse_to_utc_timestamp
from telegram_auto_poster.utils.trash import (
    delete_from_trash,
    move_to_trash,
    purge_expired_trash,
    restore_from_trash,
)
from telegram_auto_poster.web.auth import validate_telegram_login


REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = REPO_ROOT / "frontend"
FRONTEND_DIST_DIR = FRONTEND_DIR / "dist"
FRONTEND_INDEX = FRONTEND_DIST_DIR / "index.html"

LANGUAGES: dict[str, str] = {
    "ru": "Русский",
    "en": "English",
}
if CONFIG.i18n.default not in LANGUAGES:
    LANGUAGES[CONFIG.i18n.default] = CONFIG.i18n.default
LANGUAGE_CODES = list(LANGUAGES)

SPA_PUBLIC_PATHS = {
    "/login",
    "/auth",
    "/logout",
    "/language",
    "/favicon.ico",
    "/robots.txt",
    "/placeholder.svg",
}
SPA_PUBLIC_PREFIXES = ("/assets", "/pydoc")
SPA_RESERVED_PREFIXES = ("api/", "assets/", "pydoc/")
SPA_RESERVED_PATHS = {
    "auth",
    "logout",
    "language",
    "favicon.ico",
    "robots.txt",
    "placeholder.svg",
}


class ActionRequest(BaseModel):
    """JSON payload for moderation actions."""

    path: str | None = None
    paths: list[str] = Field(default_factory=list)
    action: str
    origin: str = "suggestions"


class ManualScheduleRequest(BaseModel):
    """JSON payload for manual scheduling."""

    scheduled_at: str
    path: str | None = None
    paths: list[str] = Field(default_factory=list)
    origin: str = "batch"


class QueueScheduleRequest(BaseModel):
    """JSON payload for queue rescheduling."""

    path: str
    scheduled_at: str


class PathListRequest(BaseModel):
    """JSON payload containing one or more paths."""

    path: str | None = None
    paths: list[str] = Field(default_factory=list)


class LanguageRequest(BaseModel):
    """JSON payload for changing dashboard language."""

    language: str


class ResetRequest(BaseModel):
    """JSON payload for reset actions."""

    next: str = "/"


def _cycle_language(current: str) -> str:
    """Return the next language code from :data:`LANGUAGES`."""

    if current in LANGUAGE_CODES:
        index = LANGUAGE_CODES.index(current)
        return LANGUAGE_CODES[(index + 1) % len(LANGUAGE_CODES)]
    return LANGUAGE_CODES[0]


def _safe_redirect_target(target: str) -> str:
    """Return a safe redirect target limited to application paths."""

    if not target:
        return "/"
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc:
        return "/"
    if not target.startswith("/"):
        return "/"
    return target


def _redirect_after_post(next_url: str | None, default: str) -> RedirectResponse:
    """Return a redirect response honoring ``next_url`` when safe."""

    destination = _safe_redirect_target(next_url or default)
    return RedirectResponse(url=destination, status_code=status.HTTP_303_SEE_OTHER)


def _set_session_username(request: Request, data: Mapping[str, object]) -> None:
    """Store the username from ``data`` in the session when present."""

    username = data.get("username")
    if isinstance(username, str) and username:
        request.session["username"] = username


def _get_request_language(request: Request) -> str:
    """Return the active language for ``request``."""

    language = getattr(request.state, "language", CONFIG.i18n.default)
    if isinstance(language, str):
        return language
    return CONFIG.i18n.default


def _session_payload(request: Request) -> dict[str, object]:
    """Return the authenticated session payload."""

    return {
        "user_id": request.session.get("user_id"),
        "username": request.session.get("username"),
        "language": _get_request_language(request),
        "languages": LANGUAGES,
        "default_language": CONFIG.i18n.default,
        "bot_username": CONFIG.bot.bot_username,
    }


def _normalize_paths(path: str | None, paths: Sequence[str]) -> list[str]:
    """Merge singular and plural path arguments into a single list."""

    merged = list(paths)
    if path:
        merged.append(path)
    return merged


def _is_background_request(request: Request) -> bool:
    """Return whether ``request`` expects a JSON background response."""

    return request.headers.get("X-Background-Request", "").lower() == "true"


def _is_spa_public_path(path: str) -> bool:
    """Return whether ``path`` is publicly accessible."""

    if path in SPA_PUBLIC_PATHS:
        return True
    return any(path.startswith(prefix) for prefix in SPA_PUBLIC_PREFIXES)


class AuthMiddleware(BaseHTTPMiddleware):
    """Session-based authentication using Telegram user IDs."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:  # type: ignore[override]
        lang = CONFIG.i18n.default
        if "session" in request.scope:
            stored_lang = request.session.get("language")
            if isinstance(stored_lang, str) and stored_lang in LANGUAGES:
                lang = stored_lang
        request.state.language = lang
        set_locale(lang)

        path = request.url.path
        if request.method == "OPTIONS" or _is_spa_public_path(path):
            return await call_next(request)

        user_id = request.session.get("user_id")
        if user_id and user_id in (CONFIG.bot.admin_ids or []):
            return await call_next(request)

        if path.startswith("/api/"):
            return JSONResponse(
                {"detail": "Unauthorized"},
                status_code=status.HTTP_401_UNAUTHORIZED,
            )

        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)


app = FastAPI(title="Telegram Autoposter Admin")
app.add_middleware(AuthMiddleware)
app.add_middleware(
    SessionMiddleware, secret_key=CONFIG.web.session_secret.get_secret_value()
)

app.mount(
    "/assets",
    StaticFiles(directory=str(FRONTEND_DIST_DIR / "assets"), check_dir=False),
    name="frontend_assets",
)

bot = Bot(token=CONFIG.bot.bot_token.get_secret_value())
TARGET_CHANNELS = CONFIG.telegram.target_channels
QUIET_START = CONFIG.schedule.quiet_hours_start
QUIET_END = CONFIG.schedule.quiet_hours_end
ITEMS_PER_PAGE = 30
MANUAL_SCHEDULE_INTERVAL_SECONDS = 3600
EVENT_HISTORY_PAGE_SIZE = 50

BATCH_ITEM_PREFIXES = (
    f"{PHOTOS_PATH}/batch_",
    f"{VIDEOS_PATH}/batch_",
)


def _is_batch_item(path: str) -> bool:
    """Return ``True`` when ``path`` belongs to the batch queue."""

    return path.startswith(BATCH_ITEM_PREFIXES)


def _extract_submitter(meta: dict[str, object] | None) -> dict[str, object] | None:
    """Return structured submitter information for API consumers and logging."""

    if not meta:
        return None

    raw_user_id = meta.get("user_id")
    try:
        user_id = int(raw_user_id) if raw_user_id is not None else None
    except (TypeError, ValueError):
        user_id = None

    source = meta.get("source")
    admin_ids = tuple(CONFIG.bot.admin_ids or [])
    is_admin = bool(user_id is not None and user_id in admin_ids)
    submitter: dict[str, object] = {
        "is_admin": is_admin,
        "is_suggestion": user_id is not None,
    }
    if user_id is not None:
        submitter["user_id"] = user_id
    if source:
        submitter["source"] = source
    return submitter


def _paginate(
    total: int, page: int, per_page: int = ITEMS_PER_PAGE
) -> tuple[int, int, int]:
    """Return sanitized page number, total pages and offset."""

    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    offset = (page - 1) * per_page
    return page, total_pages, offset


def _parse_iso_timestamp(value: object) -> str | None:
    """Normalize ``value`` into an ISO timestamp string when possible."""

    if isinstance(value, datetime.datetime):
        dt = value
    elif isinstance(value, str):
        try:
            dt = datetime.datetime.fromisoformat(value)
        except ValueError:
            return value
    else:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.isoformat()


def _media_kind(path: str, mime: str | None = None) -> str:
    """Return ``image`` or ``video`` based on object path and mime type."""

    guessed_mime = mime or mimetypes.guess_type(path)[0]
    if path.startswith(f"{VIDEOS_PATH}/") or path.startswith(f"{TRASH_PATH}/{VIDEOS_PATH}/"):
        return "video"
    if path.startswith(f"{PHOTOS_PATH}/") or path.startswith(f"{TRASH_PATH}/{PHOTOS_PATH}/"):
        return "image"
    if guessed_mime and guessed_mime.startswith("video/"):
        return "video"
    return "image"


def _media_item(
    path: str,
    url: str,
    meta: dict[str, object] | None,
    *,
    trashed_at: str | None = None,
    expires_at: str | None = None,
) -> dict[str, object]:
    """Build a normalized media item payload."""

    mime, _ = mimetypes.guess_type(path)
    kind = _media_kind(path, mime)
    return {
        "path": path,
        "name": os.path.basename(path),
        "url": url,
        "mime_type": mime,
        "kind": kind,
        "caption": meta.get("caption") if meta else None,
        "source": meta.get("source") if meta else None,
        "group_id": meta.get("group_id") if meta else None,
        "trashed_at": trashed_at,
        "expires_at": expires_at,
    }


def _group_payload(
    items: list[dict[str, object]],
    meta: dict[str, object] | None = None,
    *,
    trashed_at: str | None = None,
    expires_at: str | None = None,
) -> dict[str, object]:
    """Build a normalized media group payload."""

    first_caption = next(
        (item["caption"] for item in items if isinstance(item.get("caption"), str) and item["caption"]),
        None,
    )
    first_source = next(
        (item["source"] for item in items if isinstance(item.get("source"), str) and item["source"]),
        None,
    )
    payload: dict[str, object] = {
        "items": items,
        "count": len(items),
        "is_group": len(items) > 1,
        "caption": first_caption,
        "source": first_source,
        "submitter": _extract_submitter(meta),
        "trashed_at": trashed_at,
        "expires_at": expires_at,
    }
    if meta:
        payload["group_id"] = meta.get("group_id")
    return payload


async def _get_metas_for_paths(
    paths: Sequence[str],
) -> list[tuple[str, dict[str, object] | None]]:
    """Fetch submission metadata for ``paths`` concurrently."""

    if not paths:
        return []
    tasks = [storage.get_submission_metadata(os.path.basename(path)) for path in paths]
    results = await asyncio.gather(*tasks)
    return [(path, meta) for path, meta in zip(paths, results)]


async def _record_event(
    action: str,
    *,
    origin: str | None = None,
    request: Request | None = None,
    items: Sequence[tuple[str, dict[str, object] | None]] | None = None,
    extra: dict[str, object] | None = None,
) -> None:
    """Persist an admin action in the event history list."""

    entry: dict[str, object] = {
        "timestamp": now_utc().isoformat(),
        "action": action,
    }
    if origin:
        entry["origin"] = origin
    if request is not None:
        actor_id = request.session.get("user_id")
        if actor_id is not None:
            entry["actor_id"] = actor_id
        actor_username = request.session.get("username")
        if actor_username:
            entry["actor_username"] = actor_username
    if extra:
        entry["extra"] = extra

    event_items: list[dict[str, object]] = []
    for path, meta in items or []:
        event_item: dict[str, object] = {"path": path}
        event_item["media_type"] = "photo" if _media_kind(path) == "image" else "video"
        submitter = _extract_submitter(meta)
        if submitter:
            event_item["submitter"] = submitter
        event_items.append(event_item)
    if event_items:
        entry["items"] = event_items

    await add_event_history_entry(entry)


async def _list_media(
    prefix_type: str, *, offset: int = 0, limit: int | None = None
) -> list[str]:
    """Return a combined list of photo and video object paths."""

    photos_count = await storage.count_files(
        BUCKET_MAIN, prefix=f"{PHOTOS_PATH}/{prefix_type}_"
    )
    objects: list[str] = []
    if offset < photos_count:
        photo_limit = None if limit is None else min(limit, photos_count - offset)
        objects += await storage.list_files(
            BUCKET_MAIN,
            prefix=f"{PHOTOS_PATH}/{prefix_type}_",
            offset=offset,
            limit=photo_limit,
        )
        video_offset = 0
        remaining = None if limit is None else limit - len(objects)
    else:
        video_offset = offset - photos_count
        remaining = None if limit is None else limit
    if remaining is None or remaining > 0:
        objects += await storage.list_files(
            BUCKET_MAIN,
            prefix=f"{VIDEOS_PATH}/{prefix_type}_",
            offset=video_offset,
            limit=remaining,
        )
    return objects


async def _list_trash_media(*, offset: int = 0, limit: int | None = None) -> list[str]:
    """Return trashed media paths for photos and videos."""

    photos_count = await storage.count_files(
        BUCKET_MAIN, prefix=f"{TRASH_PATH}/{PHOTOS_PATH}/"
    )
    objects: list[str] = []
    if offset < photos_count:
        photo_limit = None if limit is None else min(limit, photos_count - offset)
        objects += await storage.list_files(
            BUCKET_MAIN,
            prefix=f"{TRASH_PATH}/{PHOTOS_PATH}/",
            offset=offset,
            limit=photo_limit,
        )
        video_offset = 0
        remaining = None if limit is None else limit - len(objects)
    else:
        video_offset = offset - photos_count
        remaining = None if limit is None else limit
    if remaining is None or remaining > 0:
        objects += await storage.list_files(
            BUCKET_MAIN,
            prefix=f"{TRASH_PATH}/{VIDEOS_PATH}/",
            offset=video_offset,
            limit=remaining,
        )
    return objects


async def _gather_posts(
    only_suggestions: bool,
    *,
    offset: int = 0,
    limit: int | None = None,
) -> list[dict[str, object]]:
    """Collect processed posts for the dashboard API."""

    objects = await _list_media("processed", offset=offset, limit=limit)
    posts: list[dict[str, object]] = []
    grouped: dict[str, dict[str, object]] = {}
    for obj in objects:
        file_name = os.path.basename(obj)
        meta = await storage.get_submission_metadata(file_name)
        is_suggestion = bool(meta and meta.get("user_id"))
        if only_suggestions and not is_suggestion:
            continue
        if not only_suggestions and is_suggestion:
            continue
        url = await storage.get_presigned_url(obj)
        if not url:
            continue

        item = _media_item(obj, url, meta)
        group_id = meta.get("group_id") if meta else None
        if group_id:
            bucket = grouped.setdefault(group_id, {"items": [], "meta": meta})
            bucket["items"].append(item)
        else:
            posts.append(_group_payload([item], meta))

    for bucket in grouped.values():
        posts.append(_group_payload(bucket["items"], bucket.get("meta")))  # type: ignore[arg-type]
    return posts


async def _gather_batch(*, offset: int = 0, limit: int | None = None) -> list[dict[str, object]]:
    """Collect batch items for display or processing."""

    objects = await _list_media("batch", offset=offset, limit=limit)
    posts: list[dict[str, object]] = []
    grouped: dict[str, dict[str, object]] = {}
    for obj in objects:
        file_name = os.path.basename(obj)
        meta = await storage.get_submission_metadata(file_name)
        url = await storage.get_presigned_url(obj)
        if not url:
            continue

        item = _media_item(obj, url, meta)
        group_id = meta.get("group_id") if meta else None
        if group_id:
            bucket = grouped.setdefault(group_id, {"items": [], "meta": meta})
            bucket["items"].append(item)
        else:
            posts.append(_group_payload([item], meta))

    for bucket in grouped.values():
        posts.append(_group_payload(bucket["items"], bucket.get("meta")))  # type: ignore[arg-type]
    return posts


async def _gather_trash(*, offset: int = 0, limit: int | None = None) -> list[dict[str, object]]:
    """Collect trashed posts for display."""

    await purge_expired_trash()
    objects = await _list_trash_media(offset=offset, limit=limit)
    posts: list[dict[str, object]] = []
    grouped: dict[str, dict[str, object]] = {}
    for obj in objects:
        file_name = os.path.basename(obj)
        meta = await storage.get_submission_metadata(file_name)
        url = await storage.get_presigned_url(obj)
        if not url:
            continue

        trashed_at = _parse_iso_timestamp(meta.get("trashed_at") if meta else None)
        expires_at = _parse_iso_timestamp(meta.get("trash_expires_at") if meta else None)
        item = _media_item(
            obj,
            url,
            meta,
            trashed_at=trashed_at,
            expires_at=expires_at,
        )
        group_id = meta.get("group_id") if meta else None
        if group_id:
            bucket = grouped.setdefault(
                group_id,
                {
                    "items": [],
                    "meta": meta,
                    "trashed_at": trashed_at,
                    "expires_at": expires_at,
                },
            )
            bucket["items"].append(item)
        else:
            posts.append(
                _group_payload(
                    [item],
                    meta,
                    trashed_at=trashed_at,
                    expires_at=expires_at,
                )
            )

    for bucket in grouped.values():
        posts.append(
            _group_payload(
                bucket["items"],  # type: ignore[arg-type]
                bucket.get("meta"),  # type: ignore[arg-type]
                trashed_at=bucket.get("trashed_at"),  # type: ignore[arg-type]
                expires_at=bucket.get("expires_at"),  # type: ignore[arg-type]
            )
        )
    return posts


async def _get_batch_count() -> int:
    """Return the total number of files currently in the batch."""

    photos, videos = await asyncio.gather(
        storage.list_files(BUCKET_MAIN, prefix=BATCH_ITEM_PREFIXES[0]),
        storage.list_files(BUCKET_MAIN, prefix=BATCH_ITEM_PREFIXES[1]),
    )
    return len(photos) + len(videos)


async def _get_suggestions_count() -> int:
    """Count queued suggestions awaiting review."""

    photo_files, video_files = await asyncio.gather(
        storage.list_files(BUCKET_MAIN, prefix=f"{PHOTOS_PATH}/processed_"),
        storage.list_files(BUCKET_MAIN, prefix=f"{VIDEOS_PATH}/processed_"),
    )
    objects: list[str] = photo_files + video_files
    tasks = [storage.get_submission_metadata(os.path.basename(obj)) for obj in objects]
    results = await asyncio.gather(*tasks)
    return sum(1 for meta in results if meta and meta.get("user_id"))


async def _get_posts_count() -> int:
    """Count processed posts ready for publishing."""

    photo_files, video_files = await asyncio.gather(
        storage.list_files(BUCKET_MAIN, prefix=f"{PHOTOS_PATH}/processed_"),
        storage.list_files(BUCKET_MAIN, prefix=f"{VIDEOS_PATH}/processed_"),
    )
    objects: list[str] = photo_files + video_files
    tasks = [storage.get_submission_metadata(os.path.basename(obj)) for obj in objects]
    results = await asyncio.gather(*tasks)

    count = 0
    groups: set[str] = set()
    for meta in results:
        if meta and meta.get("user_id"):
            continue
        group_id = meta.get("group_id") if meta else None
        if group_id:
            groups.add(str(group_id))
        else:
            count += 1
    return count + len(groups)


async def _get_trash_count() -> int:
    """Return the number of items currently in the trash."""

    await purge_expired_trash()
    photo_files, video_files = await asyncio.gather(
        storage.list_files(BUCKET_MAIN, prefix=f"{TRASH_PATH}/{PHOTOS_PATH}/"),
        storage.list_files(BUCKET_MAIN, prefix=f"{TRASH_PATH}/{VIDEOS_PATH}/"),
    )
    return len(photo_files) + len(video_files)


async def _get_events_payload(limit: int = EVENT_HISTORY_PAGE_SIZE) -> dict[str, object]:
    """Return normalized administrative event history."""

    clamped_limit = max(1, min(limit, EVENT_HISTORY_LIMIT))
    history = await get_event_history(limit=clamped_limit)
    events: list[dict[str, object]] = []
    for entry in history:
        items: list[dict[str, object]] = []
        raw_items = entry.get("items")
        for item in raw_items if isinstance(raw_items, list) else []:
            if not isinstance(item, dict):
                continue
            path = item.get("path")
            if not isinstance(path, str):
                continue
            items.append(
                {
                    "path": path,
                    "name": os.path.basename(path),
                    "media_type": item.get("media_type"),
                    "submitter": item.get("submitter"),
                }
            )
        events.append(
            {
                "timestamp": _parse_iso_timestamp(entry.get("timestamp")),
                "action": entry.get("action"),
                "origin": entry.get("origin"),
                "actor": entry.get("actor_username") or entry.get("actor_id"),
                "items": items,
                "extra": entry.get("extra", {}),
            }
        )
    return {"items": events, "limit": clamped_limit}


async def _get_queue_payload(
    *, page: int = 1, per_page: int = ITEMS_PER_PAGE
) -> dict[str, object]:
    """Return scheduled posts in a paginated API format."""

    count = await run_in_threadpool(get_scheduled_posts_count)
    page, total_pages, offset = _paginate(count, page, per_page)
    raw_posts = await run_in_threadpool(get_scheduled_posts, offset=offset, limit=per_page)
    items: list[dict[str, object]] = []
    for path, ts in raw_posts:
        url = await storage.get_presigned_url(path)
        if not url:
            continue
        meta = await storage.get_submission_metadata(os.path.basename(path))
        dt = datetime.datetime.fromtimestamp(ts, tz=UTC)
        items.append(
            {
                "path": path,
                "name": os.path.basename(path),
                "url": url,
                "mime_type": mimetypes.guess_type(path)[0],
                "kind": _media_kind(path),
                "caption": meta.get("caption") if meta else None,
                "source": meta.get("source") if meta else None,
                "scheduled_at": dt.isoformat(),
                "scheduled_ts": ts,
            }
        )

    return {
        "items": items,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "total_items": count,
    }


async def _get_stats_payload() -> dict[str, object]:
    """Return statistics and analytics payloads."""

    (
        daily,
        total,
        perf,
        busiest,
        source_acceptance,
        processing_histogram,
        daily_post_counts,
    ) = await asyncio.gather(
        stats.get_daily_stats(reset_if_new_day=False),
        stats.get_total_stats(),
        stats.get_performance_metrics(),
        stats.get_busiest_hour(),
        stats.get_source_acceptance(),
        stats.get_processing_histogram(),
        stats.get_daily_post_counts(),
    )
    approval_24h, approval_total, success_24h = await asyncio.gather(
        stats.get_approval_rate_24h(daily),
        stats.get_approval_rate_total(),
        stats.get_success_rate_24h(daily),
    )
    busiest_hour, busiest_count = busiest
    daily_errors = (
        int(daily["processing_errors"])
        + int(daily["storage_errors"])
        + int(daily["telegram_errors"])
    )
    total_errors = (
        total["processing_errors"] + total["storage_errors"] + total["telegram_errors"]
    )
    return {
        "daily": daily,
        "total": total,
        "performance": perf,
        "approval_24h": approval_24h,
        "approval_total": approval_total,
        "success_24h": success_24h,
        "busiest_hour": busiest_hour,
        "busiest_count": busiest_count,
        "daily_errors": daily_errors,
        "total_errors": total_errors,
        "source_acceptance": source_acceptance,
        "processing_histogram": processing_histogram,
        "daily_post_counts": daily_post_counts,
    }


async def _get_dashboard_payload() -> dict[str, object]:
    """Return dashboard summary counts and recent activity."""

    (
        suggestions_count,
        batch_count,
        posts_count,
        trash_count,
        scheduled_count,
        daily,
        events_payload,
    ) = await asyncio.gather(
        _get_suggestions_count(),
        _get_batch_count(),
        _get_posts_count(),
        _get_trash_count(),
        run_in_threadpool(get_scheduled_posts_count),
        stats.get_daily_stats(reset_if_new_day=False),
        _get_events_payload(limit=5),
    )
    next_scheduled: str | None = None
    next_items = await run_in_threadpool(get_scheduled_posts, offset=0, limit=1)
    if next_items:
        next_scheduled = datetime.datetime.fromtimestamp(
            next_items[0][1], tz=UTC
        ).isoformat()
    return {
        "suggestions_count": suggestions_count,
        "batch_count": batch_count,
        "posts_count": posts_count,
        "trash_count": trash_count,
        "scheduled_count": scheduled_count,
        "next_scheduled_at": next_scheduled,
        "daily": daily,
        "recent_events": events_payload["items"],
    }


async def _perform_action(
    request: Request,
    *,
    action: str,
    path: str | None,
    paths: Sequence[str],
    origin: str,
) -> dict[str, object]:
    """Execute one moderation action and return a JSON-friendly result."""

    all_paths = _normalize_paths(path, paths)
    if not all_paths:
        raise HTTPException(status_code=400, detail="No paths provided")

    metas = await _get_metas_for_paths(all_paths)
    if action == "push":
        if len(all_paths) > 1:
            await _push_post_group(all_paths)
        else:
            await _push_post(all_paths[0])
    elif action == "schedule":
        for item_path in all_paths:
            await _schedule_post(item_path)
    elif action == "ok":
        for item_path in all_paths:
            await _ok_post(item_path)
    elif action == "notok":
        for item_path in all_paths:
            await _notok_post(item_path)
    elif action == "remove_batch":
        for item_path in all_paths:
            await _remove_batch(item_path)
    else:
        raise HTTPException(status_code=400, detail="Unsupported action")

    await _record_event(action, origin=origin, request=request, items=metas)
    return {"status": "ok"}


async def _send_batch_now(request: Request) -> dict[str, object]:
    """Send all batch items to Telegram."""

    posts = await _gather_batch()
    if not posts:
        return {"status": "ok", "processed_groups": 0}

    event_items: list[tuple[str, dict[str, object] | None]] = []
    processed_groups = 0
    for post in posts:
        paths = [
            item["path"]
            for item in post["items"]
            if isinstance(item, dict) and isinstance(item.get("path"), str)
        ]
        event_items.extend(await _get_metas_for_paths(paths))
        try:
            await _push_post_group(paths)
            await decrement_batch_count(len(paths))
            await stats.record_batch_sent(1)
            processed_groups += 1
        except Exception:
            logger.exception("Failed to send batch group")
    if event_items:
        await _record_event(
            "batch_send",
            origin="batch",
            request=request,
            items=event_items,
        )
    return {"status": "ok", "processed_groups": processed_groups}


async def _manual_schedule_batch(
    request: Request,
    *,
    scheduled_at: str,
    path: str | None,
    paths: Sequence[str],
    origin: str,
) -> dict[str, object]:
    """Schedule batch items starting at a manually provided time."""

    all_paths = _normalize_paths(path, paths)
    if not all_paths:
        return {"status": "ok", "scheduled": 0}

    try:
        base_ts = parse_to_utc_timestamp(scheduled_at)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid_datetime") from exc

    next_ts = base_ts
    metas = await _get_metas_for_paths(all_paths)
    for item_path, _meta in metas:
        await _schedule_post_at(item_path, next_ts)
        next_ts += MANUAL_SCHEDULE_INTERVAL_SECONDS

    if metas:
        await _record_event(
            "manual_schedule",
            origin=origin,
            request=request,
            items=metas,
            extra={"scheduled_at": scheduled_at},
        )

    return {"status": "ok", "scheduled": len(all_paths)}


async def _schedule_queue_item(path: str, scheduled_at: str) -> dict[str, object]:
    """Update the scheduled time for a queued post."""

    try:
        ts = parse_to_utc_timestamp(scheduled_at)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid_datetime") from exc
    await run_in_threadpool(add_scheduled_post, ts, path)
    return {"status": "ok"}


async def _unschedule_queue_item(path: str) -> dict[str, object]:
    """Remove a post from the scheduled queue."""

    await run_in_threadpool(remove_scheduled_post, path)
    try:
        if await storage.file_exists(path, BUCKET_MAIN):
            await storage.delete_file(path, BUCKET_MAIN)
    except Exception:
        logger.exception("Failed to delete scheduled object %s after unschedule", path)
    return {"status": "ok"}


async def _restore_trash_items(path: str | None, paths: Sequence[str]) -> dict[str, object]:
    """Restore one or more trashed posts."""

    all_paths = _normalize_paths(path, paths)
    for item in all_paths:
        await restore_from_trash(item)
    return {"status": "ok", "restored": len(all_paths)}


async def _delete_trash_items(path: str | None, paths: Sequence[str]) -> dict[str, object]:
    """Permanently delete one or more trashed posts."""

    all_paths = _normalize_paths(path, paths)
    for item in all_paths:
        await delete_from_trash(item)
    return {"status": "ok", "deleted": len(all_paths)}


async def _reset_events_history(request: Request) -> dict[str, object]:
    """Clear the stored administrative event history."""

    await clear_event_history()
    logger.info("Event history reset by user %s", request.session.get("user_id"))
    return {"status": "ok"}


async def _reset_stats_data(request: Request) -> dict[str, object]:
    """Reset daily statistics and persist the change."""

    message = await stats.reset_daily_stats()
    await stats.force_save()
    await _record_event(
        "stats_reset",
        origin="stats",
        request=request,
        extra={"detail": message},
    )
    return {"status": "ok", "message": message}


async def _reset_leaderboard_data(request: Request) -> dict[str, object]:
    """Clear leaderboard statistics and persist the change."""

    message = await stats.reset_leaderboard()
    await stats.force_save()
    await _record_event(
        "leaderboard_reset",
        origin="leaderboard",
        request=request,
        extra={"detail": message},
    )
    return {"status": "ok", "message": message}


async def _push_post(path: str) -> None:
    """Publish a single media item and clean up storage."""

    file_name = os.path.basename(path)
    media_type = "photo" if _media_kind(path) == "image" else "video"
    caption = ""
    meta = await storage.get_submission_metadata(file_name)
    if meta and meta.get("user_id"):
        caption = SUGGESTION_CAPTION

    temp_path, _ = await download_from_minio(path, BUCKET_MAIN)
    try:
        size = os.path.getsize(temp_path)
    except OSError:
        size = 0

    if size == 0:
        logger.warning("Downloaded file appears empty, retrying: %s", path)
        cleanup_temp_file(temp_path)
        temp_path, _ = await download_from_minio(path, BUCKET_MAIN)
        try:
            size = os.path.getsize(temp_path)
        except OSError:
            size = 0
        if size == 0:
            logger.error("Skipping empty file after retry: %s", path)
            cleanup_temp_file(temp_path)
            return

    item = {
        "file_name": file_name,
        "media_type": media_type,
        "temp_path": temp_path,
        "meta": meta,
        "path": path,
    }
    try:
        await send_media_to_telegram(
            bot,
            TARGET_CHANNELS,
            temp_path,
            caption=caption or None,
            supports_streaming=media_type == "video",
        )
        await stats.record_post_published(len(TARGET_CHANNELS))
        await _finalize_post(item, len(TARGET_CHANNELS))
    finally:
        cleanup_temp_file(temp_path)


async def _push_post_group(paths: list[str]) -> None:
    """Publish a group of media items in a single post."""

    items, caption = await prepare_group_items(paths)
    try:
        await send_group_media(bot, TARGET_CHANNELS, items, caption)
        await stats.record_post_published(len(TARGET_CHANNELS))
        for item in items:
            await _finalize_post(item, len(TARGET_CHANNELS))
    finally:
        for item in items:
            file_obj = item["file_obj"]
            temp_path = item["temp_path"]
            file_obj.close()
            cleanup_temp_file(temp_path)


async def _finalize_post(item: dict[str, object], dest_count: int) -> None:
    """Remove temporary files and update statistics after publishing."""

    file_name = item["file_name"]
    media_type = item["media_type"]
    temp_path = item["temp_path"]
    meta = item.get("meta")
    path = item["path"]

    await storage.delete_file(path, BUCKET_MAIN)
    if meta and isinstance(meta, dict) and meta.get("hash"):
        add_approved_hash(meta.get("hash"))
    else:
        media_hash = (
            calculate_image_hash(temp_path)
            if media_type == "photo"
            else calculate_video_hash(temp_path)
        )
        if media_hash:
            add_approved_hash(media_hash)
    await stats.record_approved(
        media_type,
        filename=file_name,
        source=meta.get("source") if isinstance(meta, dict) else None,
        count=dest_count,
    )

    review = await storage.get_review_message(file_name)
    if review:
        chat_id, message_id = review
        await bot.edit_message_caption(
            chat_id=chat_id,
            message_id=message_id,
            caption=f"Post approved with media {file_name}!",
            reply_markup=None,
        )


async def _schedule_post_at(path: str, scheduled_ts: int) -> None:
    """Move a processed post into the scheduled queue at ``scheduled_ts``."""

    file_name = os.path.basename(path)
    source = CopySource(BUCKET_MAIN, path)
    new_object_name = f"{SCHEDULED_PATH}/{file_name}"
    await storage.client.copy_object(BUCKET_MAIN, new_object_name, source)
    await storage.delete_file(path, BUCKET_MAIN)
    await run_in_threadpool(add_scheduled_post, scheduled_ts, new_object_name)
    if _is_batch_item(path):
        await decrement_batch_count(1)
    review = await storage.get_review_message(file_name)
    if review:
        chat_id, message_id = review
        scheduled_dt = datetime.datetime.fromtimestamp(scheduled_ts, tz=UTC)
        await bot.edit_message_caption(
            chat_id=chat_id,
            message_id=message_id,
            caption=f"Post scheduled for {scheduled_dt.isoformat()}!",
            reply_markup=None,
        )


async def _schedule_post(path: str) -> None:
    """Move a processed post into the next available scheduled slot."""

    scheduled_posts = await run_in_threadpool(get_scheduled_posts)
    next_slot = find_next_available_slot(
        now_utc(), scheduled_posts, QUIET_START, QUIET_END
    )
    await _schedule_post_at(path, int(next_slot.timestamp()))


async def _ok_post(path: str) -> None:
    """Move a processed post into the batch queue."""

    file_name = os.path.basename(path)
    meta = await storage.get_submission_metadata(file_name)
    media_type = "photo" if _media_kind(path) == "image" else "video"
    temp_path, _ = await download_from_minio(path, BUCKET_MAIN)
    try:
        batch_name = f"batch_{file_name}"
        prefix = PHOTOS_PATH if media_type == "photo" else VIDEOS_PATH
        await storage.upload_file(
            temp_path,
            BUCKET_MAIN,
            f"{prefix}/{batch_name}",
            user_id=meta.get("user_id") if meta else None,
            chat_id=meta.get("chat_id") if meta else None,
            message_id=meta.get("message_id") if meta else None,
            group_id=meta.get("group_id") if meta else None,
            source=meta.get("source") if meta else None,
        )
        await storage.delete_file(path, BUCKET_MAIN)
        count = await increment_batch_count()
        await stats.record_added_to_batch(media_type)
    finally:
        cleanup_temp_file(temp_path)

    review = await storage.get_review_message(file_name)
    if review:
        chat_id, message_id = review
        await bot.edit_message_caption(
            chat_id=chat_id,
            message_id=message_id,
            caption=f"Post added to batch! There are {count} posts in the batch.",
            reply_markup=None,
        )


async def _notok_post(path: str) -> None:
    """Move a processed post into trash and record rejection metrics."""

    file_name = os.path.basename(path)
    media_type = "photo" if _media_kind(path) == "image" else "video"
    meta = await storage.get_submission_metadata(file_name)
    await move_to_trash(path)
    await stats.record_rejected(
        media_type,
        filename=file_name,
        source=meta.get("source") if meta else None,
    )
    review = await storage.get_review_message(file_name)
    if review:
        chat_id, message_id = review
        await bot.edit_message_caption(
            chat_id=chat_id,
            message_id=message_id,
            caption=f"Post rejected: {file_name}",
            reply_markup=None,
        )


async def _remove_batch(path: str) -> None:
    """Remove a batch item and decrement batch counters."""

    await storage.delete_file(path, BUCKET_MAIN)
    await decrement_batch_count(1)


def _serve_frontend_asset(filename: str) -> Response:
    """Serve a file from the frontend build directory."""

    asset_path = FRONTEND_DIST_DIR / filename
    if asset_path.exists():
        return FileResponse(asset_path)
    raise HTTPException(status_code=404, detail="Asset not found")


def _render_spa_shell() -> HTMLResponse:
    """Serve the compiled frontend shell or a development fallback."""

    if FRONTEND_INDEX.exists():
        html = FRONTEND_INDEX.read_text(encoding="utf-8")
        public_config = (
            "<script>"
            "window.__TELEGRAM_AUTO_POSTER__ = "
            f'{{"botUsername": "{CONFIG.bot.bot_username}", '
            f'"defaultLanguage": "{CONFIG.i18n.default}"}};'
            "</script>"
        )
        return HTMLResponse(html.replace("</head>", f"{public_config}</head>", 1))

    return HTMLResponse(
        """
        <!doctype html>
        <html lang="en">
          <head>
            <meta charset="utf-8" />
            <meta name="viewport" content="width=device-width, initial-scale=1" />
            <title>Telegram Autoposter Admin</title>
            <script>
              window.__TELEGRAM_AUTO_POSTER__ = {
                botUsername: "%s",
                defaultLanguage: "%s"
              };
            </script>
          </head>
          <body>
            <div id="root">Frontend build missing. Run the frontend build first.</div>
          </body>
        </html>
        """
        .strip()
        % (CONFIG.bot.bot_username, CONFIG.i18n.default)
    )


@app.post("/auth", response_class=JSONResponse)
async def auth_post(request: Request) -> Response:
    """Validate Telegram login payload and establish a session."""

    data = await request.json()
    if not validate_telegram_login(data, CONFIG.bot.bot_token.get_secret_value()):
        return Response(status_code=status.HTTP_400_BAD_REQUEST, content="Invalid data")
    user_id = int(data.get("id", 0))
    if user_id not in (CONFIG.bot.admin_ids or []):
        return Response(status_code=status.HTTP_403_FORBIDDEN, content="Unauthorized")
    request.session["user_id"] = user_id
    _set_session_username(request, data)
    return JSONResponse({"status": "ok"})


@app.get("/auth", response_class=HTMLResponse)
async def auth_get(request: Request) -> Response:
    """Validate Telegram login payload and establish a session."""

    data = dict(request.query_params)
    if not data:
        return Response(status_code=status.HTTP_400_BAD_REQUEST, content="Missing data")
    if not validate_telegram_login(data, CONFIG.bot.bot_token.get_secret_value()):
        return Response(status_code=status.HTTP_400_BAD_REQUEST, content="Invalid data")
    try:
        user_id = int(data.get("id", 0))
    except ValueError:
        return Response(status_code=status.HTTP_400_BAD_REQUEST, content="Invalid id")
    if user_id not in (CONFIG.bot.admin_ids or []):
        return Response(status_code=status.HTTP_403_FORBIDDEN, content="Unauthorized")
    request.session["user_id"] = user_id
    _set_session_username(request, data)
    return HTMLResponse(
        """
        <!doctype html>
        <html>
          <body>
            <script>
              if (window.opener) {
                window.opener.location.reload();
                window.close();
              } else {
                window.location.href = "/";
              }
            </script>
            Authentication complete.
          </body>
        </html>
        """.strip()
    )


@app.get("/logout")
async def logout_get(request: Request) -> Response:
    """Clear the current session and redirect to login."""

    request.session.clear()
    return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/logout")
async def logout_post(request: Request) -> Response:
    """Clear the current session for API callers."""

    request.session.clear()
    return JSONResponse({"status": "ok"})


@app.post("/language")
async def change_language(
    request: Request,
    lang: str = Form(...),
    next_url: str = Form(alias="next", default="/"),
) -> Response:
    """Persist the selected language in the session and redirect back."""

    if lang not in LANGUAGES:
        return JSONResponse(
            {"status": "error", "detail": "invalid language"},
            status_code=400,
        )
    request.session["language"] = lang
    set_locale(lang)
    if _is_background_request(request):
        return JSONResponse({"status": "ok", "language": lang})
    return RedirectResponse(
        url=_safe_redirect_target(next_url),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@app.get("/api/session")
async def api_session(request: Request) -> JSONResponse:
    """Return the authenticated admin session."""

    return JSONResponse(_session_payload(request))


@app.post("/api/session/language")
async def api_session_language(
    request: Request, payload: LanguageRequest
) -> JSONResponse:
    """Update the dashboard language."""

    if payload.language not in LANGUAGES:
        raise HTTPException(status_code=400, detail="invalid language")
    request.session["language"] = payload.language
    set_locale(payload.language)
    return JSONResponse({"status": "ok", "language": payload.language})


@app.get("/api/dashboard")
async def api_dashboard() -> JSONResponse:
    """Return dashboard counts and recent events."""

    return JSONResponse(await _get_dashboard_payload())


@app.get("/api/suggestions")
async def api_suggestions(page: int = 1) -> JSONResponse:
    """Return paginated suggestions awaiting review."""

    count = await _get_suggestions_count()
    page, total_pages, offset = _paginate(count, page, ITEMS_PER_PAGE)
    items = await _gather_posts(True, offset=offset, limit=ITEMS_PER_PAGE)
    return JSONResponse(
        {
            "items": items,
            "page": page,
            "per_page": ITEMS_PER_PAGE,
            "total_pages": total_pages,
            "total_items": count,
        }
    )


@app.get("/api/posts")
async def api_posts(page: int = 1) -> JSONResponse:
    """Return paginated processed posts awaiting publication."""

    count = await _get_posts_count()
    page, total_pages, offset = _paginate(count, page, ITEMS_PER_PAGE)
    items = await _gather_posts(False, offset=offset, limit=ITEMS_PER_PAGE)
    return JSONResponse(
        {
            "items": items,
            "page": page,
            "per_page": ITEMS_PER_PAGE,
            "total_pages": total_pages,
            "total_items": count,
        }
    )


@app.get("/api/batch")
async def api_batch(page: int = 1) -> JSONResponse:
    """Return paginated batch items."""

    count = await _get_batch_count()
    page, total_pages, offset = _paginate(count, page, ITEMS_PER_PAGE)
    items = await _gather_batch(offset=offset, limit=ITEMS_PER_PAGE)
    return JSONResponse(
        {
            "items": items,
            "page": page,
            "per_page": ITEMS_PER_PAGE,
            "total_pages": total_pages,
            "total_items": count,
        }
    )


@app.get("/api/trash")
async def api_trash(page: int = 1) -> JSONResponse:
    """Return paginated trash items."""

    count = await _get_trash_count()
    page, total_pages, offset = _paginate(count, page, ITEMS_PER_PAGE)
    items = await _gather_trash(offset=offset, limit=ITEMS_PER_PAGE)
    return JSONResponse(
        {
            "items": items,
            "page": page,
            "per_page": ITEMS_PER_PAGE,
            "total_pages": total_pages,
            "total_items": count,
        }
    )


@app.get("/api/queue")
async def api_queue(page: int = 1) -> JSONResponse:
    """Return paginated queue items."""

    return JSONResponse(await _get_queue_payload(page=page))


@app.get("/api/events")
async def api_events(limit: int = EVENT_HISTORY_PAGE_SIZE) -> JSONResponse:
    """Return recent administrative events."""

    return JSONResponse(await _get_events_payload(limit=limit))


@app.get("/api/stats")
async def api_stats() -> JSONResponse:
    """Return analytics and runtime statistics."""

    return JSONResponse(await _get_stats_payload())


@app.get("/api/leaderboard")
async def api_leaderboard() -> JSONResponse:
    """Return submission leaderboards."""

    return JSONResponse(await stats.get_leaderboard())


@app.post("/api/actions")
async def api_actions(request: Request, payload: ActionRequest) -> JSONResponse:
    """Execute one moderation action."""

    result = await _perform_action(
        request,
        action=payload.action,
        path=payload.path,
        paths=payload.paths,
        origin=payload.origin,
    )
    return JSONResponse(result)


@app.post("/api/batch/send")
async def api_batch_send(request: Request) -> JSONResponse:
    """Send all batch items immediately."""

    return JSONResponse(await _send_batch_now(request))


@app.post("/api/batch/manual-schedule")
async def api_batch_manual_schedule(
    request: Request, payload: ManualScheduleRequest
) -> JSONResponse:
    """Schedule one or more batch items manually."""

    return JSONResponse(
        await _manual_schedule_batch(
            request,
            scheduled_at=payload.scheduled_at,
            path=payload.path,
            paths=payload.paths,
            origin=payload.origin,
        )
    )


@app.post("/api/queue/schedule")
async def api_queue_schedule(payload: QueueScheduleRequest) -> JSONResponse:
    """Reschedule a queued item."""

    return JSONResponse(await _schedule_queue_item(payload.path, payload.scheduled_at))


@app.post("/api/queue/unschedule")
async def api_queue_unschedule(payload: PathListRequest) -> JSONResponse:
    """Unschedule and remove one queued item."""

    all_paths = _normalize_paths(payload.path, payload.paths)
    if len(all_paths) != 1:
        raise HTTPException(status_code=400, detail="Exactly one path is required")
    return JSONResponse(await _unschedule_queue_item(all_paths[0]))


@app.post("/api/trash/restore")
async def api_trash_restore(payload: PathListRequest) -> JSONResponse:
    """Restore trashed items."""

    return JSONResponse(await _restore_trash_items(payload.path, payload.paths))


@app.post("/api/trash/delete")
async def api_trash_delete(payload: PathListRequest) -> JSONResponse:
    """Delete trashed items permanently."""

    return JSONResponse(await _delete_trash_items(payload.path, payload.paths))


@app.post("/api/events/reset")
async def api_events_reset(
    request: Request, _payload: ResetRequest | None = None
) -> JSONResponse:
    """Clear event history."""

    return JSONResponse(await _reset_events_history(request))


@app.post("/api/stats/reset")
async def api_stats_reset(
    request: Request, _payload: ResetRequest | None = None
) -> JSONResponse:
    """Reset daily statistics."""

    return JSONResponse(await _reset_stats_data(request))


@app.post("/api/leaderboard/reset")
async def api_leaderboard_reset(
    request: Request, _payload: ResetRequest | None = None
) -> JSONResponse:
    """Reset leaderboard metrics."""

    return JSONResponse(await _reset_leaderboard_data(request))


@app.post("/action")
async def action_compat(
    request: Request,
    path: str | None = Form(None),
    paths: list[str] = Form([]),
    action: str = Form(...),
    origin: str = Form("suggestions"),
) -> Response:
    """Legacy form-based action endpoint kept for compatibility."""

    result = await _perform_action(
        request,
        action=action,
        path=path,
        paths=paths,
        origin=origin,
    )
    if _is_background_request(request):
        return JSONResponse(result)
    return RedirectResponse(url=f"/{origin}", status_code=303)


@app.post("/batch/send")
async def batch_send_compat(request: Request) -> Response:
    """Legacy batch send form endpoint."""

    result = await _send_batch_now(request)
    if _is_background_request(request):
        return JSONResponse(result)
    return RedirectResponse(url="/batch", status_code=303)


@app.post("/batch/manual_schedule")
async def batch_manual_schedule_compat(
    request: Request,
    scheduled_at: str = Form(...),
    path: str | None = Form(None),
    paths: list[str] = Form([]),
    origin: str = Form("batch"),
) -> Response:
    """Legacy manual schedule form endpoint."""

    result = await _manual_schedule_batch(
        request,
        scheduled_at=scheduled_at,
        path=path,
        paths=paths,
        origin=origin,
    )
    if _is_background_request(request):
        return JSONResponse(result)
    return RedirectResponse(url=f"/{origin}", status_code=303)


@app.post("/queue/schedule")
async def queue_schedule_compat(
    request: Request,
    path: str = Form(...),
    scheduled_at: str = Form(...),
) -> Response:
    """Legacy queue reschedule form endpoint."""

    result = await _schedule_queue_item(path, scheduled_at)
    if _is_background_request(request):
        return JSONResponse(result)
    return RedirectResponse(url="/queue", status_code=303)


@app.post("/queue/unschedule")
async def queue_unschedule_compat(request: Request, path: str = Form(...)) -> Response:
    """Legacy queue unschedule form endpoint."""

    result = await _unschedule_queue_item(path)
    if _is_background_request(request):
        return JSONResponse(result)
    return RedirectResponse(url="/queue", status_code=303)


@app.post("/trash/untrash")
async def trash_restore_compat(
    request: Request,
    path: str | None = Form(None),
    paths: list[str] = Form([]),
) -> Response:
    """Legacy trash restore form endpoint."""

    result = await _restore_trash_items(path, paths)
    if _is_background_request(request):
        return JSONResponse(result)
    return RedirectResponse(url="/trash", status_code=303)


@app.post("/trash/delete")
async def trash_delete_compat(
    request: Request,
    path: str | None = Form(None),
    paths: list[str] = Form([]),
) -> Response:
    """Legacy permanent delete form endpoint."""

    result = await _delete_trash_items(path, paths)
    if _is_background_request(request):
        return JSONResponse(result)
    return RedirectResponse(url="/trash", status_code=303)


@app.post("/events/reset")
async def reset_events_compat(
    request: Request, next_url: str = Form("/events", alias="next")
) -> Response:
    """Legacy event reset form endpoint."""

    result = await _reset_events_history(request)
    if _is_background_request(request):
        return JSONResponse(result)
    return _redirect_after_post(next_url, "/events")


@app.post("/stats/reset")
async def reset_stats_compat(
    request: Request, next_url: str = Form("/stats", alias="next")
) -> Response:
    """Legacy stats reset form endpoint."""

    result = await _reset_stats_data(request)
    if _is_background_request(request):
        return JSONResponse(result)
    return _redirect_after_post(next_url, "/stats")


@app.post("/leaderboard/reset")
async def reset_leaderboard_compat(
    request: Request, next_url: str = Form("/leaderboard", alias="next")
) -> Response:
    """Legacy leaderboard reset form endpoint."""

    result = await _reset_leaderboard_data(request)
    if _is_background_request(request):
        return JSONResponse(result)
    return _redirect_after_post(next_url, "/leaderboard")


@app.get("/favicon.ico")
async def favicon() -> Response:
    """Serve the frontend favicon."""

    return _serve_frontend_asset("favicon.ico")


@app.get("/robots.txt")
async def robots() -> Response:
    """Serve the frontend robots file."""

    return _serve_frontend_asset("robots.txt")


@app.get("/placeholder.svg")
async def placeholder() -> Response:
    """Serve the frontend placeholder asset."""

    return _serve_frontend_asset("placeholder.svg")


@app.get("/pydoc/{module:path}", response_class=HTMLResponse)
async def render_pydoc(module: str = "") -> HTMLResponse:
    """Serve pydoc-generated documentation for the given module."""

    if module and not module.startswith("telegram_auto_poster"):
        return HTMLResponse(
            content="Access to this module is restricted.",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    obj = locate(module) if module else None
    if obj is None:
        html = (
            "<html><body><h1>pydoc</h1><p>Specify a module path in the URL.</p>"
            "</body></html>"
        )
    else:
        html = pydoc.HTMLDoc().document(obj)
    return HTMLResponse(content=html)


@app.get("/login", response_class=HTMLResponse)
async def login_view() -> HTMLResponse:
    """Serve the React login route."""

    return _render_spa_shell()


@app.get("/", response_class=HTMLResponse)
async def index_view() -> HTMLResponse:
    """Serve the React dashboard shell."""

    return _render_spa_shell()


@app.get("/{full_path:path}", response_class=HTMLResponse)
async def spa_fallback(full_path: str) -> HTMLResponse:
    """Serve the React SPA for dashboard routes and client-side 404 pages."""

    normalized = full_path.strip("/")
    if not normalized:
        return _render_spa_shell()
    if normalized in SPA_RESERVED_PATHS:
        raise HTTPException(status_code=404, detail="Not found")
    if any(normalized.startswith(prefix) for prefix in SPA_RESERVED_PREFIXES):
        raise HTTPException(status_code=404, detail="Not found")
    return _render_spa_shell()
