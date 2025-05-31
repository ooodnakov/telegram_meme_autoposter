import os
import asyncio
import tempfile
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    InputMediaVideo,
)
from telegram.ext import ContextTypes
from loguru import logger

from ..media.photo import add_watermark_to_image
from ..media.video import add_watermark_to_video
from ..config import LUBA_CHAT, load_config
from ..client.client import client_instance
from ..utils.storage import storage, PHOTOS_BUCKET, VIDEOS_BUCKET, DOWNLOADS_BUCKET

# Load target_channel from config
config = load_config()
target_channel = config["target_channel"]


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

    # Check if the file exists in MinIO
    if storage.file_exists(object_name, PHOTOS_BUCKET):
        await update.message.reply_text("Post approved!")

        # Download to temp file with correct extension
        ext = get_file_extension(object_name)
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
        temp_file_path = temp_file.name
        temp_file.close()

        try:
            # Download file from MinIO to temp file
            storage.download_file(object_name, PHOTOS_BUCKET, temp_file_path)

            # Send photo using bot instead of client
            if ext.lower() in [".jpg", ".jpeg", ".png"]:
                await context.bot.send_photo(
                    chat_id=target_channel, photo=open(temp_file_path, "rb")
                )
            elif ext.lower() in [".mp4", ".avi", ".mov"]:
                await context.bot.send_video(
                    chat_id=target_channel,
                    video=open(temp_file_path, "rb"),
                    supports_streaming=True,
                )
            else:
                await context.bot.send_document(
                    chat_id=target_channel, document=open(temp_file_path, "rb")
                )

            # Clean up
            os.unlink(temp_file_path)
            storage.delete_file(object_name, PHOTOS_BUCKET)
            logger.info("Created new post!")
        except Exception as e:
            logger.error(f"Error sending media: {e}")
            await update.message.reply_text(f"Error sending media: {str(e)}")
        finally:
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
    else:
        await update.message.reply_text(
            "No approved post image, it's already disapproved!"
        )
        logger.warning("No file!")


async def notok_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(f"Received /notok command from user {update.effective_user.id}")
    await update.message.reply_text("Post disapproved!")

    message_id = str(update.effective_message.message_id)
    object_name = f"{message_id}.jpg"

    # Delete from MinIO if exists
    if storage.file_exists(object_name, PHOTOS_BUCKET):
        storage.delete_file(object_name, PHOTOS_BUCKET)


async def send_batch_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    logger.info(f"Received /send_batch command from user {update.effective_user.id}")

    # Get all files with batch_ prefix from photos bucket
    batch_files = storage.list_files(PHOTOS_BUCKET, prefix="batch_")

    if batch_files:
        media_group = []
        temp_files = []

        try:
            for i, object_name in enumerate(
                batch_files[:10]
            ):  # Telegram limits to 10 per group
                # Get file extension
                ext = get_file_extension(object_name)
                # Create temp file with correct extension
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
                temp_file.close()
                temp_path = temp_file.name

                # Download from MinIO
                storage.download_file(object_name, PHOTOS_BUCKET, temp_path)
                temp_files.append(temp_path)

                # Add to media group based on file type
                if ext.lower() in [".jpg", ".jpeg", ".png"]:
                    caption = "Новый пак мемов." if i == 0 else None
                    media_group.append(
                        InputMediaPhoto(media=open(temp_path, "rb"), caption=caption)
                    )
                else:
                    caption = "Новый пак мемов." if i == 0 else None
                    media_group.append(
                        InputMediaVideo(
                            media=open(temp_path, "rb"),
                            caption=caption,
                            supports_streaming=True,
                        )
                    )

            if media_group:
                # Send as a group using bot
                await context.bot.send_media_group(
                    chat_id=target_channel, media=media_group
                )

                # Delete from MinIO
                for object_name in batch_files:
                    storage.delete_file(object_name, PHOTOS_BUCKET)

                logger.info(f"Sent batch of {len(media_group)} files to channel")
                await update.message.reply_text(
                    f"Sent batch of {len(media_group)} files to channel"
                )

        except Exception as e:
            logger.error(f"Error sending batch: {e}")
            await update.message.reply_text(f"Error sending batch: {str(e)}")
        finally:
            # Clean up media files and temp files
            for handle in media_group:
                if hasattr(handle.media, "close"):
                    handle.media.close()

            # Clean up temp files
            for temp_file in temp_files:
                if os.path.exists(temp_file):
                    try:
                        os.unlink(temp_file)
                    except:
                        pass
    else:
        await context.bot.send_message(
            chat_id=context.bot_data["chat_id"], text="Empty batch!"
        )


async def delete_batch_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    logger.info(f"Received /delete_batch command from user {update.effective_user.id}")

    # Get all files with batch_ prefix from photos bucket
    batch_files = storage.list_files(PHOTOS_BUCKET, prefix="batch_")

    # Delete from MinIO
    for object_name in batch_files:
        storage.delete_file(object_name, PHOTOS_BUCKET)

    await context.bot.send_message(
        chat_id=context.bot_data["chat_id"], text="Batch deleted!"
    )


async def send_luba_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(f"Received /luba command from user {update.effective_user.id}")

    # Get all files from downloads bucket
    download_files = storage.list_files(DOWNLOADS_BUCKET)

    sent_count = 0
    for object_name in download_files:
        # Get file extension
        ext = get_file_extension(object_name)
        # Create temp file with correct extension
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
        temp_file.close()
        temp_path = temp_file.name

        try:
            storage.download_file(object_name, DOWNLOADS_BUCKET, temp_path)

            # Send to Luba using bot
            if ext.lower() in [".jpg", ".jpeg", ".png"]:
                await context.bot.send_photo(
                    chat_id=LUBA_CHAT, photo=open(temp_path, "rb"), caption=object_name
                )
            elif ext.lower() in [".mp4", ".avi", ".mov"]:
                await context.bot.send_video(
                    chat_id=LUBA_CHAT,
                    video=open(temp_path, "rb"),
                    caption=object_name,
                    supports_streaming=True,
                )
            else:
                await context.bot.send_document(
                    chat_id=LUBA_CHAT,
                    document=open(temp_path, "rb"),
                    caption=object_name,
                )

            sent_count += 1
            await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"Error sending to Luba: {e}")
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    await update.message.reply_text(f"Sent {sent_count} files to Luba")


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

    if storage.file_exists(object_name, bucket):
        if "suggestion" in update.effective_message.caption:
            caption = "Пост из предложки @ooodnakov_memes_suggest_bot"
            await update.effective_message.edit_caption(
                f"Post approved with media {filename}!", reply_markup=None
            )

            # Get file extension
            ext = get_file_extension(object_name)
            # Create temp file with correct extension
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
            temp_file.close()
            temp_path = temp_file.name

            try:
                # Get file from MinIO
                storage.download_file(object_name, bucket, temp_path)

                # Send media using bot
                if ext.lower() in [".jpg", ".jpeg", ".png"]:
                    await context.bot.send_photo(
                        chat_id=target_channel,
                        photo=open(temp_path, "rb"),
                        caption=caption,
                    )
                elif ext.lower() in [".mp4", ".avi", ".mov"]:
                    await context.bot.send_video(
                        chat_id=target_channel,
                        video=open(temp_path, "rb"),
                        caption=caption,
                        supports_streaming=True,
                    )
                else:
                    await context.bot.send_document(
                        chat_id=target_channel,
                        document=open(temp_path, "rb"),
                        caption=caption,
                    )

                # Delete from MinIO
                storage.delete_file(object_name, bucket)
            except Exception as e:
                logger.error(f"Error sending media: {e}")
                await update.effective_message.reply_text(
                    f"Error sending media: {str(e)}"
                )
            finally:
                # Clean up temp file
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
        else:
            # Rename for batch (move to batch_ prefix)
            new_object_name = f"batch_{object_name}"

            # Download and re-upload with new name
            # Get file extension
            ext = get_file_extension(object_name)
            # Create temp file with correct extension
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
            temp_file.close()
            temp_path = temp_file.name

            try:
                # Get file from MinIO
                storage.download_file(object_name, bucket, temp_path)

                # Upload with new name
                storage.upload_file(temp_path, PHOTOS_BUCKET, new_object_name)

                # Delete original
                storage.delete_file(object_name, bucket)

                # Count batch files
                batch_count = len(storage.list_files(PHOTOS_BUCKET, prefix="batch_"))

                await update.effective_message.edit_caption(
                    f"Post added to batch! There are {batch_count} posts in the batch.",
                    reply_markup=None,
                )
            finally:
                # Clean up temp file
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
    else:
        await update.callback_query.message.reply_text(
            "No approved post media, it's already disapproved!"
        )
        logger.warning("No file!")


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

    if storage.file_exists(object_name, bucket):
        if "suggestion" in update.effective_message.caption:
            caption = "Пост из предложки @ooodnakov_memes_suggest_bot"
        else:
            caption = ""

        await update.effective_message.edit_caption(
            f"Post approved with image {filename}!", reply_markup=None
        )

        # Get file extension
        ext = get_file_extension(object_name)
        # Create temp file with correct extension
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
        temp_file.close()
        temp_path = temp_file.name

        try:
            # Get file from MinIO
            storage.download_file(object_name, bucket, temp_path)

            # Send media using bot
            if ext.lower() in [".jpg", ".jpeg", ".png"]:
                await context.bot.send_photo(
                    chat_id=target_channel, photo=open(temp_path, "rb"), caption=caption
                )
            elif ext.lower() in [".mp4", ".avi", ".mov"]:
                await context.bot.send_video(
                    chat_id=target_channel,
                    video=open(temp_path, "rb"),
                    caption=caption,
                    supports_streaming=True,
                )
            else:
                await context.bot.send_document(
                    chat_id=target_channel,
                    document=open(temp_path, "rb"),
                    caption=caption,
                )

            logger.info(f"Created new post from image {filename}!")

            # Delete from MinIO
            storage.delete_file(object_name, bucket)
        except Exception as e:
            logger.error(f"Error sending media: {e}")
            await update.effective_message.reply_text(f"Error sending media: {str(e)}")
        finally:
            # Clean up temp file
            if os.path.exists(temp_path):
                os.unlink(temp_path)
    else:
        await update.callback_query.message.reply_text(
            "No approved post image, it's already disapproved!"
        )
        logger.warning("No file!")


async def notok_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(f"Received /notok callback from user {update.effective_user.id}")
    logger.debug(f"Callback data: {update.callback_query.data}")

    # Always answer callback query to avoid the loading indicator
    await update.callback_query.answer()

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


def get_file_name(caption):
    return caption.split("\n")[-1]


async def process_photo(custom_text: str, name: str, bot_chat_id: str, application):
    # Add watermark and upload to MinIO
    processed_name = f"processed_{os.path.basename(name)}"
    await add_watermark_to_image(name, f"photos/{processed_name}")

    # Check if processed file exists in MinIO
    if storage.file_exists(processed_name, PHOTOS_BUCKET):
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
        ext = ".jpg"  # Enforce jpg extension
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as temp_file:
            temp_file_path = temp_file.name

        try:
            storage.download_file(processed_name, PHOTOS_BUCKET, temp_file_path)

            # Send photo using bot
            await application.bot.send_photo(
                bot_chat_id,
                open(temp_file_path, "rb"),
                custom_text + "\nNew post found\n" + f"photos/{processed_name}",
                reply_markup=keyboard,
                read_timeout=60,
                write_timeout=60,
                connect_timeout=60,
                pool_timeout=60,
            )
            logger.info(f"New photo {name} in channel!")
        finally:
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)


async def process_video(
    custom_text: str, name: str, bot_chat_id: str, application
) -> None:
    # Add watermark and upload to MinIO
    processed_name = f"processed_{os.path.basename(name)}"
    await add_watermark_to_video(name, f"videos/{processed_name}")

    # Check if processed file exists in MinIO
    if storage.file_exists(processed_name, VIDEOS_BUCKET):
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
        ext = ".mp4"  # Enforce mp4 extension
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as temp_file:
            temp_file_path = temp_file.name

        try:
            storage.download_file(processed_name, VIDEOS_BUCKET, temp_file_path)

            # Send video using bot
            await application.bot.send_video(
                bot_chat_id,
                video=open(temp_file_path, "rb"),
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
            logger.error(f"Failed to upload video with error {e}")
        finally:
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)


async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if update.message and update.message.photo:
        file_id = update.message.photo[-1].file_id
        message_id = update.message.message_id
        file_name = f"downloaded_image_{chat_id}_{file_id}_{message_id}.jpg"

        # Download to temp file with correct extension
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as temp_file:
            temp_path = temp_file.name

        try:
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
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    elif update.message.video:
        logger.info(f"Video from chat {chat_id} has started downloading!")
        file_id = update.message.video.file_id
        message_id = update.message.message_id
        file_name = f"downloaded_video_{chat_id}_{file_id}_{message_id}.mp4"

        # Download to temp file with correct extension
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_file:
            temp_path = temp_file.name

        try:
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
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
