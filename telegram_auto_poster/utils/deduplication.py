import hashlib
import imagehash
from PIL import Image
from loguru import logger

from .db import get_redis_client

DEDUPLICATION_SET_KEY = "telegram_auto_poster:media_hashes"  # Stores hashes of APPROVED media


def calculate_image_hash(file_path: str) -> str:
    """
    Calculates the perceptual hash of an image.
    """
    try:
        hash_value = imagehash.phash(Image.open(file_path))
        return str(hash_value)
    except Exception as e:
        logger.error(f"Could not calculate hash for image {file_path}: {e}")
        return None


def calculate_video_hash(file_path: str) -> str:
    """
    Calculates the MD5 hash of a video file.
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
    """
    Legacy helper: add hash to the approved corpus if not exists.
    Returns True if the hash was added (i.e., not already present), False otherwise.
    """
    return add_approved_hash(media_hash, redis_client=redis_client)


def is_duplicate_hash(media_hash: str, redis_client=None) -> bool:
    """Check if a media hash exists in the APPROVED corpus."""
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
    """Add a media hash to the APPROVED corpus; returns True if newly added."""
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
