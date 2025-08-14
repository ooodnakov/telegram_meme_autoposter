import os
import tempfile
import time

from loguru import logger
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import ContextTypes

from telegram_auto_poster.utils import (
    MediaError,
    MinioError,
    TelegramMediaError,
    cleanup_temp_file,
    download_from_minio,
)

from ..config import (
    BUCKET_MAIN,
    PHOTOS_PATH,
    VIDEOS_PATH,
)
from ..media.photo import add_watermark_to_image
from ..media.video import add_watermark_to_video
from ..utils.deduplication import (
    calculate_image_hash,
    calculate_video_hash,
    is_duplicate_hash,
)
from ..utils.stats import stats
from ..utils.storage import storage

# Define error constants
ERROR_MINIO_FILE_NOT_FOUND = "File not found in MinIO storage"
ERROR_MINIO_DOWNLOAD_FAILED = "Failed to download file from MinIO"
ERROR_TELEGRAM_SEND_FAILED = "Failed to send media to Telegram"
ERROR_TEMP_FILE_CREATION = "Failed to create temporary file"
ERROR_FILE_NOT_SUPPORTED = "File type not supported"


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
    file_id = update.message.photo[-1].file_id
    message_id = update.message.message_id
    user_id = update.effective_user.id
    file_name = f"downloaded_image_{chat_id}_{file_id}_{message_id}.jpg"
    logger.info(f"file_name {file_name}, message_id {message_id}")
    # Record received media
    stats.record_received("photo")

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
            stats.record_rejected("photo", file_name, "duplicate")
            await update.message.reply_text(
                "Этот пост уже есть в канале.",
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
            "Спасибо за вашу предложку! Мы рассмотрим её и сообщим вам, если она будет одобрена.",
            do_quote=True,
        )
    except Exception as e:
        logger.error(f"Error handling photo: {e}")
        stats.record_error("processing", f"Error handling photo: {str(e)}")
        await update.message.reply_text(
            "Произошла ошибка при обработке вашего фото. Пожалуйста, попробуйте позже.",
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
    logger.info(f"Video from chat {chat_id} has started downloading!")
    file_id = update.message.video.file_id
    message_id = update.message.message_id
    user_id = update.effective_user.id
    file_name = f"downloaded_video_{chat_id}_{file_id}_{message_id}.mp4"

    # Record received media
    stats.record_received("video")

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
            stats.record_rejected("video", file_name, "duplicate")
            await update.message.reply_text(
                "Этот пост уже есть в канале.",
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
            "Спасибо за ваше видео! Мы его рассмотрим и сообщим, если оно будет одобрено.",
            do_quote=True,
        )
    except Exception as e:
        logger.error(f"Error handling video: {e}")
        stats.record_error("processing", f"Error handling video: {str(e)}")
        await update.message.reply_text(
            "Произошла ошибка при обработке вашего видео. Пожалуйста, попробуйте позже.",
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
        stats.record_error("telegram", f"Failed to notify user: {str(e)}")


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

        # Copy user metadata to processed file if exists
        if user_metadata:
            storage.store_submission_metadata(
                processed_name,
                user_metadata["user_id"],
                user_metadata["chat_id"],
                user_metadata["media_type"],
                user_metadata["message_id"],
                media_hash=media_hash,
            )

        # Record processing time
        processing_time = time.time() - start_time
        stats.record_processed("photo", processing_time)

        # Check if processed file exists in MinIO, with retries for eventual consistency
        max_retries = 5
        retry_delay = 1  # seconds
        file_found = False
        for i in range(max_retries):
            if storage.file_exists(PHOTOS_PATH + "/" + processed_name, BUCKET_MAIN):
                file_found = True
                break
            logger.warning(
                f"Attempt {i+1}/{max_retries}: Processed photo not yet found in MinIO: {processed_name}. Retrying in {retry_delay}s..."
            )
            time.sleep(retry_delay)

        if not file_found:
            logger.error(
                f"Processed photo not found in MinIO after {max_retries} retries: {processed_name}"
            )
            stats.record_error(
                "processing", f"Processed photo not found: {processed_name}"
            )
            raise MinioError(f"Processed photo not found in MinIO: {processed_name}")

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("Send to batch!", callback_data="/ok"),
                    InlineKeyboardButton("Schedule", callback_data="/schedule"),
                ],
                [
                    InlineKeyboardButton("Push!", callback_data="/push"),
                    InlineKeyboardButton("No!", callback_data="/notok"),
                ],
            ]
        )

        # Download to temp file for bot with correct extension
        temp_path, _ = await download_from_minio(
            PHOTOS_PATH + "/" + processed_name, BUCKET_MAIN, ".jpg"
        )

        try:
            # Send photo using bot
            await application.bot.send_photo(
                bot_chat_id,
                open(temp_path, "rb"),
                custom_text + "\nNew post found\n" + f"{PHOTOS_PATH}/{processed_name}",
                reply_markup=keyboard,
                read_timeout=60,
                write_timeout=60,
                connect_timeout=60,
                pool_timeout=60,
            )
            logger.info(f"New photo {processed_name} in channel!")
        except Exception as e:
            logger.error(f"Failed to send photo to review channel: {e}")
            stats.record_error("telegram", f"Failed to send to review: {str(e)}")
            raise TelegramMediaError(f"Failed to send photo to review: {str(e)}")
        finally:
            cleanup_temp_file(temp_path)
        return True
    except MinioError as e:
        logger.error(f"MinIO error in process_photo: {e}")
        stats.record_error("storage", f"MinIO error: {str(e)}")
    except MediaError as e:
        logger.error(f"Media processing error in process_photo: {e}")
        stats.record_error("processing", f"Media error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error in process_photo: {e}")
        stats.record_error("processing", f"Unexpected error: {str(e)}")
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

        # Copy user metadata to processed file if exists
        if user_metadata:
            storage.store_submission_metadata(
                processed_name,
                user_metadata["user_id"],
                user_metadata["chat_id"],
                user_metadata["media_type"],
                user_metadata["message_id"],
                media_hash=media_hash,
            )

        # Record processing time
        processing_time = time.time() - start_time
        stats.record_processed("video", processing_time)

        # Check if processed file exists in MinIO, with retries for eventual consistency
        max_retries = 5
        retry_delay = 1  # seconds
        file_found = False
        for i in range(max_retries):
            if storage.file_exists(VIDEOS_PATH + "/" + processed_name, BUCKET_MAIN):
                file_found = True
                break
            logger.warning(
                f"Attempt {i+1}/{max_retries}: Processed video not yet found in MinIO: {processed_name}. Retrying in {retry_delay}s..."
            )
            time.sleep(retry_delay)

        if not file_found:
            logger.error(
                f"Processed video not found in MinIO after {max_retries} retries: {processed_name}"
            )
            stats.record_error(
                "processing", f"Processed video not found: {processed_name}"
            )
            raise MinioError(f"Processed video not found in MinIO: {processed_name}")

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("Send to batch!", callback_data="/ok"),
                    InlineKeyboardButton("Schedule", callback_data="/schedule"),
                ],
                [
                    InlineKeyboardButton("Push!", callback_data="/push"),
                    InlineKeyboardButton("No!", callback_data="/notok"),
                ],
            ]
        )

        # Download to temp file for bot with correct extension
        temp_path, _ = await download_from_minio(
            VIDEOS_PATH + "/" + processed_name, BUCKET_MAIN, ".mp4"
        )

        try:
            # Send video using bot
            with open(temp_path, "rb") as media_file:
                await application.bot.send_video(
                    chat_id=bot_chat_id,
                    video=media_file,
                    caption=custom_text
                    + "\nNew post found\n"
                    + f"{VIDEOS_PATH}/{processed_name}",
                    supports_streaming=True,
                    reply_markup=keyboard,
                    read_timeout=60,
                    write_timeout=60,
                    connect_timeout=60,
                    pool_timeout=60,
                )
            logger.info(f"New video {processed_name} in channel!")
        except Exception as e:
            logger.error(f"Failed to send video to review channel: {e}")
            stats.record_error("telegram", f"Failed to send video to review: {str(e)}")
            raise TelegramMediaError(f"Failed to send video to review: {str(e)}")
        finally:
            cleanup_temp_file(temp_path)
        return True
    except MinioError as e:
        logger.error(f"MinIO error in process_video: {e}")
        stats.record_error("storage", f"MinIO error: {str(e)}")
    except MediaError as e:
        logger.error(f"Media processing error in process_video: {e}")
        stats.record_error("processing", f"Media error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error in process_video: {e}")
        stats.record_error("processing", f"Unexpected error: {str(e)}")
    return False


async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle media uploads from users"""
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
        stats.record_error("processing", f"Error handling media: {str(e)}")
        await update.message.reply_text(
            "Произошла ошибка при обработке вашего сообщения. Пожалуйста, попробуйте позже.",
            do_quote=True,
        )
