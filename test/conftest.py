import os
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import fakeredis
import fakeredis.aioredis
import pytest
import valkey

valkey.Valkey = lambda *a, **k: fakeredis.FakeRedis(decode_responses=True)
valkey.asyncio.Valkey = lambda *a, **k: fakeredis.aioredis.FakeRedis(
    decode_responses=True
)

# Provide a minimal async MiniO stub so imports succeed without the real library
# miniopy_async is the async variant of the MinIO client used by the project.
miniopy_module = types.ModuleType("miniopy_async")
error_module = types.ModuleType("miniopy_async.error")


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


# Expose the dummy client and error classes on the module
miniopy_module.Minio = DummyMinio
miniopy_module.error = error_module
error_module.MinioException = MinioException
error_module.S3Error = S3Error

commonconfig_module = types.ModuleType("miniopy_async.commonconfig")

class CopySource:
    def __init__(self, *a, **k):
        pass


commonconfig_module.CopySource = CopySource
miniopy_module.commonconfig = commonconfig_module

# Register stub modules so that imports of miniopy_async work without the real package
sys.modules["miniopy_async"] = miniopy_module
sys.modules["miniopy_async.error"] = error_module
sys.modules["miniopy_async.commonconfig"] = commonconfig_module

# Backwards compatibility if any code still imports the old package name
sys.modules["minio"] = miniopy_module
sys.modules["minio.error"] = error_module
sys.modules["minio.commonconfig"] = commonconfig_module

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
    from telegram_auto_poster.config import (
        BotConfig,
        ChatsConfig,
        Config,
        TelegramConfig,
    )

    mocker.patch(
        "telegram_auto_poster.config.load_config",
        return_value=Config(
            telegram=TelegramConfig(
                api_id=1,
                api_hash="test",
                username="test",
                target_channel="@test",
            ),
            bot=BotConfig(
                bot_token="token",
                bot_username="bot",
                bot_chat_id=1,
                admin_ids=[1],
            ),
            chats=ChatsConfig(
                selected_chats=["@test1", "@test2"],
                luba_chat="@luba",
            ),
        ),
    )
