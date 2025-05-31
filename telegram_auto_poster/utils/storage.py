import os
import io
import tempfile
from pathlib import Path
from minio import Minio
from minio.error import S3Error
from loguru import logger

# Get MinIO configuration from environment variables
MINIO_HOST = os.environ.get("MINIO_HOST", "localhost")
MINIO_PORT = os.environ.get("MINIO_PORT", "9000")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "minioadmin")

# Define bucket names
PHOTOS_BUCKET = "photos"
VIDEOS_BUCKET = "videos"
DOWNLOADS_BUCKET = "downloads"


class MinioStorage:
    """MinIO storage client for handling file operations."""

    _instance = None

    def __new__(cls):
        """Singleton pattern to ensure only one client instance."""
        if cls._instance is None:
            cls._instance = super(MinioStorage, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize MinIO client if not already done."""
        if self._initialized:
            return

        try:
            # Connect to MinIO
            self.client = Minio(
                f"{MINIO_HOST}:{MINIO_PORT}",
                access_key=MINIO_ACCESS_KEY,
                secret_key=MINIO_SECRET_KEY,
                secure=False,  # Set to True if using HTTPS
            )

            # Ensure buckets exist
            self._ensure_bucket_exists(PHOTOS_BUCKET)
            self._ensure_bucket_exists(VIDEOS_BUCKET)
            self._ensure_bucket_exists(DOWNLOADS_BUCKET)

            logger.info(f"Connected to MinIO at {MINIO_HOST}:{MINIO_PORT}")
            self._initialized = True
        except Exception as e:
            logger.error(f"Failed to initialize MinIO client: {e}")
            raise

    def _ensure_bucket_exists(self, bucket_name):
        """Create bucket if it doesn't exist."""
        try:
            if not self.client.bucket_exists(bucket_name):
                self.client.make_bucket(bucket_name)
                logger.info(f"Created bucket: {bucket_name}")
        except S3Error as err:
            logger.error(f"Error creating bucket {bucket_name}: {err}")
            raise

    def upload_file(self, file_path, bucket=None, object_name=None):
        """Upload a file to MinIO.

        Args:
            file_path: Path to the local file
            bucket: Bucket name (default determined by file extension)
            object_name: Name for the object in MinIO (default is filename)

        Returns:
            object_name: The name of the stored object
        """
        try:
            # Determine bucket based on file extension if not provided
            if bucket is None:
                if file_path.endswith((".jpg", ".jpeg", ".png")):
                    bucket = PHOTOS_BUCKET
                elif file_path.endswith((".mp4", ".avi", ".mov")):
                    bucket = VIDEOS_BUCKET
                else:
                    bucket = DOWNLOADS_BUCKET

            # Use filename as object_name if not provided
            if object_name is None:
                object_name = os.path.basename(file_path)

            # Upload file
            self.client.fput_object(
                bucket_name=bucket, object_name=object_name, file_path=file_path
            )

            logger.info(f"Uploaded {file_path} to {bucket}/{object_name}")
            return object_name
        except S3Error as err:
            logger.error(f"Error uploading {file_path}: {err}")
            raise

    def download_file(self, object_name, bucket, file_path=None):
        """Download a file from MinIO.

        Args:
            object_name: Name of the object in MinIO
            bucket: Bucket name
            file_path: Local path to save file (default is temp file)

        Returns:
            file_path: Path to the downloaded file
        """
        try:
            # Create a temporary file if file_path not provided
            temp_file = None
            if file_path is None:
                temp_file = tempfile.NamedTemporaryFile(delete=False)
                file_path = temp_file.name
                temp_file.close()

            # Download the object
            self.client.fget_object(
                bucket_name=bucket, object_name=object_name, file_path=file_path
            )

            logger.info(f"Downloaded {bucket}/{object_name} to {file_path}")
            return file_path
        except S3Error as err:
            logger.error(f"Error downloading {bucket}/{object_name}: {err}")
            if temp_file and os.path.exists(file_path):
                os.unlink(file_path)
            raise

    def get_object_data(self, object_name, bucket):
        """Get object data as bytes.

        Args:
            object_name: Name of the object in MinIO
            bucket: Bucket name

        Returns:
            bytes: Object data
        """
        try:
            response = self.client.get_object(
                bucket_name=bucket, object_name=object_name
            )

            data = response.read()
            response.close()
            response.release_conn()

            return data
        except S3Error as err:
            logger.error(f"Error getting object {bucket}/{object_name}: {err}")
            raise

    def delete_file(self, object_name, bucket):
        """Delete an object from MinIO.

        Args:
            object_name: Name of the object to delete
            bucket: Bucket name
        """
        try:
            self.client.remove_object(bucket_name=bucket, object_name=object_name)
            logger.info(f"Deleted {bucket}/{object_name}")
            return True
        except S3Error as err:
            logger.error(f"Error deleting {bucket}/{object_name}: {err}")
            return False

    def list_files(self, bucket, prefix=None):
        """List all files in a bucket with optional prefix.

        Args:
            bucket: Bucket name
            prefix: Optional prefix filter

        Returns:
            list: List of object names
        """
        try:
            objects = []
            for obj in self.client.list_objects(bucket, prefix=prefix, recursive=True):
                objects.append(obj.object_name)
            return objects
        except S3Error as err:
            logger.error(
                f"Error listing objects in {bucket} with prefix {prefix}: {err}"
            )
            return []

    def file_exists(self, object_name, bucket):
        """Check if a file exists in MinIO.

        Args:
            object_name: Name of the object
            bucket: Bucket name

        Returns:
            bool: True if file exists, False otherwise
        """
        try:
            self.client.stat_object(bucket_name=bucket, object_name=object_name)
            return True
        except S3Error:
            return False


# Create a singleton instance
storage = MinioStorage()
