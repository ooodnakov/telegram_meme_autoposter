import os
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import fakeredis
import fakeredis.aioredis
import pytest
import sqlalchemy as sa
import valkey

_real_create_engine = sa.create_engine
sa.create_engine = lambda *args, **kwargs: _real_create_engine("sqlite:///:memory:")
valkey.Valkey = lambda *a, **k: fakeredis.FakeRedis(decode_responses=True)
valkey.asyncio.Valkey = lambda *a, **k: fakeredis.aioredis.FakeRedis(
    decode_responses=True
)

# Provide a minimal async Minio stub so imports succeed without the real library
minio_module = types.ModuleType("minio")
error_module = types.ModuleType("minio.error")


class MinioException(Exception):
    pass


class S3Error(Exception):
    pass


class DummyMinio:
    def __init__(self, *a, **k):
        pass
    async def bucket_exists(self, *a, **k):
        return True

    async def make_bucket(self, *a, **k):
        return None

    async def fput_object(self, *a, **k):
        return None

    async def fget_object(self, *a, **k):
        return None

    async def get_object(self, *a, **k):
        async def _read():
            return b""

        async def _close():
            return None

        async def _release():
            return None

        return SimpleNamespace(read=_read, close=_close, release_conn=_release)

    async def remove_object(self, *a, **k):
        return None

    async def stat_object(self, *a, **k):
        return SimpleNamespace(metadata={})

    async def list_objects(self, *a, **k):
        return []


minio_module.Minio = DummyMinio
minio_module.error = error_module
error_module.MinioException = MinioException
error_module.S3Error = S3Error

commonconfig_module = types.ModuleType("minio.commonconfig")

class CopySource:
    def __init__(self, *a, **k):
        pass


commonconfig_module.CopySource = CopySource
minio_module.commonconfig = commonconfig_module
sys.modules["minio.commonconfig"] = commonconfig_module

sys.modules["minio"] = minio_module
sys.modules["minio.error"] = error_module

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
