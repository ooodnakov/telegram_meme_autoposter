"""Typed configuration management using Pydantic."""

from __future__ import annotations

import configparser
import os
from typing import Any

from loguru import logger
from pydantic import BaseModel, SecretStr, model_validator


class TelegramConfig(BaseModel):
    api_id: int
    api_hash: str
    username: str
    target_channel: str


class BotConfig(BaseModel):
    bot_token: SecretStr
    bot_username: str
    bot_chat_id: int
    admin_ids: list[int] | None = None

    @model_validator(mode="after")
    def default_admins(self) -> "BotConfig":
        """Populate ``admin_ids`` with ``bot_chat_id`` when not provided."""

        if self.admin_ids is None:
            self.admin_ids = [self.bot_chat_id]
        return self


class ChatsConfig(BaseModel):
    selected_chats: list[str]
    luba_chat: str


class ScheduleConfig(BaseModel):
    quiet_hours_start: int = 22
    quiet_hours_end: int = 10


class MinioConfig(BaseModel):
    host: str = "localhost"
    port: int = 9000
    url: str | None = None
    public_url: str | None = None
    access_key: SecretStr = SecretStr("minioadmin")
    secret_key: SecretStr = SecretStr("minioadmin")


class ValkeyConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 6379
    password: SecretStr = SecretStr("redis")
    prefix: str = "telegram_auto_poster"


class WebConfig(BaseModel):
    access_key: SecretStr | None = None


class RateLimitConfig(BaseModel):
    rate: float = 1.0
    capacity: int = 5


class I18nConfig(BaseModel):
    """Internationalization settings."""

    default: str = "ru"
    users: dict[int, str] = {}


class Config(BaseModel):
    telegram: TelegramConfig
    bot: BotConfig
    chats: ChatsConfig
    schedule: ScheduleConfig = ScheduleConfig()
    minio: MinioConfig = MinioConfig()
    valkey: ValkeyConfig = ValkeyConfig()
    web: WebConfig = WebConfig()
    rate_limit: RateLimitConfig = RateLimitConfig()
    timezone: str = "UTC"
    i18n: I18nConfig = I18nConfig()


ENV_MAP: dict[str, tuple[str, str | None]] = {
    "TELEGRAM_API_ID": ("telegram", "api_id"),
    "TELEGRAM_API_HASH": ("telegram", "api_hash"),
    "TELEGRAM_USERNAME": ("telegram", "username"),
    "TELEGRAM_TARGET_CHANNEL": ("telegram", "target_channel"),
    "BOT_BOT_TOKEN": ("bot", "bot_token"),
    "BOT_BOT_USERNAME": ("bot", "bot_username"),
    "BOT_BOT_CHAT_ID": ("bot", "bot_chat_id"),
    "BOT_ADMIN_IDS": ("bot", "admin_ids"),
    "CHATS_SELECTED_CHATS": ("chats", "selected_chats"),
    "CHATS_LUBA_CHAT": ("chats", "luba_chat"),
    "SCHEDULE_QUIET_HOURS_START": ("schedule", "quiet_hours_start"),
    "SCHEDULE_QUIET_HOURS_END": ("schedule", "quiet_hours_end"),
    "MINIO_HOST": ("minio", "host"),
    "MINIO_PORT": ("minio", "port"),
    "MINIO_URL": ("minio", "url"),
    "MINIO_PUBLIC_URL": ("minio", "public_url"),
    "MINIO_ACCESS_KEY": ("minio", "access_key"),
    "MINIO_SECRET_KEY": ("minio", "secret_key"),
    "VALKEY_HOST": ("valkey", "host"),
    "VALKEY_PORT": ("valkey", "port"),
    "VALKEY_PASS": ("valkey", "password"),
    "REDIS_PREFIX": ("valkey", "prefix"),
    "WEB_ACCESS_KEY": ("web", "access_key"),
    "RATE_LIMIT_RATE": ("rate_limit", "rate"),
    "RATE_LIMIT_CAPACITY": ("rate_limit", "capacity"),
    "TZ": ("timezone", None),
    "I18N_DEFAULT": ("i18n", "default"),
    "I18N_USERS": ("i18n", "users"),
}


def _load_ini(path: str) -> dict[str, Any]:
    parser = configparser.ConfigParser()
    parser.read(path)

    data: dict[str, Any] = {}

    section_map: dict[str, tuple[str, type[BaseModel]]] = {
        "Telegram": ("telegram", TelegramConfig),
        "Schedule": ("schedule", ScheduleConfig),
        "Minio": ("minio", MinioConfig),
        "Valkey": ("valkey", ValkeyConfig),
        "RateLimit": ("rate_limit", RateLimitConfig),
    }

    for section_name, (key, model) in section_map.items():
        if parser.has_section(section_name):
            section_data = {
                field: parser.get(section_name, field)
                for field in model.model_fields
                if parser.has_option(section_name, field)
            }
            if section_data:
                data[key] = section_data

    if parser.has_section("Bot"):
        bot_section: dict[str, Any] = {}
        for k in BotConfig.model_fields:
            if parser.has_option("Bot", k):
                if k == "admin_ids":
                    bot_section[k] = [
                        int(x.strip())
                        for x in parser.get("Bot", k).split(",")
                        if x.strip()
                    ]
                else:
                    bot_section[k] = parser.get("Bot", k)
        if bot_section:
            data["bot"] = bot_section

    if parser.has_section("Chats"):
        chats_section: dict[str, Any] = {}
        for k in ChatsConfig.model_fields:
            if parser.has_option("Chats", k):
                if k == "selected_chats":
                    chats_section[k] = [
                        c.strip()
                        for c in parser.get("Chats", k).split(",")
                        if c.strip()
                    ]
                else:
                    chats_section[k] = parser.get("Chats", k)
        if chats_section:
            data["chats"] = chats_section
    if parser.has_section("Schedule"):
        data["schedule"] = {
            k: parser.get("Schedule", k)
            for k in ScheduleConfig.model_fields
            if parser.has_option("Schedule", k)
        }
    if parser.has_section("Web"):
        data["web"] = {
            k: parser.get("Web", k)
            for k in WebConfig.model_fields
            if parser.has_option("Web", k)
        }
    if parser.has_section("RateLimit"):
        data["rate_limit"] = {
            k: parser.get("RateLimit", k)
            for k in RateLimitConfig.model_fields
            if parser.has_option("RateLimit", k)
        }
    if parser.has_section("I18n"):
        i18n_section: dict[str, Any] = {}
        if parser.has_option("I18n", "default"):
            i18n_section["default"] = parser.get("I18n", "default")
        if parser.has_option("I18n", "users"):
            raw_users = parser.get("I18n", "users")
            users: dict[int, str] = {}
            for part in raw_users.split(","):
                if not part.strip():
                    continue
                uid, _, lang = part.partition(":")
                try:
                    users[int(uid.strip())] = lang.strip()
                except ValueError:
                    continue
            i18n_section["users"] = users
        if i18n_section:
            data["i18n"] = i18n_section
    return data


def _load_env() -> dict[str, Any]:
    env_data: dict[str, Any] = {}
    for env_name, (section, field) in ENV_MAP.items():
        if env_name not in os.environ:
            continue
        value: str = os.environ[env_name]
        if field is None:
            env_data[section] = value
            continue
        env_section = env_data.setdefault(section, {})
        if field in {"selected_chats", "admin_ids"}:
            env_section[field] = [x.strip() for x in value.split(",") if x.strip()]
        elif field == "users":
            users: dict[int, str] = {}
            for part in value.split(","):
                if not part.strip():
                    continue
                uid, _, lang = part.partition(":")
                try:
                    users[int(uid.strip())] = lang.strip()
                except ValueError:
                    continue
            env_section[field] = users
        else:
            env_section[field] = value
    return env_data


def _deep_update(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    for key, value in overrides.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_update(base[key], value)
        else:
            base[key] = value
    return base


def load_config() -> Config:
    """Read configuration and return a typed ``Config`` instance."""

    config_path = os.getenv("CONFIG_PATH", "config.ini")
    data = _load_ini(config_path)
    env_overrides = _load_env()
    merged = _deep_update(data, env_overrides)

    config = Config.model_validate(merged)
    logger.bind(event="config_loaded").info(f"Config loaded: {config}")

    return config


# Define path names
BUCKET_MAIN = "telegram-auto-poster"
PHOTOS_PATH = "photos"
VIDEOS_PATH = "videos"
SCHEDULED_PATH = "scheduled"
DOWNLOADS_PATH = "downloads"

# Watermark animation speed range in pixels per second
WATERMARK_MIN_SPEED = 80
WATERMARK_MAX_SPEED = 120

# Caption appended to posts originating from user suggestions
SUGGESTION_CAPTION = "Пост из предложки @ooodnakov_memes_suggest_bot"


# Global configuration instance
CONFIG = load_config()
