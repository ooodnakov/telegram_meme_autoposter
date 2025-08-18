import sqlalchemy
from pytest_mock import MockerFixture
import importlib

def test_list_files_records(monkeypatch, mocker: MockerFixture):
    engine = sqlalchemy.create_engine("sqlite:///:memory:")
    monkeypatch.setattr(sqlalchemy, "create_engine", lambda *a, **k: engine)

    from telegram_auto_poster.utils import stats, storage
    importlib.reload(stats)
    importlib.reload(storage)
    stats.Base.metadata.create_all(engine)

    mocker.patch.object(storage.storage, 'client', mocker.MagicMock())
    storage.storage.client.list_objects.return_value = []

    storage.storage.list_files("bucket")

    session = stats.stats.db
    assert session.query(stats.History).filter_by(category="list").count() == 1
    assert (
        session.query(stats.StatsCounter)
        .filter_by(scope="daily", name="list_operations")
        .first()
        .value
        == 1
    )
    assert (
        session.query(stats.StatsCounter)
        .filter_by(scope="total", name="list_operations")
        .first()
        .value
        == 1
    )

def test_invalid_operation_ignored(monkeypatch, mocker: MockerFixture):
    engine = sqlalchemy.create_engine("sqlite:///:memory:")
    monkeypatch.setattr(sqlalchemy, "create_engine", lambda *a, **k: engine)

    from telegram_auto_poster.utils import stats
    importlib.reload(stats)
    stats.Base.metadata.create_all(engine)

    stats.stats.record_storage_operation("invalid", 0.1)
    session = stats.stats.db
    assert session.query(stats.History).count() == 0
    assert stats.stats.r.get("daily:list_operations") in (None, "0")