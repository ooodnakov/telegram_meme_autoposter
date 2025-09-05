import asyncio
import os
import tempfile
import time
import uuid
from typing import IO

from loguru import logger
from telegram import InputMediaPhoto, InputMediaVideo, Update
from telegram.ext import ContextTypes

from telegram_auto_poster.config import (
    BUCKET_MAIN,
    CONFIG,
    PHOTOS_PATH,
    VIDEOS_PATH,
)
from telegram_auto_poster.media.photo import add_watermark_to_image
from telegram_auto_poster.media.video import add_watermark_to_video
from telegram_auto_poster.utils.caption import generate_caption
from telegram_auto_poster.utils.deduplication import (
    calculate_image_hash,
    calculate_video_hash,
    is_duplicate_hash,
)
from telegram_auto_poster.utils.general import (
    MediaError,
    MinioError,
    TelegramMediaError,
    cleanup_temp_file,
    download_from_minio,
)
from telegram_auto_poster.utils.i18n import _, resolve_locale, set_locale
from telegram_auto_poster.utils.stats import stats
from telegram_auto_poster.utils.storage import storage
from telegram_auto_poster.utils.ui import approval_keyboard

# Define error constants
ERROR_MINIO_FILE_NOT_FOUND = "File not found in MinIO storage"
ERROR_MINIO_DOWNLOAD_FAILED = "Failed to download file from MinIO"
ERROR_TELEGRAM_SEND_FAILED = "Failed to send media to Telegram"
ERROR_TEMP_FILE_CREATION = "Failed to create temporary file"
ERROR_FILE_NOT_SUPPORTED = "File type not supported"
MAX_RETRIES = 5
RETRY_DELAY = 1


# Helper function to handle common errors and return appropriate user messages
def get_user_friendly_error_message(error):
    """Convert system errors to user-friendly messages"""
    if isinstance(error, MinioError):
        if ERROR_MINIO_FILE_NOT_FOUND in str(error):
            return "The requested media file could not be found. It might have been deleted or moved."
        else:
            return "There was a problem accessing the media storage. Please try again later."
    elif isinstance(error, TelegramMediaError):
        return "There was a problem sending the media. Please try again later."
    elif isinstance(error, FileNotFoundError):
        return "The media file could not be accessed. It might have been deleted."
    else:
        return f"An error occurred: {str(error)}"


def get_file_name(caption):
    return caption.split("\n")[-1]


async def handle_photo(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
):
    """Handle photo uploads"""
    set_locale(resolve_locale(update))
    file_id = update.message.photo[-1].file_id
    message_id = update.message.message_id
    user_id = update.effective_user.id
    file_name = f"photo_{chat_id}_{message_id}.jpg"
    logger.info(f"file_name {file_name}, message_id {message_id}")
    # Record received media
    await stats.record_received("photo")

    temp_path = None
    try:
        # Download to temp file with correct extension
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
        temp_path = temp_file.name
        temp_file.close()

        # Download from Telegram
        start_time = time.time()
        f = await context.bot.get_file(file_id)
        await f.download_to_drive(temp_path)
        download_time = time.time() - start_time

        download_time = time.time() - start_time
        logger.info(f"Photo from chat {chat_id} has downloaded in {download_time:.2f}s")

        image_hash = calculate_image_hash(temp_path)
        if is_duplicate_hash(image_hash):
            logger.info(f"Duplicate photo detected, hash: {image_hash}. Skipping.")
            await stats.record_rejected("photo", file_name, "duplicate")
            await update.message.reply_text(
                _("Этот пост уже есть в канале."),
                do_quote=True,
            )
            return

        user_metadata = {
            "user_id": user_id,
            "chat_id": chat_id,
            "message_id": message_id,
            "media_type": "photo",
        }

        # Process the photo
        await process_photo(
            "New suggestion in bot",
            temp_path,
            file_name,
            context.bot_data["chat_id"],
            context.application,
            user_metadata=user_metadata,
            media_hash=image_hash,
        )

        # Send confirmation to user
        await update.message.reply_text(
            _(
                "Спасибо за вашу предложку! Мы рассмотрим её и сообщим вам, если она будет одобрена."
            ),
            do_quote=True,
        )
    except Exception as e:
        logger.error(f"Error handling photo: {e}")
        await stats.record_error("processing", f"Error handling photo: {str(e)}")
        await update.message.reply_text(
            _(
                "Произошла ошибка при обработке вашего фото. Пожалуйста, попробуйте позже."
            ),
            do_quote=True,
        )
    finally:
        cleanup_temp_file(temp_path)


async def handle_video(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
):
    """Handle video uploads"""
    set_locale(resolve_locale(update))
    logger.info(f"Video from chat {chat_id} has started downloading!")
    file_id = update.message.video.file_id
    message_id = update.message.message_id
    user_id = update.effective_user.id
    file_name = f"video_{chat_id}_{message_id}.mp4"

    # Record received media
    await stats.record_received("video")

    temp_path = None
    try:
        # Download to temp file with correct extension
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
        temp_path = temp_file.name
        temp_file.close()

        # Download from Telegram
        start_time = time.time()
        f = await context.bot.get_file(file_id)
        await f.download_to_drive(temp_path)
        download_time = time.time() - start_time

        download_time = time.time() - start_time
        logger.info(f"Video from chat {chat_id} has downloaded in {download_time:.2f}s")

        video_hash = calculate_video_hash(temp_path)
        if is_duplicate_hash(video_hash):
            logger.info(f"Duplicate video detected, hash: {video_hash}. Skipping.")
            await stats.record_rejected("video", file_name, "duplicate")
            await update.message.reply_text(
                _("Этот пост уже есть в канале."),
                do_quote=True,
            )
            return

        user_metadata = {
            "user_id": user_id,
            "chat_id": chat_id,
            "message_id": message_id,
            "media_type": "video",
        }

        # Process the video
        await process_video(
            "New suggestion in bot",
            temp_path,
            file_name,
            context.bot_data["chat_id"],
            context.application,
            user_metadata=user_metadata,
            media_hash=video_hash,
        )

        # Send confirmation to user
        await update.message.reply_text(
            _(
                "Спасибо за ваше видео! Мы его рассмотрим и сообщим, если оно будет одобрено."
            ),
            do_quote=True,
        )
    except Exception as e:
        logger.error(f"Error handling video: {e}")
        await stats.record_error("processing", f"Error handling video: {str(e)}")
        await update.message.reply_text(
            _(
                "Произошла ошибка при обработке вашего видео. Пожалуйста, попробуйте позже."
            ),
            do_quote=True,
        )
    finally:
        cleanup_temp_file(temp_path)


async def notify_user(
    context, user_id, message, reply_to_message_id=None, media_type=None
):
    """Send a notification to a user about their submission status

    Args:
        context: The bot context
        user_id: The user's Telegram ID
        message: The message to send
        reply_to_message_id: Optional message_id to reply to
        media_type: Optional media type for stats tracking
    """
    try:
        params = {"chat_id": user_id, "text": message}
        if reply_to_message_id and user_id:
            params["reply_to_message_id"] = reply_to_message_id
        await context.bot.send_message(**params)
        logger.info(
            f"Sent notification to user {user_id} with reply_to {reply_to_message_id}"
        )
    except Exception as e:
        logger.error(f"Failed to send notification to user {user_id}: {e}")
        await stats.record_error("telegram", f"Failed to notify user: {str(e)}")


async def _send_to_review(
    processed_name: str,
    path_prefix: str,
    extension: str,
    send_func,
    user_metadata: dict | None,
    media_hash: str | None,
    media_type: str,
):
    keyboard = approval_keyboard()

    temp_path, _ = await download_from_minio(
        f"{path_prefix}/{processed_name}", BUCKET_MAIN, extension
    )

    caption = ""
    if CONFIG.caption.enabled:
        caption = await asyncio.to_thread(
            generate_caption, temp_path, CONFIG.caption.target_lang
        )

    if user_metadata:
        await storage.store_submission_metadata(
            processed_name,
            user_metadata["user_id"],
            user_metadata["chat_id"],
            user_metadata["media_type"],
            user_metadata["message_id"],
            media_hash=media_hash,
            caption=caption,
        )

    try:
        with open(temp_path, "rb") as media_file:
            msg = await send_func(media_file, caption, keyboard)
        await storage.store_review_message(processed_name, msg.chat_id, msg.message_id)
        logger.info(f"New {media_type} {processed_name} in channel!")
    except Exception as e:
        logger.error(f"Failed to send {media_type} to review channel: {e}")
        await stats.record_error(
            "telegram", f"Failed to send {media_type} to review: {str(e)}"
        )
        raise TelegramMediaError(f"Failed to send {media_type} to review: {str(e)}")
    finally:
        cleanup_temp_file(temp_path)
    return True


async def process_photo(
    custom_text: str,
    input_path: str,
    original_name: str,
    bot_chat_id: str,
    application,
    user_metadata: dict = None,
    media_hash: str = None,
):
    """Process a photo by adding watermark and sending to review bot"""
    start_time = time.time()
    try:
        # Add watermark and upload to MinIO
        processed_name = f"processed_{os.path.basename(original_name)}"

        await add_watermark_to_image(
            input_path,
            processed_name,
            user_metadata=user_metadata,
            media_hash=media_hash,
        )

        # Record processing time
        processing_time = time.time() - start_time
        await stats.record_processed("photo", processing_time)

        # Check if processed file exists in MinIO, with retries for eventual consistency
        file_found = False
        for i in range(MAX_RETRIES):
            if await storage.file_exists(
                PHOTOS_PATH + "/" + processed_name, BUCKET_MAIN
            ):
                file_found = True
                break
            logger.warning(
                f"Attempt {i + 1}/{MAX_RETRIES}: Processed photo not yet found in MinIO: {processed_name}. Retrying in {RETRY_DELAY}s..."
            )
            await asyncio.sleep(RETRY_DELAY)

        if not file_found:
            logger.error(
                f"Processed photo not found in MinIO after {MAX_RETRIES} retries: {processed_name}"
            )
            await stats.record_error(
                "processing", f"Processed photo not found: {processed_name}"
            )
            raise MinioError(f"Processed photo not found in MinIO: {processed_name}")

        async def _send(media_file, caption, keyboard):
            return await application.bot.send_photo(
                bot_chat_id,
                media_file,
                custom_text
                + "\nNew post found\n"
                + f"{PHOTOS_PATH}/{processed_name}"
                + (f"\nSuggested caption:\n{caption}" if caption else ""),
                reply_markup=keyboard,
                read_timeout=60,
                write_timeout=60,
                connect_timeout=60,
                pool_timeout=60,
            )

        await _send_to_review(
            processed_name,
            PHOTOS_PATH,
            ".jpg",
            _send,
            user_metadata,
            media_hash,
            "photo",
        )
        return True
    except MinioError as e:
        logger.error(f"MinIO error in process_photo: {e}")
        await stats.record_error("storage", f"MinIO error: {str(e)}")
    except MediaError as e:
        logger.error(f"Media processing error in process_photo: {e}")
        await stats.record_error("processing", f"Media error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error in process_photo: {e}")
        await stats.record_error("processing", f"Unexpected error: {str(e)}")
    return False


async def process_video(
    custom_text: str,
    input_path: str,
    original_name: str,
    bot_chat_id: str,
    application,
    user_metadata: dict = None,
    media_hash: str = None,
):
    """Process a video and send to review bot"""
    start_time = time.time()
    try:
        # Add watermark and upload to MinIO
        processed_name = f"processed_{os.path.basename(original_name)}"

        # Add watermark to video and upload to MinIO
        await add_watermark_to_video(
            input_path,
            processed_name,
            user_metadata=user_metadata,
            media_hash=media_hash,
        )

        # Record processing time
        processing_time = time.time() - start_time
        await stats.record_processed("video", processing_time)

        # Check if processed file exists in MinIO, with retries for eventual consistency
        file_found = False
        for i in range(MAX_RETRIES):
            if await storage.file_exists(
                VIDEOS_PATH + "/" + processed_name, BUCKET_MAIN
            ):
                file_found = True
                break
            logger.warning(
                f"Attempt {i + 1}/{MAX_RETRIES}: Processed video not yet found in MinIO: {processed_name}. Retrying in {RETRY_DELAY}s..."
            )
            await asyncio.sleep(RETRY_DELAY)

        if not file_found:
            logger.error(
                f"Processed video not found in MinIO after {MAX_RETRIES} retries: {processed_name}"
            )
            await stats.record_error(
                "processing", f"Processed video not found: {processed_name}"
            )
            raise MinioError(f"Processed video not found in MinIO: {processed_name}")

        async def _send(media_file, caption, keyboard):
            return await application.bot.send_video(
                chat_id=bot_chat_id,
                video=media_file,
                caption=custom_text
                + "\nNew post found\n"
                + f"{VIDEOS_PATH}/{processed_name}"
                + (f"\nSuggested caption:\n{caption}" if caption else ""),
                supports_streaming=True,
                reply_markup=keyboard,
                read_timeout=60,
                write_timeout=60,
                connect_timeout=60,
                pool_timeout=60,
            )

        await _send_to_review(
            processed_name,
            VIDEOS_PATH,
            ".mp4",
            _send,
            user_metadata,
            media_hash,
            "video",
        )
        return True
    except MinioError as e:
        logger.error(f"MinIO error in process_video: {e}")
        await stats.record_error("storage", f"MinIO error: {str(e)}")
    except MediaError as e:
        logger.error(f"Media processing error in process_video: {e}")
        await stats.record_error("processing", f"Media error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error in process_video: {e}")
        await stats.record_error("processing", f"Unexpected error: {str(e)}")
    return False


async def process_media_group(
    custom_text: str,
    media_files: list[tuple[str, str, str]],
    bot_chat_id: str,
    application,
):
    """Process a list of media files and send as a media group."""
    processed: list[tuple[str, str]] = []
    group_id = uuid.uuid4().hex
    temp_files: list[tuple[str, IO[bytes]]] = []
    media_config = {
        "photo": (add_watermark_to_image, PHOTOS_PATH, ".jpg", InputMediaPhoto),
        "video": (add_watermark_to_video, VIDEOS_PATH, ".mp4", InputMediaVideo),
    }

    try:
        for input_path, original_name, media_type in media_files:
            processed_name = f"processed_{os.path.basename(original_name)}"
            watermark_func, _, _, _ = media_config[media_type]
            start_time = time.time()
            await watermark_func(input_path, processed_name, group_id=group_id)
            processing_time = time.time() - start_time
            await stats.record_processed(media_type, processing_time)
            processed.append((processed_name, media_type))
        # Download processed files and send as a single media group
        # (chunked by 10 to respect Telegram limits)
        input_media: list[tuple[str, str, object, IO[bytes]]] = []
        # tuple: (processed_name, object_path, input_media_obj, file_handle)
        for processed_name, media_type in processed:
            _, path_prefix, extension, media_cls = media_config[media_type]
            object_path = f"{path_prefix}/{processed_name}"
            temp_path, _ = await download_from_minio(
                object_path, BUCKET_MAIN, extension
            )
            fh = open(temp_path, "rb")
            temp_files.append((temp_path, fh))
            if media_type == "photo":
                im = media_cls(fh)
            else:
                # InputMediaVideo supports supports_streaming
                im = media_cls(fh, supports_streaming=True)
            input_media.append((processed_name, object_path, im, fh))

        sent_paths: list[str] = []
        if input_media:
            # Chunk by 10
            for i in range(0, len(input_media), 10):
                chunk = input_media[i : i + 10]
                media_group = [im for _, _, im, _ in chunk]
                try:
                    msgs = await application.bot.send_media_group(
                        chat_id=bot_chat_id,
                        media=media_group,
                        read_timeout=60,
                        write_timeout=60,
                        connect_timeout=60,
                        pool_timeout=60,
                    )
                except Exception as e:
                    logger.error(f"Failed to send media group to review channel: {e}")
                    await stats.record_error(
                        "telegram", f"Failed to send media group: {str(e)}"
                    )
                    raise
                # Store mapping for each message
                for (processed_name, object_path, _im, _fh), msg in zip(chunk, msgs):
                    await storage.store_review_message(
                        processed_name, msg.chat_id, msg.message_id
                    )
                    sent_paths.append(object_path)

            # Send the summary message with keyboard for approval actions
            keyboard = approval_keyboard()
            summary_text = custom_text + "\nNew grouped post:\n" + "\n".join(sent_paths)
            await application.bot.send_message(
                chat_id=bot_chat_id,
                text=summary_text,
                reply_markup=keyboard,
                read_timeout=60,
                write_timeout=60,
                connect_timeout=60,
                pool_timeout=60,
            )
            logger.info(
                "New media group in review chat (album): {}".format(
                    ", ".join(sent_paths)
                )
            )
        return True
    except Exception as e:
        logger.error(f"Failed to process media group: {e}")
        await stats.record_error("processing", f"Media group error: {str(e)}")
    finally:
        for temp_path, handle in temp_files:
            try:
                handle.close()
            finally:
                cleanup_temp_file(temp_path)
    return False


async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle media uploads from users"""
    set_locale(resolve_locale(update))
    chat_id = update.effective_chat.id
    try:
        if update.message and update.message.photo:
            await handle_photo(update, context, chat_id)
        elif update.message and update.message.video:
            await handle_video(update, context, chat_id)
        else:
            logger.warning(f"Unsupported media type from chat {chat_id}")
    except Exception as e:
        logger.error(f"Error in handle_media: {e}")
        await stats.record_error("processing", f"Error handling media: {str(e)}")
        await update.message.reply_text(
            _(
                "Произошла ошибка при обработке вашего сообщения. Пожалуйста, попробуйте позже."
            ),
            do_quote=True,
        )
