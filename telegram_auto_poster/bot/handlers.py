import os
import asyncio
import tempfile
from typing import Optional, Tuple, Dict, Any
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    InputMediaVideo,
)
from telegram.ext import ContextTypes
from telegram.error import TimedOut, NetworkError, BadRequest
from loguru import logger

from ..media.photo import add_watermark_to_image
from ..media.video import add_watermark_to_video
from ..config import LUBA_CHAT, load_config
from ..client.client import client_instance
from ..utils.storage import storage, PHOTOS_BUCKET, VIDEOS_BUCKET, DOWNLOADS_BUCKET

# Load target_channel from config
config = load_config()
target_channel = config["target_channel"]

# Define error constants
ERROR_MINIO_FILE_NOT_FOUND = "File not found in MinIO storage"
ERROR_MINIO_DOWNLOAD_FAILED = "Failed to download file from MinIO"
ERROR_TELEGRAM_SEND_FAILED = "Failed to send media to Telegram"
ERROR_TEMP_FILE_CREATION = "Failed to create temporary file"
ERROR_FILE_NOT_SUPPORTED = "File type not supported"


# Custom exceptions
class MinioError(Exception):
    """Raised when there's an issue with MinIO operations"""

    pass


class MediaError(Exception):
    """Raised when there's an issue with media processing"""

    pass


class TelegramMediaError(Exception):
    """Raised when there's an issue sending media to Telegram"""

    pass


# Helper function to get the client from context or global variable
def get_client(context=None):
    # First try to get client from context
    if (
        context
        and hasattr(context, "bot_data")
        and "telethon_client" in context.bot_data
    ):
        return context.bot_data["telethon_client"]

    # Fall back to global instance
    if client_instance:
        return client_instance

    # No client available
    logger.error("No Telethon client available!")
    return None


# Helper function to get file extension
def get_file_extension(filename):
    _, ext = os.path.splitext(filename)
    return ext if ext else ".unknown"


# Helper function to download a file from MinIO to a temporary file
async def download_from_minio(
    object_name, bucket, extension=None
) -> Tuple[Optional[str], Optional[str]]:
    """
    Download a file from MinIO to a temporary file.

    Args:
        object_name: The name of the object in MinIO
        bucket: The MinIO bucket to download from
        extension: Optional file extension to use

    Returns:
        Tuple of (temp_file_path, extension) or (None, None) if download fails

    Raises:
        MinioError: If there's an issue with MinIO operations
    """
    if not object_name or not bucket:
        logger.error(f"Invalid parameters: object_name={object_name}, bucket={bucket}")
        return None, None

    try:
        if not storage.file_exists(object_name, bucket):
            logger.warning(f"File {object_name} does not exist in bucket {bucket}")
            raise MinioError(f"{ERROR_MINIO_FILE_NOT_FOUND}: {object_name} in {bucket}")

        # If extension not provided, get from filename
        if not extension:
            extension = get_file_extension(object_name)

        # Create temp file with correct extension
        try:
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=extension)
            temp_path = temp_file.name
            temp_file.close()
        except (IOError, OSError) as e:
            logger.error(f"Failed to create temporary file: {e}")
            raise MinioError(f"{ERROR_TEMP_FILE_CREATION}: {str(e)}")

        try:
            # Download file from MinIO to temp file
            storage.download_file(object_name, bucket, temp_path)
            logger.debug(
                f"Successfully downloaded {object_name} from {bucket} to {temp_path}"
            )
            return temp_path, extension
        except Exception as e:
            logger.error(f"Error downloading file from MinIO: {e}")
            cleanup_temp_file(temp_path)
            raise MinioError(f"{ERROR_MINIO_DOWNLOAD_FAILED}: {str(e)}")
    except MinioError:
        # Re-raise MinioError to be caught by caller
        raise
    except Exception as e:
        logger.error(f"Unexpected error in download_from_minio: {e}")
        raise MinioError(f"Unexpected error: {str(e)}")


# Helper function to send media to Telegram
async def send_media_to_telegram(
    bot, chat_id, file_path, caption=None, supports_streaming=True
):
    """
    Send media to Telegram based on file extension.

    Args:
        bot: The Telegram bot instance
        chat_id: The chat ID to send to
        file_path: The path to the media file
        caption: Optional caption for the media
        supports_streaming: Whether video streaming is supported

    Returns:
        The message sent or None if sending fails

    Raises:
        TelegramMediaError: If there's an issue sending media to Telegram
        FileNotFoundError: If the file does not exist
    """
    if not os.path.exists(file_path):
        logger.error(f"File {file_path} does not exist")
        raise FileNotFoundError(f"File {file_path} does not exist")

    try:
        ext = get_file_extension(file_path).lower()

        # Max retries for sending media
        max_retries = 3
        retry_count = 0
        last_error = None

        while retry_count < max_retries:
            try:
                if ext in [".jpg", ".jpeg", ".png"]:
                    with open(file_path, "rb") as media_file:
                        return await bot.send_photo(
                            chat_id=chat_id,
                            photo=media_file,
                            caption=caption,
                            read_timeout=60,
                            write_timeout=60,
                        )
                elif ext in [".mp4", ".avi", ".mov"]:
                    with open(file_path, "rb") as media_file:
                        return await bot.send_video(
                            chat_id=chat_id,
                            video=media_file,
                            caption=caption,
                            supports_streaming=supports_streaming,
                            read_timeout=60,
                            write_timeout=60,
                        )
                elif ext in [".gif"]:
                    with open(file_path, "rb") as media_file:
                        return await bot.send_animation(
                            chat_id=chat_id,
                            animation=media_file,
                            caption=caption,
                            read_timeout=60,
                            write_timeout=60,
                        )
                else:
                    logger.warning(f"Unsupported file type {ext}, sending as document")
                    with open(file_path, "rb") as media_file:
                        return await bot.send_document(
                            chat_id=chat_id,
                            document=media_file,
                            caption=caption,
                            read_timeout=60,
                            write_timeout=60,
                        )
            except (TimedOut, NetworkError) as e:
                # These errors are retryable
                retry_count += 1
                last_error = e
                wait_time = 2**retry_count  # Exponential backoff
                logger.warning(
                    f"Network error, retrying in {wait_time}s (attempt {retry_count}/{max_retries}): {e}"
                )
                await asyncio.sleep(wait_time)
            except BadRequest as e:
                # Bad request errors are usually not retryable
                logger.error(f"Bad request error when sending media: {e}")
                raise TelegramMediaError(
                    f"{ERROR_TELEGRAM_SEND_FAILED} (bad request): {str(e)}"
                )
            except Exception as e:
                logger.error(f"Unexpected error in send_media_to_telegram: {e}")
                raise TelegramMediaError(f"Unexpected error: {str(e)}")

        # If we've exhausted retries
        if last_error:
            logger.error(f"Failed to send media after {max_retries} retries")
            raise TelegramMediaError(
                f"{ERROR_TELEGRAM_SEND_FAILED} after {max_retries} retries: {str(last_error)}"
            )

    except (FileNotFoundError, TelegramMediaError):
        # Re-raise these specific exceptions
        raise
    except Exception as e:
        logger.error(f"Unexpected error in send_media_to_telegram: {e}")
        raise TelegramMediaError(f"Unexpected error: {str(e)}")


# Helper function to clean up temporary files
def cleanup_temp_file(file_path):
    """Safely remove a temporary file if it exists"""
    if file_path and os.path.exists(file_path):
        try:
            os.unlink(file_path)
        except Exception as e:
            logger.error(f"Error deleting temp file {file_path}: {e}")


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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(f"Received /start command from user {update.effective_user.id}")
    await update.message.reply_text("Привет! Присылай сюда свои мемы)")


async def get_chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    logger.info(f"Received /get chat_id command, returning ID: {chat_id}")
    await update.message.reply_text(f"This chat ID is: {chat_id}")


async def ok_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(f"Received /ok command from user {update.effective_user.id}")

    message_id = str(update.effective_message.message_id)
    object_name = f"{message_id}.jpg"

    temp_path = None
    try:
        # Use helper function to download from MinIO
        temp_path, ext = await download_from_minio(object_name, PHOTOS_BUCKET)

        await update.message.reply_text("Post approved!")

        # Use helper function to send media
        await send_media_to_telegram(context.bot, target_channel, temp_path)

        # Clean up
        storage.delete_file(object_name, PHOTOS_BUCKET)
        logger.info("Created new post!")
    except MinioError as e:
        logger.error(f"MinIO error in ok_command: {e}")
        await update.message.reply_text(get_user_friendly_error_message(e))
    except TelegramMediaError as e:
        logger.error(f"Telegram error in ok_command: {e}")
        await update.message.reply_text(get_user_friendly_error_message(e))
    except Exception as e:
        logger.error(f"Unexpected error in ok_command: {e}")
        await update.message.reply_text(f"An unexpected error occurred: {str(e)}")
    finally:
        cleanup_temp_file(temp_path)


async def notok_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(f"Received /notok command from user {update.effective_user.id}")

    try:
        message_id = str(update.effective_message.message_id)
        object_name = f"{message_id}.jpg"

        # Delete from MinIO if exists
        if storage.file_exists(object_name, PHOTOS_BUCKET):
            storage.delete_file(object_name, PHOTOS_BUCKET)
            await update.message.reply_text("Post disapproved!")
        else:
            await update.message.reply_text("No post found to disapprove.")
    except Exception as e:
        logger.error(f"Error in notok_command: {e}")
        await update.message.reply_text(get_user_friendly_error_message(e))


async def send_batch_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    logger.info(f"Received /send_batch command from user {update.effective_user.id}")

    # Get all files with batch_ prefix from photos bucket
    try:
        batch_files = storage.list_files(PHOTOS_BUCKET, prefix="batch_")

        if not batch_files:
            await context.bot.send_message(
                chat_id=context.bot_data["chat_id"], text="Empty batch!"
            )
            return

        media_group = []
        temp_files = []

        try:
            for i, object_name in enumerate(
                batch_files[:10]
            ):  # Telegram limits to 10 per group
                try:
                    # Use helper function to download from MinIO
                    temp_path, ext = await download_from_minio(
                        object_name, PHOTOS_BUCKET
                    )
                    if not temp_path:
                        continue

                    temp_files.append(temp_path)

                    # Add to media group based on file type
                    caption = "Новый пак мемов." if i == 0 else None
                    if ext.lower() in [".jpg", ".jpeg", ".png"]:
                        media_group.append(
                            InputMediaPhoto(
                                media=open(temp_path, "rb"), caption=caption
                            )
                        )
                    elif ext.lower() in [".mp4", ".avi", ".mov"]:
                        media_group.append(
                            InputMediaVideo(
                                media=open(temp_path, "rb"),
                                caption=caption,
                                supports_streaming=True,
                            )
                        )
                    else:
                        logger.warning(f"Unsupported file type for batch: {ext}")
                        continue
                except MinioError as e:
                    logger.error(f"Error with file {object_name} in batch: {e}")
                    continue

            if media_group:
                # Send as a group using bot
                try:
                    await context.bot.send_media_group(
                        chat_id=target_channel, media=media_group
                    )

                    # Delete from MinIO only after successful sending
                    for object_name in batch_files:
                        storage.delete_file(object_name, PHOTOS_BUCKET)

                    logger.info(f"Sent batch of {len(media_group)} files to channel")
                    await update.message.reply_text(
                        f"Sent batch of {len(media_group)} files to channel"
                    )
                except Exception as e:
                    logger.error(f"Failed to send media group: {e}")
                    await update.message.reply_text(
                        "Failed to send media batch. Please try again later."
                    )
            else:
                await update.message.reply_text("No compatible media in batch")

        except Exception as e:
            logger.error(f"Error preparing batch media: {e}")
            await update.message.reply_text(
                f"Error preparing batch: {get_user_friendly_error_message(e)}"
            )
        finally:
            # Clean up media files and temp files
            for handle in media_group:
                if hasattr(handle.media, "close"):
                    handle.media.close()

            # Clean up temp files using helper
            for temp_file in temp_files:
                cleanup_temp_file(temp_file)
    except Exception as e:
        logger.error(f"Error accessing batch files: {e}")
        await update.message.reply_text(get_user_friendly_error_message(e))


async def delete_batch_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    logger.info(f"Received /delete_batch command from user {update.effective_user.id}")

    try:
        # Get all files with batch_ prefix from photos bucket
        batch_files = storage.list_files(PHOTOS_BUCKET, prefix="batch_")

        if not batch_files:
            await context.bot.send_message(
                chat_id=context.bot_data["chat_id"], text="No files in batch to delete!"
            )
            return

        # Delete from MinIO
        deleted_count = 0
        for object_name in batch_files:
            try:
                storage.delete_file(object_name, PHOTOS_BUCKET)
                deleted_count += 1
            except Exception as e:
                logger.error(f"Error deleting {object_name}: {e}")
                # Continue with other files

        await context.bot.send_message(
            chat_id=context.bot_data["chat_id"],
            text=f"Batch deleted! ({deleted_count} files removed)",
        )
    except Exception as e:
        logger.error(f"Error in delete_batch_command: {e}")
        await update.message.reply_text(get_user_friendly_error_message(e))


async def send_luba_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(f"Received /luba command from user {update.effective_user.id}")

    try:
        # Get all files from downloads bucket
        download_files = storage.list_files(DOWNLOADS_BUCKET)

        if not download_files:
            await update.message.reply_text("No files to send to Luba.")
            return

        sent_count = 0
        error_count = 0

        for object_name in download_files:
            temp_path = None
            try:
                # Use helper function to download from MinIO
                temp_path, ext = await download_from_minio(
                    object_name, DOWNLOADS_BUCKET
                )
                if not temp_path:
                    error_count += 1
                    continue

                # Use helper function to send media
                await send_media_to_telegram(
                    context.bot, LUBA_CHAT, temp_path, object_name
                )
                sent_count += 1
                await asyncio.sleep(1)  # Rate limiting
            except (MinioError, TelegramMediaError) as e:
                logger.error(f"Error sending {object_name} to Luba: {e}")
                error_count += 1
            finally:
                cleanup_temp_file(temp_path)

        status_message = f"Sent {sent_count} files to Luba."
        if error_count > 0:
            status_message += f" {error_count} files could not be sent."

        await update.message.reply_text(status_message)
    except Exception as e:
        logger.error(f"Error in send_luba_command: {e}")
        await update.message.reply_text(get_user_friendly_error_message(e))


async def ok_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(f"Received /ok callback from user {update.effective_user.id}")
    logger.debug(f"Callback data: {update.callback_query.data}")

    # Always answer callback query to avoid the loading indicator
    await update.callback_query.answer()

    caption = update.effective_message.caption
    filename = get_file_name(caption)
    object_name = os.path.basename(filename)

    # Check if file exists in MinIO
    bucket = PHOTOS_BUCKET if "photos/processed_" in filename else VIDEOS_BUCKET

    try:
        if not storage.file_exists(object_name, bucket):
            raise MinioError(f"{ERROR_MINIO_FILE_NOT_FOUND}: {object_name} in {bucket}")

        if "suggestion" in update.effective_message.caption:
            caption = "Пост из предложки @ooodnakov_memes_suggest_bot"
            await update.effective_message.edit_caption(
                f"Post approved with media {filename}!", reply_markup=None
            )

            # Use helper function to download from MinIO
            temp_path, ext = await download_from_minio(object_name, bucket)

            try:
                # Use helper function to send media
                await send_media_to_telegram(
                    context.bot, target_channel, temp_path, caption
                )

                # Delete from MinIO
                storage.delete_file(object_name, bucket)
                logger.info(f"Suggestion post sent to channel: {filename}")
            finally:
                cleanup_temp_file(temp_path)
        else:
            # Rename for batch (move to batch_ prefix)
            new_object_name = f"batch_{object_name}"

            # Use helper function to download from MinIO
            temp_path, ext = await download_from_minio(object_name, bucket)

            try:
                # Upload with new name - use the appropriate bucket for videos and photos
                target_batch_bucket = PHOTOS_BUCKET
                # For videos, make sure we correctly identify and store in the right bucket
                if ext.lower() in [".mp4", ".avi", ".mov"] or bucket == VIDEOS_BUCKET:
                    target_batch_bucket = PHOTOS_BUCKET  # We'll store all batch files in PHOTOS_BUCKET for consistency

                storage.upload_file(temp_path, target_batch_bucket, new_object_name)

                # Delete original
                storage.delete_file(object_name, bucket)

                # Count batch files
                batch_count = len(storage.list_files(PHOTOS_BUCKET, prefix="batch_"))

                await update.effective_message.edit_caption(
                    f"Post added to batch! There are {batch_count} posts in the batch.",
                    reply_markup=None,
                )
                logger.info(f"Added {filename} to batch ({batch_count} total)")
            finally:
                cleanup_temp_file(temp_path)
    except MinioError as e:
        logger.error(f"MinIO error in ok_callback: {e}")
        await update.callback_query.message.reply_text(
            get_user_friendly_error_message(e)
        )
    except TelegramMediaError as e:
        logger.error(f"Telegram error in ok_callback: {e}")
        await update.callback_query.message.reply_text(
            get_user_friendly_error_message(e)
        )
    except Exception as e:
        logger.error(f"Unexpected error in ok_callback: {e}")
        await update.callback_query.message.reply_text(
            f"An unexpected error occurred: {str(e)}"
        )


async def push_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(f"Received /push callback from user {update.effective_user.id}")
    logger.debug(f"Callback data: {update.callback_query.data}")

    # Always answer callback query to avoid the loading indicator
    await update.callback_query.answer()

    caption = update.effective_message.caption
    filename = get_file_name(caption)
    object_name = os.path.basename(filename)

    # Check if file exists in MinIO
    bucket = PHOTOS_BUCKET if "photos/processed_" in filename else VIDEOS_BUCKET

    try:
        if not storage.file_exists(object_name, bucket):
            raise MinioError(f"{ERROR_MINIO_FILE_NOT_FOUND}: {object_name} in {bucket}")

        # Set caption based on source
        if "suggestion" in update.effective_message.caption:
            caption = "Пост из предложки @ooodnakov_memes_suggest_bot"
        else:
            caption = ""

        await update.effective_message.edit_caption(
            f"Post approved with image {filename}!", reply_markup=None
        )

        # Use helper function to download from MinIO
        temp_path, ext = await download_from_minio(object_name, bucket)

        try:
            # Use helper function to send media
            await send_media_to_telegram(
                context.bot, target_channel, temp_path, caption
            )
            logger.info(f"Created new post from image {filename}!")

            # Delete from MinIO
            storage.delete_file(object_name, bucket)
        finally:
            cleanup_temp_file(temp_path)
    except MinioError as e:
        logger.error(f"MinIO error in push_callback: {e}")
        await update.callback_query.message.reply_text(
            get_user_friendly_error_message(e)
        )
    except TelegramMediaError as e:
        logger.error(f"Telegram error in push_callback: {e}")
        await update.callback_query.message.reply_text(
            get_user_friendly_error_message(e)
        )
    except Exception as e:
        logger.error(f"Unexpected error in push_callback: {e}")
        await update.callback_query.message.reply_text(
            f"An unexpected error occurred: {str(e)}"
        )


async def notok_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(f"Received /notok callback from user {update.effective_user.id}")
    logger.debug(f"Callback data: {update.callback_query.data}")

    # Always answer callback query to avoid the loading indicator
    await update.callback_query.answer()

    try:
        caption = update.effective_message.caption
        photo_name = get_file_name(caption)
        object_name = os.path.basename(photo_name)

        await update.effective_message.edit_caption(
            f"Post disapproved with media {photo_name}!",
            reply_markup=None,
        )

        # Check if file exists in MinIO
        bucket = PHOTOS_BUCKET if "photos/processed_" in photo_name else VIDEOS_BUCKET

        if storage.file_exists(object_name, bucket):
            logger.info(f"Removing file from MinIO: {bucket}/{object_name}")
            storage.delete_file(object_name, bucket)
        else:
            logger.warning(f"File not found for deletion: {bucket}/{object_name}")
    except Exception as e:
        logger.error(f"Error in notok_callback: {e}")
        await update.callback_query.message.reply_text(
            get_user_friendly_error_message(e)
        )


def get_file_name(caption):
    return caption.split("\n")[-1]


async def process_photo(custom_text: str, name: str, bot_chat_id: str, application):
    """Process a photo by adding watermark and sending to review bot"""
    try:
        # Add watermark and upload to MinIO
        processed_name = f"processed_{os.path.basename(name)}"
        await add_watermark_to_image(name, f"photos/{processed_name}")

        # Check if processed file exists in MinIO
        if not storage.file_exists(processed_name, PHOTOS_BUCKET):
            logger.error(f"Processed photo not found in MinIO: {processed_name}")
            return

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("Send to batch!", callback_data="/ok"),
                ],
                [
                    InlineKeyboardButton("Push!", callback_data="/push"),
                    InlineKeyboardButton("No!", callback_data="/notok"),
                ],
            ]
        )

        # Download to temp file for bot with correct extension
        temp_path, _ = await download_from_minio(processed_name, PHOTOS_BUCKET, ".jpg")

        try:
            # Send photo using bot
            await application.bot.send_photo(
                bot_chat_id,
                open(temp_path, "rb"),
                custom_text + "\nNew post found\n" + f"photos/{processed_name}",
                reply_markup=keyboard,
                read_timeout=60,
                write_timeout=60,
                connect_timeout=60,
                pool_timeout=60,
            )
            logger.info(f"New photo {name} in channel!")
        except Exception as e:
            logger.error(f"Failed to send photo to review channel: {e}")
            raise TelegramMediaError(f"Failed to send photo to review: {str(e)}")
        finally:
            cleanup_temp_file(temp_path)
    except MinioError as e:
        logger.error(f"MinIO error in process_photo: {e}")
    except MediaError as e:
        logger.error(f"Media processing error in process_photo: {e}")
    except Exception as e:
        logger.error(f"Unexpected error in process_photo: {e}")


async def process_video(
    custom_text: str, name: str, bot_chat_id: str, application
) -> None:
    """Process a video by adding watermark and sending to review bot"""
    try:
        # Add watermark and upload to MinIO
        processed_name = f"processed_{os.path.basename(name)}"
        await add_watermark_to_video(name, f"videos/{processed_name}")

        # Check if processed file exists in MinIO
        if not storage.file_exists(processed_name, VIDEOS_BUCKET):
            logger.error(f"Processed video not found in MinIO: {processed_name}")
            return

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("Send to batch!", callback_data="/ok"),
                ],
                [
                    InlineKeyboardButton("Push!", callback_data="/push"),
                    InlineKeyboardButton("No!", callback_data="/notok"),
                ],
            ]
        )

        # Download to temp file for bot with correct extension
        temp_path, _ = await download_from_minio(processed_name, VIDEOS_BUCKET, ".mp4")

        try:
            # Send video using bot
            await application.bot.send_video(
                bot_chat_id,
                video=open(temp_path, "rb"),
                caption=custom_text
                + "\nNew video found\n"
                + f"videos/{processed_name}",
                supports_streaming=True,
                reply_markup=keyboard,
                read_timeout=60,
                write_timeout=60,
                connect_timeout=60,
                pool_timeout=60,
            )
            logger.info(f"New video {name} in channel!")
        except Exception as e:
            logger.error(f"Failed to send video to review channel: {e}")
            raise TelegramMediaError(f"Failed to send video to review: {str(e)}")
        finally:
            cleanup_temp_file(temp_path)
    except MinioError as e:
        logger.error(f"MinIO error in process_video: {e}")
    except MediaError as e:
        logger.error(f"Media processing error in process_video: {e}")
    except Exception as e:
        logger.error(f"Unexpected error in process_video: {e}")


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
        await update.message.reply_text(
            "Sorry, there was an error processing your media. Please try again later."
        )


async def handle_photo(update, context, chat_id):
    """Handle photo uploads"""
    file_id = update.message.photo[-1].file_id
    message_id = update.message.message_id
    file_name = f"downloaded_image_{chat_id}_{file_id}_{message_id}.jpg"

    temp_path = None
    try:
        # Download to temp file with correct extension
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
        temp_path = temp_file.name
        temp_file.close()

        # Download from Telegram
        f = await context.bot.get_file(file_id)
        await f.download_to_drive(temp_path)

        # Upload to MinIO
        storage.upload_file(temp_path, DOWNLOADS_BUCKET, file_name)

        logger.info(f"Photo from chat {chat_id} has downloaded and stored in MinIO")

        # Process the photo (which will handle MinIO operations)
        await process_photo(
            "New suggestion in bot",
            file_name,
            context.bot_data["chat_id"],
            context.application,
        )
    except Exception as e:
        logger.error(f"Error handling photo: {e}")
        await update.message.reply_text(
            "There was an error processing your photo. Please try again later."
        )
    finally:
        cleanup_temp_file(temp_path)


async def handle_video(update, context, chat_id):
    """Handle video uploads"""
    logger.info(f"Video from chat {chat_id} has started downloading!")
    file_id = update.message.video.file_id
    message_id = update.message.message_id
    file_name = f"downloaded_video_{chat_id}_{file_id}_{message_id}.mp4"

    temp_path = None
    try:
        # Download to temp file with correct extension
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
        temp_path = temp_file.name
        temp_file.close()

        # Download from Telegram
        f = await context.bot.get_file(file_id)
        await f.download_to_drive(temp_path)

        # Upload to MinIO
        storage.upload_file(temp_path, DOWNLOADS_BUCKET, file_name)

        logger.info(f"Video from chat {chat_id} has downloaded and stored in MinIO")

        # Process the video (which will handle MinIO operations)
        await process_video(
            "New suggestion in bot",
            file_name,
            context.bot_data["chat_id"],
            context.application,
        )
    except Exception as e:
        logger.error(f"Error handling video: {e}")
        await update.message.reply_text(
            "There was an error processing your video. Please try again later."
        )
    finally:
        cleanup_temp_file(temp_path)
