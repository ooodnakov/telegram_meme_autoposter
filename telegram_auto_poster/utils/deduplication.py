import hashlib

import imagehash
from loguru import logger
from PIL import Image
from telegram_auto_poster.utils.db import get_redis_client

DEDUPLICATION_SET_KEY = (
    "telegram_auto_poster:media_hashes"  # Stores hashes of APPROVED media
)


def calculate_image_hash(file_path: str) -> str | None:
    """Calculate the perceptual hash of an image.

    Args:
        file_path: Path to the image file.

    Returns:
        The perceptual hash as a string, or ``None`` if the hash
        calculation fails.
    """
    try:
        hash_value = imagehash.phash(Image.open(file_path))
        return str(hash_value)
    except Exception as e:
        logger.error(f"Could not calculate hash for image {file_path}: {e}")
        return None


def calculate_video_hash(file_path: str) -> str | None:
    """Calculate the MD5 hash of a video file.

    Args:
        file_path: Path to the video file.

    Returns:
        The MD5 hash of the file as a hexadecimal string, or ``None``
        if the hash calculation fails.
    """
    hash_md5 = hashlib.md5()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except Exception as e:
        logger.error(f"Could not calculate hash for video {file_path}: {e}")
        return None


def check_and_add_hash(media_hash: str, redis_client=None) -> bool:
    """Add a hash to the approved corpus if it is not already present.

    This is a compatibility wrapper around :func:`add_approved_hash`.

    Args:
        media_hash: Hash value of the media to store.
        redis_client: Optional redis client instance.

    Returns:
        ``True`` if the hash was newly added, ``False`` if it already
        existed or if the operation fails.

    """
    return add_approved_hash(media_hash, redis_client=redis_client)


def is_duplicate_hash(media_hash: str, redis_client=None) -> bool:
    """Check if a media hash exists in the approved corpus.

    Args:
        media_hash: Hash value to look up.
        redis_client: Optional redis client instance.

    Returns:
        ``True`` if the hash is already stored, ``False`` otherwise. If
        the redis operation fails, ``False`` is returned.
    """
    if not media_hash:
        return False
    if redis_client is None:
        redis_client = get_redis_client()
    try:
        return bool(redis_client.sismember(DEDUPLICATION_SET_KEY, media_hash))
    except Exception as e:
        logger.error(f"Could not check hash in deduplication set: {e}")
        # Fail open, treat as not duplicate if Redis check fails
        return False


def add_approved_hash(media_hash: str, redis_client=None) -> bool:
    """Store a media hash in the approved corpus.

    Args:
        media_hash: Hash value of the approved media.
        redis_client: Optional redis client instance.

    Returns:
        ``True`` if the hash was newly added or if `media_hash` is empty,
        ``False`` if the hash already existed or if storing fails.
    """
    if not media_hash:
        return True
    if redis_client is None:
        redis_client = get_redis_client()
    try:
        return redis_client.sadd(DEDUPLICATION_SET_KEY, media_hash) == 1
    except Exception as e:
        logger.error(f"Could not add hash to deduplication set: {e}")
        # Treat as not added on failure
        return False
