import asyncio
import os
import tempfile
import time
from inspect import iscoroutinefunction
from unittest.mock import MagicMock

import telegram_auto_poster.utils.stats as stats_module
from miniopy_async import Minio
from miniopy_async.error import MinioException, S3Error
from opentelemetry import trace
from telegram_auto_poster.config import (
    BUCKET_MAIN,
    CONFIG,
    DOWNLOADS_PATH,
    PHOTOS_PATH,
    VIDEOS_PATH,
)
from telegram_auto_poster.utils.logger_setup import get_logger
from telegram_auto_poster.utils.timezone import now_utc

tracer = trace.get_tracer(__name__)

# Get MinIO configuration from centralized config
MINIO_HOST = CONFIG["minio"]["host"]
MINIO_PORT = CONFIG["minio"]["port"]
MINIO_ACCESS_KEY = CONFIG["minio"]["access_key"]
MINIO_SECRET_KEY = CONFIG["minio"]["secret_key"]


class MinioStorage:
    """Wrapper around :class:`minio.Minio` providing convenience helpers.

    The class exposes a singleton interface used throughout the project to
    upload and download media files.  It also records timing information about
    storage operations for later analysis.

    Attributes:
        client (Minio): Underlying MinIO client instance.
        submission_metadata (dict): In-memory metadata indexed by object name.
    """

    _instance = None

    def __new__(cls, *args, **kwargs):
        """Implement the singleton pattern for the storage client."""
        if cls._instance is None:
            cls._instance = super(MinioStorage, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, client=None):
        """Connect to MinIO and prepare buckets on first instantiation."""
        if self._initialized:
            return

        try:
            if client:
                self.client = client
            else:
                self.client = Minio(
                    f"{MINIO_HOST}:{MINIO_PORT}",
                    access_key=MINIO_ACCESS_KEY,
                    secret_key=MINIO_SECRET_KEY,
                    secure=False,
                    region="ru-west",
                )

            # Store metadata about submissions
            self.submission_metadata = {}

            get_logger(operation="storage_init").info("MinIO client initialized")

            # Ensure buckets exist
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._ensure_bucket_exists(BUCKET_MAIN))
            except RuntimeError:
                asyncio.run(self._ensure_bucket_exists(BUCKET_MAIN))

            self._initialized = True
        except Exception as e:
            get_logger(operation="storage_init").error(
                f"Error initializing MinIO client: {e}"
            )
            asyncio.run(
                _stats_record_error(
                    "storage", f"Failed to initialize MinIO client: {e}"
                )
            )
            raise

    async def _ensure_bucket_exists(self, bucket_name: str) -> None:
        """Create the given bucket in MinIO if it has not been created yet.

        Args:
            bucket_name: Bucket to verify or create.
        """
        try:
            if not await self.client.bucket_exists(bucket_name):
                await self.client.make_bucket(bucket_name)
                get_logger(object_name=bucket_name, operation="ensure_bucket").info(
                    "Created new bucket"
                )
        except Exception as e:
            get_logger(object_name=bucket_name, operation="ensure_bucket").error(
                f"Error creating bucket {bucket_name}: {e}"
            )
            await _stats_record_error(
                "storage", f"Failed to create bucket {bucket_name}: {e}"
            )
            raise

    async def store_submission_metadata(
        self,
        object_name,
        user_id,
        chat_id,
        media_type,
        message_id=None,
        media_hash: str | None = None,
    ):
        """Store information about who submitted a particular media object.

        The metadata is kept in memory for quick feedback to users and also
        mirrored in MinIO object metadata so it survives restarts.

        Args:
            object_name: Name of the object in MinIO.
            user_id: The Telegram ``user_id`` of the submitter.
            chat_id: The Telegram ``chat_id`` where the media was submitted.
            media_type: Type of media (``'photo'`` or ``'video'``).
            message_id: Optional Telegram ``message_id`` of the original
                submission.
            media_hash: Optional hash used for deduplication.
        """
        self.submission_metadata[object_name] = {
            "user_id": user_id,
            "chat_id": chat_id,
            "media_type": media_type,
            "timestamp": now_utc().isoformat(),
            "notified": False,
            "message_id": message_id,
            "hash": media_hash,
        }
        get_logger(object_name=object_name, operation="store_metadata").debug(
            f"Stored metadata for {object_name}: user_id={user_id}, chat_id={chat_id}, message_id={message_id}"
        )

    async def get_submission_metadata(self, object_name: str) -> dict | None:
        """Return metadata for a stored object if available.

        Args:
            object_name: Name of the object stored in MinIO.

        Returns:
            dict | None: Metadata dictionary or ``None`` if not found.
        """
        # Check in-memory metadata first
        meta = self.submission_metadata.get(object_name)
        if meta:
            return meta
        # Try to fetch metadata from MinIO across known buckets
        for prepath in [PHOTOS_PATH, VIDEOS_PATH, DOWNLOADS_PATH]:
            try:
                stat = await self.client.stat_object(
                    bucket_name=BUCKET_MAIN, object_name=prepath + "/" + object_name
                )
                md = stat.metadata or {}
                return {
                    "user_id": int(md.get("user_id")) if md.get("user_id") else None,
                    "chat_id": int(md.get("chat_id")) if md.get("chat_id") else None,
                    "media_type": md.get("media_type"),
                    "message_id": int(md.get("message_id"))
                    if md.get("message_id")
                    else None,
                    "hash": md.get("hash"),
                    # notified state is managed in-memory
                    "notified": False,
                }
            except Exception:
                continue
        return None

    async def mark_notified(self, object_name):
        """Mark that the user has been notified about their submission.

        Args:
            object_name: Name of the object in MinIO.

        Returns:
            bool: ``True`` if metadata exists and was updated, ``False``
            otherwise.
        """
        if object_name in self.submission_metadata:
            self.submission_metadata[object_name]["notified"] = True
            return True
        return False

    async def upload_file(
        self,
        file_path,
        bucket=None,
        object_name=None,
        user_id=None,
        chat_id=None,
        message_id=None,
        media_hash: str | None = None,
    ):
        """Upload a file to MinIO and record how long the operation took.

        Additional metadata about the submitting user can be attached to the
        object for later feedback or auditing.  The appropriate bucket and
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

        Returns:
            bool: ``True`` if upload was successful, ``False`` otherwise.
        """
        with tracer.start_as_current_span("storage.upload_file") as span:
            start_time = time.time()
            log = get_logger(object_name=object_name, operation="upload_file")
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

                span.set_attribute("object_name", object_name)
                span.set_attribute("bucket", bucket)

                # Build MinIO object metadata
                minio_metadata = {}
                if user_id is not None:
                    minio_metadata["user_id"] = str(user_id)
                if chat_id is not None:
                    minio_metadata["chat_id"] = str(chat_id)
                minio_metadata["media_type"] = media_type
                if message_id is not None:
                    minio_metadata["message_id"] = str(message_id)
                if media_hash is not None:
                    minio_metadata["hash"] = str(media_hash)
                # Upload file with metadata
                log = get_logger(
                    chat_id=chat_id,
                    user_id=user_id,
                    object_name=object_name,
                    operation="upload_file",
                )
                log.debug(
                    f"Uploading {file_path} to {bucket}/{object_name} with metadata {minio_metadata}"
                )
                await self.client.fput_object(
                    bucket_name=bucket,
                    object_name=object_name,
                    file_path=file_path,
                    metadata=minio_metadata,
                )
                log.debug(
                    f"Uploaded {file_path} to {bucket}/{object_name} with metadata {minio_metadata}"
                )
                # Store submission metadata in-memory as well
                if user_id and chat_id:
                    await self.store_submission_metadata(
                        object_name, user_id, chat_id, media_type, message_id
                    )

                duration = time.time() - start_time
                await _stats_record_operation("upload", duration)
                return True
            except MinioException as e:
                get_logger(
                    chat_id=chat_id,
                    user_id=user_id,
                    object_name=object_name,
                    operation="upload_file",
                ).error(f"MinIO error uploading {file_path}: {e}")
                await _stats_record_error(
                    "storage", f"Failed to upload {file_path}: {e}"
                )
                return False
            except Exception as e:
                get_logger(
                    chat_id=chat_id,
                    user_id=user_id,
                    object_name=object_name,
                    operation="upload_file",
                ).error(f"Error uploading {file_path}: {e}")
                await _stats_record_error(
                    "storage", f"Unexpected error uploading {file_path}: {e}"
                )
                return False

    async def download_file(self, object_name, bucket, file_path=None):
        """Download an object from MinIO and measure the duration.

        Args:
            object_name: Name of the object in MinIO.
            bucket: Bucket name.
            file_path: Local path to save file (defaults to a temporary file).

        Returns:
            bool: ``True`` if download was successful, ``False`` otherwise.
        """
        with tracer.start_as_current_span(
            "storage.download_file",
            attributes={"object_name": object_name, "bucket": bucket},
        ):
            start_time = time.time()
            log = get_logger(object_name=object_name, operation="download_file")
            try:
                # Create a temporary file if file_path not provided
                temp_file = None
                if file_path is None:
                    temp_file = tempfile.NamedTemporaryFile(delete=False)
                    file_path = temp_file.name
                    temp_file.close()

                # Download the object
                await self.client.fget_object(
                    bucket_name=bucket, object_name=object_name, file_path=file_path
                )

                log.debug(f"Downloaded {bucket}/{object_name} to {file_path}")

                duration = time.time() - start_time
                await _stats_record_operation("download", duration)
                return True
            except MinioException as e:
                log.error(f"MinIO error downloading {bucket}/{object_name}: {e}")
                await _stats_record_error(
                    "storage", f"Failed to download {bucket}/{object_name}: {e}"
                )
                if temp_file and os.path.exists(file_path):
                    os.unlink(file_path)
                return False
            except Exception as e:
                log.error(f"Error downloading {bucket}/{object_name}: {e}")
                if temp_file and os.path.exists(file_path):
                    os.unlink(file_path)
                await _stats_record_error(
                    "storage",
                    f"Unexpected error downloading {bucket}/{object_name}: {e}",
                )
                return False

    async def get_object_data(self, object_name, bucket):
        """Return raw object data as bytes.

        Args:
            object_name: Name of the object in MinIO.
            bucket: Bucket name.

        Returns:
            bytes: The object's contents.
        """
        log = get_logger(object_name=object_name, operation="get_object")
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
            log.error(f"Error getting object {bucket}/{object_name}: {err}")
            raise

    async def delete_file(self, object_name, bucket):
        """Remove an object from MinIO and record the operation time.

        Args:
            object_name: Name of the object to delete.
            bucket: Bucket name.

        Returns:
            bool: ``True`` if deletion was successful, ``False`` otherwise.
        """
        try:
            log = get_logger(object_name=object_name, operation="delete_file")
            await self.client.remove_object(bucket_name=bucket, object_name=object_name)
            log.debug(f"Deleted {bucket}/{object_name}")
            return True
        except MinioException as e:
            log = get_logger(object_name=object_name, operation="delete_file")
            log.error(f"MinIO error deleting {bucket}/{object_name}: {e}")
            await _stats_record_error(
                "storage", f"Failed to delete {bucket}/{object_name}: {e}"
            )
            return False
        except Exception as e:
            log = get_logger(object_name=object_name, operation="delete_file")
            log.error(f"Error deleting {bucket}/{object_name}: {e}")
            await _stats_record_error(
                "storage", f"Unexpected error deleting {bucket}/{object_name}: {e}"
            )
            return False

    async def list_files(self, bucket, prefix=None):
        """List objects in a bucket and record how long the listing took.

        Args:
            bucket: Bucket name.
            prefix: Optional prefix filter.

        Returns:
            list: List of object names.
        """
        start_time = time.time()
        log = get_logger(operation="list_files")
        try:
            objects = []
            results = await self.client.list_objects(
                bucket, prefix=prefix, recursive=True
            )
            for obj in results:
                objects.append(obj.object_name)
            log.debug(f"Listed {len(objects)} objects in {bucket} with prefix {prefix}")

            duration = time.time() - start_time
            await _stats_record_operation("list", duration)
            return objects
        except MinioException as e:
            log.error(
                f"MinIO error listing objects in {bucket} with prefix {prefix}: {e}"
            )
            await _stats_record_error(
                "storage",
                f"Failed to list objects in {bucket} with prefix {prefix}: {e}",
            )
            return []
        except Exception as e:
            log.error(f"Error listing objects in {bucket} with prefix {prefix}: {e}")
            await _stats_record_error(
                "storage",
                f"Unexpected error listing objects in {bucket} with prefix {prefix}: {e}",
            )
            return []

    async def file_exists(self, object_name, bucket):
        """Check if a file exists in MinIO by attempting to stat it.

        Args:
            object_name: Name of the object.
            bucket: Bucket name.

        Returns:
            bool: ``True`` if file exists, ``False`` otherwise.
        """
        log = get_logger(object_name=object_name, operation="file_exists")
        try:
            await self.client.stat_object(bucket_name=bucket, object_name=object_name)
            return True
        except MinioException:
            return False
        except Exception as e:
            log.error(f"Error checking if {bucket}/{object_name} exists: {e}")
            await _stats_record_error(
                "storage",
                f"Unexpected error checking if {bucket}/{object_name} exists: {e}",
            )
            return False


async def _stats_record_error(*args, **kwargs):
    if stats_module.stats and not isinstance(stats_module.stats, MagicMock):
        await stats_module.stats.record_error(*args, **kwargs)


async def _stats_record_operation(*args, **kwargs):
    if stats_module.stats and not isinstance(stats_module.stats, MagicMock):
        await stats_module.stats.record_storage_operation(*args, **kwargs)


storage = MinioStorage()
