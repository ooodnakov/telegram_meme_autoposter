import asyncio
import datetime
import os

from loguru import logger
from telegram import InputMediaDocument, InputMediaPhoto, InputMediaVideo, Update
from telegram.ext import ContextTypes

import telegram_auto_poster.utils.db as db
from telegram_auto_poster.bot.callbacks import (
    list_batch_files,
    send_batch_preview,
    send_schedule_preview,
)
from telegram_auto_poster.bot.handlers import notify_user
from telegram_auto_poster.bot.permissions import check_admin_rights
from telegram_auto_poster.config import (
    BUCKET_MAIN,
    DOWNLOADS_PATH,
    PHOTOS_PATH,
    VIDEOS_PATH,
)
from telegram_auto_poster.utils.general import (
    MinioError,
    TelegramMediaError,
    cleanup_temp_file,
    download_from_minio,
    send_media_to_telegram,
)
from telegram_auto_poster.utils.i18n import _, resolve_locale, set_locale
from telegram_auto_poster.utils.stats import stats
from telegram_auto_poster.utils.storage import storage
from telegram_auto_poster.utils.timezone import UTC, format_display, now_utc


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start the bot and provide welcome message"""
    logger.info(f"Received /start command from user {update.effective_user.id}")
    set_locale(resolve_locale(update))
    await update.message.reply_text(_("Привет! Присылай сюда свои мемы)"))


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display help information about the bot"""
    logger.info(f"Received /help command from user {update.effective_user.id}")
    set_locale(resolve_locale(update))

    is_admin = False
    user_id = update.effective_user.id
    if hasattr(context, "bot_data") and "admin_ids" in context.bot_data:
        admin_ids = context.bot_data["admin_ids"]
        if user_id in admin_ids:
            is_admin = True
    help_text_parts = [
        _(
            "<b>Предложка для @ooodnakov_memes</b>\n\n"
            "<b>Команды пользователя:</b>\n"
            "• /start - Запустить бота\n"
            "• /help - Показать это сообщение помощи\n\n"
            "<b>Как использовать:</b>\n"
            "1. Отправьте фото или видео этому боту\n"
            "2. Администраторы проверят ваши отправления\n"
            "3. Вы получите уведомление, когда ваш контент будет одобрен или отклонен"
        )
    ]

    if is_admin:
        help_text_parts.append(
            _(
                "<b>Команды администратора:</b>\n"
                "• /stats - Просмотр статистики обработки медиа\n"
                "• /reset_stats - Сбросить ежедневную статистику\n"
                "• /save_stats - Принудительно сохранить статистику\n"
                "• /sendall - Отправить все одобренные медиафайлы из пакета в целевой канал\n"
                "• /delete_batch - Удалить текущий пакет медиафайлов\n"
                "• /get - Получить текущий ID чата\n\n"
                "<b>Проверка контента администратором:</b>\n"
                "При проверке контента вы можете использовать кнопки для:\n"
                "• Send to batch - Добавить медиа в пакет для последующей отправки\n"
                "• Schedule - Добавляет медиа в очередь\n"
                "• Push - Немедленно опубликовать медиа в канале\n"
                "• No - Отклонить медиа"
            )
        )

    help_text = "\n\n".join(help_text_parts)

    logger.info(help_text)
    await update.message.reply_text(help_text, parse_mode="HTML")


async def get_chat_id_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Get the current chat ID"""
    chat_id = update.effective_chat.id
    logger.info(f"Received /get chat_id command, returning ID: {chat_id}")
    await update.message.reply_text(
        _("This chat ID is: {chat_id}").format(chat_id=chat_id)
    )


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Command to show bot statistics"""
    logger.info(f"Received /stats command from user {update.effective_user.id}")

    # Check admin rights
    if not await check_admin_rights(update, context):
        return

    try:
        # Generate statistics report
        report = await stats.generate_stats_report()
        if not report or not report.strip():
            report = _("No statistics available.")
        await update.message.reply_text(report, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error generating stats report: {e}")
        await update.message.reply_text(
            _("Sorry, there was an error generating the statistics report.")
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
        result = await stats.reset_daily_stats()
        if not result or not result.strip():
            result = _("Daily statistics have been reset.")
        await update.message.reply_text(result)
    except Exception as e:
        logger.error(f"Error resetting stats: {e}")
        await update.message.reply_text(
            _("Sorry, there was an error resetting the statistics.")
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
        await stats.force_save()
        await update.message.reply_text(_("Stats saved!"))
    except Exception as e:
        logger.error(f"Error saving stats: {e}")
        await update.message.reply_text(
            _("Sorry, there was an error saving the statistics.")
        )


async def daily_stats_callback(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send daily statistics report to the admin chat at midnight."""
    try:
        report = await stats.generate_stats_report(reset_daily=False)
        chat_id = (
            context.job.chat_id
            if getattr(context, "job", None) and context.job.chat_id
            else context.application.bot_data.get("chat_id")
        )
        await context.bot.send_message(chat_id=chat_id, text=report, parse_mode="HTML")
        await stats.reset_daily_stats()
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
        await storage.delete_file(PHOTOS_PATH + "/" + object_name, BUCKET_MAIN)
        logger.info("Created new post!")

        # Record stats
        media_type = "photo" if ext.lower() in [".jpg", ".jpeg", ".png"] else "video"
        await stats.record_approved(
            media_type, filename=object_name, source="ok_command"
        )

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
        if await storage.file_exists(PHOTOS_PATH + "/" + object_name, BUCKET_MAIN):
            await storage.delete_file(PHOTOS_PATH + "/" + object_name, BUCKET_MAIN)
            await update.message.reply_text("Post disapproved!")

            # Record stats
            await stats.record_rejected(
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
        photo_batch = await storage.list_files(
            BUCKET_MAIN, prefix=f"{PHOTOS_PATH}/batch_"
        )
        video_batch = await storage.list_files(
            BUCKET_MAIN, prefix=f"{VIDEOS_PATH}/batch_"
        )
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
                await storage.delete_file(object_name, BUCKET_MAIN)
                deleted_count += 1
            except Exception as e:
                logger.error(f"Error deleting {object_name}: {e}")
                await stats.record_error(
                    "storage", f"Failed to delete batch file: {str(e)}"
                )
                # Continue with other files

        await db.decrement_batch_count(deleted_count)
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
        download_files = await storage.list_files(BUCKET_MAIN, prefix=DOWNLOADS_PATH)

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


async def post_scheduled_media_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Job to post scheduled media."""
    logger.info("Running scheduled media job...")
    try:
        now_ts = int(now_utc().timestamp())
        # Get posts scheduled up to now
        scheduled_posts = db.get_scheduled_posts(max_score=now_ts)

        if not scheduled_posts:
            logger.info("No scheduled posts to publish.")
            return

        target_channel = context.bot_data.get("target_channel_id")
        if not target_channel:
            logger.error("Target channel ID not set! Cannot post scheduled media.")
            return

        for post in scheduled_posts:
            file_path, timestamp = post
            logger.info(
                f"Processing scheduled post: {file_path} scheduled for "
                f"{format_display(datetime.datetime.fromtimestamp(timestamp, tz=UTC))}"
            )

            temp_path = None
            try:
                # Download from MinIO
                temp_path, _ = await download_from_minio(file_path, BUCKET_MAIN)

                # Send to channel without caption, enabling streaming for videos
                await send_media_to_telegram(
                    context.bot,
                    target_channel,
                    temp_path,
                    caption=None,
                    supports_streaming=(
                        os.path.splitext(temp_path)[1].lower()
                        in [".mp4", ".avi", ".mov"]
                    ),
                )

                # Clean up
                await storage.delete_file(file_path, BUCKET_MAIN)
                db.remove_scheduled_post(file_path)

                logger.info(f"Successfully posted scheduled media: {file_path}")
                # stats.record_published_scheduled(
                #     "video"
                #     if os.path.splitext(temp_path)[1].lower() in [".mp4", ".avi", ".mov"]
                #     else "photo"
                # )
            except Exception as e:
                logger.error(f"Error processing scheduled post {file_path}: {e}")
            finally:
                cleanup_temp_file(temp_path)

    except Exception as e:
        logger.error(f"Error in post_scheduled_media_job: {e}")


async def sch_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Command to show scheduled posts"""
    logger.info(f"Received /sch command from user {update.effective_user.id}")

    # Check admin rights
    if not await check_admin_rights(update, context):
        return

    try:
        scheduled_posts = db.get_scheduled_posts()
        if not scheduled_posts:
            await update.message.reply_text("No posts scheduled.")
            return

        first_path = scheduled_posts[0][0]
        await send_schedule_preview(
            context.bot, update.effective_chat.id, first_path, 0
        )
    except Exception as e:
        logger.error(f"Error in sch_command: {e}")
        await update.message.reply_text(
            "Sorry, there was an error retrieving the schedule."
        )


async def batch_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Command to show batch posts"""
    logger.info(f"Received /batch command from user {update.effective_user.id}")
    if not await check_admin_rights(update, context):
        return
    try:
        batch_files = await list_batch_files()
        if not batch_files:
            await update.message.reply_text("No items in batch.")
            return
        first_path = batch_files[0]
        await send_batch_preview(context.bot, update.effective_chat.id, first_path, 0)
    except Exception as e:
        logger.error(f"Error in batch_command: {e}")
        await update.message.reply_text(
            "Sorry, there was an error retrieving the batch."
        )


async def send_batch_command(update, context):
    """Send all batch_ files from MinIO to the target channel."""
    if not await check_admin_rights(update, context):
        return

    try:
        target_channel = context.bot_data.get("target_channel_id")
        if not target_channel:
            await update.message.reply_text("Target channel ID not set!")
            return

        # Collect current batch files directly from MinIO
        batch_files = await list_batch_files()
        if not batch_files:
            await update.message.reply_text("No items in batch!")
            return

        notified_users: set[int] = set()
        sent_count = 0

        media_info: list[dict[str, object]] = []

        for file_path in batch_files:
            temp_path, _ = await download_from_minio(file_path, BUCKET_MAIN)
            ext = os.path.splitext(temp_path)[1].lower()
            file_obj = open(temp_path, "rb")
            info = {
                "file_path": file_path,
                "temp_path": temp_path,
                "file_obj": file_obj,
                "media_type": "video" if ext in [".mp4", ".avi", ".mov"] else "photo",
                "base_name": os.path.basename(file_path),
            }
            if ext in [".mp4", ".avi", ".mov"]:
                info["input_media"] = InputMediaVideo(file_obj, supports_streaming=True)
            elif ext in [".jpg", ".jpeg", ".png"]:
                info["input_media"] = InputMediaPhoto(file_obj)
            else:
                info["input_media"] = InputMediaDocument(file_obj)
            media_info.append(info)

        for i in range(0, len(media_info), 10):
            chunk = media_info[i : i + 10]
            media_group = [item["input_media"] for item in chunk]
            try:
                await context.bot.send_media_group(
                    chat_id=target_channel, media=media_group
                )
            except Exception as e:
                logger.error(f"Error sending media group: {e}")
                await stats.record_error(
                    "telegram", f"Failed to send media group: {str(e)}"
                )
                continue

            for item in chunk:
                file_path = item["file_path"]
                temp_path = item["temp_path"]
                file_obj = item["file_obj"]
                media_type = item["media_type"]
                base_name = item["base_name"]
                file_obj.close()

                await stats.record_approved(
                    media_type,
                    filename=base_name,
                    source="send_batch_command",
                )

                user_metadata = await storage.get_submission_metadata(base_name)
                if user_metadata and not user_metadata.get("notified"):
                    user_id = user_metadata.get("user_id")
                    if user_id and user_id not in notified_users:
                        text = (
                            "Отличные новости! Ваша фотография была одобрена и размещена в канале как часть пакета. Спасибо за ваш вклад!"
                            if media_type == "photo"
                            else "Отличные новости! Ваше видео было одобрено и размещено в канале как часть пакета. Спасибо за ваш вклад!"
                        )
                        await notify_user(context, user_id, text)
                        notified_users.add(user_id)
                    await storage.mark_notified(base_name)

                cleanup_temp_file(temp_path)

                try:
                    await storage.delete_file(file_path, BUCKET_MAIN)
                except Exception as de:
                    logger.error(f"Failed to delete batch item {file_path}: {de}")

                sent_count += 1

        if sent_count:
            await db.decrement_batch_count(sent_count)
            await stats.record_batch_sent(1)
            await update.message.reply_text(
                f"Batch sent to channel! ({sent_count} items)"
            )
        else:
            await update.message.reply_text("No items were sent.")
    except Exception as e:
        logger.error(f"Error sending batch: {e}")
        await stats.record_error("processing", f"Error sending batch: {str(e)}")
        await update.message.reply_text(f"Error sending batch: {str(e)}")
