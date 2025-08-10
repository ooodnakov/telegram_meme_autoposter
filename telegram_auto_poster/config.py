import configparser
import os


REQUIRED_FIELDS = {
    "Telegram": ["api_id", "api_hash", "username", "target_channel"],
    "Bot": ["bot_token", "bot_username", "bot_chat_id"],
    "Chats": ["selected_chats", "luba_chat"],
}


def load_config():
    config = configparser.ConfigParser()
    config_path = os.getenv("CONFIG_PATH", "config.ini")
    config.read(config_path)

    for section, fields in REQUIRED_FIELDS.items():
        if not config.has_section(section):
            raise RuntimeError(f"Missing section [{section}] in config.ini")
        for field in fields:
            if not config.has_option(section, field) or not config.get(section, field):
                raise RuntimeError(
                    f"Missing required field '{field}' in section [{section}]"
                )

    try:
        api_id = int(config["Telegram"]["api_id"])
    except ValueError as exc:
        raise RuntimeError(
            "Параметр api_id должен быть числом в секции [Telegram]"
        ) from exc

    conf_dict = {
        "api_id": api_id,
        "api_hash": config["Telegram"]["api_hash"],
        "username": config["Telegram"]["username"],
        "target_channel": config["Telegram"]["target_channel"],
        "bot_token": config["Bot"]["bot_token"],
        "bot_username": config["Bot"]["bot_username"],
        "bot_chat_id": config["Bot"]["bot_chat_id"],
        "selected_chats": [
            chat.strip() for chat in config["Chats"]["selected_chats"].split(",")
        ],
        "luba_chat": config["Chats"]["luba_chat"],
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


# Define path names
BUCKET_MAIN = "telegram-auto-poster"
PHOTOS_PATH = "photos"
VIDEOS_PATH = "videos"
DOWNLOADS_PATH = "downloads"
