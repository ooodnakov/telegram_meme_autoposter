import pytest
from telegram_auto_poster.utils import db


class FakeRedis:
    def __init__(self):
        self.store: dict[str, int] = {}

    async def incrby(self, key, amount):
        self.store[key] = int(self.store.get(key, 0)) + amount
        return self.store[key]

    async def decrby(self, key, amount):
        self.store[key] = int(self.store.get(key, 0)) - amount
        return self.store[key]

    async def get(self, key):
        value = self.store.get(key)
        return str(value) if value is not None else None

    async def set(self, key, value):
        self.store[key] = int(value)


@pytest.fixture
def mock_async_redis(mocker):
    client = FakeRedis()
    mocker.patch(
        "telegram_auto_poster.utils.db.get_async_redis_client", return_value=client
    )
    return client


@pytest.mark.asyncio
async def test_batch_counter(mock_async_redis):
    assert await db.get_batch_count() == 0
    assert await db.increment_batch_count() == 1
    assert await db.increment_batch_count(2) == 3
    assert await db.decrement_batch_count(1) == 2
    assert await db.get_batch_count() == 2
