import asyncio
import os
import tempfile
import time
from typing import Optional, Tuple

from loguru import logger
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    InputMediaVideo,
    Update,
)
from telegram.error import BadRequest, NetworkError, TimedOut
from telegram.ext import ContextTypes

from telegram_auto_poster.utils import (
    MediaError,
    MinioError,
    TelegramMediaError,
    cleanup_temp_file,
    download_from_minio,
    send_media_to_telegram,
)

from ..client.client import client_instance
from ..config import LUBA_CHAT, load_config
from ..media.photo import add_watermark_to_image
from ..media.video import add_watermark_to_video
from ..utils.stats import stats
from ..utils.storage import DOWNLOADS_BUCKET, PHOTOS_BUCKET, VIDEOS_BUCKET, storage

# Load target_channel from config
config = load_config()
target_channel = config["target_channel"]

# Define error constants
ERROR_MINIO_FILE_NOT_FOUND = "File not found in MinIO storage"
ERROR_MINIO_DOWNLOAD_FAILED = "Failed to download file from MinIO"
ERROR_TELEGRAM_SEND_FAILED = "Failed to send media to Telegram"
ERROR_TEMP_FILE_CREATION = "Failed to create temporary file"
ERROR_FILE_NOT_SUPPORTED = "File type not supported"


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
            stats.record_error("processing", f"{ERROR_TEMP_FILE_CREATION}: {str(e)}")
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
            stats.record_error("storage", f"{ERROR_MINIO_DOWNLOAD_FAILED}: {str(e)}")
            raise MinioError(f"{ERROR_MINIO_DOWNLOAD_FAILED}: {str(e)}")
    except MinioError:
        # Re-raise MinioError to be caught by caller
        raise
    except Exception as e:
        logger.error(f"Unexpected error in download_from_minio: {e}")
        stats.record_error("storage", f"Unexpected error: {str(e)}")
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
        stats.record_error("telegram", f"File {file_path} does not exist")
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
                    stats.record_error(
                        "processing", f"{ERROR_FILE_NOT_SUPPORTED}: {ext}"
                    )
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
                stats.record_error("telegram", f"Network error (retrying): {str(e)}")
                await asyncio.sleep(wait_time)
            except BadRequest as e:
                # Bad request errors are usually not retryable
                logger.error(f"Bad request error when sending media: {e}")
                stats.record_error(
                    "telegram", f"{ERROR_TELEGRAM_SEND_FAILED} (bad request): {str(e)}"
                )
                raise TelegramMediaError(
                    f"{ERROR_TELEGRAM_SEND_FAILED} (bad request): {str(e)}"
                )
            except Exception as e:
                logger.error(f"Unexpected error in send_media_to_telegram: {e}")
                stats.record_error("telegram", f"Unexpected error: {str(e)}")
                raise TelegramMediaError(f"Unexpected error: {str(e)}")

        # If we've exhausted retries
        if last_error:
            logger.error(f"Failed to send media after {max_retries} retries")
            stats.record_error(
                "telegram",
                f"{ERROR_TELEGRAM_SEND_FAILED} after {max_retries} retries: {str(last_error)}",
            )
            raise TelegramMediaError(
                f"{ERROR_TELEGRAM_SEND_FAILED} after {max_retries} retries: {str(last_error)}"
            )

    except (FileNotFoundError, TelegramMediaError):
        # Re-raise these specific exceptions
        raise
    except Exception as e:
        logger.error(f"Unexpected error in send_media_to_telegram: {e}")
        stats.record_error("telegram", f"Unexpected error: {str(e)}")
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


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display help information about the bot"""
    logger.info(f"Received /help command from user {update.effective_user.id}")

    # Check if the user is an admin to customize the help message
    is_admin = False
    user_id = update.effective_user.id

    if hasattr(context, "bot_data") and "admin_ids" in context.bot_data:
        admin_ids = context.bot_data["admin_ids"]
        if user_id in admin_ids:
            is_admin = True

    # Base help message for all users
    help_text = [
        "<b>Предложка для @ooodnakov_memes</b>",
        "",
        "<b>Команды пользователя:</b>",
        "• /start - Запустить бота",
        "• /help - Показать это сообщение помощи",
        "",
        "<b>Как использовать:</b>",
        "1. Отправьте фото или видео этому боту",
        "2. Администраторы проверят ваши отправления",
        "3. Вы получите уведомление, когда ваш контент будет одобрен или отклонен",
    ]

    # Add admin commands if the user is an admin
    if is_admin:
        help_text.extend(
            [
                "",
                "<b>Команды администратора:</b>",
                "• /stats - Просмотр статистики обработки медиа",
                "• /reset_stats - Сбросить ежедневную статистику",
                "• /save_stats - Принудительно сохранить статистику",
                "• /sendall - Отправить все одобренные медиафайлы из пакета в целевой канал",
                "• /delete_batch - Удалить текущий пакет медиафайлов",
                "• /get - Получить текущий ID чата",
                "",
                "<b>Проверка контента администратором:</b>",
                "При проверке контента вы можете использовать кнопки для:",
                "• Send to batch - Добавить медиа в пакет для последующей отправки",
                "• Push - Немедленно опубликовать медиа в канале",
                "• No - Отклонить медиа",
            ]
        )

    # Send the help message
    help_text = "\n".join(help_text)
    logger.info(help_text)
    await update.message.reply_text(help_text, parse_mode="HTML")


async def get_chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    logger.info(f"Received /get chat_id command, returning ID: {chat_id}")
    await update.message.reply_text(f"This chat ID is: {chat_id}")


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Command to show bot statistics"""
    logger.info(f"Received /stats command from user {update.effective_user.id}")

    # Check admin rights
    from telegram_auto_poster.bot.permissions import check_admin_rights

    if not await check_admin_rights(update, context):
        return

    try:
        # Generate statistics report
        report = stats.generate_stats_report()
        await update.message.reply_text(report)
    except Exception as e:
        logger.error(f"Error generating stats report: {e}")
        await update.message.reply_text(
            "Sorry, there was an error generating the statistics report."
        )


async def reset_stats_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Command to reset daily statistics"""
    logger.info(f"Received /reset_stats command from user {update.effective_user.id}")

    # Check admin rights
    from telegram_auto_poster.bot.permissions import check_admin_rights

    if not await check_admin_rights(update, context):
        return

    try:
        # Reset daily statistics
        result = stats.reset_daily_stats()
        await update.message.reply_text(result)
    except Exception as e:
        logger.error(f"Error resetting stats: {e}")
        await update.message.reply_text(
            "Sorry, there was an error resetting the statistics."
        )


async def save_stats_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Command to save statistics"""
    logger.info(f"Received /save_stats command from user {update.effective_user.id}")

    # Check admin rights
    from telegram_auto_poster.bot.permissions import check_admin_rights

    if not await check_admin_rights(update, context):
        return

    try:
        # Save statistics
        stats.force_save()
        await update.message.reply_text("Stats saved!")
    except Exception as e:
        logger.error(f"Error saving stats: {e}")
        await update.message.reply_text(
            "Sorry, there was an error saving the statistics."
        )


async def ok_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(f"Received /ok command from user {update.effective_user.id}")

    # Check admin rights
    from telegram_auto_poster.bot.permissions import check_admin_rights

    if not await check_admin_rights(update, context):
        return

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

        # Record stats
        media_type = "photo" if ext.lower() in [".jpg", ".jpeg", ".png"] else "video"
        stats.record_approved(media_type)

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

    # Check admin rights
    from telegram_auto_poster.bot.permissions import check_admin_rights

    if not await check_admin_rights(update, context):
        return

    try:
        message_id = str(update.effective_message.message_id)
        object_name = f"{message_id}.jpg"

        # Try to determine media type
        media_type = "photo"  # Default

        # Delete from MinIO if exists
        if storage.file_exists(object_name, PHOTOS_BUCKET):
            storage.delete_file(object_name, PHOTOS_BUCKET)
            await update.message.reply_text("Post disapproved!")

            # Record stats
            stats.record_rejected(media_type)
        else:
            await update.message.reply_text("No post found to disapprove.")
    except Exception as e:
        logger.error(f"Error in notok_command: {e}")
        await update.message.reply_text(get_user_friendly_error_message(e))


async def send_batch_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    logger.info(f"Received /send_batch command from user {update.effective_user.id}")

    # Check admin rights
    from telegram_auto_poster.bot.permissions import check_admin_rights

    if not await check_admin_rights(update, context):
        return

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
        len(batch_files[:10])  # Telegram limits to 10 per group

        try:
            for i, object_name in enumerate(batch_files[:10]):
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

                    # Record batch sent stats
                    stats.record_batch_sent(len(media_group))
                except Exception as e:
                    logger.error(f"Failed to send media group: {e}")
                    stats.record_error("telegram", f"Failed to send batch: {str(e)}")
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

    # Check admin rights
    from telegram_auto_poster.bot.permissions import check_admin_rights

    if not await check_admin_rights(update, context):
        return

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
                stats.record_error("storage", f"Failed to delete batch file: {str(e)}")
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

    # Check admin rights
    from telegram_auto_poster.bot.permissions import check_admin_rights

    if not await check_admin_rights(update, context):
        return

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

    # Determine media type from filename
    media_type = "photo" if "photos/" in filename else "video"

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
            logger.info(f"Downloaded file {object_name} from {bucket} to {temp_path}")
            try:
                # Use helper function to send media
                await send_media_to_telegram(
                    context.bot, target_channel, temp_path, caption
                )

                # Delete from MinIO
                storage.delete_file(object_name, bucket)
                logger.info(f"Suggestion post sent to channel: {filename}")

                # Record stats
                stats.record_approved(media_type)
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

                # Record stats
                stats.record_added_to_batch(media_type)
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

    # Determine media type from filename
    media_type = "photo" if "photos/" in filename else "video"

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

            # Record stats
            stats.record_approved(media_type)
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

        # Determine media type
        media_type = "photo" if "photos/" in photo_name else "video"

        await update.effective_message.edit_caption(
            f"Post disapproved with media {photo_name}!",
            reply_markup=None,
        )

        # Check if file exists in MinIO
        bucket = PHOTOS_BUCKET if "photos/processed_" in photo_name else VIDEOS_BUCKET

        if storage.file_exists(object_name, bucket):
            logger.info(f"Removing file from MinIO: {bucket}/{object_name}")
            storage.delete_file(object_name, bucket)

            # Record stats
            stats.record_rejected(media_type)
        else:
            logger.warning(f"File not found for deletion: {bucket}/{object_name}")
    except Exception as e:
        logger.error(f"Error in notok_callback: {e}")
        await update.callback_query.message.reply_text(
            get_user_friendly_error_message(e)
        )


def get_file_name(caption):
    return caption.split("\n")[-1]


async def handle_photo(update, context, chat_id):
    """Handle photo uploads"""
    file_id = update.message.photo[-1].file_id
    message_id = update.message.message_id
    user_id = update.effective_user.id
    file_name = f"downloaded_image_{chat_id}_{file_id}_{message_id}.jpg"

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

        # Upload to MinIO with user info
        start_upload_time = time.time()
        storage.upload_file(
            temp_path, DOWNLOADS_BUCKET, file_name, user_id=user_id, chat_id=chat_id
        )
        upload_time = time.time() - start_upload_time

        logger.info(
            f"Photo from chat {chat_id} has downloaded and stored in MinIO wiht filename {file_name}"
        )
        logger.debug(
            f"Download time: {download_time:.2f}s, Upload time: {upload_time:.2f}s"
        )

        # Process the photo (which will handle MinIO operations)
        await process_photo(
            "New suggestion in bot",
            file_name,
            context.bot_data["chat_id"],
            context.application,
        )

        # Send confirmation to user
        await update.message.reply_text(
            "Спасибо за вашу предложку! Мы рассмотрим её и сообщим вам, если она будет одобрена."
        )
    except Exception as e:
        logger.error(f"Error handling photo: {e}")
        stats.record_error("processing", f"Error handling photo: {str(e)}")
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

        # Upload to MinIO with user info
        start_upload_time = time.time()
        storage.upload_file(
            temp_path, DOWNLOADS_BUCKET, file_name, user_id=user_id, chat_id=chat_id
        )
        upload_time = time.time() - start_upload_time

        logger.info(f"Video from chat {chat_id} has downloaded and stored in MinIO")
        logger.debug(
            f"Download time: {download_time:.2f}s, Upload time: {upload_time:.2f}s"
        )

        # Process the video (which will handle MinIO operations)
        await process_video(
            "New suggestion in bot",
            file_name,
            context.bot_data["chat_id"],
            context.application,
        )

        # Send confirmation to user
        await update.message.reply_text(
            "Thank you for your video submission! We'll review it and let you know if it's approved."
        )
    except Exception as e:
        logger.error(f"Error handling video: {e}")
        stats.record_error("processing", f"Error handling video: {str(e)}")
        await update.message.reply_text(
            "There was an error processing your video. Please try again later."
        )
    finally:
        cleanup_temp_file(temp_path)


async def notify_user(context, user_id, message, media_type=None):
    """Send a notification to a user about their submission status

    Args:
        context: The bot context
        user_id: The user's Telegram ID
        message: The message to send
        media_type: Optional media type for stats tracking
    """
    try:
        await context.bot.send_message(chat_id=user_id, text=message)
        logger.info(f"Sent notification to user {user_id}")
    except Exception as e:
        logger.error(f"Failed to send notification to user {user_id}: {e}")
        stats.record_error("telegram", f"Failed to notify user: {str(e)}")


async def process_photo(custom_text: str, name: str, bot_chat_id: str, application):
    """Process a photo by adding watermark and sending to review bot"""
    start_time = time.time()
    try:
        # Add watermark and upload to MinIO
        processed_name = f"processed_{os.path.basename(name)}"

        # Transfer user metadata from original to processed file
        user_metadata = storage.get_submission_metadata(os.path.basename(name))

        await add_watermark_to_image(name, f"photos/{processed_name}")

        # Copy user metadata to processed file if exists
        if user_metadata:
            storage.store_submission_metadata(
                processed_name,
                user_metadata["user_id"],
                user_metadata["chat_id"],
                user_metadata["media_type"],
            )

        # Record processing time
        processing_time = time.time() - start_time
        stats.record_processed("photo", processing_time)

        # Check if processed file exists in MinIO
        if not storage.file_exists(processed_name, PHOTOS_BUCKET):
            logger.error(f"Processed photo not found in MinIO: {processed_name}")
            stats.record_error(
                "processing", f"Processed photo not found: {processed_name}"
            )
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
            stats.record_error("telegram", f"Failed to send to review: {str(e)}")
            raise TelegramMediaError(f"Failed to send photo to review: {str(e)}")
        finally:
            cleanup_temp_file(temp_path)
    except MinioError as e:
        logger.error(f"MinIO error in process_photo: {e}")
        stats.record_error("storage", f"MinIO error: {str(e)}")
    except MediaError as e:
        logger.error(f"Media processing error in process_photo: {e}")
        stats.record_error("processing", f"Media error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error in process_photo: {e}")
        stats.record_error("processing", f"Unexpected error: {str(e)}")


async def process_video(custom_text: str, name: str, bot_chat_id: str, application):
    """Process a video and send to review bot"""
    start_time = time.time()
    try:
        # Add watermark and upload to MinIO
        processed_name = f"processed_{os.path.basename(name)}"

        # Transfer user metadata from original to processed file
        user_metadata = storage.get_submission_metadata(os.path.basename(name))

        # Add watermark to video and upload to MinIO
        await add_watermark_to_video(name, processed_name)

        # Copy user metadata to processed file if exists
        if user_metadata:
            storage.store_submission_metadata(
                processed_name,
                user_metadata["user_id"],
                user_metadata["chat_id"],
                user_metadata["media_type"],
            )

        # Record processing time
        processing_time = time.time() - start_time
        stats.record_processed("video", processing_time)

        # Check if processed file exists in MinIO
        if not storage.file_exists(processed_name, VIDEOS_BUCKET):
            logger.error(f"Processed video not found in MinIO: {processed_name}")
            stats.record_error(
                "processing", f"Processed video not found: {processed_name}"
            )
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
            with open(temp_path, "rb") as media_file:
                await application.bot.send_video(
                    chat_id=bot_chat_id,
                    video=media_file,
                    caption=custom_text
                    + "\nNew post found\n"
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
            stats.record_error("telegram", f"Failed to send video to review: {str(e)}")
            raise TelegramMediaError(f"Failed to send video to review: {str(e)}")
        finally:
            cleanup_temp_file(temp_path)
    except MinioError as e:
        logger.error(f"MinIO error in process_video: {e}")
        stats.record_error("storage", f"MinIO error: {str(e)}")
    except MediaError as e:
        logger.error(f"Media processing error in process_video: {e}")
        stats.record_error("processing", f"Media error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error in process_video: {e}")
        stats.record_error("processing", f"Unexpected error: {str(e)}")


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
            "Sorry, there was an error processing your media. Please try again later."
        )
