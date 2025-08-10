import os
import pytest
from unittest.mock import patch
from PIL import Image
from fakeredis import FakeStrictRedis

from telegram_auto_poster.utils.deduplication import (
    calculate_image_hash,
    calculate_video_hash,
    is_duplicate,
    add_hash,
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

def test_add_and_check_duplicate(fake_redis):
    """Test adding a hash and checking for duplicates"""
    media_hash = "test_hash"

    # Initially, it's not a duplicate
    assert not is_duplicate(media_hash, redis_client=fake_redis)

    # Add the hash
    add_hash(media_hash, redis_client=fake_redis)

    # Now it should be a duplicate
    assert is_duplicate(media_hash, redis_client=fake_redis)

def test_is_duplicate_with_empty_hash(fake_redis):
    """Test that is_duplicate returns False for empty hash"""
    assert not is_duplicate(None, redis_client=fake_redis)
    assert not is_duplicate("", redis_client=fake_redis)

def test_add_hash_with_empty_hash(fake_redis):
    """Test that add_hash does not add empty hashes"""
    add_hash(None, redis_client=fake_redis)
    add_hash("", redis_client=fake_redis)
    assert fake_redis.scard(DEDUPLICATION_SET_KEY) == 0
