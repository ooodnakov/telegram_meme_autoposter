import importlib
import os
import sys
import types

import sqlalchemy
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from telegram_auto_poster import config as conf_module


def setup_modules(monkeypatch):
    """Prepare test environment with in-memory DB and fake Minio."""
    engine = sqlalchemy.create_engine("sqlite:///:memory:")
    monkeypatch.setattr(sqlalchemy, "create_engine", lambda *a, **k: engine)

    class FakeMinio:
        def __init__(self, *a, **k):
            pass

        def bucket_exists(self, bucket):
            return True

        def make_bucket(self, bucket):
            pass

        def list_objects(self, bucket, prefix=None, recursive=True):
            class Obj:
                def __init__(self, name):
                    self.object_name = name
            yield Obj("a")
            yield Obj("b")

    import minio

    monkeypatch.setattr(minio, "Minio", FakeMinio)
    monkeypatch.setattr(
        minio,
        "error",
        types.SimpleNamespace(S3Error=Exception, MinioException=Exception),
    )

    monkeypatch.setattr(
        conf_module,
        "load_config",
        lambda: {
            "bot_chat_id": "1",
            "bot_token": "t",
            "bot_username": "u",
            "api_id": 1,
            "api_hash": "h",
            "username": "x",
            "target_channel": "tc",
            "admin_ids": [1],
        },
    )

    os.environ["DB_MYSQL_USER"] = "u"
    os.environ["DB_MYSQL_PASSWORD"] = "p"
    os.environ["DB_MYSQL_NAME"] = "db"

    stats_mod = importlib.reload(
        importlib.import_module("telegram_auto_poster.utils.stats")
    )
    storage_mod = importlib.reload(
        importlib.import_module("telegram_auto_poster.utils.storage")
    )
    return stats_mod, storage_mod


def test_list_files_records(monkeypatch):
    stats_mod, storage_mod = setup_modules(monkeypatch)
    storage = storage_mod.MinioStorage()
    storage.list_files("bucket")

    session = stats_mod.stats.db
    assert (
        session.query(stats_mod.History)
        .filter_by(category="list")
        .count()
        == 1
    )
    assert (
        session.query(stats_mod.StatsCounter)
        .filter_by(scope="daily", name="list_operations")
        .first()
        .value
        == 1
    )
    assert (
        session.query(stats_mod.StatsCounter)
        .filter_by(scope="total", name="list_operations")
        .first()
        .value
        == 1
    )


def test_invalid_operation_ignored(monkeypatch):
    stats_mod, _ = setup_modules(monkeypatch)
    stats_mod.stats.record_storage_operation("invalid", 0.1)
    session = stats_mod.stats.db
    assert session.query(stats_mod.History).count() == 0
