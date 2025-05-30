import os
import asyncio
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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(f"Received /start command from user {update.effective_user.id}")
    await update.message.reply_text("Привет! Присылай сюда свои мемы)")


async def get_chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    logger.info(f"Received /get chat_id command, returning ID: {chat_id}")
    await update.message.reply_text(f"This chat ID is: {chat_id}")


async def ok_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(f"Received /ok command from user {update.effective_user.id}")
    if os.path.isfile(str(update.effective_message.message_id) + ".jpg"):
        await update.message.reply_text("Post approved!")
        # Use client.send_file instead of context.bot.send_photo
        client = get_client(context)
        if client:
            await client.send_file(
                target_channel, str(update.effective_message.message_id) + ".jpg"
            )
            logger.info("Created new post!")
        else:
            logger.error("Client instance not available!")
        os.remove(str(update.effective_message.message_id) + ".jpg")
    else:
        await update.message.reply_text(
            "No approved post image, it's already disapproved!"
        )
        logger.warning("No file!")


async def notok_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(f"Received /notok command from user {update.effective_user.id}")
    await update.message.reply_text("Post disapproved!")
    if os.path.isfile(f"photos/{str(update.effective_message.message_id)}.jpg"):
        os.remove(f"photos/{str(update.effective_message.message_id)}.jpg")


async def send_batch_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    logger.info(f"Received /send_batch command from user {update.effective_user.id}")
    batch = []
    for p in os.listdir("photos"):
        if "batch" in p:
            batch.append(f"photos/{p}")
    if len(batch) > 0:
        # Use client.send_file for batch media
        client = get_client(context)
        if client:
            await client.send_file(target_channel, batch, caption="Новый пак мемов.")
            logger.info(f"Sent batch of {len(batch)} files to channel")
        else:
            logger.error("Client instance not available!")

        for p in os.listdir("photos"):
            if "batch" in p:
                os.remove("photos/" + p)
    else:
        await context.bot.send_message(
            chat_id=context.bot_data["chat_id"], text="Empty batch!"
        )


async def delete_batch_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    logger.info(f"Received /delete_batch command from user {update.effective_user.id}")
    for p in os.listdir("photos"):
        if "batch" in p:
            os.remove("photos/" + p)
    await context.bot.send_message(
        chat_id=context.bot_data["chat_id"], text="Batch deleted!"
    )


async def ok_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(f"Received /ok callback from user {update.effective_user.id}")
    logger.debug(f"Callback data: {update.callback_query.data}")

    # Always answer callback query to avoid the loading indicator
    await update.callback_query.answer()

    caption = update.effective_message.caption
    filename = get_file_name(caption)
    if os.path.isfile(filename):
        if "suggestion" in update.effective_message.caption:
            caption = "Пост из предложки @ooodnakov_memes_suggest_bot"
            await update.effective_message.edit_caption(
                f"Post approved with media {filename}!", reply_markup=None
            )
            # Use client.send_file for sending media to channel
            client = get_client(context)
            if client:
                await client.send_file(
                    target_channel,
                    filename,
                    caption=caption,
                    supports_streaming=(True if ".mp4" in filename else False),
                )
            else:
                logger.error("Client instance not available!")
        else:
            os.rename(
                filename,
                "".join([filename.split("/")[0], "/batch_", filename.split("/")[1]]),
            )
            batch_c = 0
            for p in os.listdir("photos"):
                if "batch" in p:
                    batch_c += 1
            await update.effective_message.edit_caption(
                f"Post added to batch! There are {batch_c} posts in the batch.",
                reply_markup=None,
            )
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
    if os.path.isfile(filename):
        if "suggestion" in update.effective_message.caption:
            caption = "Пост из предложки @ooodnakov_memes_suggest_bot"
        else:
            caption = ""
        await update.effective_message.edit_caption(
            f"Post approved with image {filename}!", reply_markup=None
        )
        # Use client.send_file for sending media to channel
        client = get_client(context)
        if client:
            await client.send_file(
                target_channel,
                filename,
                caption=caption,
                supports_streaming=(True if ".mp4" in filename else False),
            )
            logger.info(f"Created new post from image {filename}!")
        else:
            logger.error("Client instance not available!")
        os.remove(filename)
    else:
        await update.callback_query.message.reply_text(
            "No approved post image, it's already disapproved!"
        )
        logger.warning("No file!")


async def notok_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(f"Received /notok callback from user {update.effective_user.id}")
    logger.debug(f"Callback data: {update.callback_query.data}")

    await update.callback_query.answer()

    caption = update.effective_message.caption
    photo_name = get_file_name(caption)
    await update.effective_message.edit_caption(
        f"Post disapproved with media {photo_name}!",
        reply_markup=None,
    )
    logger.info(f"Post disapproved with media \n{photo_name}!")
    if os.path.isfile(photo_name):
        logger.info("Removing photo!")
        os.remove(photo_name)


def get_file_name(caption):
    return caption.split("\n")[-1]


async def process_photo(custom_text: str, name: str, bot_chat_id: str, application):
    await add_watermark_to_image(name, "photos/processed_" + name)
    if os.path.isfile("photos/processed_" + name):
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

        await application.bot.send_photo(
            bot_chat_id,
            "photos/processed_" + name,
            custom_text + "\nNew post found\n" + "photos/processed_" + name,
            reply_markup=keyboard,
            read_timeout=60,
            write_timeout=60,
            connect_timeout=60,
            pool_timeout=60,
        )
        logger.info(f"New photo {name} in channel!")


async def process_video(
    custom_text: str, name: str, bot_chat_id: str, application
) -> None:
    await add_watermark_to_video(name, "videos/processed_" + name)
    if os.path.isfile("videos/processed_" + name):
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
        try:
            await application.bot.send_video(
                bot_chat_id,
                video=open("videos/processed_" + name, "rb"),
                caption=custom_text
                + "\nNew video found\n"
                + "videos/processed_"
                + name,
                supports_streaming=True,
                reply_markup=keyboard,
                read_timeout=60,
                write_timeout=60,
                connect_timeout=60,
                pool_timeout=60,
            )
            logger.info(f"New video {name} in channel!")
        except Exception as e:
            logger.error("Failed to upload video with error {}", e)


async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        message_id = update.message.message_id
        file_path = f"downloaded_image_{chat_id}_{file_id}_{message_id}.jpg"
        f = await context.bot.get_file(file_id)
        await f.download_to_drive(file_path)
        logger.info(f"Photo from chat {chat_id} has downloaded!")
        await process_photo(
            "New suggestion in bot",
            file_path,
            context.bot_data["chat_id"],
            context.application,
        )
    elif update.message.video:
        logger.info(f"Video from chat {chat_id} has started downloading!")
        file_id = update.message.video.file_id
        message_id = update.message.message_id
        file_path = f"downloaded_video_{chat_id}_{file_id}_{message_id}.mp4"
        f = await context.bot.get_file(file_id)
        await f.download_to_drive(file_path)
        logger.info(f"Video from chat {chat_id} has been downloaded!")
        await process_video(
            "New suggestion in bot",
            file_path,
            context.bot_data["chat_id"],
            context.application,
        )
