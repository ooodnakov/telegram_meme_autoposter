"""Administrative web dashboard for reviewing and scheduling posts."""

from __future__ import annotations

import asyncio
import datetime
import mimetypes
import os
import pydoc
from pathlib import Path
from pydoc import locate
from typing import Awaitable, Callable, Mapping, Sequence
from urllib.parse import urlparse

from fastapi import FastAPI, Form, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from loguru import logger
from miniopy_async.commonconfig import CopySource
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
    decrement_batch_count,
    clear_event_history,
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
from telegram_auto_poster.utils.i18n import _, set_locale
from telegram_auto_poster.utils.scheduler import find_next_available_slot
from telegram_auto_poster.utils.stats import stats
from telegram_auto_poster.utils.storage import storage
from telegram_auto_poster.utils.trash import (
    delete_from_trash,
    move_to_trash,
    purge_expired_trash,
    restore_from_trash,
)
from telegram_auto_poster.utils.timezone import (
    FLATPICKR_FORMAT,
    UTC,
    format_display,
    now_utc,
    parse_to_utc_timestamp,
)
from telegram_auto_poster.web.auth import validate_telegram_login


class AuthMiddleware(BaseHTTPMiddleware):
    """Session-based authentication using Telegram user IDs."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:  # type: ignore[override]
        lang = CONFIG.i18n.default
        if "session" in request.scope:
            stored_lang = request.session.get("language")  # type: ignore[assignment]
            if isinstance(stored_lang, str) and stored_lang in LANGUAGES:
                lang = stored_lang
        request.state.language = lang
        set_locale(lang)
        path = request.url.path
        if path.startswith("/static") or path in {
            "/login",
            "/auth",
            "/logout",
            "/language",
        }:
            return await call_next(request)
        user_id = request.session.get("user_id")
        logger.debug(
            f"AuthMiddleware: path={path}, user_id={user_id}, admin_ids={CONFIG.bot.admin_ids}"
        )
        if user_id and user_id in (CONFIG.bot.admin_ids or []):
            return await call_next(request)
        logger.warning(
            f"AuthMiddleware: Unauthorized access to {path}, user_id={user_id}"
        )
        return Response(
            status_code=status.HTTP_401_UNAUTHORIZED, content="Unauthorized"
        )


app = FastAPI(title="Telegram Autoposter Admin")
app.add_middleware(AuthMiddleware)
app.add_middleware(
    SessionMiddleware, secret_key=CONFIG.web.session_secret.get_secret_value()
)

base_path = Path(__file__).parent
templates = Jinja2Templates(directory=str(base_path / "templates"))
templates.env.globals["_"] = _
templates.env.globals["BOT_USERNAME"] = CONFIG.bot.bot_username


LANGUAGES: dict[str, str] = {
    "ru": "Русский",
    "en": "English",
}
if CONFIG.i18n.default not in LANGUAGES:
    LANGUAGES[CONFIG.i18n.default] = CONFIG.i18n.default

LANGUAGE_CODES = list(LANGUAGES)


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
    return RedirectResponse(url=destination, status_code=303)


def _set_session_username(request: Request, data: Mapping[str, object]) -> None:
    """Store the username from ``data`` in the session when present."""

    username = data.get("username")
    if isinstance(username, str) and username:
        request.session["username"] = username


async def _get_metas_for_paths(
    paths: Sequence[str],
) -> list[tuple[str, dict[str, object] | None]]:
    """Fetch submission metadata for ``paths`` concurrently."""

    if not paths:
        return []
    tasks = [storage.get_submission_metadata(os.path.basename(path)) for path in paths]
    results = await asyncio.gather(*tasks)
    return [(path, meta) for path, meta in zip(paths, results)]


templates.env.globals["LANGUAGES"] = LANGUAGES
templates.env.globals["DEFAULT_LANGUAGE"] = CONFIG.i18n.default
templates.env.globals["cycle_language"] = _cycle_language
templates.env.globals["get_language_label"] = LANGUAGES.get
set_locale(CONFIG.i18n.default)
app.mount("/static", StaticFiles(directory=str(base_path / "static")), name="static")

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
    """Return True if ``path`` belongs to the batch queue."""

    return path.startswith(BATCH_ITEM_PREFIXES)


def _extract_submitter(meta: dict[str, object] | None) -> dict[str, object] | None:
    """Return structured submitter information for templates and logging."""

    if not meta:
        return None

    raw_user_id = meta.get("user_id")
    try:
        user_id = int(raw_user_id) if raw_user_id is not None else None
    except (TypeError, ValueError):  # pragma: no cover - defensive
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
        item: dict[str, object] = {"path": path}
        if path.startswith(f"{PHOTOS_PATH}/"):
            item["media_type"] = "photo"
        elif path.startswith(f"{VIDEOS_PATH}/"):
            item["media_type"] = "video"
        submitter = _extract_submitter(meta)
        if submitter:
            item["submitter"] = submitter
        event_items.append(item)
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
) -> list[dict]:
    """Collect processed posts for rendering in the dashboard."""
    objects = await _list_media("processed", offset=offset, limit=limit)
    posts: list[dict] = []
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
        mime, _ = mimetypes.guess_type(obj)
        is_video = obj.startswith(f"{VIDEOS_PATH}/") or (mime or "").startswith(
            "video/"
        )
        is_image = obj.startswith(f"{PHOTOS_PATH}/") or (mime or "").startswith(
            "image/"
        )
        item = {
            "path": obj,
            "url": url,
            "is_video": is_video,
            "is_image": is_image,
        }
        submitter = _extract_submitter(meta)
        group_id = meta.get("group_id") if meta else None
        if group_id:
            bucket = grouped.setdefault(group_id, {"items": [], "meta": {}})
            bucket["items"].append(item)
            if submitter and not bucket["meta"].get("submitter"):
                bucket["meta"]["submitter"] = submitter
        else:
            post_entry = {"items": [item]}
            if submitter:
                post_entry["meta"] = {"submitter": submitter}
            posts.append(post_entry)
    for bucket in grouped.values():
        entry = {"items": bucket["items"]}
        if bucket.get("meta"):
            entry["meta"] = bucket["meta"]
        posts.append(entry)
    return posts


async def _gather_batch(*, offset: int = 0, limit: int | None = None) -> list[dict]:
    """Collect batch items for display or processing."""
    objects = await _list_media("batch", offset=offset, limit=limit)
    posts: list[dict] = []
    grouped: dict[str, list[dict]] = {}
    for obj in objects:
        file_name = os.path.basename(obj)
        meta = await storage.get_submission_metadata(file_name)
        url = await storage.get_presigned_url(obj)
        if not url:
            continue
        mime, _ = mimetypes.guess_type(obj)
        is_video = obj.startswith(f"{VIDEOS_PATH}/") or (mime or "").startswith(
            "video/"
        )
        is_image = obj.startswith(f"{PHOTOS_PATH}/") or (mime or "").startswith(
            "image/"
        )
        item = {"path": obj, "url": url, "is_video": is_video, "is_image": is_image}
        group_id = meta.get("group_id") if meta else None
        if group_id:
            grouped.setdefault(group_id, []).append(item)
        else:
            posts.append({"items": [item]})
    posts.extend({"items": items} for items in grouped.values())
    return posts


async def _gather_trash(*, offset: int = 0, limit: int | None = None) -> list[dict]:
    """Collect trashed posts for display."""

    await purge_expired_trash()
    objects = await _list_trash_media(offset=offset, limit=limit)
    posts: list[dict] = []
    grouped: dict[str, dict] = {}
    for obj in objects:
        file_name = os.path.basename(obj)
        meta = await storage.get_submission_metadata(file_name)
        url = await storage.get_presigned_url(obj)
        if not url:
            continue
        mime, _ = mimetypes.guess_type(obj)
        is_video = obj.startswith(f"{TRASH_PATH}/{VIDEOS_PATH}/") or (
            mime or ""
        ).startswith("video/")
        is_image = obj.startswith(f"{TRASH_PATH}/{PHOTOS_PATH}/") or (
            mime or ""
        ).startswith("image/")
        trashed_at_raw = meta.get("trashed_at") if meta else None
        expires_at_raw = meta.get("trash_expires_at") if meta else None
        trashed_at = (
            datetime.datetime.fromisoformat(str(trashed_at_raw))
            if trashed_at_raw
            else None
        )
        expires_at = (
            datetime.datetime.fromisoformat(str(expires_at_raw))
            if expires_at_raw
            else None
        )
        trashed_display = format_display(trashed_at) if trashed_at else None
        expires_display = format_display(expires_at) if expires_at else None
        item = {
            "path": obj,
            "url": url,
            "is_video": is_video,
            "is_image": is_image,
        }
        group_id = meta.get("group_id") if meta else None
        if group_id:
            entry = grouped.setdefault(
                group_id,
                {
                    "items": [],
                    "trashed_at": trashed_display,
                    "expires_at": expires_display,
                },
            )
            entry["items"].append(item)
            if trashed_display and not entry.get("trashed_at"):
                entry["trashed_at"] = trashed_display
            if expires_display and not entry.get("expires_at"):
                entry["expires_at"] = expires_display
        else:
            posts.append(
                {
                    "items": [item],
                    "trashed_at": trashed_display,
                    "expires_at": expires_display,
                }
            )
    posts.extend(grouped.values())
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

    count = 0
    for meta in results:
        if meta and meta.get("user_id"):
            count += 1

    return count


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
            groups.add(group_id)
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


async def _render_posts_page(
    request: Request,
    *,
    only_suggestions: bool,
    origin: str,
    alt_text: str,
    empty_message: str,
    template_name: str,
    page: int = 1,
    per_page: int = ITEMS_PER_PAGE,
) -> HTMLResponse:
    """Render a page listing either suggestions or processed posts."""
    count = (
        await _get_suggestions_count() if only_suggestions else await _get_posts_count()
    )
    page, total_pages, offset = _paginate(count, page, per_page)
    posts = await _gather_posts(only_suggestions, offset=offset, limit=per_page)
    context = {
        "request": request,
        "posts": posts,
        "origin": origin,
        "alt_text": alt_text,
        "empty_message": empty_message,
        "page": page,
        "total_pages": total_pages,
    }
    template = (
        "_post_grid.html"
        if request.headers.get("HX-Request", "").lower() == "true"
        else template_name
    )
    return templates.TemplateResponse(template, context)


@app.get("/login", response_class=HTMLResponse)
async def login_view(request: Request) -> HTMLResponse:
    """Render the Telegram login page."""

    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/auth", response_class=JSONResponse)
async def auth_post(request: Request) -> Response:
    """Validate Telegram login payload (POST JSON) and establish a session."""

    data = await request.json()
    if not validate_telegram_login(data, CONFIG.bot.bot_token.get_secret_value()):
        logger.warning("Auth POST: Invalid data")
        return Response(status_code=status.HTTP_400_BAD_REQUEST, content="Invalid data")
    user_id = int(data.get("id", 0))
    logger.info(f"Auth POST: user_id={user_id}, admin_ids={CONFIG.bot.admin_ids}")
    if user_id not in (CONFIG.bot.admin_ids or []):
        logger.warning(f"Auth POST: user_id {user_id} not in admin_ids")
        return Response(status_code=status.HTTP_403_FORBIDDEN, content="Unauthorized")
    request.session["user_id"] = user_id
    _set_session_username(request, data)
    logger.info(f"Auth POST: Session set for user_id={user_id}")
    return JSONResponse({"status": "ok"})


@app.get("/auth", response_class=HTMLResponse)
async def auth_get(request: Request) -> Response:
    """Validate Telegram login payload (GET query) and establish a session.

    This supports the Telegram widget "data-auth-url" flow where Telegram opens
    a popup and appends user data as query parameters. On success the popup
    closes and the opener page is reloaded.
    """

    data = dict(request.query_params)
    if not data:
        logger.warning("Auth GET: Missing data")
        return Response(status_code=status.HTTP_400_BAD_REQUEST, content="Missing data")
    if not validate_telegram_login(data, CONFIG.bot.bot_token.get_secret_value()):
        logger.warning("Auth GET: Invalid data")
        return Response(status_code=status.HTTP_400_BAD_REQUEST, content="Invalid data")
    try:
        user_id = int(data.get("id", 0))
    except ValueError:
        logger.warning("Auth GET: Invalid id")
        return Response(status_code=status.HTTP_400_BAD_REQUEST, content="Invalid id")
    logger.info(f"Auth GET: user_id={user_id}, admin_ids={CONFIG.bot.admin_ids}")
    if user_id not in (CONFIG.bot.admin_ids or []):
        logger.warning(f"Auth GET: user_id {user_id} not in admin_ids")
        return Response(status_code=status.HTTP_403_FORBIDDEN, content="Unauthorized")
    request.session["user_id"] = user_id
    _set_session_username(request, data)
    logger.info(f"Auth GET: Session set for user_id={user_id}")

    # Return a success page that refreshes the opener and closes the popup
    return templates.TemplateResponse("auth_success.html", {"request": request})


@app.get("/logout")
async def logout(request: Request) -> Response:
    """Clear the current session."""

    request.session.clear()
    return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/language")
async def change_language(
    request: Request,
    lang: str = Form(...),
    next_url: str = Form(alias="next", default="/"),
) -> Response:
    """Persist the selected language in the session and redirect back."""

    if lang not in LANGUAGES:
        return JSONResponse(
            {"status": "error", "detail": "invalid language"}, status_code=400
        )
    request.session["language"] = lang
    set_locale(lang)
    target = _safe_redirect_target(next_url)
    if request.headers.get("X-Background-Request", "").lower() == "true":
        return JSONResponse({"status": "ok", "language": lang})
    return RedirectResponse(url=target, status_code=status.HTTP_303_SEE_OTHER)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    """Display the dashboard overview with counts and daily stats."""
    (
        suggestions_count,
        batch_count,
        posts_count,
        trash_count,
        scheduled_posts_raw,
        daily,
    ) = await asyncio.gather(
        _get_suggestions_count(),
        _get_batch_count(),
        _get_posts_count(),
        _get_trash_count(),
        run_in_threadpool(get_scheduled_posts),
        stats.get_daily_stats(reset_if_new_day=False),
    )
    context = {
        "request": request,
        "suggestions_count": suggestions_count,
        "batch_count": batch_count,
        "posts_count": posts_count,
        "trash_count": trash_count,
        "scheduled_count": len(scheduled_posts_raw),
        "daily": daily,
    }
    return templates.TemplateResponse("index.html", context)


@app.get(
    "/suggestions",
    response_class=HTMLResponse,
)
async def suggestions_view(request: Request, page: int = 1) -> HTMLResponse:
    """Render the suggestions review page."""
    return await _render_posts_page(
        request,
        only_suggestions=True,
        origin="suggestions",
        alt_text="suggestion",
        empty_message="No suggestions pending.",
        template_name="suggestions.html",
        page=page,
    )


@app.get(
    "/posts",
    response_class=HTMLResponse,
)
async def posts_view(request: Request, page: int = 1) -> HTMLResponse:
    """Render the processed posts page."""
    return await _render_posts_page(
        request,
        only_suggestions=False,
        origin="posts",
        alt_text="post",
        empty_message="No posts pending.",
        template_name="posts.html",
        page=page,
    )


@app.get(
    "/events",
    response_class=HTMLResponse,
)
async def events_view(
    request: Request, limit: int = EVENT_HISTORY_PAGE_SIZE
) -> HTMLResponse:
    """Render the recent administrative event history."""

    clamped_limit = max(1, min(limit, EVENT_HISTORY_LIMIT))
    history = await get_event_history(limit=clamped_limit)
    events: list[dict[str, object]] = []
    for entry in history:
        timestamp = entry.get("timestamp")
        display_timestamp = timestamp
        if isinstance(timestamp, str):
            try:
                dt = datetime.datetime.fromisoformat(timestamp)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=UTC)
                display_timestamp = format_display(dt)
            except ValueError:  # pragma: no cover - defensive
                display_timestamp = timestamp
        actor_label = entry.get("actor_username") or entry.get("actor_id")
        items: list[dict[str, object]] = []
        raw_items = entry.get("items")
        for item in raw_items if isinstance(raw_items, list) else []:
            if not isinstance(item, dict):
                continue
            path = item.get("path")
            items.append(
                {
                    "path": path,
                    "basename": os.path.basename(path)
                    if isinstance(path, str)
                    else path,
                    "media_type": item.get("media_type"),
                    "submitter": item.get("submitter"),
                }
            )
        events.append(
            {
                "timestamp": display_timestamp,
                "action": entry.get("action"),
                "origin": entry.get("origin"),
                "actor": actor_label,
                "items": items,
                "extra": entry.get("extra", {}),
            }
        )

    context = {"request": request, "events": events, "limit": clamped_limit}
    return templates.TemplateResponse("events.html", context)


@app.post("/events/reset")
async def reset_events_history(
    request: Request, next: str = Form("/events")
) -> Response:
    """Clear the stored administrative event history."""

    await clear_event_history()
    logger.info(
        "Event history reset by user %s",
        request.session.get("user_id"),
    )
    if request.headers.get("X-Background-Request", "").lower() == "true":
        return JSONResponse({"status": "ok"})
    return _redirect_after_post(next, "/events")


@app.get(
    "/trash",
    response_class=HTMLResponse,
)
async def trash_view(request: Request, page: int = 1) -> HTMLResponse:
    """Render the trashed posts page."""

    count = await _get_trash_count()
    page, total_pages, offset = _paginate(count, page, ITEMS_PER_PAGE)
    posts = await _gather_trash(offset=offset, limit=ITEMS_PER_PAGE)
    context = {
        "request": request,
        "posts": posts,
        "page": page,
        "total_pages": total_pages,
        "empty_message": "Trash is empty.",
    }
    template = (
        "_trash_grid.html"
        if request.headers.get("HX-Request", "").lower() == "true"
        else "trash.html"
    )
    return templates.TemplateResponse(template, context)


@app.post("/trash/untrash")
async def trash_untrash(
    request: Request,
    path: str | None = Form(None),
    paths: list[str] = Form([]),
) -> Response:
    """Restore one or more trashed posts."""

    all_paths = paths or []
    if path:
        all_paths.append(path)
    for item in all_paths:
        await restore_from_trash(item)

    if request.headers.get("X-Background-Request", "").lower() == "true":
        return JSONResponse({"status": "ok"})
    return RedirectResponse(url="/trash", status_code=303)


@app.post("/trash/delete")
async def trash_delete(
    request: Request,
    path: str | None = Form(None),
    paths: list[str] = Form([]),
) -> Response:
    """Permanently delete trashed posts."""

    all_paths = paths or []
    if path:
        all_paths.append(path)
    for item in all_paths:
        await delete_from_trash(item)

    if request.headers.get("X-Background-Request", "").lower() == "true":
        return JSONResponse({"status": "ok"})
    return RedirectResponse(url="/trash", status_code=303)


@app.get(
    "/batch",
    response_class=HTMLResponse,
)
async def batch_view(request: Request, page: int = 1) -> HTMLResponse:
    """Render the batch management page."""
    count = await _get_batch_count()
    page, total_pages, offset = _paginate(count, page, ITEMS_PER_PAGE)
    posts_page = await _gather_batch(offset=offset, limit=ITEMS_PER_PAGE)
    context = {
        "request": request,
        "posts": posts_page,
        "origin": "batch",
        "alt_text": "batch item",
        "empty_message": "Batch is empty.",
        "page": page,
        "total_pages": total_pages,
        "datetime_format_js": FLATPICKR_FORMAT,
    }
    template = (
        "_batch_grid.html"
        if request.headers.get("HX-Request", "").lower() == "true"
        else "batch.html"
    )
    return templates.TemplateResponse(template, context)


@app.post("/batch/send")
async def send_batch(request: Request) -> Response:
    """Send all items currently in the batch to the target channel."""
    posts = await _gather_batch()
    if not posts:
        return RedirectResponse(url="/batch", status_code=303)
    event_items: list[tuple[str, dict[str, object] | None]] = []
    for post in posts:
        paths = [item["path"] for item in post["items"]]
        event_items.extend(await _get_metas_for_paths(paths))
        try:
            await _push_post_group(paths)
            await decrement_batch_count(len(paths))
            await stats.record_batch_sent(1)
        except Exception:
            # Error should be logged in _push_post_group. Here we prevent incorrect state changes.
            # A user-facing error message would be a good addition here.
            pass
    if event_items:
        await _record_event(
            "batch_send",
            origin="batch",
            request=request,
            items=event_items,
        )
    return RedirectResponse(url="/batch", status_code=303)


@app.post("/batch/manual_schedule")
async def manual_schedule_batch(
    request: Request,
    scheduled_at: str = Form(...),
    path: str | None = Form(None),
    paths: list[str] = Form([]),
    origin: str = Form("batch"),
) -> Response:
    """Schedule batch items starting at a manually provided time."""
    all_paths: list[str] = list(paths)
    if path:
        all_paths.append(path)

    if not all_paths:
        if request.headers.get("X-Background-Request", "").lower() == "true":
            return JSONResponse({"status": "ok"})
        return RedirectResponse(url=f"/{origin}", status_code=303)

    try:
        base_ts = parse_to_utc_timestamp(scheduled_at)
    except ValueError:
        logger.warning(f"Invalid manual schedule time provided: {scheduled_at}")
        if request.headers.get("X-Background-Request", "").lower() == "true":
            return JSONResponse({"status": "error", "detail": "invalid_datetime"})
        return RedirectResponse(url=f"/{origin}", status_code=303)

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

    if request.headers.get("X-Background-Request", "").lower() == "true":
        return JSONResponse({"status": "ok"})

    return RedirectResponse(url=f"/{origin}", status_code=303)


@app.post("/action")
async def handle_action(
    request: Request,
    path: str | None = Form(None),
    paths: list[str] = Form([]),
    action: str = Form(...),
    origin: str = Form("suggestions"),
) -> Response:
    """Handle form actions for approving, rejecting, or moving posts."""
    all_paths = paths or []
    if path:
        all_paths.append(path)
    metas = await _get_metas_for_paths(all_paths)
    if action == "push":
        if len(all_paths) > 1:
            await _push_post_group(all_paths)
        else:
            await _push_post(all_paths[0])
    elif action == "schedule":
        for p in all_paths:
            await _schedule_post(p)
    elif action == "ok":
        for p in all_paths:
            await _ok_post(p)
    elif action == "notok":
        for p in all_paths:
            await _notok_post(p)
    elif action == "remove_batch":
        for p in all_paths:
            await _remove_batch(p)
    if metas:
        await _record_event(
            action,
            origin=origin,
            request=request,
            items=metas,
        )
    # If this is a background (AJAX) request, return JSON instead of redirect
    if request.headers.get("X-Background-Request", "").lower() == "true":
        return JSONResponse({"status": "ok"})

    return RedirectResponse(url=f"/{origin}", status_code=303)


async def _push_post(path: str) -> None:
    """Publish a single media item and clean up storage."""
    file_name = os.path.basename(path)
    media_type = "photo" if path.startswith(f"{PHOTOS_PATH}/") else "video"
    caption = ""
    meta = await storage.get_submission_metadata(file_name)
    if meta and meta.get("user_id"):
        caption = SUGGESTION_CAPTION

    temp_path, _ = await download_from_minio(path, BUCKET_MAIN)
    # Ensure downloaded file is non-empty; retry once if empty
    try:
        size = os.path.getsize(temp_path)
    except OSError:
        size = 0
    if size == 0:
        logger.warning(f"Downloaded file appears empty, retrying: {path}")
        cleanup_temp_file(temp_path)
        temp_path, _ = await download_from_minio(path, BUCKET_MAIN)
        try:
            size = os.path.getsize(temp_path)
        except OSError:
            size = 0
        if size == 0:
            logger.error(f"Skipping empty file after retry: {path}")
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
        for it in items:
            await _finalize_post(it, len(TARGET_CHANNELS))
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
    if meta and meta.get("hash"):
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
        source=meta.get("source") if meta else None,
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
            caption=f"Post scheduled for {format_display(scheduled_dt)}!",
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
    file_name = os.path.basename(path)
    meta = await storage.get_submission_metadata(file_name)
    media_type = "photo" if path.startswith(f"{PHOTOS_PATH}/") else "video"
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
    file_name = os.path.basename(path)
    media_type = "photo" if path.startswith(f"{PHOTOS_PATH}/") else "video"
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
    await storage.delete_file(path, BUCKET_MAIN)
    await decrement_batch_count(1)


@app.get(
    "/queue",
    response_class=HTMLResponse,
)
async def queue(request: Request, page: int = 1) -> HTMLResponse:
    """Show scheduled posts awaiting publication."""
    count = await run_in_threadpool(get_scheduled_posts_count)
    page, total_pages, offset = _paginate(count, page, ITEMS_PER_PAGE)
    raw_posts = await run_in_threadpool(
        get_scheduled_posts, offset=offset, limit=ITEMS_PER_PAGE
    )
    posts: list[dict] = []
    for path, ts in raw_posts:
        url = await storage.get_presigned_url(path)
        if not url:
            continue

        # Derive media information for proper embedding in template
        mime, _ = mimetypes.guess_type(path)
        is_video = path.startswith("videos/") or (mime or "").startswith("video/")
        is_image = path.startswith("photos/") or (mime or "").startswith("image/")

        meta = await storage.get_submission_metadata(path)
        dt = datetime.datetime.fromtimestamp(ts, tz=UTC)
        display = format_display(dt)

        posts.append(
            {
                "path": path,
                "ts": display,
                "dt_input": display,
                "url": url,
                "mime": mime or ("video/mp4" if is_video else None),
                "is_video": is_video,
                "is_image": is_image,
                "caption": meta.get("caption") if meta else None,
            }
        )

    context = {
        "request": request,
        "posts": posts,
        "page": page,
        "total_pages": total_pages,
        "datetime_format_js": FLATPICKR_FORMAT,
    }
    return templates.TemplateResponse("queue.html", context)


@app.post("/queue/schedule")
async def reschedule(
    request: Request, path: str = Form(...), scheduled_at: str = Form(...)
) -> Response:
    """Update the scheduled time for a queued post."""
    try:
        ts = parse_to_utc_timestamp(scheduled_at)
    except ValueError:
        return JSONResponse(
            {"status": "error", "detail": "invalid datetime"}, status_code=400
        )
    await run_in_threadpool(add_scheduled_post, ts, path)
    if request.headers.get("X-Background-Request", "").lower() == "true":
        return JSONResponse({"status": "ok"})
    return RedirectResponse(url="/queue", status_code=303)


@app.post("/queue/unschedule")
async def unschedule(request: Request, path: str = Form(...)) -> Response:
    """Remove a post from the scheduled queue."""
    await run_in_threadpool(remove_scheduled_post, path)
    try:
        if await storage.file_exists(path, BUCKET_MAIN):
            await storage.delete_file(path, BUCKET_MAIN)
    except Exception:
        # Best-effort delete; still redirect to keep UX smooth
        pass
    # Background (AJAX) flow returns JSON instead of redirect
    if request.headers.get("X-Background-Request", "").lower() == "true":
        return JSONResponse({"status": "ok"})

    return RedirectResponse(url="/queue", status_code=303)


@app.get(
    "/stats",
    response_class=HTMLResponse,
)
async def stats_view(request: Request) -> HTMLResponse:
    """Render statistics about bot usage and performance."""
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
    busiest_hour, busiest_count = busiest
    approval_24h, approval_total, success_24h = await asyncio.gather(
        stats.get_approval_rate_24h(daily),
        stats.get_approval_rate_total(),
        stats.get_success_rate_24h(daily),
    )
    daily_errors = (
        daily["processing_errors"] + daily["storage_errors"] + daily["telegram_errors"]
    )
    total_errors = (
        total["processing_errors"] + total["storage_errors"] + total["telegram_errors"]
    )
    context = {
        "request": request,
        "daily": daily,
        "total": total,
        "perf": perf,
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
    return templates.TemplateResponse("stats.html", context)


@app.post("/stats/reset")
async def reset_stats(request: Request, next: str = Form("/stats")) -> Response:
    """Reset daily statistics and persist the change."""

    message = await stats.reset_daily_stats()
    await stats.force_save()
    await _record_event(
        "stats_reset",
        origin="stats",
        request=request,
        extra={"detail": message},
    )
    if request.headers.get("X-Background-Request", "").lower() == "true":
        return JSONResponse({"status": "ok", "message": message})
    return _redirect_after_post(next, "/stats")


@app.get("/leaderboard", response_class=HTMLResponse)
async def leaderboard(request: Request) -> HTMLResponse:
    """Display the leaderboard of top submitters."""
    data = await stats.get_leaderboard()
    context = {"request": request, **data}
    return templates.TemplateResponse("leaderboard.html", context)


@app.post("/leaderboard/reset")
async def reset_leaderboard_view(
    request: Request, next: str = Form("/leaderboard")
) -> Response:
    """Clear leaderboard statistics and persist the change."""

    message = await stats.reset_leaderboard()
    await stats.force_save()
    await _record_event(
        "leaderboard_reset",
        origin="leaderboard",
        request=request,
        extra={"detail": message},
    )
    if request.headers.get("X-Background-Request", "").lower() == "true":
        return JSONResponse({"status": "ok", "message": message})
    return _redirect_after_post(next, "/leaderboard")


@app.get("/pydoc/{module:path}", response_class=HTMLResponse)
async def render_pydoc(module: str = "") -> HTMLResponse:
    """Serve pydoc-generated documentation for the given module.

    Args:
        module: Dotted path of the module or object to document.

    Returns:
        HTML page containing the generated documentation or a landing page if
        the module cannot be located.

    """
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
