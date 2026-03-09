import fakeredis
import fakeredis.aioredis
import pytest

from telegram_auto_poster.utils import channels


@pytest.fixture
def shared_valkey(mocker):
    server = fakeredis.FakeServer()
    sync_client = fakeredis.FakeRedis(server=server, decode_responses=True)
    async_client = fakeredis.aioredis.FakeRedis(server=server, decode_responses=True)
    mocker.patch(
        "telegram_auto_poster.utils.channels.get_redis_client", return_value=sync_client
    )
    mocker.patch(
        "telegram_auto_poster.utils.channels.get_async_redis_client",
        return_value=async_client,
    )
    return sync_client, async_client


def test_ensure_selected_chats_cached_initializes_missing_value(shared_valkey):
    sync_client, _async_client = shared_valkey

    cached = channels.ensure_selected_chats_cached([" @one ", "@two", "@one"])

    assert cached == ["@one", "@two"]
    assert sync_client.get(channels.SELECTED_CHATS_KEY) == '["@one", "@two"]'


def test_ensure_selected_chats_cached_preserves_intentional_empty_list(shared_valkey):
    sync_client, _async_client = shared_valkey
    sync_client.set(channels.SELECTED_CHATS_KEY, "[]")

    cached = channels.ensure_selected_chats_cached(["@default"])

    assert cached == []
    assert sync_client.get(channels.SELECTED_CHATS_KEY) == "[]"


@pytest.mark.asyncio
async def test_fetch_and_store_selected_chats_round_trip(shared_valkey):
    _sync_client, _async_client = shared_valkey

    stored = await channels.store_selected_chats(["@one", " @two ", "@one"])
    fetched = await channels.fetch_selected_chats(fallback=["@fallback"])

    assert stored == ["@one", "@two"]
    assert fetched == ["@one", "@two"]


@pytest.mark.asyncio
async def test_fetch_selected_chats_uses_fallback_when_key_missing(shared_valkey):
    _sync_client, _async_client = shared_valkey

    fetched = await channels.fetch_selected_chats(fallback=["@fallback", "@fallback"])

    assert fetched == ["@fallback"]
