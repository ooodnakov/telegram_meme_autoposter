"""Callback handlers and helpers for Telegram bot interactions."""

import datetime
import os
from typing import Any

from loguru import logger
from miniopy_async.commonconfig import CopySource
from telegram import (
    Bot,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    Update,
)
from telegram.ext import ContextTypes

import telegram_auto_poster.utils.db as db
from telegram_auto_poster.bot.handlers import (
    get_user_friendly_error_message,
    notify_user,
)
from telegram_auto_poster.config import (
    BUCKET_MAIN,
    PHOTOS_PATH,
    SCHEDULED_PATH,
    VIDEOS_PATH,
)
from telegram_auto_poster.utils.deduplication import (
    add_approved_hash,
    calculate_image_hash,
    calculate_video_hash,
)
from telegram_auto_poster.utils.general import (
    MinioError,
    TelegramMediaError,
    cleanup_temp_file,
    download_from_minio,
    extract_paths_from_message,
    prepare_group_items,
    send_group_media,
    send_media_to_telegram,
)
from telegram_auto_poster.utils.scheduler import find_next_available_slot
from telegram_auto_poster.utils.stats import stats
from telegram_auto_poster.utils.storage import storage
from telegram_auto_poster.utils.timezone import (
    DISPLAY_TZ,
    UTC,
    format_display,
    now_utc,
)
from telegram_auto_poster.utils.ui import (
    CALLBACK_NOTOK,
    CALLBACK_OK,
    CALLBACK_PUSH,
    CALLBACK_SCHEDULE,
)


def _is_streaming_video(file_path: str) -> bool:
    """Check if a file is a video that supports streaming."""
    return os.path.splitext(file_path)[1].lower() in [".mp4", ".avi", ".mov"]


def _translated_media_type(media_type: str) -> str:
    """Return a Russian label for ``media_type``."""
    return "фото" if media_type == "photo" else "видео"


async def _notify_submitter(
    context: ContextTypes.DEFAULT_TYPE,
    user_metadata: dict[str, Any] | None,
    media_type: str,
    template: str,
    storage_name: str,
) -> None:
    """Send a templated notification to the submitting user if possible."""
    if (
        user_metadata
        and not user_metadata.get("notified")
        and user_metadata.get("user_id")
    ):
        translated = _translated_media_type(media_type)
        await notify_user(
            context,
            user_metadata.get("user_id"),
            template.format(translated_media_type=translated),
            reply_to_message_id=user_metadata.get("message_id"),
        )
        await storage.mark_notified(storage_name)
        logger.info(
            f"Notified user {user_metadata.get('user_id')} about {storage_name}"
        )


def _compute_media_hash(temp_path: str, media_type: str) -> str | None:
    """Return a content hash for the temporary file based on ``media_type``."""
    return (
        calculate_image_hash(temp_path)
        if media_type == "photo"
        else calculate_video_hash(temp_path)
    )


async def _add_media_hash(
    file_name: str,
    media_type: str,
    file_prefix: str,
    temp_path: str | None,
    metadata: dict[str, Any] | None,
    context_name: str,
) -> str | None:
    """Ensure ``file_name`` is present in the deduplication corpus."""
    media_hash = None
    try:
        meta = metadata or await storage.get_submission_metadata(file_name)
        if meta and meta.get("hash"):
            media_hash = meta.get("hash")
        else:
            if temp_path is None:
                temp_path, _ = await download_from_minio(
                    file_prefix + file_name, BUCKET_MAIN
                )
                temp_created = True
            else:
                temp_created = False
            try:
                media_hash = _compute_media_hash(temp_path, media_type)
            finally:
                if temp_created:
                    cleanup_temp_file(temp_path)
        if media_hash:
            add_approved_hash(media_hash)
    except MinioError as _e:
        logger.warning(
            f"MinIO error while adding approved hash for {file_name} in {context_name}: {_e}"
        )
    except Exception as _e:
        logger.warning(
            f"Unexpected error when adding approved hash for {file_name} in {context_name}: {_e}"
        )
    return media_hash


async def _edit_message(query: CallbackQuery, text: str) -> None:
    """Edit the caption or text of ``query``'s message to ``text``."""
    if query.message.caption:
        await query.message.edit_caption(text, reply_markup=None)
    else:
        await query.message.edit_text(text, reply_markup=None)


async def schedule_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle scheduling a post."""
    logger.info(
        f"Received {CALLBACK_SCHEDULE} callback from user {update.callback_query.from_user.id}"
    )
    query = update.callback_query
    await query.answer()

    paths = extract_paths_from_message(query.message)
    if not paths:
        return

    try:
        # Prepare common config
        now = now_utc()
        bot_data = context.application.bot_data
        quiet_start = bot_data.get("quiet_hours_start", 22)
        quiet_end = bot_data.get("quiet_hours_end", 10)

        scheduled_info: list[tuple[str, str]] = []  # (file_name, display_time)

        for file_path in paths:
            file_name = os.path.basename(file_path)
            file_prefix = (
                f"{PHOTOS_PATH}/"
                if file_path.startswith(f"{PHOTOS_PATH}/")
                else f"{VIDEOS_PATH}/"
            )

            # 1. Find next available slot (refresh scheduled posts each time)
            scheduled_posts = db.get_scheduled_posts()
            next_slot = find_next_available_slot(
                now, scheduled_posts, quiet_start, quiet_end
            )
            # Shift base time slightly for next computation
            now = next_slot

            # 2. Add to approved dedup corpus (use stored hash or compute)
            media_type = "photo" if file_path.startswith(f"{PHOTOS_PATH}/") else "video"
            await _add_media_hash(
                file_name,
                media_type,
                file_prefix,
                None,
                None,
                "schedule_callback",
            )

            # 3. Move file in MinIO
            new_object_name = SCHEDULED_PATH + "/" + file_name
            source = CopySource(BUCKET_MAIN, f"{file_prefix}{file_name}")
            await storage.client.copy_object(
                BUCKET_MAIN,
                new_object_name,
                source,
            )
            await storage.delete_file(file_prefix + file_name, BUCKET_MAIN)

            # 4. Add to database
            db.add_scheduled_post(int(next_slot.timestamp()), new_object_name)
            scheduled_info.append((file_name, format_display(next_slot)))

        # 5. Update message (caption if media, otherwise text)
        summary = "Scheduled posts:\n" + "\n".join(
            f"{n} → {t}" for n, t in scheduled_info
        )
        await _edit_message(query, summary)
    except Exception as e:
        logger.error(f"Error in schedule_callback: {e}")
        await query.message.reply_text(f"An unexpected error occurred: {str(e)}")


async def ok_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle approval: add post to batch."""
    logger.info(
        f"Received {CALLBACK_OK} callback from user {update.callback_query.from_user.id}"
    )
    logger.debug(f"Callback data: {update.callback_query.data}")

    query = update.callback_query
    await query.answer()

    paths = extract_paths_from_message(query.message)
    if not paths:
        return

    try:
        approved_counts = {"photo": 0, "video": 0}
        total_batch_count = None

        for file_path in paths:
            file_name = os.path.basename(file_path)
            media_type = "photo" if file_path.startswith(f"{PHOTOS_PATH}/") else "video"
            file_prefix = (
                f"{PHOTOS_PATH}/"
                if file_path.startswith(f"{PHOTOS_PATH}/")
                else f"{VIDEOS_PATH}/"
            )

            # Verify file existence
            if not await storage.file_exists(file_prefix + file_name, BUCKET_MAIN):
                raise MinioError(
                    f"File not found: {file_prefix + file_name} in {BUCKET_MAIN}"
                )

            # Add to batch in MinIO for later sending
            new_object_name = f"batch_{file_name}"
            temp_path, _ = await download_from_minio(
                file_prefix + file_name, BUCKET_MAIN
            )
            try:
                target_prefix = PHOTOS_PATH if media_type == "photo" else VIDEOS_PATH
                src_meta = await storage.get_submission_metadata(file_name)
                media_hash = await _add_media_hash(
                    file_name,
                    media_type,
                    file_prefix,
                    temp_path,
                    src_meta,
                    "ok_callback(batch)",
                )
                await storage.upload_file(
                    temp_path,
                    BUCKET_MAIN,
                    f"{target_prefix}/{new_object_name}",
                    user_id=src_meta.get("user_id") if src_meta else None,
                    chat_id=src_meta.get("chat_id") if src_meta else None,
                    message_id=src_meta.get("message_id") if src_meta else None,
                    media_hash=media_hash,
                    source=src_meta.get("source") if src_meta else None,
                )

                user_metadata = await storage.get_submission_metadata(new_object_name)
                await storage.delete_file(file_prefix + file_name, BUCKET_MAIN)

                total_batch_count = await db.increment_batch_count()
                approved_counts[media_type] += 1
                await stats.record_added_to_batch(media_type)

                await _notify_submitter(
                    context,
                    user_metadata,
                    media_type,
                    "Отличные новости! Ваша {translated_media_type} публикация была одобрена и скоро будет размещена. Спасибо за ваш вклад!",
                    new_object_name,
                )
            finally:
                cleanup_temp_file(temp_path)

        # Update the summary message
        summary = f"Added to batch: {approved_counts['photo']} photos, {approved_counts['video']} videos.\n"
        if total_batch_count is not None:
            summary += f"There are {total_batch_count} items in the batch."
        await _edit_message(query, summary)
    except MinioError as e:
        logger.error(f"MinIO error in ok_callback: {e}")
        await query.message.reply_text(get_user_friendly_error_message(e))
    except TelegramMediaError as e:
        logger.error(f"Telegram error in ok_callback: {e}")
        await query.message.reply_text(get_user_friendly_error_message(e))
    except Exception as e:
        logger.error(f"Unexpected error in ok_callback: {e}")
        await stats.record_error("processing", f"Error in ok_callback: {str(e)}")
        await query.message.reply_text(f"An unexpected error occurred: {str(e)}")


async def push_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle direct publish of approved media."""
    logger.info(
        f"Received {CALLBACK_PUSH} callback from user {update.callback_query.from_user.id}"
    )
    logger.debug(f"Callback data: {update.callback_query.data}")

    query = update.callback_query
    await query.answer()

    target_channels = context.bot_data.get("target_channel_ids")
    prompt = context.bot_data.get("prompt_target_channel")
    data = query.data
    if prompt and data and ":" in data:
        _, selected = data.split(":", 1)
        if selected != "all":
            target_channels = [selected]

    paths = extract_paths_from_message(query.message)
    if not paths:
        return

    try:
        media_items, caption_to_send = await prepare_group_items(paths)
        sent_counts = {"photo": 0, "video": 0}

        await send_group_media(
            context.bot, target_channels, media_items, caption_to_send
        )

        # Post-send bookkeeping: dedup, delete, stats, notify
        for item in media_items:
            file_name = item["file_name"]
            media_type = item["media_type"]
            file_prefix = item["file_prefix"]
            temp_path = item["temp_path"]
            fh = item["file_obj"]
            user_metadata = item["meta"]
            try:
                await _add_media_hash(
                    file_name,
                    media_type,
                    file_prefix,
                    temp_path,
                    user_metadata,
                    "push_callback",
                )

                # Delete from MinIO
                await storage.delete_file(file_prefix + file_name, BUCKET_MAIN)

                await stats.record_approved(
                    media_type,
                    filename=file_name,
                    source=user_metadata.get("source") if user_metadata else None,
                    count=len(target_channels),
                )
                sent_counts[media_type] += 1

                await _notify_submitter(
                    context,
                    user_metadata,
                    media_type,
                    "Отличные новости! Ваша {translated_media_type} публикация была одобрена и размещена в канале. Спасибо за ваш вклад!",
                    file_name,
                )
            finally:
                try:
                    fh.close()
                finally:
                    cleanup_temp_file(temp_path)

        # Update the summary message
        summary = (
            f"Pushed: {sent_counts['photo']} photos, {sent_counts['video']} videos."
        )
        await _edit_message(query, summary)
        logger.info(
            f"Media group sent to channels {', '.join(map(str, target_channels))}"
        )
    except MinioError as e:
        logger.error(f"MinIO error in push_callback: {e}")
        await query.message.reply_text(get_user_friendly_error_message(e))
    except TelegramMediaError as e:
        logger.error(f"Telegram error in push_callback: {e}")
        await query.message.reply_text(get_user_friendly_error_message(e))
    except Exception as e:
        logger.error(f"Error in push_callback: {e}")
        await stats.record_error("processing", f"Error in push_callback: {str(e)}")
        await query.message.reply_text(f"Error sending to channel: {str(e)}")


async def notok_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle rejection of media submissions."""
    logger.info(
        f"Received {CALLBACK_NOTOK} callback from user {update.callback_query.from_user.id}"
    )
    logger.debug(f"Callback data: {update.callback_query.data}")

    query = update.callback_query
    await query.answer()

    try:
        paths = extract_paths_from_message(query.message)
        if not paths:
            return

        # Update the message first
        await _edit_message(query, "Post(s) disapproved!")

        for file_path in paths:
            file_name = os.path.basename(file_path)
            media_type = "photo" if file_path.startswith(f"{PHOTOS_PATH}/") else "video"
            file_prefix = (
                f"{PHOTOS_PATH}/"
                if file_path.startswith(f"{PHOTOS_PATH}/")
                else f"{VIDEOS_PATH}/"
            )
            # Get user metadata
            user_metadata = await storage.get_submission_metadata(file_name)
            # Delete from MinIO if exists
            if await storage.file_exists(file_prefix + file_name, BUCKET_MAIN):
                await storage.delete_file(file_prefix + file_name, BUCKET_MAIN)
            else:
                logger.warning(
                    f"File not found for deletion: {BUCKET_MAIN}/{file_prefix + file_name}"
                )

            await stats.record_rejected(
                media_type,
                filename=file_name,
                source=user_metadata.get("source") if user_metadata else None,
            )

            await _notify_submitter(
                context,
                user_metadata,
                media_type,
                "Ваша {translated_media_type} публикация была рассмотрена, но не была опубликована. Вы можете попробовать еще раз в будущем!",
                file_name,
            )
    except Exception as e:
        logger.error(f"Error in notok_callback: {e}")
        await query.message.reply_text(get_user_friendly_error_message(e))


async def unschedule_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle removal of scheduled posts from Redis and MinIO."""
    logger.info(
        f"Received /unschedule callback from user {update.callback_query.from_user.id}"
    )
    query = update.callback_query
    await query.answer()

    try:
        data = query.data or ""
        if not data.startswith("/unschedule:"):
            await query.message.reply_text("Invalid request")
            return

        try:
            idx = int(data.split(":", 1)[1])
        except (ValueError, IndexError):
            await query.message.reply_text("Invalid request")
            return
        scheduled_posts = db.get_scheduled_posts()
        if not scheduled_posts or idx >= len(scheduled_posts):
            await query.message.edit_text("No posts scheduled.")
            return

        file_path = scheduled_posts[idx][0]
        # Remove from DB first
        db.remove_scheduled_post(file_path)
        # Attempt to remove object; ignore if already missing
        if await storage.file_exists(file_path, BUCKET_MAIN):
            await storage.delete_file(file_path, BUCKET_MAIN)

        # Refresh the list inline by rebuilding the keyboard
        scheduled_posts = db.get_scheduled_posts()
        if not scheduled_posts:
            await query.message.edit_text("No posts scheduled.")
            return

        buttons = []
        for i, (path, ts) in enumerate(scheduled_posts):
            dt = datetime.datetime.fromtimestamp(int(ts), tz=UTC).astimezone(DISPLAY_TZ)
            label = f"{dt.strftime('%m-%d %H:%M')} • {path.split('/')[-1]}"
            buttons.append(
                [InlineKeyboardButton(text=label, callback_data=f"/unschedule:{i}")]
            )
        markup = InlineKeyboardMarkup(buttons)
        await query.message.edit_text(
            "Choose a scheduled post to remove:", reply_markup=markup
        )
    except Exception as e:
        logger.error(f"Error in unschedule_callback: {e}")
        await query.message.reply_text(f"Failed to remove scheduled post: {str(e)}")


async def send_schedule_preview(
    bot: Bot,
    chat_id: int,
    file_path: str,
    index: int,
    target_channels: list[str] | None = None,
    prompt_channel: bool = False,
) -> Message:
    """Send a preview of a scheduled post with navigation buttons."""
    buttons = [
        [
            InlineKeyboardButton("Prev", callback_data=f"/sch_prev:{index}"),
            InlineKeyboardButton(
                "Unschedule",
                callback_data=f"/sch_unschedule:{index}",
            ),
            InlineKeyboardButton("Next", callback_data=f"/sch_next:{index}"),
        ]
    ]
    channels = target_channels or []
    if prompt_channel and len(channels) > 1:
        for ch in channels:
            buttons.append(
                [
                    InlineKeyboardButton(
                        f"Push {ch}", callback_data=f"/sch_push:{index}:{ch}"
                    )
                ]
            )
        buttons.append(
            [InlineKeyboardButton("Push all", callback_data=f"/sch_push:{index}:all")]
        )
    else:
        buttons[0].insert(
            2, InlineKeyboardButton("Push", callback_data=f"/sch_push:{index}")
        )
    markup = InlineKeyboardMarkup(buttons)

    temp_path = None
    try:
        temp_path, _ = await download_from_minio(file_path, BUCKET_MAIN)
        message = await send_media_to_telegram(
            bot,
            chat_id,
            temp_path,
            caption=file_path,
            supports_streaming=_is_streaming_video(temp_path),
        )
        await message.edit_reply_markup(reply_markup=markup)
        return message
    finally:
        cleanup_temp_file(temp_path)


async def _remove_post_and_show_next(
    query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE, index: int, file_path: str
) -> None:
    """Remove a post then display the next available one."""
    db.remove_scheduled_post(file_path)
    if await storage.file_exists(file_path, BUCKET_MAIN):
        await storage.delete_file(file_path, BUCKET_MAIN)

    scheduled_posts = db.get_scheduled_posts()
    if not scheduled_posts:
        await query.message.edit_text("No posts scheduled.")
        return

    await query.message.delete()
    idx = min(index, len(scheduled_posts) - 1)
    next_path = scheduled_posts[idx][0]
    await send_schedule_preview(
        context.bot,
        query.message.chat_id,
        next_path,
        idx,
        getattr(context, "bot_data", {}).get("target_channel_ids"),
        bool(getattr(context, "bot_data", {}).get("prompt_target_channel")),
    )


async def schedule_browser_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle navigation and actions for scheduled posts."""
    logger.info(
        f"Received schedule browser callback from user {update.callback_query.from_user.id}"
    )

    query = update.callback_query
    await query.answer()

    try:
        data = query.data or ""
        action_part, *payload_parts = data.split(":")
        action = action_part.split("_", 1)[1]

        if action in {"prev", "next"}:
            try:
                idx = int(payload_parts[0])
            except (ValueError, IndexError):
                await query.message.reply_text("Invalid request")
                return
            scheduled_posts = db.get_scheduled_posts()
            if not scheduled_posts:
                await query.message.edit_text("No posts scheduled.")
                return

            if action == "prev":
                idx = (idx - 1) % len(scheduled_posts)
            else:
                idx = (idx + 1) % len(scheduled_posts)

            await query.message.delete()
            file_path = scheduled_posts[idx][0]
            await send_schedule_preview(
                context.bot,
                query.message.chat_id,
                file_path,
                idx,
                getattr(context, "bot_data", {}).get("target_channel_ids"),
                bool(getattr(context, "bot_data", {}).get("prompt_target_channel")),
            )
            return

        if action == "unschedule":
            try:
                idx = int(payload_parts[0])
            except (ValueError, IndexError):
                await query.message.reply_text("Invalid request")
                return
            scheduled_posts = db.get_scheduled_posts()
            if not scheduled_posts or idx >= len(scheduled_posts):
                await query.message.edit_text("No posts scheduled.")
                return
            file_path = scheduled_posts[idx][0]
            await _remove_post_and_show_next(query, context, idx, file_path)
            return

        if action == "push":
            try:
                idx = int(payload_parts[0])
            except (ValueError, IndexError):
                await query.message.reply_text("Invalid request")
                return
            selected = payload_parts[1] if len(payload_parts) > 1 else None
            scheduled_posts = db.get_scheduled_posts()
            if not scheduled_posts or idx >= len(scheduled_posts):
                await query.message.edit_text("No posts scheduled.")
                return
            file_path = scheduled_posts[idx][0]
            temp_path = None
            try:
                temp_path, _ = await download_from_minio(file_path, BUCKET_MAIN)
                target_channels = getattr(context, "bot_data", {}).get(
                    "target_channel_ids"
                )
                prompt = getattr(context, "bot_data", {}).get("prompt_target_channel")
                if target_channels:
                    if prompt and selected and selected != "all":
                        target_channels = [selected]
                    await send_media_to_telegram(
                        context.bot,
                        target_channels,
                        temp_path,
                        caption=None,
                        supports_streaming=_is_streaming_video(temp_path),
                    )
            finally:
                cleanup_temp_file(temp_path)
            await _remove_post_and_show_next(query, context, idx, file_path)
    except Exception as e:
        logger.error(f"Error in schedule_browser_callback: {e}")
        await query.message.reply_text("Failed to process request")


async def list_batch_files() -> list[str]:
    """Return the combined list of photo and video batch files."""
    photo_batch = await storage.list_files(BUCKET_MAIN, prefix=f"{PHOTOS_PATH}/batch_")
    video_batch = await storage.list_files(BUCKET_MAIN, prefix=f"{VIDEOS_PATH}/batch_")
    return photo_batch + video_batch


async def send_batch_preview(
    bot: Bot,
    chat_id: int,
    file_path: str,
    index: int,
    target_channels: list[str] | None = None,
    prompt_channel: bool = False,
) -> Message:
    """Show a preview of a batch file with navigation buttons."""
    buttons = [
        [
            InlineKeyboardButton("Prev", callback_data=f"/batch_prev:{index}"),
            InlineKeyboardButton("Remove", callback_data=f"/batch_remove:{index}"),
            InlineKeyboardButton("Next", callback_data=f"/batch_next:{index}"),
        ]
    ]
    channels = target_channels or []
    if prompt_channel and len(channels) > 1:
        for ch in channels:
            buttons.append(
                [
                    InlineKeyboardButton(
                        f"Push {ch}", callback_data=f"/batch_push:{index}:{ch}"
                    )
                ]
            )
        buttons.append(
            [InlineKeyboardButton("Push all", callback_data=f"/batch_push:{index}:all")]
        )
    else:
        buttons[0].insert(
            2, InlineKeyboardButton("Push", callback_data=f"/batch_push:{index}")
        )
    markup = InlineKeyboardMarkup(buttons)
    temp_path = None
    try:
        temp_path, _ = await download_from_minio(file_path, BUCKET_MAIN)
        message = await send_media_to_telegram(
            bot,
            chat_id,
            temp_path,
            caption=file_path,
            supports_streaming=_is_streaming_video(temp_path),
        )
        await message.edit_reply_markup(reply_markup=markup)
        return message
    finally:
        cleanup_temp_file(temp_path)


async def batch_browser_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle navigation and actions for batch posts."""
    logger.info(
        f"Received batch browser callback from user {update.callback_query.from_user.id}"
    )
    query = update.callback_query
    await query.answer()
    try:
        data = query.data or ""
        action_part, *payload_parts = data.split(":")
        action = action_part.split("_", 1)[1]
        batch_files = await list_batch_files()
        if not batch_files:
            await query.message.edit_text("No items in batch.")
            return
        if action in {"prev", "next"}:
            try:
                idx = int(payload_parts[0])
            except (ValueError, IndexError):
                await query.message.reply_text("Invalid request")
                return
            if action == "prev":
                idx = (idx - 1) % len(batch_files)
            else:
                idx = (idx + 1) % len(batch_files)
            await query.message.delete()
            file_path = batch_files[idx]
            await send_batch_preview(
                context.bot,
                query.message.chat_id,
                file_path,
                idx,
                getattr(context, "bot_data", {}).get("target_channel_ids"),
                bool(getattr(context, "bot_data", {}).get("prompt_target_channel")),
            )
            return
        if action == "remove":
            try:
                idx = int(payload_parts[0])
            except (ValueError, IndexError):
                await query.message.reply_text("Invalid request")
                return
            file_path = batch_files[idx]
            await storage.delete_file(file_path, BUCKET_MAIN)
            await db.decrement_batch_count(1)
            batch_files = await list_batch_files()
            if not batch_files:
                await query.message.edit_text("No items in batch.")
                return
            await query.message.delete()
            next_idx = min(idx, len(batch_files) - 1)
            await send_batch_preview(
                context.bot,
                query.message.chat_id,
                batch_files[next_idx],
                next_idx,
                getattr(context, "bot_data", {}).get("target_channel_ids"),
                bool(getattr(context, "bot_data", {}).get("prompt_target_channel")),
            )
            return
        if action == "push":
            try:
                idx = int(payload_parts[0])
            except (ValueError, IndexError):
                await query.message.reply_text("Invalid request")
                return
            selected = payload_parts[1] if len(payload_parts) > 1 else None
            file_path = batch_files[idx]
            temp_path = None
            try:
                temp_path, _ = await download_from_minio(file_path, BUCKET_MAIN)
                target_channels = getattr(context, "bot_data", {}).get(
                    "target_channel_ids"
                )
                prompt = getattr(context, "bot_data", {}).get("prompt_target_channel")
                if target_channels:
                    if prompt and selected and selected != "all":
                        target_channels = [selected]
                    await send_media_to_telegram(
                        context.bot,
                        target_channels,
                        temp_path,
                        caption=None,
                        supports_streaming=_is_streaming_video(temp_path),
                    )
            finally:
                cleanup_temp_file(temp_path)
            await storage.delete_file(file_path, BUCKET_MAIN)
            await db.decrement_batch_count(1)
            batch_files = await list_batch_files()
            if not batch_files:
                await query.message.edit_text("No items in batch.")
                return
            await query.message.delete()
            next_idx = min(idx, len(batch_files) - 1)
            await send_batch_preview(
                context.bot,
                query.message.chat_id,
                batch_files[next_idx],
                next_idx,
                getattr(context, "bot_data", {}).get("target_channel_ids"),
                bool(getattr(context, "bot_data", {}).get("prompt_target_channel")),
            )
    except Exception as e:
        logger.error(f"Error in batch_browser_callback: {e}")
        await query.message.reply_text("Failed to process request")
