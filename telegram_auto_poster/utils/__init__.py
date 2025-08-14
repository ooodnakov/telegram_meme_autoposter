import asyncio
import os
import tempfile
from typing import Any, Optional, Tuple

from loguru import logger
from telegram.error import BadRequest, NetworkError, TimedOut

# Import stats and storage modules but expose their singletons under distinct
# names so the submodules remain importable as
# ``telegram_auto_poster.utils.stats`` and ``telegram_auto_poster.utils.storage``.
import telegram_auto_poster.utils.stats as stats_module
import telegram_auto_poster.utils.storage as storage_module
from telegram_auto_poster.config import PHOTOS_PATH, VIDEOS_PATH

stats_client = stats_module.stats
storage_client = storage_module.storage


class MinioError(Exception):
    """Raised when a MinIO storage operation fails."""

    pass


class MediaError(Exception):
    """Raised when processing an uploaded piece of media fails."""

    pass


class TelegramMediaError(Exception):
    """Raised when sending media to Telegram results in an error."""

    pass


def extract_filename(text: str) -> Optional[str]:
    """Pull a file name from an arbitrary text message.

    The bot often receives captions that contain the original file name on the
    last line.  This helper tries to extract such a name by scanning the text
    from bottom to top.

    Args:
        text: Message text that potentially contains a filename (usually in the
            format ``"Some text\nfilename.ext"``).

    Returns:
        Extracted filename or ``None`` if no filename could be determined.
    """
    if not text:
        return None

    # Try to get the last line, which should contain the path
    lines = text.strip().split("\n")
    if not lines:
        return None

    # Look for lines containing file paths
    photo_prefix = f"{PHOTOS_PATH}/"
    video_prefix = f"{VIDEOS_PATH}/"
    for line in reversed(lines):
        if any(
            path_prefix in line
            for path_prefix in [photo_prefix, video_prefix, "downloaded_"]
        ):
            return line.strip()

    # Fall back to the last line if no path was found
    return lines[-1].strip()


def cleanup_temp_file(file_path: str | None) -> None:
    """Safely remove a temporary file if it exists.

    Args:
        file_path: Path to the temporary file.
    """
    if file_path and os.path.exists(file_path):
        try:
            os.unlink(file_path)
        except Exception as e:
            logger.error(f"Error deleting temp file {file_path}: {e}")


async def download_from_minio(
    object_name, bucket, extension=None
) -> Tuple[Optional[str], Optional[str]]:
    """Fetch an object from MinIO into a temporary file on disk.

    Args:
        object_name: The name of the object in MinIO.
        bucket: The MinIO bucket to download from.
        extension: Optional file extension to use for the temporary file.

    Returns:
        Tuple of ``(temp_file_path, mime_type)`` or ``(None, None)`` if the
        download fails.
    """
    if not object_name or not bucket:
        logger.error(f"Invalid parameters: object_name={object_name}, bucket={bucket}")
        return None, None

    try:
        if not storage_client.file_exists(object_name, bucket):
            logger.warning(f"File {object_name} does not exist in bucket {bucket}")
            raise MinioError(f"File not found: {object_name} in {bucket}")

        # If extension not provided, get from filename
        if not extension:
            extension = get_file_extension(object_name)

        # Create temp file with correct extension
        try:
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=extension)
            temp_path = temp_file.name
            temp_file.close()
        except (IOError, OSError) as e:
            logger.error(f"Failed to create temporary file: {e}")
            stats_client.record_error(
                "processing", f"Failed to create temporary file: {str(e)}"
            )
            raise MinioError(f"Failed to create temporary file: {str(e)}")

        try:
            # Download file from MinIO to temp file
            storage_client.download_file(object_name, bucket, temp_path)
            logger.debug(
                f"Successfully downloaded {object_name} from {bucket} to {temp_path}"
            )

            # Determine mime type based on extension
            mime_type = None
            if extension.lower() in [".jpg", ".jpeg"]:
                mime_type = "image/jpeg"
            elif extension.lower() == ".png":
                mime_type = "image/png"
            elif extension.lower() == ".mp4":
                mime_type = "video/mp4"

            return temp_path, mime_type
        except Exception as e:
            logger.error(f"Error downloading file from MinIO: {e}")
            cleanup_temp_file(temp_path)
            stats_client.record_error("storage", f"Failed to download file: {str(e)}")
            raise MinioError(f"Failed to download file: {str(e)}")
    except MinioError:
        # Re-raise MinioError to be caught by caller
        raise
    except Exception as e:
        logger.error(f"Unexpected error in download_from_minio: {e}")
        stats_client.record_error("storage", f"Unexpected error: {str(e)}")
        raise MinioError(f"Unexpected error: {str(e)}")


# Helper function to get file extension
def get_file_extension(filename: str) -> str:
    """Return the extension of ``filename`` or ``.unknown`` if absent.

    Args:
        filename: File name to inspect.

    Returns:
        str: Extension including the leading dot.
    """
    _, ext = os.path.splitext(filename)
    return ext if ext else ".unknown"


# Helper function to send media to Telegram
async def send_media_to_telegram(
    bot, chat_id, file_path, caption=None, supports_streaming=True
) -> Any:
    """Send media to Telegram based on file extension.

    Args:
        bot: The Telegram bot instance.
        chat_id: Chat ID to send the media to.
        file_path: Path to the media file.
        caption: Optional caption for the media.
        supports_streaming: Whether video streaming is supported.

    Returns:
        telegram.Message | None: Message sent on success, otherwise ``None``.

    Raises:
        TelegramMediaError: If there's an issue sending media to Telegram.
        FileNotFoundError: If the file does not exist.
    """

    # Define error constants
    ERROR_TELEGRAM_SEND_FAILED = "Failed to send media to Telegram"
    ERROR_FILE_NOT_SUPPORTED = "File type not supported"

    if not os.path.exists(file_path):
        logger.error(f"File {file_path} does not exist")
        stats_client.record_error("telegram", f"File {file_path} does not exist")
        raise FileNotFoundError(f"File {file_path} does not exist")

    try:
        ext = get_file_extension(file_path).lower()

        # Max retries for sending media
        max_retries = 3
        retry_count = 0
        last_error = None

        while retry_count < max_retries:
            try:
                if ext in [".jpg", ".jpeg", ".png"]:
                    with open(file_path, "rb") as media_file:
                        return await bot.send_photo(
                            chat_id=chat_id,
                            photo=media_file,
                            caption=caption,
                            read_timeout=60,
                            write_timeout=60,
                        )
                elif ext in [".mp4", ".avi", ".mov"]:
                    with open(file_path, "rb") as media_file:
                        return await bot.send_video(
                            chat_id=chat_id,
                            video=media_file,
                            caption=caption,
                            supports_streaming=supports_streaming,
                            read_timeout=60,
                            write_timeout=60,
                        )
                elif ext in [".gif"]:
                    with open(file_path, "rb") as media_file:
                        return await bot.send_animation(
                            chat_id=chat_id,
                            animation=media_file,
                            caption=caption,
                            read_timeout=60,
                            write_timeout=60,
                        )
                else:
                    logger.warning(f"Unsupported file type {ext}, sending as document")
                    stats_client.record_error(
                        "processing", f"{ERROR_FILE_NOT_SUPPORTED}: {ext}"
                    )
                    with open(file_path, "rb") as media_file:
                        return await bot.send_document(
                            chat_id=chat_id,
                            document=media_file,
                            caption=caption,
                            read_timeout=60,
                            write_timeout=60,
                        )
            except (TimedOut, NetworkError) as e:
                # These errors are retryable
                retry_count += 1
                last_error = e
                wait_time = 2**retry_count  # Exponential backoff
                logger.warning(
                    f"Network error, retrying in {wait_time}s (attempt {retry_count}/{max_retries}): {e}"
                )
                stats_client.record_error(
                    "telegram", f"Network error (retrying): {str(e)}"
                )
                await asyncio.sleep(wait_time)
            except BadRequest as e:
                # Bad request errors are usually not retryable
                logger.error(f"Bad request error when sending media: {e}")
                stats_client.record_error(
                    "telegram", f"{ERROR_TELEGRAM_SEND_FAILED} (bad request): {str(e)}"
                )
                raise TelegramMediaError(
                    f"{ERROR_TELEGRAM_SEND_FAILED} (bad request): {str(e)}"
                )
            except Exception as e:
                logger.error(f"Unexpected error in send_media_to_telegram: {e}")
                stats_client.record_error("telegram", f"Unexpected error: {str(e)}")
                raise TelegramMediaError(f"Unexpected error: {str(e)}")

        # If we've exhausted retries
        if last_error:
            logger.error(f"Failed to send media after {max_retries} retries")
            stats_client.record_error(
                "telegram",
                f"{ERROR_TELEGRAM_SEND_FAILED} after {max_retries} retries: {str(last_error)}",
            )
            raise TelegramMediaError(
                f"{ERROR_TELEGRAM_SEND_FAILED} after {max_retries} retries: {str(last_error)}"
            )

    except (FileNotFoundError, TelegramMediaError):
        # Re-raise these specific exceptions
        raise
    except Exception as e:
        logger.error(f"Unexpected error in send_media_to_telegram: {e}")
        stats_client.record_error("telegram", f"Unexpected error: {str(e)}")
        raise TelegramMediaError(f"Unexpected error: {str(e)}")
