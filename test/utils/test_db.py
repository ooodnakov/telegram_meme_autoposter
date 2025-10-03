import pytest
import pytest_asyncio

import pytest
import pytest_asyncio

from telegram_auto_poster.utils import db


@pytest_asyncio.fixture
async def redis_state():
    db.reset_cache_for_tests()
    client = db.get_async_redis_client()
    await client.flushdb()
    yield client
    await client.flushdb()
    db.reset_cache_for_tests()


@pytest.mark.asyncio
async def test_batch_counter(redis_state):
    assert await db.get_batch_count() == 0
    assert await db.increment_batch_count() == 1
    assert await db.increment_batch_count(2) == 3
    assert await db.decrement_batch_count(1) == 2
    assert await db.get_batch_count() == 2


@pytest.mark.asyncio
async def test_decrement_batch_clamped_to_zero(redis_state):
    assert await db.get_batch_count() == 0
    assert await db.decrement_batch_count(5) == 0


def test_reset_cache_clears_values():
    db.reset_cache_for_tests()
    client = db.get_redis_client()
    client.set("foo", "1")
    assert client.get("foo") == "1"
    db.reset_cache_for_tests()
    client = db.get_redis_client()
    assert client.get("foo") is None


def test_schedule_roundtrip(monkeypatch):
    db.reset_cache_for_tests()
    db.add_scheduled_post(100, "foo")
    assert db.get_scheduled_posts() == [("foo", 100.0)]
    assert db.get_scheduled_time("foo") == 100
    db.remove_scheduled_post("foo")
    assert db.get_scheduled_posts() == []
    assert db.get_scheduled_time("foo") is None
