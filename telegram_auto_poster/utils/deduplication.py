import hashlib
import imagehash
from PIL import Image
from loguru import logger

from .db import get_redis_client

DEDUPLICATION_SET_KEY = "media_hashes"


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
    Adds a media hash to the Redis set if it doesn't exist.
    Returns True if the hash was added (i.e., not a duplicate), False otherwise.
    """
    if not media_hash:
        return True  # Not a duplicate, allow processing
    if redis_client is None:
        redis_client = get_redis_client()
    try:
        # SADD returns the number of elements that were added to the set.
        return redis_client.sadd(DEDUPLICATION_SET_KEY, media_hash) == 1
    except Exception as e:
        logger.error(f"Could not add hash to deduplication set: {e}")
        # Fail open, assume not a duplicate if Redis check fails
        return True
