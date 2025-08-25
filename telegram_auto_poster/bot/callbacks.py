import datetime
import os

from loguru import logger
from miniopy_async.commonconfig import CopySource
from telegram import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Update
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
    extract_filename,
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

    message_text = query.message.caption or query.message.text
    file_path = extract_filename(message_text)
    if not file_path:
        await query.message.reply_text("Could not extract file path from the message")
        return

    file_name = os.path.basename(file_path)
    file_prefix = (
        f"{PHOTOS_PATH}/"
        if file_path.startswith(f"{PHOTOS_PATH}/")
        else f"{VIDEOS_PATH}/"
    )

    try:
        # 1. Find next available slot
        now = now_utc()
        scheduled_posts = db.get_scheduled_posts()
        bot_data = context.application.bot_data
        quiet_start = bot_data.get("quiet_hours_start", 22)
        quiet_end = bot_data.get("quiet_hours_end", 10)
        next_slot = find_next_available_slot(
            now, scheduled_posts, quiet_start, quiet_end
        )

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
            # Non-blocking: failure to compute hash should not prevent scheduling
            logger.warning(f"Failed to add approved hash for {file_name}: {_e}")

        # 3. Move file in MinIO
        new_object_name = SCHEDULED_PATH + "/" + file_name
        # Copy object within the same bucket using proper CopySource
        source = CopySource(BUCKET_MAIN, f"{file_prefix}{file_name}")
        await storage.client.copy_object(
            BUCKET_MAIN,
            new_object_name,
            source,
        )
        await storage.delete_file(file_prefix + file_name, BUCKET_MAIN)

        # 4. Add to database
        db.add_scheduled_post(int(next_slot.timestamp()), new_object_name)

        # 5. Update message
        await query.message.edit_caption(
            f"Post scheduled for {format_display(next_slot)}!",
            reply_markup=None,
        )
        # stats.record_scheduled(media_type)
    except Exception as e:
        logger.error(f"Error in schedule_callback: {e}")
        await query.message.reply_text(f"An unexpected error occurred: {str(e)}")


async def ok_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle approval: add post to batch"""
    logger.info(f"Received /ok callback from user {update.callback_query.from_user.id}")
    logger.debug(f"Callback data: {update.callback_query.data}")

    query = update.callback_query
    await query.answer()

    message_text = query.message.caption or query.message.text
    file_path = extract_filename(message_text)
    if not file_path:
        await query.message.reply_text("Could not extract file path from the message")
        return

    file_name = os.path.basename(file_path)
    media_type = "photo" if file_path.startswith(f"{PHOTOS_PATH}/") else "video"
    file_prefix = (
        f"{PHOTOS_PATH}/"
        if file_path.startswith(f"{PHOTOS_PATH}/")
        else f"{VIDEOS_PATH}/"
    )

    try:
        # Verify file existence
        if not await storage.file_exists(file_prefix + file_name, BUCKET_MAIN):
            raise MinioError(
                f"File not found: {file_prefix + file_name} in {BUCKET_MAIN}"
            )

        # Add to batch in MinIO for later sending
        new_object_name = f"batch_{file_name}"
        temp_path, _ = await download_from_minio(file_prefix + file_name, BUCKET_MAIN)
        try:
            # Upload to appropriate prefix as batch_*, preserving metadata and hash
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

            # Add to approved dedup corpus
            try:
                if media_hash:
                    add_approved_hash(media_hash)
            except Exception as _e:
                logger.warning(
                    f"Failed to add approved hash for {file_name} in ok_callback(batch): {_e}"
                )

            # Get user metadata
            user_metadata = await storage.get_submission_metadata(new_object_name)

            # Delete from MinIO
            await storage.delete_file(file_prefix + file_name, BUCKET_MAIN)

            batch_count = await db.increment_batch_count()

            await query.message.edit_caption(
                f"Post added to batch! There are {batch_count} posts in the batch.",
                reply_markup=None,
            )
            await stats.record_added_to_batch(media_type)
            logger.info(
                f"Added {file_prefix + file_name} to batch ({batch_count} total)"
            )
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
                logger.info(
                    f"User {user_metadata.get('user_id')} was notified about approval of {file_name} from message_id {user_metadata.get('message_id')}"
                )
        finally:
            cleanup_temp_file(temp_path)
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

    message_text = query.message.caption or query.message.text
    file_path = extract_filename(message_text)
    if not file_path:
        await query.message.reply_text("Could not extract file path from the message")
        return

    file_name = os.path.basename(file_path)
    media_type = "photo" if file_path.startswith(f"{PHOTOS_PATH}/") else "video"
    file_prefix = (
        f"{PHOTOS_PATH}/"
        if file_path.startswith(f"{PHOTOS_PATH}/")
        else f"{VIDEOS_PATH}/"
    )

    try:
        if not await storage.file_exists(file_prefix + file_name, BUCKET_MAIN):
            raise MinioError(
                f"File not found: {file_prefix + file_name} in {BUCKET_MAIN}"
            )

        caption_to_send = (
            "Пост из предложки @ooodnakov_memes_suggest_bot"
            if "suggestion" in message_text
            else ""
        )

        await query.message.edit_caption(
            f"Post approved with media {file_name}!", reply_markup=None
        )

        temp_path, _ = await download_from_minio(file_prefix + file_name, BUCKET_MAIN)
        logger.info(f"Downloaded file {file_name} from {BUCKET_MAIN} to {temp_path}")
        try:
            # Use helper function to send media
            await send_media_to_telegram(
                context.bot, target_channel, temp_path, caption_to_send
            )
            logger.info(f"Created new post from image {file_path}!")

            # Add to approved dedup corpus
            try:
                user_metadata = await storage.get_submission_metadata(file_name)
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

            # Get user metadata
            user_metadata = await storage.get_submission_metadata(file_name)

            # Delete from MinIO
            await storage.delete_file(file_prefix + file_name, BUCKET_MAIN)

            await stats.record_approved(
                media_type, filename=file_name, source="push_callback"
            )

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
                    f"Отличные новости! Ваша {translated_media_type} публикация была одобрена и размещена в канале. Спасибо за ваш вклад!",
                    reply_to_message_id=user_metadata.get("message_id"),
                )
                await storage.mark_notified(file_name)
                logger.info(
                    f"User {user_metadata.get('user_id')} was notified about approval of {file_name} from message_id {user_metadata.get('message_id')}"
                )
        finally:
            cleanup_temp_file(temp_path)

        # await query.message.reply_text(f"{media_type.capitalize()} sent to channel!")
        logger.info(f"Media {file_name} sent to channel {target_channel}")
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
        message_text = query.message.caption or query.message.text
        file_path = extract_filename(message_text)
        if not file_path:
            await query.message.reply_text(
                "Could not extract file path from the message"
            )
            return

        file_name = os.path.basename(file_path)
        media_type = "photo" if file_path.startswith(f"{PHOTOS_PATH}/") else "video"

        await query.message.edit_caption(
            f"Post disapproved with media {file_name}!", reply_markup=None
        )

        file_prefix = (
            f"{PHOTOS_PATH}/"
            if file_path.startswith(f"{PHOTOS_PATH}/")
            else f"{VIDEOS_PATH}/"
        )
        # Get user metadata
        user_metadata = await storage.get_submission_metadata(file_name)
        # Delete from MinIO
        if await storage.file_exists(file_prefix + file_name, BUCKET_MAIN):
            await storage.delete_file(file_prefix + file_name, BUCKET_MAIN)
        else:
            logger.warning(
                f"File not found for deletion: {BUCKET_MAIN}/{file_prefix + file_name}"
            )

        await stats.record_rejected(
            media_type, filename=file_name, source="notok_callback"
        )

        # Notify original submitter using notify_user reply functionality
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
