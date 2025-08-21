"""Typed configuration management using Pydantic."""

from __future__ import annotations

import configparser
import os
from typing import Any

from loguru import logger
from pydantic import BaseModel, model_validator


class TelegramConfig(BaseModel):
    api_id: int
    api_hash: str
    username: str
    target_channel: str


class BotConfig(BaseModel):
    bot_token: str
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
    access_key: str = "minioadmin"
    secret_key: str = "minioadmin"


class ValkeyConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 6379
    password: str = "redis"
    prefix: str = "telegram_auto_poster"


class MySQLConfig(BaseModel):
    host: str = "localhost"
    port: int = 3306
    user: str
    password: str
    name: str


class Config(BaseModel):
    telegram: TelegramConfig
    bot: BotConfig
    chats: ChatsConfig
    schedule: ScheduleConfig = ScheduleConfig()
    minio: MinioConfig = MinioConfig()
    valkey: ValkeyConfig = ValkeyConfig()
    mysql: MySQLConfig
    timezone: str = "UTC"


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
    "MINIO_ACCESS_KEY": ("minio", "access_key"),
    "MINIO_SECRET_KEY": ("minio", "secret_key"),
    "VALKEY_HOST": ("valkey", "host"),
    "VALKEY_PORT": ("valkey", "port"),
    "VALKEY_PASS": ("valkey", "password"),
    "REDIS_PREFIX": ("valkey", "prefix"),
    "DB_MYSQL_HOST": ("mysql", "host"),
    "DB_MYSQL_PORT": ("mysql", "port"),
    "DB_MYSQL_USER": ("mysql", "user"),
    "DB_MYSQL_PASSWORD": ("mysql", "password"),
    "DB_MYSQL_NAME": ("mysql", "name"),
    "TZ": ("timezone", None),
}


def _load_ini(path: str) -> dict[str, Any]:
    parser = configparser.ConfigParser()
    parser.read(path)

    data: dict[str, Any] = {}
    if parser.has_section("Telegram"):
        data["telegram"] = {
            k: parser.get("Telegram", k)
            for k in ["api_id", "api_hash", "username", "target_channel"]
            if parser.has_option("Telegram", k)
        }
    if parser.has_section("Bot"):
        bot_section = {
            k: parser.get("Bot", k)
            for k in ["bot_token", "bot_username", "bot_chat_id"]
            if parser.has_option("Bot", k)
        }
        if parser.has_option("Bot", "admin_ids"):
            admin_ids = [
                int(x.strip())
                for x in parser.get("Bot", "admin_ids").split(",")
                if x.strip()
            ]
            bot_section["admin_ids"] = admin_ids
        data["bot"] = bot_section
    if parser.has_section("Chats"):
        chats_section: dict[str, Any] = {}
        if parser.has_option("Chats", "selected_chats"):
            chats_section["selected_chats"] = [
                c.strip()
                for c in parser.get("Chats", "selected_chats").split(",")
                if c.strip()
            ]
        if parser.has_option("Chats", "luba_chat"):
            chats_section["luba_chat"] = parser.get("Chats", "luba_chat")
        if chats_section:
            data["chats"] = chats_section
    if parser.has_section("Schedule"):
        sched_section: dict[str, Any] = {}
        if parser.has_option("Schedule", "quiet_hours_start"):
            sched_section["quiet_hours_start"] = parser.get(
                "Schedule", "quiet_hours_start"
            )
        if parser.has_option("Schedule", "quiet_hours_end"):
            sched_section["quiet_hours_end"] = parser.get("Schedule", "quiet_hours_end")
        if sched_section:
            data["schedule"] = sched_section
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

    safe = config.model_copy(deep=True)
    safe.bot.bot_token = "***"
    safe.minio.access_key = "***"
    safe.minio.secret_key = "***"
    safe.valkey.password = "***"
    safe.mysql.password = "***"
    logger.bind(event="config_loaded").info(safe.model_dump())

    return config


# Define path names
BUCKET_MAIN = "telegram-auto-poster"
PHOTOS_PATH = "photos"
VIDEOS_PATH = "videos"
SCHEDULED_PATH = "scheduled"
DOWNLOADS_PATH = "downloads"


# Global configuration instance
CONFIG = load_config()
