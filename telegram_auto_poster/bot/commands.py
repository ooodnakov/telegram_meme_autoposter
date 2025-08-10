import asyncio
from loguru import logger
from telegram import Update
from telegram.ext import ContextTypes
from telegram_auto_poster.utils import (
    download_from_minio,
    cleanup_temp_file,
    send_media_to_telegram,
)
from telegram_auto_poster.utils.stats import stats
from telegram_auto_poster.utils.storage import storage
from telegram_auto_poster.config import (
    PHOTOS_PATH,
    VIDEOS_PATH,
    DOWNLOADS_PATH,
    BUCKET_MAIN,
)
from telegram_auto_poster.bot.permissions import check_admin_rights
from telegram_auto_poster.utils import MinioError, TelegramMediaError


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start the bot and provide welcome message"""
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


async def get_chat_id_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Get the current chat ID"""
    chat_id = update.effective_chat.id
    logger.info(f"Received /get chat_id command, returning ID: {chat_id}")
    await update.message.reply_text(f"This chat ID is: {chat_id}")


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Command to show bot statistics"""
    logger.info(f"Received /stats command from user {update.effective_user.id}")

    # Check admin rights
    if not await check_admin_rights(update, context):
        return

    try:
        # Generate statistics report
        report = stats.generate_stats_report()
        await update.message.reply_text(report, parse_mode="HTML")
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


async def daily_stats_callback(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send daily statistics report to the admin chat at midnight."""
    try:
        report = stats.generate_stats_report(reset_daily=False)
        chat_id = (
            context.job.chat_id
            if getattr(context, "job", None) and context.job.chat_id
            else context.application.bot_data.get("chat_id")
        )
        await context.bot.send_message(chat_id=chat_id, text=report, parse_mode="HTML")
        stats.reset_daily_stats()
    except Exception as e:
        logger.error(f"Error sending daily stats report: {e}")


async def ok_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Command to approve a media item"""
    logger.info(f"Received /ok command from user {update.effective_user.id}")

    # Check admin rights
    if not await check_admin_rights(update, context):
        return

    message_id = str(update.effective_message.message_id)
    object_name = f"{message_id}.jpg"

    temp_path = None
    try:
        # Use helper function to download from MinIO
        temp_path, ext = await download_from_minio(
            PHOTOS_PATH + "/" + object_name, BUCKET_MAIN
        )

        await update.message.reply_text("Post approved!")

        # Get the target channel from config
        target_channel = context.bot_data.get("target_channel_id")
        if not target_channel:
            await update.message.reply_text("Target channel ID not set!")
            return

        # Use helper function to send media
        await send_media_to_telegram(context.bot, target_channel, temp_path, "photo")

        # Clean up
        storage.delete_file(PHOTOS_PATH + "/" + object_name, BUCKET_MAIN)
        logger.info("Created new post!")

        # Record stats
        media_type = "photo" if ext.lower() in [".jpg", ".jpeg", ".png"] else "video"
        stats.record_approved(media_type, filename=object_name, source="ok_command")

    except MinioError as e:
        logger.error(f"MinIO error in ok_command: {e}")
        await update.message.reply_text(f"Error: {str(e)}")
    except TelegramMediaError as e:
        logger.error(f"Telegram error in ok_command: {e}")
        await update.message.reply_text(f"Error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error in ok_command: {e}")
        await update.message.reply_text(f"An unexpected error occurred: {str(e)}")
    finally:
        cleanup_temp_file(temp_path)


async def notok_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Command to reject a media item"""
    logger.info(f"Received /notok command from user {update.effective_user.id}")

    # Check admin rights
    if not await check_admin_rights(update, context):
        return

    try:
        message_id = str(update.effective_message.message_id)
        object_name = f"{message_id}.jpg"

        # Try to determine media type
        media_type = "photo"  # Default

        # Delete from MinIO if exists
        if storage.file_exists(PHOTOS_PATH + "/" + object_name, BUCKET_MAIN):
            storage.delete_file(PHOTOS_PATH + "/" + object_name, BUCKET_MAIN)
            await update.message.reply_text("Post disapproved!")

            # Record stats
            stats.record_rejected(
                media_type, filename=object_name, source="notok_command"
            )
        else:
            await update.message.reply_text("No post found to disapprove.")
    except Exception as e:
        logger.error(f"Error in notok_command: {e}")
        await update.message.reply_text(f"Error: {str(e)}")


async def delete_batch_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Command to delete the current batch of media"""
    logger.info(f"Received /delete_batch command from user {update.effective_user.id}")

    # Check admin rights
    if not await check_admin_rights(update, context):
        return

    try:
        # Get all files with batch_ prefix from photos and videos directories
        photo_batch = storage.list_files(BUCKET_MAIN, prefix=f"{PHOTOS_PATH}/batch_")
        video_batch = storage.list_files(BUCKET_MAIN, prefix=f"{VIDEOS_PATH}/batch_")
        batch_files = photo_batch + video_batch

        if not batch_files:
            await context.bot.send_message(
                chat_id=context.bot_data["chat_id"], text="No files in batch to delete!"
            )
            return

        # Delete from MinIO
        deleted_count = 0
        for object_name in batch_files:
            try:
                storage.delete_file(object_name, BUCKET_MAIN)
                deleted_count += 1
            except Exception as e:
                logger.error(f"Error deleting {object_name}: {e}")
                stats.record_error("storage", f"Failed to delete batch file: {str(e)}")
                # Continue with other files

        await update.message.reply_text(
            f"Batch deleted! ({deleted_count} files removed)"
        )
    except Exception as e:
        logger.error(f"Error in delete_batch_command: {e}")
        await update.message.reply_text(f"Error: {str(e)}")


async def send_luba_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Command to send all files to Luba"""
    logger.info(f"Received /luba command from user {update.effective_user.id}")

    luba_chat = context.bot_data.get("luba_chat")

    # Check admin rights
    if not await check_admin_rights(update, context):
        return

    try:
        # Get all files from downloads bucket
        download_files = storage.list_files(BUCKET_MAIN, prefix=DOWNLOADS_PATH)

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
                    object_name, DOWNLOADS_PATH + "/" + BUCKET_MAIN
                )
                if not temp_path:
                    error_count += 1
                    continue

                # Determine media type based on extension
                media_type = "photo"
                if ext.lower() in [".mp4", ".avi", ".mov"]:
                    media_type = "video"

                # Отправляем медиа без подписи, включая поддержку потокового
                # воспроизведения для видео
                await send_media_to_telegram(
                    context.bot,
                    luba_chat,
                    temp_path,
                    caption=None,
                    supports_streaming=(media_type == "video"),
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
        await update.message.reply_text(f"Error: {str(e)}")


async def send_batch_command(update, context):
    """Command handler to send all items in the batch to the target channel"""
    if not await check_admin_rights(update, context):
        return

    try:
        # Get the target channel from config
        target_channel = context.bot_data.get("target_channel_id")
        if not target_channel:
            await update.message.reply_text("Target channel ID not set!")
            return

        batch_sent = False
        notified_users = set()  # Track which users we've notified

        # Process photo batch
        if "photo_batch" in context.bot_data and context.bot_data["photo_batch"]:
            batch_sent = True
            photo_count = len(context.bot_data["photo_batch"])
            logger.info(f"Sending photo batch with {photo_count} photos")

            # Process each photo in the batch
            for file_name in context.bot_data["photo_batch"]:
                temp_path = None
                try:
                    # Download photo from MinIO
                    temp_path, _ = await download_from_minio(
                        PHOTOS_PATH + "/" + file_name, BUCKET_MAIN, ".jpg"
                    )

                    # Send to target channel
                    with open(temp_path, "rb") as f:
                        await context.bot.send_photo(chat_id=target_channel, photo=f)
                    stats.record_approved(
                        "photo", filename=file_name, source="send_batch_command"
                    )

                    # Notify the user if this is their media
                    user_metadata = storage.get_submission_metadata(file_name)
                    if user_metadata and not user_metadata.get("notified"):
                        user_id = user_metadata["user_id"]

                        # Only notify each user once per batch to avoid spam
                        if user_id not in notified_users:
                            from telegram_auto_poster.bot.handlers import notify_user

                            await notify_user(
                                context,
                                user_id,
                                "Отличные новости! Ваша фотография была одобрена и размещена в канале как часть пакета. Спасибо за ваш вклад!",
                            )
                            notified_users.add(user_id)

                        # Mark as notified regardless
                        storage.mark_notified(file_name)

                except Exception as e:
                    logger.error(f"Error sending photo {file_name}: {e}")
                    stats.record_error(
                        "telegram", f"Failed to send photo in batch: {str(e)}"
                    )
                finally:
                    cleanup_temp_file(temp_path)

            # Clear the photo batch
            context.bot_data["photo_batch"] = []

        # Process video batch
        if "video_batch" in context.bot_data and context.bot_data["video_batch"]:
            batch_sent = True
            video_count = len(context.bot_data["video_batch"])
            logger.info(f"Sending video batch with {video_count} videos")

            # Process each video in the batch
            for file_name in context.bot_data["video_batch"]:
                temp_path = None
                try:
                    # Download video from MinIO
                    temp_path, _ = await download_from_minio(
                        VIDEOS_PATH + "/" + file_name, BUCKET_MAIN, ".mp4"
                    )

                    # Send to target channel
                    with open(temp_path, "rb") as f:
                        await context.bot.send_video(
                            chat_id=target_channel,
                            video=f,
                            supports_streaming=True,
                        )
                    stats.record_approved(
                        "video", filename=file_name, source="send_batch_command"
                    )

                    # Notify the user if this is their media
                    user_metadata = storage.get_submission_metadata(file_name)
                    if user_metadata and not user_metadata.get("notified"):
                        user_id = user_metadata["user_id"]

                        # Only notify each user once per batch to avoid spam
                        if user_id not in notified_users:
                            from telegram_auto_poster.bot.handlers import notify_user

                            await notify_user(
                                context,
                                user_id,
                                "Отличные новости! Ваше видео было одобрено и размещено в канале как часть пакета. Спасибо за ваш вклад!",
                            )
                            notified_users.add(user_id)

                        # Mark as notified regardless
                        storage.mark_notified(file_name)

                except Exception as e:
                    logger.error(f"Error sending video {file_name}: {e}")
                    stats.record_error(
                        "telegram", f"Failed to send video in batch: {str(e)}"
                    )
                finally:
                    cleanup_temp_file(temp_path)

            # Clear the video batch
            context.bot_data["video_batch"] = []

        if batch_sent:
            stats.record_batch_sent(1)
            await update.message.reply_text("Batch sent to channel!")
        else:
            await update.message.reply_text("No items in batch!")
    except Exception as e:
        logger.error(f"Error sending batch: {e}")
        stats.record_error("processing", f"Error sending batch: {str(e)}")
        await update.message.reply_text(f"Error sending batch: {str(e)}")
