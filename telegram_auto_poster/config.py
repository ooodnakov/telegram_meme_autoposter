import configparser
import os


def load_config():
    config = configparser.ConfigParser()
    config.read("config.ini")

    # Load basic configuration from config.ini
    conf_dict = {
        "api_id": int(config["Telegram"]["api_id"]),
        "api_hash": config["Telegram"]["api_hash"],
        "username": config["Telegram"]["username"],
        "target_channel": config["Telegram"]["target_channel"],
        "bot_token": config["Bot"]["bot_token"],
        "bot_username": config["Bot"]["bot_username"],
        "bot_chat_id": config["Bot"]["bot_chat_id"],
    }

    # Add admin IDs if they exist in config
    if config.has_option("Bot", "admin_ids"):
        # Admin IDs can be comma-separated list of user IDs
        admin_ids_str = config["Bot"]["admin_ids"]
        admin_ids = [int(id.strip()) for id in admin_ids_str.split(",") if id.strip()]
        conf_dict["admin_ids"] = admin_ids
    # If admin_ids isn't in config, check environment variable
    elif os.environ.get("TELEGRAM_ADMIN_IDS"):
        admin_ids_str = os.environ.get("TELEGRAM_ADMIN_IDS")
        admin_ids = [int(id.strip()) for id in admin_ids_str.split(",") if id.strip()]
        conf_dict["admin_ids"] = admin_ids
    # Default to bot_chat_id if no admin IDs are specified
    else:
        conf_dict["admin_ids"] = [int(conf_dict["bot_chat_id"])]

    return conf_dict


SELECTED_CHATS = [
    "@rand2ch",
    "@grotesque_tg",
    "@axaxanakanecta",
    "@gvonotestsh",
    "@profunctor_io",
    "@ttttttttttttsdsd",
    "@dsasdadsasda",
]

LUBA_CHAT = "@Shanova_uuu"


# Define bucket names
PHOTOS_BUCKET = "photos"
VIDEOS_BUCKET = "videos"
DOWNLOADS_BUCKET = "downloads"
