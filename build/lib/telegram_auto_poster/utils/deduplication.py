import hashlib
import imagehash
from PIL import Image
from loguru import logger

from .stats import redis_client

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


def is_duplicate(media_hash: str) -> bool:
    """
    Checks if a media hash already exists in the Redis set.
    """
    if not media_hash:
        return False
    try:
        return redis_client.sismember(DEDUPLICATION_SET_KEY, media_hash)
    except Exception as e:
        logger.error(f"Could not check for duplicate hash: {e}")
        # Fail open, i.e., assume not a duplicate if Redis check fails
        return False


def add_hash(media_hash: str):
    """
    Adds a media hash to the Redis set.
    """
    if not media_hash:
        return
    try:
        redis_client.sadd(DEDUPLICATION_SET_KEY, media_hash)
        logger.info(f"Added hash {media_hash} to deduplication set.")
    except Exception as e:
        logger.error(f"Could not add hash to deduplication set: {e}")
