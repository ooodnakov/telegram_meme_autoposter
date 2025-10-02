"""Asynchronous MinIO storage helpers with submission metadata support."""

import asyncio
import os
import tempfile
import time
from datetime import timedelta
from inspect import iscoroutinefunction
from unittest.mock import MagicMock
from urllib.parse import urlparse

import telegram_auto_poster.utils.stats as stats_module
from loguru import logger
from telegram_auto_poster.config import (
    BUCKET_MAIN,
    CONFIG,
    DOWNLOADS_PATH,
    PHOTOS_PATH,
    VIDEOS_PATH,
)
from telegram_auto_poster.utils.db import _redis_key, get_async_redis_client
from telegram_auto_poster.utils.timezone import now_utc

MINIO_BACKEND = CONFIG.minio.backend

if MINIO_BACKEND == "garage":
    from telegram_auto_poster.utils.garage import GarageClient as Minio
    from telegram_auto_poster.utils.garage import GarageCopySource as CopySource

    class MinioException(Exception):
        """Fallback exception used by the Garage backend."""

    class S3Error(MinioException):
        """Compatibility alias for Garage errors."""

    MINIO_ENDPOINT = "garage"
    MINIO_SECURE = False
    MINIO_INTERNAL_URL = CONFIG.minio.public_url or ""
else:
    from miniopy_async import Minio
    from miniopy_async.commonconfig import CopySource
    from miniopy_async.error import MinioException, S3Error

    # Get MinIO configuration from centralized config
    MINIO_URL = CONFIG.minio.url
    MINIO_HOST = CONFIG.minio.host
    MINIO_PORT = CONFIG.minio.port
    MINIO_ACCESS_KEY = CONFIG.minio.access_key.get_secret_value()
    MINIO_SECRET_KEY = CONFIG.minio.secret_key.get_secret_value()

    if MINIO_URL:
        parsed = urlparse(MINIO_URL)
        if not parsed.netloc:
            # Ensure a scheme is present so ``urlparse`` extracts the host correctly
            parsed = urlparse(f"http://{MINIO_URL}")
        MINIO_ENDPOINT = parsed.netloc
        MINIO_SECURE = parsed.scheme == "https"
        MINIO_INTERNAL_URL = f"{parsed.scheme}://{MINIO_ENDPOINT}"
    else:
        MINIO_ENDPOINT = f"{MINIO_HOST}:{MINIO_PORT}"
        MINIO_SECURE = False
        MINIO_INTERNAL_URL = f"http://{MINIO_ENDPOINT}"

MINIO_ACCESS_KEY = CONFIG.minio.access_key.get_secret_value()
MINIO_SECRET_KEY = CONFIG.minio.secret_key.get_secret_value()


def _to_int(value: str | None) -> int | None:
    """Convert a string to ``int`` if not ``None``."""
    return int(value) if value is not None else None


class MinioStorage:
    """Wrapper around :class:`minio.Minio` providing convenience helpers.

    The class exposes a singleton interface used throughout the project to
    upload and download media files.  It also records timing information about
    storage operations for later analysis.

    Attributes:
        client (Minio): Underlying MinIO client instance.
        submission_metadata (dict): In-memory metadata indexed by object name.

    """

    _instance: "MinioStorage | None" = None
    _initialized: bool

    def __new__(cls, *args: object, **kwargs: object) -> "MinioStorage":
        """Implement the singleton pattern for the storage client."""
        if cls._instance is None:
            cls._instance = super(MinioStorage, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, client: Minio | None = None) -> None:
        """Connect to MinIO and prepare buckets on first instantiation."""
        if self._initialized:
            return

        try:
            if client is not None:
                self.client = client
            else:
                if MINIO_BACKEND == "garage":
                    garage_root = CONFIG.minio.garage_root
                    logger.info(f"Initializing Garage client at {garage_root}")
                    self.client = Minio(garage_root)
                else:
                    logger.info(
                        f"Initializing MinIO client for {MINIO_ENDPOINT} (secure={MINIO_SECURE})"
                    )
                    self.client = Minio(
                        MINIO_ENDPOINT,
                        access_key=MINIO_ACCESS_KEY,
                        secret_key=MINIO_SECRET_KEY,
                        secure=MINIO_SECURE,
                    )

            # Store metadata about submissions
            self.submission_metadata: dict[str, dict[str, object]] = {}

            logger.info("MinIO client initialized")

            # Ensure buckets exist
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._ensure_bucket_exists(BUCKET_MAIN))
            except RuntimeError:
                asyncio.run(self._ensure_bucket_exists(BUCKET_MAIN))

            self._initialized = True
        except Exception as e:
            logger.error(f"Error initializing MinIO client: {e}")
            asyncio.run(
                _stats_record_error(
                    "storage", f"Failed to initialize MinIO client: {e}"
                )
            )
            raise

    async def get_presigned_url(self, object_name: str) -> str | None:
        """Generate a presigned URL for an object.

        Args:
            object_name (str): Name of the object in the bucket.

        Returns:
            str | None: Time-limited URL or ``None`` if unavailable.

        """
        try:
            # Generate a presigned URL that expires in 7 days
            internal_url = await self.client.presigned_get_object(
                BUCKET_MAIN,
                object_name,
                expires=timedelta(days=7),
                response_headers={"response-content-disposition": "inline"},
            )

            public_url = CONFIG.minio.public_url
            if public_url:
                if MINIO_INTERNAL_URL and MINIO_INTERNAL_URL in internal_url:
                    return internal_url.replace(MINIO_INTERNAL_URL, public_url)
                return f"{public_url.rstrip('/')}/{object_name}"

            return internal_url
        except Exception as e:
            logger.error(f"Failed to get presigned URL for '{object_name}': {e}")
            return None

    async def _ensure_bucket_exists(self, bucket_name: str) -> None:
        """Create the given bucket in MinIO if it has not been created yet.

        Args:
            bucket_name: Bucket to verify or create.

        """
        try:
            if not await self.client.bucket_exists(bucket_name):
                await self.client.make_bucket(bucket_name)
                logger.info(f"Created new bucket: {bucket_name}")
        except Exception as e:
            logger.error(f"Error creating bucket {bucket_name}: {e}")
            await _stats_record_error(
                "storage", f"Failed to create bucket {bucket_name}: {e}"
            )
            raise

    async def store_submission_metadata(
        self,
        object_name: str,
        user_id: int | None = None,
        chat_id: int | None = None,
        media_type: str | None = None,
        message_id: int | None = None,
        media_hash: str | None = None,
        group_id: str | None = None,
        caption: str | None = None,
        source: str | None = None,
    ) -> None:
        """Store information about who submitted a particular media object.

        The metadata is kept in memory for quick feedback to users and also
        mirrored in Valkey so it survives restarts.

        Args:
            object_name: Name of the object in MinIO.
            user_id: The Telegram ``user_id`` of the submitter.
            chat_id: The Telegram ``chat_id`` where the media was submitted.
            media_type: Type of media (``'photo'`` or ``'video'``).
            message_id: Optional Telegram ``message_id`` of the original
                submission.
            media_hash: Optional hash used for deduplication.
            group_id: Optional identifier for media groups/albums.
            caption: Optional caption suggestion.
            source: Optional identifier of the originating channel or user.

        """
        meta: dict[str, object] = {
            "user_id": user_id,
            "chat_id": chat_id,
            "media_type": media_type,
            "timestamp": now_utc().isoformat(),
            "notified": False,
            "message_id": message_id,
            "hash": media_hash,
            "group_id": group_id,
            "caption": caption,
            "source": source,
        }
        self.submission_metadata[object_name] = meta
        try:
            r = get_async_redis_client()
            await r.hset(
                _redis_key("submissions", object_name),
                mapping={k: str(v) for k, v in meta.items() if v is not None},
            )
        except Exception as e:
            logger.error(f"Failed to store submission metadata in Redis: {e}")
        logger.debug(
            "Stored metadata for {}: user_id={}, chat_id={}, message_id={}, group_id={}, caption={}, source={}".format(
                object_name,
                user_id,
                chat_id,
                message_id,
                group_id,
                caption,
                source,
            )
        )

    async def get_submission_metadata(
        self, object_name: str
    ) -> dict[str, object] | None:
        """Return metadata for a stored object if available.

        Args:
            object_name: Name of the object stored in MinIO.

        Returns:
            dict | None: Metadata dictionary or ``None`` if not found.

        """
        # Normalise object name to account for callers that pass only the basename
        candidates = [object_name]
        if "/" not in object_name:
            candidates.extend(
                [
                    f"{PHOTOS_PATH}/{object_name}",
                    f"{VIDEOS_PATH}/{object_name}",
                    f"{DOWNLOADS_PATH}/{object_name}",
                ]
            )

        # Check in-memory metadata first
        for name in candidates:
            meta = self.submission_metadata.get(name)
            if meta:
                return meta

        # Try Redis (Valkey) next
        try:
            r = get_async_redis_client()
            for name in candidates:
                data = await r.hgetall(_redis_key("submissions", name))
                if data:
                    meta = {
                        "user_id": _to_int(data.get("user_id")),
                        "chat_id": _to_int(data.get("chat_id")),
                        "media_type": data.get("media_type"),
                        "timestamp": data.get("timestamp"),
                        "notified": data.get("notified") in {"True", "1"},
                        "message_id": _to_int(data.get("message_id")),
                        "hash": data.get("hash"),
                        "review_chat_id": _to_int(data.get("review_chat_id")),
                        "review_message_id": _to_int(data.get("review_message_id")),
                        "group_id": data.get("group_id"),
                        "trashed_at": data.get("trashed_at"),
                        "trash_expires_at": data.get("trash_expires_at"),
                    }
                    self.submission_metadata[name] = meta
                    return meta
        except Exception as e:
            logger.error(f"Failed to get submission metadata from Redis: {e}")
        return None

    async def update_submission_metadata(
        self, object_name: str, **fields: object | None
    ) -> dict[str, object]:
        """Update cached and persisted metadata for ``object_name``.

        ``None`` values remove the corresponding keys from the stored
        metadata.
        """

        meta = await self.get_submission_metadata(object_name) or {}
        to_set = {k: v for k, v in fields.items() if v is not None}
        to_delete = [k for k, v in fields.items() if v is None]

        meta.update(to_set)
        for key in to_delete:
            meta.pop(key, None)

        self.submission_metadata[object_name] = meta

        try:
            r = get_async_redis_client()
            redis_key = _redis_key("submissions", object_name)
            pipe = r.pipeline()
            has_commands = False
            if to_set:
                pipe.hset(redis_key, mapping={k: str(v) for k, v in to_set.items()})
                has_commands = True
            for field in to_delete:
                pipe.hdel(redis_key, field)
                has_commands = True
            if has_commands:
                await pipe.execute()
        except Exception as e:
            logger.error(f"Failed to update submission metadata in Redis: {e}")

        return meta

    async def mark_notified(self, object_name: str) -> bool:
        """Mark that the user has been notified about their submission.

        Args:
            object_name: Name of the object in MinIO.

        Returns:
            bool: ``True`` if metadata exists and was updated, ``False``
            otherwise.

        """
        meta = await self.get_submission_metadata(object_name)
        if not meta:
            return False
        meta["notified"] = True
        self.submission_metadata[object_name] = meta
        try:
            r = get_async_redis_client()
            await r.hset(_redis_key("submissions", object_name), "notified", "1")
        except Exception as e:
            logger.error(f"Failed to mark notified in Redis: {e}")
        return True

    async def store_review_message(
        self, object_name: str, chat_id: int, message_id: int
    ) -> None:
        """Store Telegram review message identifiers for later editing."""
        meta: dict[str, object] = self.submission_metadata.setdefault(object_name, {})
        meta["review_chat_id"] = chat_id
        meta["review_message_id"] = message_id
        try:
            r = get_async_redis_client()
            await r.hset(
                _redis_key("submissions", object_name),
                mapping={
                    "review_chat_id": str(chat_id),
                    "review_message_id": str(message_id),
                },
            )
        except Exception as e:
            logger.error(f"Failed to store review message in Redis: {e}")
        logger.debug(f"Stored review message for {object_name}: {chat_id}/{message_id}")

    async def get_review_message(self, object_name: str) -> tuple[int, int] | None:
        """Return stored review message identifiers if available."""
        meta = await self.get_submission_metadata(object_name)
        if not meta:
            return None
        chat_id_val = meta.get("review_chat_id")
        message_id_val = meta.get("review_message_id")
        if isinstance(chat_id_val, (int, str)) and isinstance(
            message_id_val, (int, str)
        ):
            return int(chat_id_val), int(message_id_val)
        return None

    async def upload_file(
        self,
        file_path: str,
        bucket: str | None = None,
        object_name: str | None = None,
        user_id: int | None = None,
        chat_id: int | None = None,
        message_id: int | None = None,
        media_hash: str | None = None,
        group_id: str | None = None,
        source: str | None = None,
    ) -> bool:
        """Upload a file to MinIO and record how long the operation took.

        Additional metadata about the submitting user is stored separately in
        Valkey for later feedback or auditing. The appropriate bucket and
        object name are determined automatically when not supplied.

        Args:
            file_path: Path to the local file.
            bucket: Bucket name (defaults to ``BUCKET_MAIN`` or based on
                extension).
            object_name: Name for the object in MinIO (defaults to the file
                name).
            user_id: Optional ``user_id`` of the submitter for feedback.
            chat_id: Optional ``chat_id`` where the submission was made.
            message_id: Optional Telegram ``message_id`` of the original
                submission.
            media_hash: Optional hash of the file for deduplication purposes.
            group_id: Optional identifier for media groups/albums.
            source: Optional channel or username of the submitter.

        Returns:
            bool: ``True`` if upload was successful, ``False`` otherwise.

        """
        start_time = time.time()
        try:
            # Determine bucket based on file extension if not provided
            if bucket is None:
                bucket = BUCKET_MAIN
            media_type = None
            if file_path.endswith((".jpg", ".jpeg", ".png")):
                object_prefix = PHOTOS_PATH
                media_type = "photo"
            elif file_path.endswith((".mp4", ".avi", ".mov")):
                object_prefix = VIDEOS_PATH
                media_type = "video"
            else:
                object_prefix = DOWNLOADS_PATH
                media_type = "document"

            if media_type:
                media_type = {
                    PHOTOS_PATH: "photo",
                    VIDEOS_PATH: "video",
                    DOWNLOADS_PATH: "document",
                }[object_prefix]

            # Use filename as object_name if not provided
            if object_name is None:
                object_name = os.path.basename(file_path)
            if "/" not in object_name:
                object_name = object_prefix + "/" + object_name

            logger.debug(f"Uploading {file_path} to {bucket}/{object_name}")
            await self.client.fput_object(
                bucket_name=bucket,
                object_name=object_name,
                file_path=file_path,
            )
            logger.debug(f"Uploaded {file_path} to {bucket}/{object_name}")
            try:
                r = get_async_redis_client()
                # Keep a complete lexicographically sorted cache of object names.
                await r.zadd(_redis_key("objects", bucket), {object_name: 0})
            except Exception as e:  # pragma: no cover - cache is best effort
                logger.error(
                    f"Failed to cache object list entry for {bucket}/{object_name}: {e}"
                )
            # Store submission metadata in-memory as well
            if any(
                x is not None
                for x in (user_id, chat_id, group_id, media_hash, message_id)
            ):
                await self.store_submission_metadata(
                    object_name,
                    user_id,
                    chat_id,
                    media_type,
                    message_id,
                    media_hash,
                    group_id,
                    source=source,
                )

            duration = time.time() - start_time
            await _stats_record_operation("upload", duration)
            return True
        except MinioException as e:
            logger.error(f"MinIO error uploading {file_path}: {e}")
            await _stats_record_error("storage", f"Failed to upload {file_path}: {e}")
            return False
        except Exception as e:
            logger.error(f"Error uploading {file_path}: {e}")
            await _stats_record_error(
                "storage", f"Unexpected error uploading {file_path}: {e}"
            )
            return False

    async def download_file(
        self, object_name: str, bucket: str, file_path: str | None = None
    ) -> bool:
        """Download an object from MinIO and measure the duration.

        Args:
            object_name: Name of the object in MinIO.
            bucket: Bucket name.
            file_path: Local path to save file (defaults to a temporary file).

        Returns:
            bool: ``True`` if download was successful, ``False`` otherwise.

        """
        start_time = time.time()
        temp_file = None
        if file_path is None:
            temp_file = tempfile.NamedTemporaryFile(delete=False)
            file_path_str = temp_file.name
            temp_file.close()
        else:
            file_path_str = file_path

        try:
            # Download the object
            await self.client.fget_object(
                bucket_name=bucket, object_name=object_name, file_path=file_path_str
            )

            logger.debug(f"Downloaded {bucket}/{object_name} to {file_path_str}")

            duration = time.time() - start_time
            await _stats_record_operation("download", duration)
            return True
        except MinioException as e:
            logger.error(f"MinIO error downloading {bucket}/{object_name}: {e}")
            await _stats_record_error(
                "storage", f"Failed to download {bucket}/{object_name}: {e}"
            )
            if temp_file and os.path.exists(file_path_str):
                os.unlink(file_path_str)
            return False
        except Exception as e:
            logger.error(f"Error downloading {bucket}/{object_name}: {e}")
            if temp_file and os.path.exists(file_path_str):
                os.unlink(file_path_str)
            await _stats_record_error(
                "storage", f"Unexpected error downloading {bucket}/{object_name}: {e}"
            )
            return False

    async def get_object_data(self, object_name: str, bucket: str) -> bytes:
        """Return raw object data as bytes.

        Args:
            object_name: Name of the object in MinIO.
            bucket: Bucket name.

        Returns:
            bytes: The object's contents.

        """
        try:
            response = await self.client.get_object(
                bucket_name=bucket, object_name=object_name
            )

            data = await response.read()
            if iscoroutinefunction(response.close):
                await response.close()
            else:
                response.close()
            if hasattr(response, "release_conn"):
                release = response.release_conn
                if iscoroutinefunction(release):
                    await release()
                else:
                    release()

            return data
        except S3Error as err:
            logger.error(f"Error getting object {bucket}/{object_name}: {err}")
            raise

    async def delete_file(self, object_name: str, bucket: str) -> bool:
        """Remove an object from MinIO and record the operation time.

        Args:
            object_name: Name of the object to delete.
            bucket: Bucket name.

        Returns:
            bool: ``True`` if deletion was successful, ``False`` otherwise.

        """
        try:
            await self.client.remove_object(bucket_name=bucket, object_name=object_name)
            logger.debug(f"Deleted {bucket}/{object_name}")
            try:
                r = get_async_redis_client()
                await r.zrem(_redis_key("objects", bucket), object_name)
            except Exception as e:  # pragma: no cover - cache is best effort
                logger.error(
                    f"Failed to evict object list entry for {bucket}/{object_name}: {e}"
                )
            return True
        except MinioException as e:
            logger.error(f"MinIO error deleting {bucket}/{object_name}: {e}")
            await _stats_record_error(
                "storage", f"Failed to delete {bucket}/{object_name}: {e}"
            )
            return False
        except Exception as e:
            logger.error(f"Error deleting {bucket}/{object_name}: {e}")
            await _stats_record_error(
                "storage", f"Unexpected error deleting {bucket}/{object_name}: {e}"
            )
            return False

    async def list_files(
        self,
        bucket: str,
        prefix: str | None = None,
        *,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[str]:
        """List objects in a bucket and record how long the listing took.

        Args:
            bucket: Bucket name.
            prefix: Optional prefix filter.
            offset: Number of leading objects to skip.
            limit: Maximum number of objects to return.

        Returns:
            list: List of object names.

        """
        start_time = time.time()
        cache_key = _redis_key("objects", bucket)
        try:
            r = get_async_redis_client()
            if await r.exists(cache_key):
                if prefix:
                    min_val = f"[{prefix}"
                    max_val = f"({prefix}\xff"
                else:
                    min_val = "-"
                    max_val = "+"
                cached = await r.zrangebylex(
                    cache_key, min_val, max_val, start=offset, num=limit
                )
                duration = time.time() - start_time
                await _stats_record_operation("list", duration)
                return list(cached)
        except Exception as e:  # pragma: no cover - cache is best effort
            logger.debug(f"Redis unavailable for list_files: {e}")

        try:
            objects: list[str] = []
            results = self.client.list_objects(bucket, prefix=prefix, recursive=True)
            async for obj in results:
                # Some SDKs may yield None or incomplete entries; skip safely
                name = getattr(obj, "object_name", None) if obj is not None else None
                if not name:
                    logger.debug("Skipping null/incomplete object from list_objects")
                    continue
                objects.append(name)
                if limit is not None and len(objects) >= offset + limit:
                    break
            objects.sort()
            end = None if limit is None else offset + limit
            result = objects[offset:end]
            logger.debug(
                f"Listed {len(result)} objects in {bucket} with prefix {prefix}"
            )

            try:
                if objects and prefix is None and offset == 0 and limit is None:
                    r = get_async_redis_client()
                    pipe = r.pipeline()
                    await pipe.delete(cache_key)
                    await pipe.zadd(cache_key, {obj: 0 for obj in objects})
                    await pipe.execute()
            except Exception as e:  # pragma: no cover - cache is best effort
                logger.error(
                    f"Failed to update cache for listing {bucket} with prefix {prefix}: {e}"
                )

            duration = time.time() - start_time
            await _stats_record_operation("list", duration)
            return result
        except MinioException as e:
            logger.error(
                f"MinIO error listing objects in {bucket} with prefix {prefix}: {e}"
            )
            await _stats_record_error(
                "storage",
                f"Failed to list objects in {bucket} with prefix {prefix}: {e}",
            )
            return []
        except Exception as e:
            logger.error(f"Error listing objects in {bucket} with prefix {prefix}: {e}")
            await _stats_record_error(
                "storage",
                f"Unexpected error listing objects in {bucket} with prefix {prefix}: {e}",
            )
            return []

    async def count_files(self, bucket: str, prefix: str | None = None) -> int:
        """Return the number of objects matching ``prefix`` in ``bucket``."""
        cache_key = _redis_key("objects", bucket)
        try:
            r = get_async_redis_client()
            if await r.exists(cache_key):
                if prefix:
                    return await r.zlexcount(cache_key, f"[{prefix}", f"({prefix}\xff")
                return await r.zcard(cache_key)
        except Exception as e:  # pragma: no cover - cache is best effort
            logger.debug(f"Redis unavailable for count_files: {e}")

        return len(await self.list_files(bucket, prefix=prefix))

    async def file_exists(self, object_name: str, bucket: str) -> bool:
        """Check if a file exists in MinIO by attempting to stat it.

        Args:
            object_name: Name of the object.
            bucket: Bucket name.

        Returns:
            bool: ``True`` if file exists, ``False`` otherwise.

        """
        try:
            await self.client.stat_object(bucket_name=bucket, object_name=object_name)
            return True
        except MinioException:
            return False
        except Exception as e:
            logger.error(f"Error checking if {bucket}/{object_name} exists: {e}")
            await _stats_record_error(
                "storage",
                f"Unexpected error checking if {bucket}/{object_name} exists: {e}",
            )
            return False


async def _stats_record_error(scope: str, message: str) -> None:
    """Forward storage errors to the statistics collector if available."""
    if stats_module.stats and not isinstance(stats_module.stats, MagicMock):
        await stats_module.stats.record_error(scope, message)


async def _stats_record_operation(name: str, duration: float) -> None:
    """Forward storage operation timings to the statistics collector."""
    if stats_module.stats and not isinstance(stats_module.stats, MagicMock):
        await stats_module.stats.record_storage_operation(name, duration)


storage = MinioStorage()


def reset_storage_for_tests() -> None:
    """Reset the singleton storage instance. Intended for test suites."""

    MinioStorage._instance = None  # type: ignore[attr-defined]
    global storage
    storage = MinioStorage()
