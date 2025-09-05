import pytest
import fakeredis.aioredis
from telegram_auto_poster.utils.stats import MediaStats


@pytest.mark.asyncio
async def test_leaderboard(mocker):
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    mocker.patch(
        "telegram_auto_poster.utils.stats.get_async_redis_client", return_value=fake
    )
    MediaStats._instance = None
    stats = MediaStats()
    await stats.record_submission("alice")
    await stats.record_submission("alice")
    await stats.record_submission("bob")
    await stats.record_approved("photo", source="alice")
    await stats.record_rejected("video", source="bob")
    lb = await stats.get_leaderboard()
    assert lb["submissions"][0]["source"] == "alice"
    assert lb["submissions"][0]["submissions"] == 2
    assert lb["approved"][0]["source"] == "alice"
    assert lb["rejected"][0]["source"] == "bob"
