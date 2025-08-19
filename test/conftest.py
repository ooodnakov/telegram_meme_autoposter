import os
from pathlib import Path
from types import SimpleNamespace

import fakeredis
import fakeredis.aioredis
import minio
import pytest
import sqlalchemy as sa
import valkey

_real_create_engine = sa.create_engine
sa.create_engine = lambda *args, **kwargs: _real_create_engine("sqlite:///:memory:")
valkey.Valkey = lambda *a, **k: fakeredis.FakeRedis(decode_responses=True)
valkey.asyncio.Valkey = (
    lambda *a, **k: fakeredis.aioredis.FakeRedis(decode_responses=True)
)
minio.Minio = lambda *a, **k: SimpleNamespace(
    bucket_exists=lambda *a, **k: True,
    make_bucket=lambda *a, **k: None,
    fput_object=lambda *a, **k: None,
    fget_object=lambda *a, **k: None,
    get_object=lambda *a, **k: SimpleNamespace(
        read=lambda: b"",
        close=lambda: None,
        release_conn=lambda: None,
    ),
    remove_object=lambda *a, **k: None,
    stat_object=lambda *a, **k: SimpleNamespace(metadata={}),
)

# Prepare minimal configuration for tests
CONFIG_CONTENT = """
[Telegram]
api_id = 1
api_hash = test
username = test
target_channel = @test
[Bot]
bot_token = token
bot_username = bot
bot_chat_id = 1
[Chats]
selected_chats = @test1,@test2
luba_chat = @luba
"""

config_path = Path("/tmp/test_config.ini")
config_path.write_text(CONFIG_CONTENT, encoding="utf-8")
os.environ.setdefault("CONFIG_PATH", str(config_path))
os.environ.setdefault("DB_MYSQL_USER", "user")
os.environ.setdefault("DB_MYSQL_PASSWORD", "pass")
os.environ.setdefault("DB_MYSQL_NAME", "db")
os.environ.setdefault("DB_MYSQL_HOST", "localhost")
os.environ.setdefault("DB_MYSQL_PORT", "3306")
os.environ.setdefault("MINIO_HOST", "localhost")
os.environ.setdefault("MINIO_PORT", "9000")
os.environ.setdefault("MINIO_ACCESS_KEY", "minio")
os.environ.setdefault("MINIO_SECRET_KEY", "minio")
os.environ.setdefault("VALKEY_HOST", "localhost")
os.environ.setdefault("VALKEY_PORT", "6379")
os.environ.setdefault("VALKEY_PASS", "redis")


@pytest.fixture(autouse=True)
def patch_external_libs(mocker):
    """Patch external libraries for tests."""
    # Minio is patched at import time to a dummy client


@pytest.fixture
def mock_config(mocker):
    """
    Autouse fixture to mock config loading for all tests.
    """
    mocker.patch(
        "telegram_auto_poster.config.load_config",
        return_value={
            "api_id": 1,
            "api_hash": "test",
            "username": "test",
            "target_channel": "@test",
            "bot_token": "token",
            "bot_username": "bot",
            "bot_chat_id": "1",
            "selected_chats": ["@test1", "@test2"],
            "luba_chat": "@luba",
            "quiet_hours_start": 22,
            "quiet_hours_end": 10,
            "admin_ids": [1],
            "minio": {
                "host": "localhost",
                "port": 9000,
                "access_key": "minio",
                "secret_key": "minio",
            },
            "valkey": {
                "host": "localhost",
                "port": 6379,
                "password": "redis",
                "prefix": "telegram_auto_poster",
            },
            "mysql": {
                "host": "localhost",
                "port": 3306,
                "user": "user",
                "password": "pass",
                "name": "db",
            },
            "timezone": "UTC",
        },
    )
