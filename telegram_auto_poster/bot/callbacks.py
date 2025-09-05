import datetime
import os

from loguru import logger
from miniopy_async.commonconfig import CopySource
from telegram import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
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


def _is_streaming_video(file_path: str) -> bool:
    """Checks if a file is a video that supports streaming."""
    return os.path.splitext(file_path)[1].lower() in [".mp4", ".avi", ".mov"]


async def schedule_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle scheduling a post."""
    logger.info(
        f"Received /schedule callback from user {update.callback_query.from_user.id}"
    )
    query = update.callback_query
    await query.answer()

    paths = extract_paths_from_message(query.message)
    if not paths:
        await query.message.reply_text("Could not extract file path from the message")
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
            media_hash = None
            try:
                user_meta = await storage.get_submission_metadata(file_name)
                if user_meta and user_meta.get("hash"):
                    media_hash = user_meta.get("hash")
                else:
                    temp_path, _ = await download_from_minio(
                        file_prefix + file_name, BUCKET_MAIN
                    )
                    try:
                        if file_path.startswith(f"{PHOTOS_PATH}/"):
                            media_hash = calculate_image_hash(temp_path)
                        else:
                            media_hash = calculate_video_hash(temp_path)
                    finally:
                        cleanup_temp_file(temp_path)
                if media_hash:
                    add_approved_hash(media_hash)
            except Exception as _e:
                logger.warning(
                    f"Failed to add approved hash for {file_name} in schedule_callback: {_e}"
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
        if query.message.caption:
            await query.message.edit_caption(summary, reply_markup=None)
        else:
            await query.message.edit_text(summary, reply_markup=None)
    except Exception as e:
        logger.error(f"Error in schedule_callback: {e}")
        await query.message.reply_text(f"An unexpected error occurred: {str(e)}")


async def ok_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle approval: add post to batch"""
    logger.info(f"Received /ok callback from user {update.callback_query.from_user.id}")
    logger.debug(f"Callback data: {update.callback_query.data}")

    query = update.callback_query
    await query.answer()

    paths = extract_paths_from_message(query.message)
    if not paths:
        await query.message.reply_text("Could not extract file path from the message")
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
                media_hash = None
                if src_meta and src_meta.get("hash"):
                    media_hash = src_meta.get("hash")
                else:
                    media_hash = (
                        calculate_image_hash(temp_path)
                        if media_type == "photo"
                        else calculate_video_hash(temp_path)
                    )
                await storage.upload_file(
                    temp_path,
                    BUCKET_MAIN,
                    f"{target_prefix}/{new_object_name}",
                    user_id=src_meta.get("user_id") if src_meta else None,
                    chat_id=src_meta.get("chat_id") if src_meta else None,
                    message_id=src_meta.get("message_id") if src_meta else None,
                    media_hash=media_hash,
                )

                try:
                    if media_hash:
                        add_approved_hash(media_hash)
                except Exception as _e:
                    logger.warning(
                        f"Failed to add approved hash for {file_name} in ok_callback(batch): {_e}"
                    )

                user_metadata = await storage.get_submission_metadata(new_object_name)
                await storage.delete_file(file_prefix + file_name, BUCKET_MAIN)

                total_batch_count = await db.increment_batch_count()
                approved_counts[media_type] += 1
                await stats.record_added_to_batch(media_type)

                # Notify original submitter
                if (
                    user_metadata
                    and not user_metadata.get("notified")
                    and user_metadata.get("user_id")
                ):
                    translated_media_type = "фото" if media_type == "photo" else "видео"
                    await notify_user(
                        context,
                        user_metadata.get("user_id"),
                        f"Отличные новости! Ваша {translated_media_type} публикация была одобрена и скоро будет размещена. Спасибо за ваш вклад!",
                        reply_to_message_id=user_metadata.get("message_id"),
                    )
                    await storage.mark_notified(new_object_name)
            finally:
                cleanup_temp_file(temp_path)

        # Update the summary message
        summary = f"Added to batch: {approved_counts['photo']} photos, {approved_counts['video']} videos.\n"
        if total_batch_count is not None:
            summary += f"There are {total_batch_count} items in the batch."
        if query.message.caption:
            await query.message.edit_caption(summary, reply_markup=None)
        else:
            await query.message.edit_text(summary, reply_markup=None)
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
    """Handle direct publish of approved media"""
    logger.info(
        f"Received /push callback from user {update.callback_query.from_user.id}"
    )
    logger.debug(f"Callback data: {update.callback_query.data}")

    query = update.callback_query
    await query.answer()

    target_channel = context.bot_data.get("target_channel_id")

    paths = extract_paths_from_message(query.message)
    if not paths:
        await query.message.reply_text("Could not extract file path from the message")
        return

    try:
        media_items, caption_to_send = await prepare_group_items(paths)
        sent_counts = {"photo": 0, "video": 0}

        await send_group_media(
            context.bot, target_channel, media_items, caption_to_send
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
                # Add to dedup corpus
                try:
                    media_hash = user_metadata.get("hash") if user_metadata else None
                    if not media_hash:
                        media_hash = (
                            calculate_image_hash(temp_path)
                            if media_type == "photo"
                            else calculate_video_hash(temp_path)
                        )
                    if media_hash:
                        add_approved_hash(media_hash)
                except Exception as _e:
                    logger.warning(
                        f"Failed to add approved hash for {file_name} in push_callback: {_e}"
                    )

                # Delete from MinIO
                await storage.delete_file(file_prefix + file_name, BUCKET_MAIN)

                await stats.record_approved(
                    media_type, filename=file_name, source="push_callback"
                )
                sent_counts[media_type] += 1

                # Notify original submitter
                if user_metadata and user_metadata.get("user_id"):
                    translated_media_type = "фото" if media_type == "photo" else "видео"
                    await notify_user(
                        context,
                        user_metadata.get("user_id"),
                        f"Отличные новости! Ваша {translated_media_type} публикация была одобрена и размещена в канале. Спасибо за ваш вклад!",
                        reply_to_message_id=user_metadata.get("message_id"),
                    )
                    await storage.mark_notified(file_name)
            finally:
                try:
                    fh.close()
                finally:
                    cleanup_temp_file(temp_path)

        # Update the summary message
        summary = (
            f"Pushed: {sent_counts['photo']} photos, {sent_counts['video']} videos."
        )
        if query.message.caption:
            await query.message.edit_caption(summary, reply_markup=None)
        else:
            await query.message.edit_text(summary, reply_markup=None)
        logger.info(f"Media group sent to channel {target_channel}")
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


async def notok_callback(update, context) -> None:
    """Handle rejection of media submissions"""
    logger.info(
        f"Received /notok callback from user {update.callback_query.from_user.id}"
    )
    logger.debug(f"Callback data: {update.callback_query.data}")

    query = update.callback_query
    await query.answer()

    try:
        paths = extract_paths_from_message(query.message)
        if not paths:
            await query.message.reply_text(
                "Could not extract file path from the message"
            )
            return

        # Update the message first
        if query.message.caption:
            await query.message.edit_caption("Post(s) disapproved!", reply_markup=None)
        else:
            await query.message.edit_text("Post(s) disapproved!", reply_markup=None)

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
                media_type, filename=file_name, source="notok_callback"
            )

            if (
                user_metadata
                and not user_metadata.get("notified")
                and user_metadata.get("user_id")
            ):
                translated_media_type = "фото" if media_type == "photo" else "видео"
                await notify_user(
                    context,
                    user_metadata.get("user_id"),
                    f"Ваша {translated_media_type} публикация была рассмотрена, но не была опубликована. Вы можете попробовать еще раз в будущем!",
                    reply_to_message_id=user_metadata.get("message_id"),
                )
                await storage.mark_notified(file_name)
                logger.info(
                    f"Notified user {user_metadata.get('user_id')} about rejection of {file_name} from message_id {user_metadata.get('message_id')}"
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


async def send_schedule_preview(bot, chat_id: int, file_path: str, index: int):
    """Send a preview of a scheduled post with navigation buttons."""
    buttons = [
        [
            InlineKeyboardButton("Prev", callback_data=f"/sch_prev:{index}"),
            InlineKeyboardButton(
                "Unschedule",
                callback_data=f"/sch_unschedule:{index}",
            ),
            InlineKeyboardButton("Push", callback_data=f"/sch_push:{index}"),
            InlineKeyboardButton("Next", callback_data=f"/sch_next:{index}"),
        ]
    ]
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
):
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
    await send_schedule_preview(context.bot, query.message.chat_id, next_path, idx)


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
                context.bot, query.message.chat_id, file_path, idx
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
            scheduled_posts = db.get_scheduled_posts()
            if not scheduled_posts or idx >= len(scheduled_posts):
                await query.message.edit_text("No posts scheduled.")
                return
            file_path = scheduled_posts[idx][0]
            temp_path = None
            try:
                temp_path, _ = await download_from_minio(file_path, BUCKET_MAIN)
                target_channel = context.bot_data.get("target_channel_id")
                if target_channel:
                    await send_media_to_telegram(
                        context.bot,
                        target_channel,
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
    photo_batch = await storage.list_files(BUCKET_MAIN, prefix=f"{PHOTOS_PATH}/batch_")
    video_batch = await storage.list_files(BUCKET_MAIN, prefix=f"{VIDEOS_PATH}/batch_")
    return photo_batch + video_batch


async def send_batch_preview(bot, chat_id: int, file_path: str, index: int):
    buttons = [
        [
            InlineKeyboardButton("Prev", callback_data=f"/batch_prev:{index}"),
            InlineKeyboardButton("Remove", callback_data=f"/batch_remove:{index}"),
            InlineKeyboardButton("Push", callback_data=f"/batch_push:{index}"),
            InlineKeyboardButton("Next", callback_data=f"/batch_next:{index}"),
        ]
    ]
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
            await send_batch_preview(context.bot, query.message.chat_id, file_path, idx)
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
                context.bot, query.message.chat_id, batch_files[next_idx], next_idx
            )
            return
        if action == "push":
            try:
                idx = int(payload_parts[0])
            except (ValueError, IndexError):
                await query.message.reply_text("Invalid request")
                return
            file_path = batch_files[idx]
            temp_path = None
            try:
                temp_path, _ = await download_from_minio(file_path, BUCKET_MAIN)
                target_channel = context.bot_data.get("target_channel_id")
                if target_channel:
                    await send_media_to_telegram(
                        context.bot,
                        target_channel,
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
                context.bot, query.message.chat_id, batch_files[next_idx], next_idx
            )
    except Exception as e:
        logger.error(f"Error in batch_browser_callback: {e}")
        await query.message.reply_text("Failed to process request")
