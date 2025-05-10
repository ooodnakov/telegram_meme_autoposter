import configparser
import asyncio
import os
import time
from PIL import Image

from telethon.sync import TelegramClient
from telethon import events, types

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

# Для корректного переноса времени сообщений в json

config = configparser.ConfigParser()
config.read("config.ini")

api_id = config["Telegram"]["api_id"]
api_hash = config["Telegram"]["api_hash"]
username = config["Telegram"]["username"]
target_channel = config["Telegram"]["target_channel"]

bot_token = config["Bot"]["bot_token"]
bot_username = config["Bot"]["bot_username"]
bot_chat_id = config["Bot"]["bot_chat_id"]


async def add_watermark_to_image(input_filename, output_filename):
    base = Image.open(input_filename)
    overlay = Image.open("wm.jpg").resize(
        [int(base.size[0] * 0.1)] * 2, Image.Resampling.NEAREST
    )
    overlay.putalpha(40)
    # Randomize position
    from random import randint

    position = (
        randint(0, base.width - overlay.width),
        randint(0, base.height - overlay.height),
    )

    base.paste(overlay, position, overlay)
    base.save(output_filename)
    os.remove(input_filename)


selected_chats = [
    "@rand2ch",
    "@grotesque_tg",
    "@axaxanakanecta",
    "@gvonotestsh",
    "@profunctor_io",
    "@ttttttttttttsdsd",
]
luba = "@Shanova_uuu"

client = TelegramClient(username, api_id, api_hash)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Привет! Присылай сюда свои мемы)")


def get_file_name(caption):
    return caption.split("\n")[-1]


async def ok_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # if os.path.isfile('downloaded_image.jpg'):
    if os.path.isfile(str(update.effective_message.message_id) + ".jpg"):
        await update.message.reply_text("Post approved!")
        await client.send_file(
            target_channel, str(update.effective_message.message_id) + ".jpg"
        )
        print("Created new post!")
        os.remove(str(update.effective_message.message_id) + ".jpg")
    else:
        await update.message.reply_text(
            "No approved post image, it's already disapproved!"
        )
        print("No file!")


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
        await client.send_file(target_channel, filename, caption=caption)
        print(f"Created new post from image {filename}!")
        os.remove(filename)
    else:
        await update.effective_message.reply_text(
            "No approved post image, it's already disapproved!"
        )
        print("No file!")


async def ok_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    caption = update.effective_message.caption
    filename = get_file_name(caption)
    if os.path.isfile(filename):
        if "suggestion" in update.effective_message.caption:
            caption = "Пост из предложки @ooodnakov_memes_suggest_bot"
            await update.effective_message.edit_caption(
                f"Post approved with image {filename}!", reply_markup=None
            )
            await client.send_file(target_channel, filename, caption=caption)
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
            "No approved post image, it's already disapproved!"
        )
        print("No file!")


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


async def send_luba_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    for p in os.listdir("downloaded_images"):
        photo_path = f"downloaded_images/{p}"
        await client.send_file(luba, photo_path, caption=p)
        time.sleep(1)


async def delete_batch_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    for p in os.listdir("photos"):
        if "batch" in p:
            os.remove("photos/" + p)
    await application.bot.send_message(bot_chat_id, "Batch deleted!")


async def notok_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Disapprove the message
    await update.effective_message.edit_caption(
        f"Post disapproved with image {update.effective_message.message_id}.jpg!",
        reply_markup=None,
    )
    print(f"Post disapproved with image {update.effective_message.message_id}.jpg!")
    if os.path.isfile(f"photos/{str(update.effective_message.message_id)}.jpg"):
        os.remove(f"photos/{str(update.effective_message.message_id)}.jpg")


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
            "New post found\n" + "photos/processed_" + name,
            reply_markup=keyboard,
            read_timeout=60,
            write_timeout=60,
            connect_timeout=60,
            pool_timeout=60,
        )
        # await m.edit_caption(f'{custom_text} {m.message_id}', reply_markup = keyboard)

        # os.rename('processed_'+name, f'photos/{m.message_id}.jpg')

        print(f"New photo {name} in channel!")


async def Photo(update: Update, context) -> None:
    chat_id = update.effective_chat.id
    file_id = update.message.photo[-1].file_id
    file_path = f"{chat_id}_{file_id}.jpg"
    f = await context.bot.get_file(file_id)
    await f.download_to_drive(file_path)
    print(f"Photo from chat {chat_id} had been downloaded!")
    await process_photo("New suggestion in bot", file_path)


async def get_chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await update.message.reply_text(f"This chat ID is: {chat_id}")


@client.on(events.NewMessage(chats=selected_chats))
async def handle_photo(event):
    if isinstance(event.media, types.MessageMediaPhoto):
        photo = event.media.photo
        file_path = f"downloaded_image_{event.id}.jpg"
        await client.download_media(photo, file=file_path)
        await process_photo("New post found with image", file_path)
    else:
        print("New non photo in channel(")


async def main():
    try:
        await client.start()

        # Get the channel entity to listen for messages
        try:
            for ch in selected_chats:
                channel = await client.get_entity(ch)
                print(f"Listening for messages in {channel.title}")
        except (TypeError, ValueError) as e:
            print(f"Error getting channel entity: {e}")
            return

        # Run the event loop indefinitely
        await asyncio.Event().wait()

    except Exception as e:
        print(f"An error occurred: {e}")


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
    application.add_handler(CommandHandler("luba", send_luba_command))
    application.add_handler(CallbackQueryHandler(ok_callback, "/ok"))
    application.add_handler(CallbackQueryHandler(push_callback, "/push"))
    application.add_handler(CallbackQueryHandler(notok_callback, "/notok"))
    application.add_handler(MessageHandler(filters.PHOTO, Photo))

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
