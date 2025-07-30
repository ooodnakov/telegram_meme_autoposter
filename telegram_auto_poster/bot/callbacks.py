import os

from loguru import logger
from telegram import Update
from telegram.ext import ContextTypes

from telegram_auto_poster.bot.handlers import (
    get_user_friendly_error_message,
    notify_user,
)
from telegram_auto_poster.config import PHOTOS_BUCKET, VIDEOS_BUCKET, load_config
from telegram_auto_poster.utils import (
    MinioError,
    TelegramMediaError,
    cleanup_temp_file,
    download_from_minio,
    extract_filename,
    send_media_to_telegram,
)
from telegram_auto_poster.utils.stats import stats
from telegram_auto_poster.utils.storage import storage
from telegram_auto_poster.utils.captioner import DEFAULT_CAPTIONS

config = load_config()
target_channel = config["target_channel"]


async def ok_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle approval: send suggestions or add to batch"""
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
    media_type = "photo" if file_path.startswith("photos/") else "video"
    bucket = PHOTOS_BUCKET if file_path.startswith("photos/") else VIDEOS_BUCKET

    try:
        # Verify file existence
        if not storage.file_exists(file_name, bucket):
            raise MinioError(f"File not found: {file_name} in {bucket}")

        # If suggestion, approve and publish immediately
        if "suggestion" in message_text:
            caption_to_send = "Пост из предложки @ooodnakov_memes_suggest_bot"
            await query.message.edit_caption(
                f"Post approved with media {file_name}!", reply_markup=None
            )

            temp_path, _ = await download_from_minio(file_name, bucket)
            try:
                if media_type == "photo":
                    await context.bot.send_photo(
                        chat_id=target_channel,
                        photo=open(temp_path, "rb"),
                        caption=caption_to_send,
                    )
                else:
                    await context.bot.send_video(
                        chat_id=target_channel,
                        video=open(temp_path, "rb"),
                        supports_streaming=True,
                        caption=caption_to_send,
                    )
                stats.record_approved(
                    media_type, filename=file_name, source="ok_callback"
                )
                # Get user metadata
                user_metadata = storage.get_submission_metadata(file_name)

                # Delete from MinIO
                storage.delete_file(file_name, bucket)

                # Notify original submitter
                if user_metadata and not user_metadata.get("notified") and user_metadata.get("user_id"):
                    translated_media_type = "фото" if media_type == "photo" else "видео"
                    await notify_user(
                        context,
                        user_metadata.get("user_id"),
                        f"Отличные новости! Ваша {translated_media_type} публикация была одобрена и размещена в канале. Спасибо за ваш вклад!",
                        reply_to_message_id=user_metadata.get("message_id"),
                    )
                    storage.mark_notified(file_name)
                    logger.info(
                        f"User {user_metadata.get('user_id')} was notified about approval of {file_name} from message_id {user_metadata.get('message_id')}"
                    )
            finally:
                cleanup_temp_file(temp_path)
        else:
            # Add to batch in MinIO for later sending
            new_object_name = f"batch_{file_name}"
            temp_path, ext = await download_from_minio(file_name, bucket)
            try:
                # Upload with new name - use the appropriate bucket for videos and photos
                target_batch_bucket = PHOTOS_BUCKET
                # For videos, make sure we correctly identify and store in the right bucket
                if ext.lower() in [".mp4", ".avi", ".mov"] or bucket == VIDEOS_BUCKET:
                    target_batch_bucket = PHOTOS_BUCKET  # We'll store all batch files in PHOTOS_BUCKET for consistency

                storage.upload_file(temp_path, target_batch_bucket, new_object_name)

                # Get user metadata
                user_metadata = storage.get_submission_metadata(new_object_name)

                # Delete from MinIO
                storage.delete_file(file_name, bucket)

                batch_count = len(
                    storage.list_files(PHOTOS_BUCKET, prefix="batch_")
                ) + len(storage.list_files(VIDEOS_BUCKET, prefix="batch_"))

                await query.message.edit_caption(
                    f"Post added to batch! There are {batch_count} posts in the batch.",
                    reply_markup=None,
                )
                stats.record_added_to_batch(media_type)
                logger.info(f"Added {file_name} to batch ({batch_count} total)")
                # Notify original submitter
                if user_metadata and not user_metadata.get("notified") and user_metadata.get("user_id"):
                    translated_media_type = "фото" if media_type == "photo" else "видео"
                    await notify_user(
                        context,
                        user_metadata.get("user_id"),
                        f"Отличные новости! Ваша {translated_media_type} публикация была одобрена и скоро будет размещена. Спасибо за ваш вклад!",
                        reply_to_message_id=user_metadata.get("message_id"),
                    )
                    storage.mark_notified(file_name)
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
        stats.record_error("processing", f"Error in ok_callback: {str(e)}")
        await query.message.reply_text(f"An unexpected error occurred: {str(e)}")


async def push_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle direct publish of approved media"""
    logger.info(
        f"Received /push callback from user {update.callback_query.from_user.id}"
    )
    logger.debug(f"Callback data: {update.callback_query.data}")

    query = update.callback_query
    await query.answer()

    message_text = query.message.caption or query.message.text
    file_path = extract_filename(message_text)
    if not file_path:
        await query.message.reply_text("Could not extract file path from the message")
        return

    file_name = os.path.basename(file_path)
    media_type = "photo" if file_path.startswith("photos/") else "video"
    bucket = PHOTOS_BUCKET if file_path.startswith("photos/") else VIDEOS_BUCKET

    try:
        if not storage.file_exists(file_name, bucket):
            raise MinioError(f"File not found: {file_name} in {bucket}")

        caption_to_send = (
            "Пост из предложки @ooodnakov_memes_suggest_bot"
            if "suggestion" in message_text
            else ""
        )

        await query.message.edit_caption(
            f"Post approved with media {file_name}!", reply_markup=None
        )

        temp_path, _ = await download_from_minio(file_name, bucket)
        logger.info(f"Downloaded file {file_name} from {bucket} to {temp_path}")
        try:
            # Use helper function to send media
            await send_media_to_telegram(
                context.bot, target_channel, temp_path, caption_to_send
            )
            logger.info(f"Created new post from image {file_path}!")

            # Get user metadata
            user_metadata = storage.get_submission_metadata(file_name)

            # Delete from MinIO
            storage.delete_file(file_name, bucket)

            stats.record_approved(
                media_type, filename=file_name, source="push_callback"
            )

            # Notify original submitter
            if user_metadata and not user_metadata.get("notified") and user_metadata.get("user_id"):
                translated_media_type = "фото" if media_type == "photo" else "видео"
                await notify_user(
                    context,
                    user_metadata.get("user_id"),
                    f"Отличные новости! Ваша {translated_media_type} публикация была одобрена и размещена в канале. Спасибо за ваш вклад!",
                    reply_to_message_id=user_metadata.get("message_id"),
                )
                storage.mark_notified(file_name)
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
        stats.record_error("processing", f"Error in push_callback: {str(e)}")
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
        media_type = "photo" if file_path.startswith("photos/") else "video"

        await query.message.edit_caption(
            f"Post disapproved with media {file_name}!", reply_markup=None
        )

        bucket = PHOTOS_BUCKET if file_path.startswith("photos/") else VIDEOS_BUCKET
        # Get user metadata
        user_metadata = storage.get_submission_metadata(file_name)
        # Delete from MinIO
        if storage.file_exists(file_name, bucket):
            storage.delete_file(file_name, bucket)
        else:
            logger.warning(f"File not found for deletion: {bucket}/{file_name}")

        stats.record_rejected(media_type, filename=file_name, source="notok_callback")

        # Notify original submitter using notify_user reply functionality
        if user_metadata and not user_metadata.get("notified") and user_metadata.get("user_id"):
            translated_media_type = "фото" if media_type == "photo" else "видео"
            await notify_user(
                context,
                user_metadata.get("user_id"),
                f"Ваша {translated_media_type} публикация была рассмотрена, но не была опубликована. Вы можете попробовать еще раз в будущем!",
                reply_to_message_id=user_metadata.get("message_id"),
            )
            storage.mark_notified(file_name)
            logger.info(
                f"Notified user {user_metadata.get('user_id')} about rejection of {file_name} from message_id {user_metadata.get('message_id')}"
            )
    except Exception as e:
        logger.error(f"Error in notok_callback: {e}")
        await query.message.reply_text(get_user_friendly_error_message(e))


async def caption_select_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send media to channel using selected caption"""
    logger.info(
        f"Received caption selection from user {update.callback_query.from_user.id}"
    )
    query = update.callback_query
    await query.answer()

    data = query.data
    prefix = "cap_"
    if not data.startswith(prefix):
        return
    try:
        index_str, bucket, file_name = data[len(prefix) :].split(":", 2)
        index = int(index_str)
    except ValueError:
        await query.message.reply_text("Неверные данные подписи")
        return

    captions = context.bot_data.get("caption_choices", {}).get(file_name, DEFAULT_CAPTIONS)
    caption = captions[index] if index < len(captions) else ""
    temp_path, _ = await download_from_minio(file_name, bucket)
    try:
        await send_media_to_telegram(context.bot, target_channel, temp_path, caption)
        storage.delete_file(file_name, bucket)
        media_type = "photo" if file_name.endswith(('.jpg', '.jpeg', '.png')) else "video"
        stats.record_approved(media_type, filename=file_name, source="caption_select_callback")
        await query.message.edit_caption(f"Пост отправлен: {caption}", reply_markup=None)
    except Exception as e:  # pragma: no cover - network errors
        logger.error(f"Error in caption_select_callback: {e}")
        await query.message.reply_text(get_user_friendly_error_message(e))
    finally:
        cleanup_temp_file(temp_path)
