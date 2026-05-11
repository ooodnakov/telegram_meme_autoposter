import pytest
from unittest.mock import patch
from telegram_auto_poster.utils.general import RateLimiter, backoff_delay


def test_backoff_delay_exponential_growth():
    # Test that the delay grows exponentially: 1, 2, 4, 8, 16...
    delays = [backoff_delay(i, base=1.0, cap=100.0, jitter=0.0) for i in range(1, 6)]
    assert delays == [1.0, 2.0, 4.0, 8.0, 16.0]


def test_backoff_delay_cap():
    # Test that the delay is capped
    delays = [backoff_delay(i, base=1.0, cap=5.0, jitter=0.0) for i in range(1, 6)]
    assert delays == [1.0, 2.0, 4.0, 5.0, 5.0]


def test_backoff_delay_base_and_cap():
    # Test with different base and cap
    delays = [backoff_delay(i, base=2.0, cap=10.0, jitter=0.0) for i in range(1, 5)]
    assert delays == [2.0, 4.0, 8.0, 10.0]


@patch("telegram_auto_poster.utils.general.random.uniform")
def test_backoff_delay_jitter(mock_uniform):
    # Base delay for retry=2 is 1 * 2**(2-1) = 2.0
    # Jitter range is 2.0 * 0.1 = 0.2
    # Delay will be 2.0 + random.uniform(-0.2, 0.2)
    mock_uniform.return_value = 0.15
    delay = backoff_delay(2, base=1.0, cap=5.0, jitter=0.1)
    mock_uniform.assert_called_once_with(-0.2, 0.2)
    assert delay == 2.15


@patch("telegram_auto_poster.utils.general.random.uniform")
def test_backoff_delay_negative_jitter(mock_uniform):
    # Same base delay, testing negative uniform value
    mock_uniform.return_value = -0.15
    delay = backoff_delay(2, base=1.0, cap=5.0, jitter=0.1)
    mock_uniform.assert_called_once_with(-0.2, 0.2)
    assert delay == 1.85


@pytest.mark.asyncio
async def test_rate_limiter_drop():
    limiter = RateLimiter(rate=1, capacity=1)
    assert await limiter.acquire(drop=True)
    assert not await limiter.acquire(drop=True)


@pytest.mark.asyncio
async def test_rate_limiter_wait_for_token():
    limiter = RateLimiter(rate=1000, capacity=1)
    assert await limiter.acquire()
    assert await limiter.acquire()
