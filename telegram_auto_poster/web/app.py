from __future__ import annotations

import asyncio
import datetime
import mimetypes
import os
import secrets
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from loguru import logger
from miniopy_async.commonconfig import CopySource
from telegram import Bot, InputMediaPhoto, InputMediaVideo

from telegram_auto_poster.config import (
    BUCKET_MAIN,
    CONFIG,
    PHOTOS_PATH,
    SCHEDULED_PATH,
    VIDEOS_PATH,
)
from telegram_auto_poster.utils.db import (
    add_scheduled_post,
    decrement_batch_count,
    get_scheduled_posts,
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
    send_media_to_telegram,
)
from telegram_auto_poster.utils.scheduler import find_next_available_slot
from telegram_auto_poster.utils.stats import stats
from telegram_auto_poster.utils.storage import storage
from telegram_auto_poster.utils.timezone import format_display, now_utc

app = FastAPI(title="Telegram Autoposter Admin")

base_path = Path(__file__).parent
templates = Jinja2Templates(directory=str(base_path / "templates"))
app.mount("/static", StaticFiles(directory=str(base_path / "static")), name="static")

bot = Bot(token=CONFIG.bot.bot_token.get_secret_value())
TARGET_CHANNEL = CONFIG.telegram.target_channel
QUIET_START = CONFIG.schedule.quiet_hours_start
QUIET_END = CONFIG.schedule.quiet_hours_end


def require_access_key(request: Request) -> None:
    access_key = CONFIG.web.access_key
    if access_key is None:
        return
    provided = request.query_params.get("key")
    expected = access_key.get_secret_value()
    if not (provided and secrets.compare_digest(provided, expected)):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access key"
        )


async def _gather_posts(only_suggestions: bool) -> list[dict]:
    objects: list[str] = []
    objects += await storage.list_files(BUCKET_MAIN, prefix=f"{PHOTOS_PATH}/processed_")
    objects += await storage.list_files(BUCKET_MAIN, prefix=f"{VIDEOS_PATH}/processed_")
    posts: list[dict] = []
    grouped: dict[str, list[dict]] = {}
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
        group_id = meta.get("group_id") if meta else None
        if group_id:
            grouped.setdefault(group_id, []).append(item)
        else:
            posts.append({"items": [item]})
    posts.extend({"items": items} for items in grouped.values())
    return posts


async def _gather_batch() -> list[dict]:
    objects: list[str] = []
    objects += await storage.list_files(BUCKET_MAIN, prefix=f"{PHOTOS_PATH}/batch_")
    objects += await storage.list_files(BUCKET_MAIN, prefix=f"{VIDEOS_PATH}/batch_")
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


async def _get_batch_count() -> int:
    photos = await storage.list_files(BUCKET_MAIN, prefix=f"{PHOTOS_PATH}/batch_")
    videos = await storage.list_files(BUCKET_MAIN, prefix=f"{VIDEOS_PATH}/batch_")
    return len(photos) + len(videos)


async def _get_suggestions_count() -> int:
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


async def _render_posts_page(
    request: Request,
    *,
    only_suggestions: bool,
    origin: str,
    alt_text: str,
    empty_message: str,
    template_name: str,
) -> HTMLResponse:
    posts = await _gather_posts(only_suggestions)
    context = {
        "request": request,
        "posts": posts,
        "origin": origin,
        "alt_text": alt_text,
        "empty_message": empty_message,
    }
    template = (
        "_post_grid.html"
        if request.headers.get("HX-Request", "").lower() == "true"
        else template_name
    )
    return templates.TemplateResponse(template, context)


@app.get("/", response_class=HTMLResponse, dependencies=[Depends(require_access_key)])
async def index(request: Request) -> HTMLResponse:
    (
        suggestions_count,
        batch_count,
        posts_count,
        scheduled_posts_raw,
        daily,
    ) = await asyncio.gather(
        _get_suggestions_count(),
        _get_batch_count(),
        _get_posts_count(),
        run_in_threadpool(get_scheduled_posts),
        stats.get_daily_stats(reset_if_new_day=False),
    )
    context = {
        "request": request,
        "suggestions_count": suggestions_count,
        "batch_count": batch_count,
        "posts_count": posts_count,
        "scheduled_count": len(scheduled_posts_raw),
        "daily": daily,
    }
    return templates.TemplateResponse("index.html", context)


@app.get(
    "/suggestions",
    response_class=HTMLResponse,
    dependencies=[Depends(require_access_key)],
)
async def suggestions_view(request: Request) -> HTMLResponse:
    return await _render_posts_page(
        request,
        only_suggestions=True,
        origin="suggestions",
        alt_text="suggestion",
        empty_message="No suggestions pending.",
        template_name="suggestions.html",
    )


@app.get(
    "/posts",
    response_class=HTMLResponse,
    dependencies=[Depends(require_access_key)],
)
async def posts_view(request: Request) -> HTMLResponse:
    return await _render_posts_page(
        request,
        only_suggestions=False,
        origin="posts",
        alt_text="post",
        empty_message="No posts pending.",
        template_name="posts.html",
    )


@app.get(
    "/batch",
    response_class=HTMLResponse,
    dependencies=[Depends(require_access_key)],
)
async def batch_view(request: Request) -> HTMLResponse:
    posts = await _gather_batch()
    return templates.TemplateResponse(
        "batch.html", {"request": request, "posts": posts}
    )


@app.post("/batch/send", dependencies=[Depends(require_access_key)])
async def send_batch(key: str | None = Form(None)) -> Response:
    posts = await _gather_batch()
    if not posts:
        suffix = f"?key={key}" if key else ""
        return RedirectResponse(url=f"/batch{suffix}", status_code=303)
    for post in posts:
        paths = [item["path"] for item in post["items"]]
        try:
            await _push_post_group(paths)
            await decrement_batch_count(len(paths))
            await stats.record_batch_sent(1)
        except Exception:
            # Error should be logged in _push_post_group. Here we prevent incorrect state changes.
            # A user-facing error message would be a good addition here.
            pass
    suffix = f"?key={key}" if key else ""
    return RedirectResponse(url=f"/batch{suffix}", status_code=303)


@app.post("/action")
async def handle_action(
    request: Request,
    path: str | None = Form(None),
    paths: list[str] = Form([]),
    action: str = Form(...),
    origin: str = Form("suggestions"),
    key: str | None = Form(None),
) -> Response:
    all_paths = paths or []
    if path:
        all_paths.append(path)
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
    # If this is a background (AJAX) request, return JSON instead of redirect
    if request.headers.get("X-Background-Request", "").lower() == "true":
        return JSONResponse({"status": "ok"})

    suffix = f"?key={key}" if key else ""
    return RedirectResponse(url=f"/{origin}{suffix}", status_code=303)


async def _push_post(path: str) -> None:
    file_name = os.path.basename(path)
    media_type = "photo" if path.startswith(f"{PHOTOS_PATH}/") else "video"
    caption = ""
    meta = await storage.get_submission_metadata(file_name)
    if meta and meta.get("user_id"):
        caption = "Пост из предложки @ooodnakov_memes_suggest_bot"

    temp_path, _ = await download_from_minio(path, BUCKET_MAIN)
    # Ensure downloaded file is non-empty; retry once if empty
    try:
        size = os.path.getsize(temp_path)
    except Exception:
        size = 0
    if size == 0:
        logger.warning(f"Downloaded file appears empty, retrying: {path}")
        cleanup_temp_file(temp_path)
        temp_path, _ = await download_from_minio(path, BUCKET_MAIN)
        try:
            size = os.path.getsize(temp_path)
        except Exception:
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
            TARGET_CHANNEL,
            temp_path,
            caption=caption or None,
            supports_streaming=media_type == "video",
        )
        await _finalize_post(item)
    finally:
        cleanup_temp_file(temp_path)


async def _push_post_group(paths: list[str]) -> None:
    items: list[dict[str, object]] = []

    for path in paths:
        file_name = os.path.basename(path)
        media_type = "photo" if path.startswith(f"{PHOTOS_PATH}/") else "video"
        caption = ""
        meta = await storage.get_submission_metadata(file_name)
        if meta and meta.get("user_id"):
            caption = "Пост из предложки @ooodnakov_memes_suggest_bot"

        temp_path, _ = await download_from_minio(path, BUCKET_MAIN)
        # Ensure downloaded file is non-empty; retry once if empty
        try:
            size = os.path.getsize(temp_path)
        except Exception:
            size = 0
        if size == 0:
            logger.warning(f"Downloaded file appears empty, retrying: {path}")
            cleanup_temp_file(temp_path)
            temp_path, _ = await download_from_minio(path, BUCKET_MAIN)
            try:
                size = os.path.getsize(temp_path)
            except Exception:
                size = 0
            if size == 0:
                logger.error(f"Skipping empty file after retry: {path}")
                cleanup_temp_file(temp_path)
                continue
        file_obj = open(temp_path, "rb")
        items.append(
            {
                "file_name": file_name,
                "media_type": media_type,
                "temp_path": temp_path,
                "file_obj": file_obj,
                "meta": meta,
                "path": path,
                "caption": caption,
            }
        )
    try:
        if len(items) >= 2:
            for i in range(0, len(items), 10):
                chunk = items[i : i + 10]
                # Build InputMedia with caption at construction for the first item only
                media_group = []
                for idx, it in enumerate(chunk):
                    is_first = i == 0 and idx == 0 and bool(it["caption"])  # type: ignore[index]
                    fh = it["file_obj"]  # type: ignore[index]
                    if it["media_type"] == "video":  # type: ignore[index]
                        media = InputMediaVideo(
                            fh,
                            supports_streaming=True,
                            caption=it["caption"] if is_first else None,  # type: ignore[index]
                        )
                    else:
                        media = InputMediaPhoto(
                            fh,
                            caption=it["caption"] if is_first else None,  # type: ignore[index]
                        )
                    media_group.append(media)
                try:
                    await bot.send_media_group(TARGET_CHANNEL, media_group)
                    for it in chunk:
                        await _finalize_post(it)
                except Exception:
                    logger.exception("Failed to send media group")
                    raise
        elif len(items) == 1:
            # Single fallback
            it = items[0]
            try:
                await send_media_to_telegram(
                    bot,
                    TARGET_CHANNEL,
                    it["temp_path"],  # type: ignore[index]
                    caption=it["caption"] or None,  # type: ignore[index]
                    supports_streaming=(it["media_type"] == "video"),  # type: ignore[index]
                )
                await _finalize_post(it)
            except Exception:
                logger.exception("Failed to send single media item")
                raise
    finally:
        for item in items:
            file_obj = item["file_obj"]
            temp_path = item["temp_path"]
            file_obj.close()
            cleanup_temp_file(temp_path)


async def _finalize_post(item: dict[str, object]) -> None:
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
    await stats.record_approved(media_type, filename=file_name, source="web_push")

    review = await storage.get_review_message(file_name)
    if review:
        chat_id, message_id = review
        await bot.edit_message_caption(
            chat_id=chat_id,
            message_id=message_id,
            caption=f"Post approved with media {file_name}!",
            reply_markup=None,
        )


async def _schedule_post(path: str) -> None:
    file_name = os.path.basename(path)
    scheduled_posts = await run_in_threadpool(get_scheduled_posts)
    next_slot = find_next_available_slot(
        now_utc(), scheduled_posts, QUIET_START, QUIET_END
    )
    source = CopySource(BUCKET_MAIN, path)
    new_object_name = f"{SCHEDULED_PATH}/{file_name}"
    await storage.client.copy_object(BUCKET_MAIN, new_object_name, source)
    await storage.delete_file(path, BUCKET_MAIN)
    await run_in_threadpool(
        add_scheduled_post, int(next_slot.timestamp()), new_object_name
    )
    review = await storage.get_review_message(file_name)
    if review:
        chat_id, message_id = review
        await bot.edit_message_caption(
            chat_id=chat_id,
            message_id=message_id,
            caption=f"Post scheduled for {format_display(next_slot)}!",
            reply_markup=None,
        )


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
    await storage.delete_file(path, BUCKET_MAIN)
    await stats.record_rejected(media_type, file_name, "web_notok")
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
    dependencies=[Depends(require_access_key)],
)
async def queue(request: Request) -> HTMLResponse:
    raw_posts = await run_in_threadpool(get_scheduled_posts)
    posts: list[dict] = []
    for path, ts in raw_posts:
        url = await storage.get_presigned_url(path)
        if not url:
            continue

        # Derive media information for proper embedding in template
        mime, _ = mimetypes.guess_type(path)
        is_video = path.startswith("videos/") or (mime or "").startswith("video/")
        is_image = path.startswith("photos/") or (mime or "").startswith("image/")

        posts.append(
            {
                "path": path,
                "ts": datetime.datetime.fromtimestamp(ts).isoformat(),
                "url": url,
                "mime": mime or ("video/mp4" if is_video else None),
                "is_video": is_video,
                "is_image": is_image,
            }
        )

    context = {"request": request, "posts": posts}
    return templates.TemplateResponse("queue.html", context)


@app.post("/queue/unschedule")
async def unschedule(
    request: Request, path: str = Form(...), key: str | None = Form(None)
) -> Response:
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

    suffix = f"?key={key}" if key else ""
    return RedirectResponse(url=f"/queue{suffix}", status_code=303)


@app.get(
    "/stats",
    response_class=HTMLResponse,
    dependencies=[Depends(require_access_key)],
)
async def stats_view(request: Request) -> HTMLResponse:
    daily, total, perf, busiest = await asyncio.gather(
        stats.get_daily_stats(reset_if_new_day=False),
        stats.get_total_stats(),
        stats.get_performance_metrics(),
        stats.get_busiest_hour(),
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
    }
    return templates.TemplateResponse("stats.html", context)
