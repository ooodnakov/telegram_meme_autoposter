import os
import pytest
from PIL import Image
from fakeredis import FakeStrictRedis
from loguru import logger

from telegram_auto_poster.utils.deduplication import (
    calculate_image_hash,
    calculate_video_hash,
    check_and_add_hash,
    is_duplicate_hash,
    add_approved_hash,
    DEDUPLICATION_SET_KEY,
)


@pytest.fixture
def fake_redis():
    """Fixture to mock redis client"""
    return FakeStrictRedis(decode_responses=True)


@pytest.fixture
def sample_image(tmpdir):
    """Fixture to create a sample image file"""
    img = Image.new("RGB", (100, 100), color="red")
    path = os.path.join(tmpdir, "sample.jpg")
    img.save(path)
    return path


@pytest.fixture
def sample_video(tmpdir):
    """Fixture to create a sample video file"""
    path = os.path.join(tmpdir, "sample.mp4")
    with open(path, "wb") as f:
        f.write(os.urandom(1024))
    return path


def test_calculate_image_hash(sample_image):
    """Test that image hash is calculated correctly"""
    image_hash = calculate_image_hash(sample_image)
    assert image_hash is not None
    assert isinstance(image_hash, str)
    assert len(image_hash) == 16  # phash is 16 chars


def test_calculate_video_hash(sample_video):
    """Test that video hash is calculated correctly"""
    video_hash = calculate_video_hash(sample_video)
    assert video_hash is not None
    assert isinstance(video_hash, str)
    assert len(video_hash) == 32  # md5 is 32 chars


def test_check_and_add_hash(fake_redis):
    """Test adding a hash and checking for duplicates"""
    media_hash = "test_hash_atomic"

    # First time, it's not a duplicate, so it should be added and return True
    assert check_and_add_hash(media_hash, redis_client=fake_redis) is True

    # Second time, it is a duplicate, so it should not be added and return False
    assert check_and_add_hash(media_hash, redis_client=fake_redis) is False


def test_check_and_add_with_empty_hash(fake_redis):
    """Test that check_and_add_hash returns True for empty hash"""
    assert check_and_add_hash(None, redis_client=fake_redis) is True
    assert check_and_add_hash("", redis_client=fake_redis) is True
    # Ensure nothing was added to the set
    assert fake_redis.scard(DEDUPLICATION_SET_KEY) == 0


def test_add_approved_hash(fake_redis):
    """Test adding a hash to the approved set"""
    media_hash = "test_hash_new"
    # First time, it's not a duplicate, so it should be added and return True
    assert add_approved_hash(media_hash, redis_client=fake_redis) is True
    # Check that it was added
    assert fake_redis.sismember(DEDUPLICATION_SET_KEY, media_hash)
    # Second time, it is a duplicate, so it should not be added and return False
    assert add_approved_hash(media_hash, redis_client=fake_redis) is False


def test_add_approved_hash_empty(fake_redis):
    """Test adding an empty hash to the approved set"""
    assert add_approved_hash(None, redis_client=fake_redis) is True
    assert add_approved_hash("", redis_client=fake_redis) is True
    assert fake_redis.scard(DEDUPLICATION_SET_KEY) == 0


def test_is_duplicate_hash(fake_redis):
    """Test checking for a duplicate hash"""
    media_hash = "test_hash_duplicate"
    # Not a duplicate yet
    assert is_duplicate_hash(media_hash, redis_client=fake_redis) is False
    # Add it
    fake_redis.sadd(DEDUPLICATION_SET_KEY, media_hash)
    # Now it's a duplicate
    assert is_duplicate_hash(media_hash, redis_client=fake_redis) is True


def test_is_duplicate_hash_empty(fake_redis):
    """Test checking for an empty duplicate hash"""
    assert is_duplicate_hash(None, redis_client=fake_redis) is False
    assert is_duplicate_hash("", redis_client=fake_redis) is False


def test_is_duplicate_hash_redis_error(mocker):
    """Test is_duplicate_hash with redis error"""
    mock_redis = mocker.MagicMock()
    mock_redis.sismember.side_effect = Exception("Redis is down")
    media_hash = "test_hash_error"
    logs = []
    logger.add(logs.append, level="ERROR")
    assert is_duplicate_hash(media_hash, redis_client=mock_redis) is False
    assert len(logs) == 1
    assert "Could not check hash" in logs[0]


def test_add_approved_hash_redis_error(mocker):
    """Test add_approved_hash with redis error"""
    mock_redis = mocker.MagicMock()
    mock_redis.sadd.side_effect = Exception("Redis is down")
    media_hash = "test_hash_error_add"
    logs = []
    logger.add(logs.append, level="ERROR")
    assert add_approved_hash(media_hash, redis_client=mock_redis) is False
    assert len(logs) == 1
    assert "Could not add hash" in logs[0]
