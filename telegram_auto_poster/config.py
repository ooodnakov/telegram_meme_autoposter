"""Configuration helpers for the Telegram meme autoposter."""

import configparser
import os

REQUIRED_FIELDS = {
    "Telegram": ["api_id", "api_hash", "username", "target_channel"],
    "Bot": ["bot_token", "bot_username", "bot_chat_id"],
    "Chats": ["selected_chats", "luba_chat"],
}


def load_config() -> dict:
    """Read ``config.ini`` and environment variables and return settings.

    The function validates that all required sections and fields are present and
    converts certain values to the appropriate types.

    Returns:
        dict: Parsed configuration mapping.

    Raises:
        RuntimeError: If required sections or values are missing or invalid.
    """
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

    try:
        quiet_start = config.getint("Schedule", "quiet_hours_start", fallback=22)
        quiet_end = config.getint("Schedule", "quiet_hours_end", fallback=10)
    except ValueError as exc:
        raise RuntimeError(
            "quiet_hours_start and quiet_hours_end must be integers"
        ) from exc
    conf_dict["quiet_hours_start"] = quiet_start
    conf_dict["quiet_hours_end"] = quiet_end

    # Add admin IDs if they exist in config
    if config.has_option("Bot", "admin_ids"):
        # Admin IDs can be comma-separated list of user IDs
        admin_ids_str = config["Bot"]["admin_ids"]
        admin_ids = [int(id.strip()) for id in admin_ids_str.split(",") if id.strip()]
        conf_dict["admin_ids"] = admin_ids
    # Default to bot_chat_id if no admin IDs are specified
    else:
        conf_dict["admin_ids"] = [int(conf_dict["bot_chat_id"])]

    # Centralized environment configuration
    try:
        minio_port = int(os.getenv("MINIO_PORT", "9000"))
        valkey_port = int(os.getenv("VALKEY_PORT", "6379"))
        mysql_port = int(os.getenv("DB_MYSQL_PORT", "3306"))
    except ValueError as exc:
        raise RuntimeError("Port environment variables must be integers.") from exc

    conf_dict["minio"] = {
        "host": os.getenv("MINIO_HOST", "localhost"),
        "port": minio_port,
        "access_key": os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
        "secret_key": os.getenv("MINIO_SECRET_KEY", "minioadmin"),
    }

    conf_dict["valkey"] = {
        "host": os.getenv("VALKEY_HOST", "127.0.0.1"),
        "port": valkey_port,
        "password": os.getenv("VALKEY_PASS", "redis"),
        "prefix": os.getenv("REDIS_PREFIX", "telegram_auto_poster"),
    }

    mysql_user = os.getenv("DB_MYSQL_USER")
    mysql_password = os.getenv("DB_MYSQL_PASSWORD")
    mysql_name = os.getenv("DB_MYSQL_NAME")

    if not all((mysql_user, mysql_password, mysql_name)):
        raise RuntimeError(
            "Missing required MySQL environment variables: "
            "DB_MYSQL_USER, DB_MYSQL_PASSWORD, DB_MYSQL_NAME"
        )

    conf_dict["mysql"] = {
        "host": os.getenv("DB_MYSQL_HOST", "localhost"),
        "port": mysql_port,
        "user": mysql_user,
        "password": mysql_password,
        "name": mysql_name,
    }

    conf_dict["timezone"] = os.getenv("TZ", "UTC")

    return conf_dict


# Define path names
BUCKET_MAIN = "telegram-auto-poster"
PHOTOS_PATH = "photos"
VIDEOS_PATH = "videos"
SCHEDULED_PATH = "scheduled"
DOWNLOADS_PATH = "downloads"


# Global configuration instance
CONFIG = load_config()
