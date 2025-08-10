import asyncio
import configparser
import json
import os
import random
import sys
from pathlib import Path
from random import randint

import piexif
from loguru import logger
from PIL import Image
from PIL.ImageFile import ImageFile
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telethon import events, types
from telethon.sync import TelegramClient

# Logging
logging_format = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{file.path}</cyan>:<cyan>{line}</cyan> <cyan>{function}</cyan> - <level>{message}</level>"
)

logger.remove()
logger.add(sys.stderr, format=logging_format)


# Для корректного переноса времени сообщений в json

config = configparser.ConfigParser()
config.read("config.ini")

api_id = int(config["Telegram"]["api_id"])
api_hash = config["Telegram"]["api_hash"]
username = config["Telegram"]["username"]
target_channel = config["Telegram"]["target_channel"]

bot_token = config["Bot"]["bot_token"]
bot_username = config["Bot"]["bot_username"]
bot_chat_id = config["Bot"]["bot_chat_id"]

selected_chats = [
    "@rand2ch",
    "@grotesque_tg",
    "@axaxanakanecta",
    "@gvonotestsh",
    "@profunctor_io",
    "@ttttttttttttsdsd",
    "@dsasdadsasda",
]
luba = "@Shanova_uuu"

client = TelegramClient(username, api_id, api_hash)


async def add_watermark_to_image(input_filename, output_filename):
    base: ImageFile = Image.open(input_filename)
    overlay = Image.open("wm.png").resize(
        [int(base.size[0] * 0.1)] * 2, Image.Resampling.NEAREST
    )
    overlay.putalpha(40)

    position = (
        randint(0, base.width - overlay.width),
        randint(0, base.height - overlay.height),
    )

    base.paste(overlay, position, overlay)

    exif_dict = {}
    exif_dict["0th"] = {}
    exif_dict["0th"][piexif.ImageIFD.Artist] = "t.me/ooodnakov_memes"
    exif_dict["0th"][piexif.ImageIFD.ImageDescription] = "t.me/ooodnakov_memes"
    exif_dict["0th"][piexif.ImageIFD.Copyright] = "t.me/ooodnakov_memes"

    # Convert the modified EXIF data to bytes
    exif_bytes = piexif.dump(exif_dict)
    base.save(output_filename, exif=exif_bytes)
    os.remove(input_filename)


async def _probe_video_size(path: str) -> tuple[int, int]:
    """
    Возвращает (width, height) первого видеопотока.
    """
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "json",
        path,
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    out, _ = await proc.communicate()
    info = json.loads(out)
    w = info["streams"][0]["width"]
    h = info["streams"][0]["height"]
    return w, h


async def add_watermark_to_video(input_filename, output_filename) -> str:
    watermark_path = str(Path("wm.png").expanduser())

    # 1. Определяем размер видео
    v_w, v_h = await _probe_video_size(input_filename)

    # 2. Рассчитываем конечную ширину водяного знака
    wm_w = int(min(v_w, v_h) * random.randint(15, 25) / 100)

    # 3. Случайные координаты левого верхнего угла, чтобы знак полностью помещался
    max_x = max(v_w - wm_w, 0)
    max_y = max(v_h - wm_w, 0)  # высоту подгоним пропорционально, поэтому тоже wm_w
    random.randint(0, max_x)
    random.randint(0, max_y)

    # 5. Строим фильтр:
    #    [1] – картинка: масштабируем, переводим в RGBA, задаём альфу
    #    затем накладываем на [0] (видео)

    # Define diagonal bouncing movement for watermark
    speed = 100
    filter_complex = (
        f"[1]scale={wm_w}:{wm_w}[wm];"
        f"[0][wm]overlay=x='if(gt(mod(t*{speed},2*({v_w}-{wm_w})),({v_w}-{wm_w})), "
        f"2*({v_w}-{wm_w})-mod(t*{speed},2*({v_w}-{wm_w})), mod(t*{speed},2*({v_w}-{wm_w})))':"
        f"y='if(gt(mod(t*{speed},2*({v_h}-{wm_w})),({v_h}-{wm_w})), "
        f"2*({v_h}-{wm_w})-mod(t*{speed},2*({v_h}-{wm_w})), mod(t*{speed},2*({v_h}-{wm_w})))'"
    )
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        input_filename,
        "-i",
        watermark_path,
        "-metadata",
        "title=t.me/ooodnakov_memes",
        "-metadata",
        "comment=t.me/ooodnakov_memes",
        "-metadata",
        "copyright=t.me/ooodnakov_memes",
        "-metadata",
        "description=t.me/ooodnakov_memes",
        "-filter_complex",
        filter_complex,
        "-c:v",
        # "mpeg4",
        # "-q:v",
        # "6",
        "libx264",
        "-preset",
        "slow",  # Balances speed and compression efficiency
        "-crf",
        "18",  # Lower CRF means better quality; 18 is visually lossless
        "-c:a",
        "copy",  # аудио не перекодируем
        output_filename,
    ]
    logger.info("Running ffmppeg cmd: {}", " ".join(cmd))
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    _, err = await proc.communicate()
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg error:\n{err.decode()}")

    logger.info("Finished processing {}", output_filename)
    os.remove(input_filename)
    return output_filename


def get_file_name(caption):
    return caption.split("\n")[-1]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Привет! Присылай сюда свои мемы)")


async def ok_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # if os.path.isfile('downloaded_image.jpg'):
    if os.path.isfile(str(update.effective_message.message_id) + ".jpg"):
        await update.message.reply_text("Post approved!")
        await client.send_file(
            target_channel, str(update.effective_message.message_id) + ".jpg"
        )
        logger.info("Created new post!")
        os.remove(str(update.effective_message.message_id) + ".jpg")
    else:
        await update.message.reply_text(
            "No approved post image, it's already disapproved!"
        )
        logger.warning("No file!")


async def notok_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Disapprove the message
    await update.message.reply_text("Post disapproved!")
    if os.path.isfile(f"photos/{str(update.effective_message.message_id)}.jpg"):
        os.remove(f"photos/{str(update.effective_message.message_id)}.jpg")


async def push_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
        await client.send_file(
            target_channel,
            filename,
            caption=caption,
            supports_streaming=(True if ".mp4" in filename else False),
        )
        logger.info(f"Created new post from image {filename}!")
        os.remove(filename)
    else:
        await update.effective_message.reply_text(
            "No approved post image, it's already disapproved!"
        )
        logger.warning("No file!")


async def ok_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    caption = update.effective_message.caption
    filename = get_file_name(caption)
    if os.path.isfile(filename):
        if "suggestion" in update.effective_message.caption:
            caption = "Пост из предложки @ooodnakov_memes_suggest_bot"
            await update.effective_message.edit_caption(
                f"Post approved with media {filename}!", reply_markup=None
            )
            await client.send_file(
                target_channel,
                filename,
                caption=caption,
                supports_streaming=(True if ".mp4" in filename else False),
            )
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
        await update.effective_message.reply_text(
            "No approved post media, it's already disapproved!"
        )
        logger.warning("No file!")


async def send_batch_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    batch = []
    for p in os.listdir("photos"):
        if "batch" in p:
            batch.append(f"photos/{p}")
    if len(batch) > 0:
        await client.send_file(target_channel, batch, caption="Новый пак мемов.")

        for p in os.listdir("photos"):
            if "batch" in p:
                os.remove("photos/" + p)
    else:
        await application.bot.send_message(bot_chat_id, "Empty batch!")


async def delete_batch_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    for p in os.listdir("photos"):
        if "batch" in p:
            os.remove("photos/" + p)
    await application.bot.send_message(bot_chat_id, "Batch deleted!")


async def notok_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Disapprove the message
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


async def process_photo(custom_text, name):
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
        # await m.edit_caption(f'{custom_text} {m.message_id}', reply_markup = keyboard)

        # os.rename('processed_'+name, f'photos/{m.message_id}.jpg')

        logger.info(f"New photo {name} in channel!")


async def process_video(custom_text, name) -> None:
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


async def Photo(update: Update, context) -> None:
    chat_id = update.effective_chat.id
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        message_id = update.message.message_id
        file_path = f"downloaded_image_{chat_id}_{file_id}_{message_id}.jpg"
        f = await context.bot.get_file(file_id)
        await f.download_to_drive(file_path)
        logger.info(f"Photo from chat {chat_id} has downloaded!")
        await process_photo("New suggestion in bot", file_path)
    elif update.message.video:
        logger.info(f"Video from chat {chat_id} has started downloading!")
        file_id = update.message.video.file_id
        message_id = update.message.message_id
        file_path = f"downloaded_video_{chat_id}_{file_id}_{message_id}.mp4"
        f = await context.bot.get_file(file_id)
        await f.download_to_drive(file_path)
        logger.info(f"Video from chat {chat_id} has been downloaded!")
        await process_video("New suggestion in bot", file_path)


async def get_chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    await update.message.reply_text(f"This chat ID is: {chat_id}")


@client.on(events.NewMessage(chats=selected_chats))
async def handle_photo(event):
    if isinstance(event.media, types.MessageMediaPhoto):
        photo = event.media.photo
        file_path = f"downloaded_image_{event.id}.jpg"
        await client.download_media(photo, file=file_path)
        await process_photo("New post found with image", file_path)
    elif isinstance(event.media, types.MessageMediaDocument):
        if event.media.video:  # Check if the media has a video
            logger.info(f"Video with eventid {event.id} has started downloading!")
            video = event.media.document
            file_path = f"downloaded_video_{event.id}.mp4"
            await client.download_media(video, file=file_path)
            logger.info(f"Video with eventid {event.id} has been downloaded!")
            await process_video("New post found with video", file_path)
    else:
        logger.info("New non photo/video in channel")


async def main():
    try:
        await client.start()

        # Get the channel entity to listen for messages
        try:
            for ch in selected_chats:
                channel = await client.get_entity(ch)
                logger.info(f"Listening for messages in {channel.title}")
        except (TypeError, ValueError) as e:
            logger.info(f"Error getting channel entity: {e}")
            return

        # Run the event loop indefinitely
        await asyncio.Event().wait()

    except Exception as e:
        logger.info(f"An error occurred: {e}")


if __name__ == "__main__":
    # Initialize the Bot and Application
    application = (
        ApplicationBuilder()
        .token(bot_token)  # Replace with your actual bot token
        .build()
    )

    # Register command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("ok", ok_command))
    application.add_handler(CommandHandler("notok", notok_command))
    application.add_handler(CommandHandler("get", get_chat_id))
    application.add_handler(CommandHandler("send_batch", send_batch_command))
    application.add_handler(CommandHandler("delete_batch", delete_batch_command))
    application.add_handler(CallbackQueryHandler(ok_callback, "/ok"))
    application.add_handler(CallbackQueryHandler(push_callback, "/push"))
    application.add_handler(CallbackQueryHandler(notok_callback, "/notok"))
    application.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO, Photo))

    # Start the Bot
    loop = asyncio.get_event_loop()
    loop.create_task(main())
    loop.create_task(
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            poll_interval=0.5,
            write_timeout=20,
            read_timeout=20,
            bootstrap_retries=1,
        )
    )

    loop.run_forever()
