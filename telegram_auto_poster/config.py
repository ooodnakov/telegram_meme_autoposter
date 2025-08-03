import configparser
import os


REQUIRED_FIELDS = {
    "Telegram": ["api_id", "api_hash", "username", "target_channel"],
    "Bot": ["bot_token", "bot_username", "bot_chat_id"],
}


def load_config():
    config = configparser.ConfigParser()
    config_path = os.getenv("CONFIG_PATH", "config.ini")
    config.read(config_path)

    if not config.has_section("Telegram") or not config.has_section("Bot"):
        raise RuntimeError("Файл config.ini заполнен некорректно")

    for section, fields in REQUIRED_FIELDS.items():
        for field in fields:
            if not config.has_option(section, field) or not config.get(section, field):
                raise RuntimeError(f"Заполните параметр {field} в секции [{section}]")

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


# Define path names
BUCKET_MAIN = "telegram-auto-poster"
PHOTOS_PATH = "photos"
VIDEOS_PATH = "videos"
DOWNLOADS_PATH = "downloads"
