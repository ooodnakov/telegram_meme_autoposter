import pytest
import sqlalchemy as sa
import fakeredis
import valkey
from types import SimpleNamespace
import minio

_real_create_engine = sa.create_engine
sa.create_engine = lambda *args, **kwargs: _real_create_engine("sqlite:///:memory:")
valkey.Valkey = lambda *a, **k: fakeredis.FakeRedis(decode_responses=True)
minio.Minio = lambda *a, **k: SimpleNamespace(
    bucket_exists=lambda *a, **k: True,
    make_bucket=lambda *a, **k: None,
    fput_object=lambda *a, **k: None,
    fget_object=lambda *a, **k: None,
    get_object=lambda *a, **k: SimpleNamespace(read=lambda: b"", close=lambda: None, release_conn=lambda: None),
    remove_object=lambda *a, **k: None,
    stat_object=lambda *a, **k: SimpleNamespace(metadata={}),
)


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
            "telegram": {"api_id": "123", "api_hash": "abc"},
            "minio": {
                "access_key": "minio",
                "secret_key": "minio123",
                "endpoint": "localhost:9000",
            },
            "settings": {
                "deduplication_threshold": "95",
                "target_channel_id": "@test",
            },
        },
    )
