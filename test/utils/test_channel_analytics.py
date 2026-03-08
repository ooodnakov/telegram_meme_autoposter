import datetime
import json

import fakeredis.aioredis
import pytest
import pytest_asyncio
from telethon import types

from telegram_auto_poster.utils.channel_analytics import (
    CHANNEL_ANALYTICS_CACHE_TTL_SECONDS,
    get_cached_channel_analytics,
    refresh_channel_analytics_cache,
)


@pytest_asyncio.fixture
async def analytics_redis(mocker):
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    mocker.patch(
        "telegram_auto_poster.utils.channel_analytics.get_async_redis_client",
        return_value=fake,
    )
    await fake.flushdb()
    yield fake
    await fake.flushdb()


class DummyEntity:
    def __init__(self, title: str, username: str, entity_id: int) -> None:
        self.title = title
        self.username = username
        self.id = entity_id


class DummyTelethonClient:
    def __init__(self, stats_payload: types.stats.BroadcastStats) -> None:
        self.stats_payload = stats_payload
        self.calls = 0

    async def get_entity(self, channel: str) -> DummyEntity:
        return DummyEntity("My Channel", "mychannel", 42)

    async def get_stats(self, _entity: DummyEntity) -> types.stats.BroadcastStats:
        self.calls += 1
        return self.stats_payload

    async def __call__(self, _request):
        raise AssertionError("async graph loading should not be used in this test")


def _build_broadcast_stats() -> types.stats.BroadcastStats:
    graph_data = json.dumps(
        {
            "columns": [
                ["x", 1711929600000, 1712016000000],
                ["y0", 100, 120],
                ["y1", 40, 55],
            ],
            "types": {
                "x": "x",
                "y0": "line",
                "y1": "bar",
            },
            "names": {
                "y0": "Followers",
                "y1": "Views",
            },
            "colors": {
                "y0": "#4ade80",
                "y1": "#38bdf8",
            },
        }
    )
    graph = types.StatsGraph(types.DataJSON(graph_data))
    now = datetime.datetime(2026, 3, 8, tzinfo=datetime.UTC)
    return types.stats.BroadcastStats(
        period=types.StatsDateRangeDays(now - datetime.timedelta(days=7), now),
        followers=types.StatsAbsValueAndPrev(1200, 1100),
        views_per_post=types.StatsAbsValueAndPrev(450, 400),
        shares_per_post=types.StatsAbsValueAndPrev(22, 18),
        reactions_per_post=types.StatsAbsValueAndPrev(35, 31),
        views_per_story=types.StatsAbsValueAndPrev(0, 0),
        shares_per_story=types.StatsAbsValueAndPrev(0, 0),
        reactions_per_story=types.StatsAbsValueAndPrev(0, 0),
        enabled_notifications=types.StatsPercentValue(35, 100),
        growth_graph=graph,
        followers_graph=graph,
        mute_graph=graph,
        top_hours_graph=graph,
        interactions_graph=graph,
        iv_interactions_graph=graph,
        views_by_source_graph=graph,
        new_followers_by_source_graph=graph,
        languages_graph=graph,
        reactions_by_emotion_graph=graph,
        story_interactions_graph=graph,
        story_reactions_by_emotion_graph=graph,
        recent_posts_interactions=[
            types.PostInteractionCountersMessage(101, 1400, 55, 87),
            types.PostInteractionCountersMessage(102, 1200, 42, 71),
        ],
    )


@pytest.mark.asyncio
async def test_refresh_channel_analytics_cache_serializes_broadcast_stats(
    analytics_redis,
):
    client = DummyTelethonClient(_build_broadcast_stats())

    payload = await refresh_channel_analytics_cache(client, ["@mychannel"], force=True)

    assert payload is not None
    assert payload["channels"][0]["title"] == "My Channel"
    assert payload["channels"][0]["kind"] == "broadcast"
    assert payload["channels"][0]["summary_metrics"][0]["key"] == "followers"
    assert payload["channels"][0]["summary_metrics"][0]["current"] == 1200.0
    assert payload["channels"][0]["ratio_metrics"][0]["percentage"] == pytest.approx(35.0)
    assert payload["channels"][0]["graphs"][0]["series"][0]["label"] == "Followers"
    assert payload["channels"][0]["recent_posts"][0]["link"] == "https://t.me/mychannel/101"

    cached = await get_cached_channel_analytics()
    assert cached == payload
    ttl = await analytics_redis.ttl("telegram_auto_poster:cache:telegram_channel_analytics")
    assert ttl > 0
    assert ttl <= CHANNEL_ANALYTICS_CACHE_TTL_SECONDS


@pytest.mark.asyncio
async def test_refresh_channel_analytics_cache_uses_existing_cache(analytics_redis):
    client = DummyTelethonClient(_build_broadcast_stats())

    first = await refresh_channel_analytics_cache(client, ["@mychannel"], force=True)
    second = await refresh_channel_analytics_cache(client, ["@mychannel"])

    assert first == second
    assert client.calls == 1
