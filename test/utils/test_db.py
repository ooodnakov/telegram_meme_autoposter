import fakeredis
import pytest
import pytest_asyncio
from telegram_auto_poster.config import CONFIG
from telegram_auto_poster.utils import db


@pytest_asyncio.fixture
async def mock_async_redis(mocker):
    mocker.patch(
        "telegram_auto_poster.utils.db.AsyncValkey", fakeredis.aioredis.FakeRedis
    )
    mocker.patch.object(CONFIG.valkey.password, "get_secret_value", return_value=None)
    db._async_redis_client = None
    client = db.get_async_redis_client()
    await client.flushdb()
    yield client
    await client.flushdb()


@pytest.mark.asyncio
async def test_batch_counter(mock_async_redis):
    assert await db.get_batch_count() == 0
    assert await db.increment_batch_count() == 1
    assert await db.increment_batch_count(2) == 3
    assert await db.decrement_batch_count(1) == 2
    assert await db.get_batch_count() == 2


@pytest.mark.asyncio
async def test_decrement_batch_clamped_to_zero(mock_async_redis):
    assert await db.get_batch_count() == 0
    assert await db.decrement_batch_count(5) == 0


def test_get_redis_client_flushes_between_calls(mocker):
    mocker.patch("telegram_auto_poster.utils.db.Valkey", fakeredis.FakeRedis)
    mocker.patch.object(CONFIG.valkey.password, "get_secret_value", return_value=None)
    db._redis_client = None
    client = db.get_redis_client()
    client.set("foo", "1")
    client = db.get_redis_client()
    assert client.get("foo") is None


def test_get_redis_client_imports_valkey(mocker):
    mocker.patch("valkey.Valkey", fakeredis.FakeRedis)
    mocker.patch.object(CONFIG.valkey.password, "get_secret_value", return_value=None)
    db._redis_client = None
    mocker.patch.object(db, "Valkey", None)
    client = db.get_redis_client()
    assert isinstance(client, fakeredis.FakeRedis)


def test_schedule_roundtrip(mocker):
    fake = fakeredis.FakeRedis(decode_responses=True)
    mocker.patch("telegram_auto_poster.utils.db.get_redis_client", return_value=fake)
    db.add_scheduled_post(100, "foo")
    assert db.get_scheduled_posts() == [("foo", 100.0)]
    assert db.get_scheduled_time("foo") == 100
    db.remove_scheduled_post("foo")
    assert db.get_scheduled_posts() == []
    assert db.get_scheduled_time("foo") is None


@pytest.mark.asyncio
async def test_event_history_roundtrip(mock_async_redis):
    entry_one = {"action": "ok", "timestamp": "2024-01-01T00:00:00+00:00"}
    entry_two = {"action": "push", "timestamp": "2024-01-02T00:00:00+00:00"}

    await db.add_event_history_entry(entry_one, max_length=2)
    await db.add_event_history_entry(entry_two, max_length=2)

    events = await db.get_event_history()
    assert len(events) == 2
    # Newest entry should come first
    assert events[0]["action"] == "push"
    assert events[1]["action"] == "ok"


@pytest.mark.asyncio
async def test_clear_event_history(mock_async_redis):
    entry = {"action": "queued", "timestamp": "2024-01-01T00:00:00+00:00"}
    await db.add_event_history_entry(entry)

    await db.clear_event_history()

    events = await db.get_event_history()
    assert events == []
