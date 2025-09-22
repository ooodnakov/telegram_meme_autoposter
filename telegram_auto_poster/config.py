"""Typed configuration management using Pydantic."""

from __future__ import annotations

import configparser
import os
from typing import Any

from loguru import logger
from pydantic import BaseModel, SecretStr, model_validator


class TelegramConfig(BaseModel):
    """Telegram API credentials and target channel settings."""

    api_id: int
    api_hash: str
    username: str
    target_channels: list[str]


class BotConfig(BaseModel):
    """Bot credentials and administrative settings."""

    bot_token: SecretStr
    bot_username: str
    bot_chat_id: int
    admin_ids: list[int] | None = None
    prompt_target_channel: bool = False

    @model_validator(mode="after")
    def default_admins(self) -> "BotConfig":
        """Populate ``admin_ids`` with ``bot_chat_id`` when not provided."""
        if self.admin_ids is None:
            self.admin_ids = [self.bot_chat_id]
        return self


class WebConfig(BaseModel):
    """Web dashboard settings."""

    session_secret: SecretStr


class ChatsConfig(BaseModel):
    """Source chat identifiers."""

    selected_chats: list[str]
    luba_chat: str


class ScheduleConfig(BaseModel):
    """Posting schedule configuration."""

    quiet_hours_start: int = 22
    quiet_hours_end: int = 10


class MinioConfig(BaseModel):
    """MinIO object storage connection settings."""

    host: str = "localhost"
    port: int = 9000
    url: str | None = None
    public_url: str | None = None
    access_key: SecretStr = SecretStr("minioadmin")
    secret_key: SecretStr = SecretStr("minioadmin")


class ValkeyConfig(BaseModel):
    """Valkey (Redis) connection settings."""

    host: str = "127.0.0.1"
    port: int = 6379
    password: SecretStr = SecretStr("redis")
    prefix: str = "telegram_auto_poster"


class RateLimitConfig(BaseModel):
    """Token bucket rate limiting parameters."""

    rate: float = 1.0
    capacity: int = 5


class I18nConfig(BaseModel):
    """Internationalization settings."""

    default: str = "ru"
    users: dict[int, str] = {}


class GeminiConfig(BaseModel):
    """Google Gemini API settings."""

    api_key: SecretStr | None = None
    model: str = "gemini-1.5-flash"


class CaptionConfig(BaseModel):
    """Caption generation settings."""

    enabled: bool = False
    target_lang: str = "en"


class BrandingConfig(BaseModel):
    """Branding strings used across media and captions."""

    attribution: str = "t.me/ooodnakov_memes"
    suggestion_caption: str = "Пост из предложки @ooodnakov_memes_suggest_bot"


class WatermarkImageConfig(BaseModel):
    """Watermark options for static images."""

    path: str = "wm.png"
    size_ratio: float = 0.1
    opacity: int = 40

    @model_validator(mode="after")
    def validate_values(self) -> "WatermarkImageConfig":
        """Ensure ratio and opacity are within supported ranges."""
        if not 0 < self.size_ratio <= 1:
            raise ValueError("size_ratio must be between 0 and 1")
        if not 0 <= self.opacity <= 255:
            raise ValueError("opacity must be between 0 and 255")
        return self


class WatermarkVideoConfig(BaseModel):
    """Watermark options for animated video overlays."""

    path: str = "wm.png"
    min_size_percent: int = 15
    max_size_percent: int = 25
    min_speed: int = 80
    max_speed: int = 120

    @model_validator(mode="after")
    def validate_values(self) -> "WatermarkVideoConfig":
        """Ensure percent and speed ranges are valid."""
        if self.min_size_percent <= 0:
            raise ValueError("min_size_percent must be positive")
        if self.max_size_percent < self.min_size_percent:
            raise ValueError("max_size_percent must be >= min_size_percent")
        if self.min_speed <= 0:
            raise ValueError("min_speed must be positive")
        if self.max_speed < self.min_speed:
            raise ValueError("max_speed must be >= min_speed")
        return self


class Config(BaseModel):
    """Aggregate application configuration."""

    telegram: TelegramConfig
    bot: BotConfig
    web: WebConfig
    chats: ChatsConfig
    schedule: ScheduleConfig = ScheduleConfig()
    minio: MinioConfig = MinioConfig()
    valkey: ValkeyConfig = ValkeyConfig()
    rate_limit: RateLimitConfig = RateLimitConfig()
    gemini: GeminiConfig = GeminiConfig()
    caption: CaptionConfig = CaptionConfig()
    branding: BrandingConfig = BrandingConfig()
    watermark_image: WatermarkImageConfig = WatermarkImageConfig()
    watermark_video: WatermarkVideoConfig = WatermarkVideoConfig()
    timezone: str = "UTC"
    i18n: I18nConfig = I18nConfig()


ENV_MAP: dict[str, tuple[str, str | None]] = {
    "TELEGRAM_API_ID": ("telegram", "api_id"),
    "TELEGRAM_API_HASH": ("telegram", "api_hash"),
    "TELEGRAM_USERNAME": ("telegram", "username"),
    "TELEGRAM_TARGET_CHANNELS": ("telegram", "target_channels"),
    "BOT_BOT_TOKEN": ("bot", "bot_token"),
    "BOT_BOT_USERNAME": ("bot", "bot_username"),
    "BOT_BOT_CHAT_ID": ("bot", "bot_chat_id"),
    "BOT_ADMIN_IDS": ("bot", "admin_ids"),
    "BOT_PROMPT_TARGET_CHANNEL": ("bot", "prompt_target_channel"),
    "WEB_SESSION_SECRET": ("web", "session_secret"),
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
    "RATE_LIMIT_RATE": ("rate_limit", "rate"),
    "RATE_LIMIT_CAPACITY": ("rate_limit", "capacity"),
    "GEMINI_API_KEY": ("gemini", "api_key"),
    "GEMINI_MODEL": ("gemini", "model"),
    "CAPTION_ENABLED": ("caption", "enabled"),
    "CAPTION_TARGET_LANG": ("caption", "target_lang"),
    "BRANDING_ATTRIBUTION": ("branding", "attribution"),
    "BRANDING_SUGGESTION_CAPTION": ("branding", "suggestion_caption"),
    "WATERMARK_IMAGE_PATH": ("watermark_image", "path"),
    "WATERMARK_IMAGE_SIZE_RATIO": ("watermark_image", "size_ratio"),
    "WATERMARK_IMAGE_OPACITY": ("watermark_image", "opacity"),
    "WATERMARK_VIDEO_PATH": ("watermark_video", "path"),
    "WATERMARK_VIDEO_MIN_SIZE_PERCENT": ("watermark_video", "min_size_percent"),
    "WATERMARK_VIDEO_MAX_SIZE_PERCENT": ("watermark_video", "max_size_percent"),
    "WATERMARK_VIDEO_MIN_SPEED": ("watermark_video", "min_speed"),
    "WATERMARK_VIDEO_MAX_SPEED": ("watermark_video", "max_speed"),
    "TZ": ("timezone", None),
    "I18N_DEFAULT": ("i18n", "default"),
    "I18N_USERS": ("i18n", "users"),
}


def _parse_i18n_users(value: str) -> dict[int, str]:
    """Parse a comma-separated user:lang string into a dict."""
    users: dict[int, str] = {}
    for part in value.split(","):
        if not part.strip():
            continue
        uid, _, lang = part.partition(":")
        try:
            users[int(uid.strip())] = lang.strip()
        except ValueError:
            continue
    return users


def _load_ini(path: str) -> dict[str, Any]:
    """Parse an INI configuration file into a nested dictionary."""
    parser = configparser.ConfigParser()
    parser.read(path)

    data: dict[str, Any] = {}

    section_map: dict[str, tuple[str, type[BaseModel]]] = {
        "Telegram": ("telegram", TelegramConfig),
        "Web": ("web", WebConfig),
        "Schedule": ("schedule", ScheduleConfig),
        "Minio": ("minio", MinioConfig),
        "Valkey": ("valkey", ValkeyConfig),
        "RateLimit": ("rate_limit", RateLimitConfig),
        "Gemini": ("gemini", GeminiConfig),
        "Caption": ("caption", CaptionConfig),
        "Branding": ("branding", BrandingConfig),
        "WatermarkImage": ("watermark_image", WatermarkImageConfig),
        "WatermarkVideo": ("watermark_video", WatermarkVideoConfig),
    }

    for section_name, (key, model) in section_map.items():
        if parser.has_section(section_name):
            section_data = {}
            for field in model.model_fields:
                if not parser.has_option(section_name, field):
                    continue
                value = parser.get(section_name, field)
                if section_name == "Telegram" and field == "target_channels":
                    section_data[field] = [
                        c.strip() for c in value.split(",") if c.strip()
                    ]
                else:
                    section_data[field] = value
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
            i18n_section["users"] = _parse_i18n_users(raw_users)
        if i18n_section:
            data["i18n"] = i18n_section
    return data


def _load_env() -> dict[str, Any]:
    """Collect configuration overrides from environment variables."""
    env_data: dict[str, Any] = {}
    for env_name, (section, field) in ENV_MAP.items():
        if env_name not in os.environ:
            continue
        value: str = os.environ[env_name]
        if field is None:
            env_data[section] = value
            continue
        env_section = env_data.setdefault(section, {})
        if field in {"selected_chats", "admin_ids", "target_channels"}:
            env_section[field] = [x.strip() for x in value.split(",") if x.strip()]
        elif field == "users":
            env_section[field] = _parse_i18n_users(value)
        else:
            env_section[field] = value
    return env_data


def _deep_update(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge ``overrides`` into ``base`` and return ``base``."""
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


# Global configuration instance
CONFIG = load_config()


# Define path names
BUCKET_MAIN = "telegram-auto-poster"
PHOTOS_PATH = "photos"
VIDEOS_PATH = "videos"
SCHEDULED_PATH = "scheduled"
DOWNLOADS_PATH = "downloads"

# Watermark animation speed range in pixels per second (backwards compatibility)
WATERMARK_MIN_SPEED = CONFIG.watermark_video.min_speed
WATERMARK_MAX_SPEED = CONFIG.watermark_video.max_speed

# Caption appended to posts originating from user suggestions (backwards compatibility)
SUGGESTION_CAPTION = CONFIG.branding.suggestion_caption
