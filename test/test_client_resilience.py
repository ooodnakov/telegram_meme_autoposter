import pytest

from telegram_auto_poster.utils.general import RateLimiter, backoff_delay


def test_backoff_delay_cap():
    delays = [backoff_delay(i, base=1, cap=5, jitter=0) for i in range(1, 10)]
    assert delays[0] == 1
    assert delays[-1] == 5


@pytest.mark.asyncio
async def test_rate_limiter_drop():
    limiter = RateLimiter(rate=1, capacity=1)
    assert await limiter.acquire(drop=True)
    assert not await limiter.acquire(drop=True)
