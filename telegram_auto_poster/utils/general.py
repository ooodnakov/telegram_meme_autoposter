"""General helper utilities for media processing and Telegram interactions."""

import asyncio
import os
import random
import tempfile
from typing import Iterable, List, Optional, Tuple

from loguru import logger
from telegram import Bot, InputMediaPhoto, InputMediaVideo, Message
from telegram.error import BadRequest, NetworkError, TimedOut
from telegram_auto_poster.config import (
    BUCKET_MAIN,
    PHOTOS_PATH,
    SUGGESTION_CAPTION,
    TRASH_PATH,
    VIDEOS_PATH,
)
from telegram_auto_poster.utils.stats import stats
from telegram_auto_poster.utils.storage import storage


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
    r"""Pull a file name from an arbitrary text message.

    The bot often receives captions that contain the original file name on the
    last line.  This helper tries to extract such a name by scanning the text
    from bottom to top.

    Args:
        text: Message text that potentially contains a filename (usually in the
            format ``"Some text\nfilename.ext"``).

    Returns:
        Extracted filename or ``None`` if no filename could be determined.

    """
    if not text or not text.strip():
        return None

    # Try to get the last line, which should contain the path
    lines = text.strip().split("\n")

    # Look for lines containing file paths
    prefixes = [
        f"{PHOTOS_PATH}/",
        f"{VIDEOS_PATH}/",
        f"{TRASH_PATH}/{PHOTOS_PATH}/",
        f"{TRASH_PATH}/{VIDEOS_PATH}/",
    ]
    for line in reversed(lines):
        if any(path_prefix in line for path_prefix in prefixes):
            return line.strip()

    # Fall back to the last line if no path was found
    return lines[-1].strip()


def extract_file_paths(text: str) -> List[str]:
    """Extract all media paths from a message text.

    The message can contain multiple lines with MinIO-style paths like
    ``photos/processed_...`` or ``videos/processed_...``. This helper returns
    all such lines in order of appearance.

    Args:
        text: Message text that may contain multiple media paths.

    Returns:
        List[str]: All detected media paths.

    """
    if not text:
        return []

    lines = [line.strip() for line in text.strip().split("\n") if line.strip()]
    if not lines:
        return []

    prefixes = [
        f"{PHOTOS_PATH}/",
        f"{VIDEOS_PATH}/",
        f"{TRASH_PATH}/{PHOTOS_PATH}/",
        f"{TRASH_PATH}/{VIDEOS_PATH}/",
    ]
    results: List[str] = []
    for line in lines:
        if any(line.startswith(prefix) for prefix in prefixes):
            results.append(line)
    return results


def extract_paths_from_message(message: object) -> List[str]:
    """Extract media paths from a Telegram message.

    Looks at ``message.caption`` and ``message.text`` to gather all file paths
    using :func:`extract_file_paths`.  If no explicit paths are found, falls
    back to :func:`extract_filename` for backward compatibility.

    Args:
        message: Telegram message object or any object with ``caption`` and
            ``text`` attributes.

    Returns:
        A list of extracted file paths. The list may be empty if nothing could
        be determined.

    """
    if not message:
        return []

    message_text = getattr(message, "caption", None) or getattr(message, "text", None)
    if isinstance(message_text, str):
        paths = extract_file_paths(message_text)
        if paths:
            return paths

        single = extract_filename(message_text)
        return [single] if single else []
    return []


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


def backoff_delay(
    retry: int, base: float = 1.0, cap: float = 300.0, jitter: float = 0.1
) -> float:
    """Calculate an exponential backoff delay with optional jitter.

    Args:
        retry: Current retry count starting at 1.
        base: Base delay in seconds.
        cap: Maximum delay in seconds.
        jitter: Fractional jitter to apply to the calculated delay.

    Returns:
        float: Delay in seconds bounded by ``cap``.

    """
    delay = min(cap, base * 2 ** (retry - 1))
    if jitter:
        jitter_range = delay * jitter
        delay += random.uniform(-jitter_range, jitter_range)
    return delay


class RateLimiter:
    """Simple token bucket rate limiter."""

    def __init__(self, rate: float, capacity: int) -> None:
        """Initialise the limiter.

        Args:
            rate: Tokens added per second.
            capacity: Maximum number of tokens.

        """
        self.rate = rate
        self.capacity = capacity
        self.tokens: float = float(capacity)
        self.updated = asyncio.get_running_loop().time()
        self.lock = asyncio.Lock()

    async def acquire(self, *, drop: bool = False) -> bool:
        """Try to consume a token.

        Args:
            drop: If ``True`` and no tokens are available, immediately return
                ``False`` instead of waiting.

        Returns:
            ``True`` if a token was consumed, otherwise ``False``.

        """
        while True:
            async with self.lock:
                now = asyncio.get_running_loop().time()
                elapsed = now - self.updated
                self.updated = now
                self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
                if self.tokens >= 1:
                    self.tokens -= 1
                    return True
                if drop:
                    return False
                wait_time = (1 - self.tokens) / self.rate
            await asyncio.sleep(wait_time)


async def download_from_minio(
    object_name: str,
    bucket: str,
    extension: str | None = None,
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
        if not await storage.file_exists(object_name, bucket):
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
            await stats.record_error(
                "processing", f"Failed to create temporary file: {str(e)}"
            )
            raise MinioError(f"Failed to create temporary file: {str(e)}")

        try:
            # Download file from MinIO to temp file
            await storage.download_file(object_name, bucket, temp_path)
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
            await stats.record_error("storage", f"Failed to download file: {str(e)}")
            raise MinioError(f"Failed to download file: {str(e)}")
    except MinioError:
        # Re-raise MinioError to be caught by caller
        raise
    except Exception as e:
        logger.error(f"Unexpected error in download_from_minio: {e}")
        await stats.record_error("storage", f"Unexpected error: {str(e)}")
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
    if ext:
        return ext
    if filename.startswith(".") and filename.count(".") == 1:
        return filename
    return ".unknown"


# Helper function to send media to Telegram
async def send_media_to_telegram(
    bot: Bot,
    chat_ids: Iterable[int | str] | int | str,
    file_path: str,
    caption: str | None = None,
    supports_streaming: bool = True,
) -> Message | None:
    """Send media to one or more Telegram chats based on file extension.

    Args:
        bot: The Telegram bot instance.
        chat_ids: One or more chat IDs to send the media to.
        file_path: Path to the media file.
        caption: Optional caption for the media.
        supports_streaming: Whether video streaming is supported.

    Returns:
        The last ``telegram.Message`` sent on success, otherwise ``None``.

    Raises:
        TelegramMediaError: If there's an issue sending media to Telegram.
        FileNotFoundError: If the file does not exist.

    """
    # Define error constants
    ERROR_TELEGRAM_SEND_FAILED = "Failed to send media to Telegram"
    ERROR_FILE_NOT_SUPPORTED = "File type not supported"

    if not os.path.exists(file_path):
        logger.error(f"File {file_path} does not exist")
        await stats.record_error("telegram", f"File {file_path} does not exist")
        raise FileNotFoundError(f"File {file_path} does not exist")

    if isinstance(chat_ids, (int, str)):
        chat_ids = [chat_ids]

    last_message: Message | None = None

    try:
        ext = get_file_extension(file_path).lower()
        method_map = {
            ".jpg": ("send_photo", "photo"),
            ".jpeg": ("send_photo", "photo"),
            ".png": ("send_photo", "photo"),
            ".mp4": ("send_video", "video"),
            ".avi": ("send_video", "video"),
            ".mov": ("send_video", "video"),
            ".gif": ("send_animation", "animation"),
        }
        method_name, arg_name = method_map.get(ext, ("send_document", "document"))
        if method_name == "send_document":
            logger.warning(f"Unsupported file type {ext}, sending as document")
            await stats.record_error("processing", f"{ERROR_FILE_NOT_SUPPORTED}: {ext}")

        send_func = getattr(bot, method_name)

        for chat_id in chat_ids:
            max_retries = 3
            retry_count = 0
            last_error: Exception | None = None

            while retry_count < max_retries:
                try:
                    with open(file_path, "rb") as media_file:
                        kwargs = {
                            "chat_id": chat_id,
                            arg_name: media_file,
                            "caption": caption,
                            "read_timeout": 60,
                            "write_timeout": 60,
                        }
                        if method_name == "send_video":
                            kwargs["supports_streaming"] = supports_streaming
                        last_message = await send_func(**kwargs)
                    break
                except (TimedOut, NetworkError) as e:
                    retry_count += 1
                    last_error = e
                    wait_time = 2**retry_count
                    logger.warning(
                        f"Network error, retrying in {wait_time}s (attempt {retry_count}/{max_retries}): {e}"
                    )
                    await stats.record_error(
                        "telegram", f"Network error (retrying): {str(e)}"
                    )
                    await asyncio.sleep(wait_time)
                except BadRequest as e:
                    logger.error(f"Bad request error when sending media: {e}")
                    await stats.record_error(
                        "telegram",
                        f"{ERROR_TELEGRAM_SEND_FAILED} (bad request): {str(e)}",
                    )
                    raise TelegramMediaError(
                        f"{ERROR_TELEGRAM_SEND_FAILED} (bad request): {str(e)}"
                    )
                except Exception as e:
                    logger.error(f"Unexpected error in send_media_to_telegram: {e}")
                    await stats.record_error("telegram", f"Unexpected error: {str(e)}")
                    raise TelegramMediaError(f"Unexpected error: {str(e)}")

            if last_error and retry_count >= max_retries:
                logger.error(f"Failed to send media after {max_retries} retries")
                await stats.record_error(
                    "telegram",
                    f"{ERROR_TELEGRAM_SEND_FAILED} after {max_retries} retries: {str(last_error)}",
                )
                raise TelegramMediaError(
                    f"{ERROR_TELEGRAM_SEND_FAILED} after {max_retries} retries: {str(last_error)}"
                )

    except (FileNotFoundError, TelegramMediaError):
        raise
    except Exception as e:
        logger.error(f"Unexpected error in send_media_to_telegram: {e}")
        await stats.record_error("telegram", f"Unexpected error: {str(e)}")
        raise TelegramMediaError(f"Unexpected error: {str(e)}")

    return last_message


async def prepare_group_items(paths: List[str]) -> Tuple[List[dict], str]:
    """Prepare media items for grouped sending.

    Downloads each path from MinIO, ensuring files are not empty, and returns
    a tuple of ``(items, caption)`` where ``items`` contains metadata required
    for sending and ``caption`` is applied to the first element of the group if
    any item originates from user suggestions.
    """
    items: List[dict] = []
    caption = ""

    for path in paths:
        file_name = os.path.basename(path)
        media_type = "photo" if path.startswith(f"{PHOTOS_PATH}/") else "video"
        file_prefix = f"{PHOTOS_PATH}/" if media_type == "photo" else f"{VIDEOS_PATH}/"

        meta = await storage.get_submission_metadata(file_name)
        if meta and meta.get("user_id"):
            caption = SUGGESTION_CAPTION

        temp_path, _ = await download_from_minio(path, BUCKET_MAIN)
        if temp_path is None:
            continue

        # Ensure file is not empty; retry once if necessary
        try:
            size = os.path.getsize(temp_path)
        except OSError:
            size = 0
        if size == 0:
            logger.warning(f"Downloaded file appears empty, retrying: {path}")
            cleanup_temp_file(temp_path)
            temp_path, _ = await download_from_minio(path, BUCKET_MAIN)
            if temp_path is None:
                continue
            try:
                size = os.path.getsize(temp_path)
            except OSError:
                size = 0
            if size == 0:
                logger.error(f"Skipping empty file after retry: {path}")
                cleanup_temp_file(temp_path)
                continue

        fh = open(temp_path, "rb")
        items.append(
            {
                "file_name": file_name,
                "media_type": media_type,
                "file_prefix": file_prefix,
                "path": path,
                "temp_path": temp_path,
                "file_obj": fh,
                "meta": meta,
            }
        )

    return items, caption


async def _send_media_group_with_retry(
    bot: Bot, chat_id: int | str, media_group: list
) -> None:
    """Send a media group with retry logic for transient failures."""

    max_retries = 3
    last_error: Exception | None = None

    for retry_count in range(1, max_retries + 1):
        try:
            await bot.send_media_group(
                chat_id=chat_id,
                media=media_group,
                read_timeout=60,
                write_timeout=60,
            )
            return
        except (TimedOut, NetworkError) as exc:
            last_error = exc
            wait_time = 2**retry_count
            logger.warning(
                "Network error sending media group, retrying in {wait_time}s (attempt {retry}/{max_retries}): {error}",
                wait_time=wait_time,
                retry=retry_count,
                max_retries=max_retries,
                error=exc,
            )
            await stats.record_error(
                "telegram",
                f"Network error sending media group (retrying): {str(exc)}",
            )
            await asyncio.sleep(wait_time)
        except BadRequest as exc:
            logger.error(
                "Bad request error when sending media group: {error}", error=exc
            )
            await stats.record_error(
                "telegram", f"Failed to send media group (bad request): {str(exc)}"
            )
            raise TelegramMediaError(
                f"Failed to send media group (bad request): {str(exc)}"
            ) from exc
        except Exception as exc:  # noqa: BLE001 - we want to log unexpected errors
            logger.error("Unexpected error sending media group: {error}", error=exc)
            await stats.record_error(
                "telegram", f"Unexpected error sending media group: {str(exc)}"
            )
            raise TelegramMediaError(
                f"Unexpected error sending media group: {str(exc)}"
            ) from exc

    logger.error(
        "Failed to send media group after {max_retries} retries",
        max_retries=max_retries,
    )
    await stats.record_error(
        "telegram",
        f"Failed to send media group after {max_retries} retries: {str(last_error)}",
    )
    raise TelegramMediaError(
        f"Failed to send media group after {max_retries} retries: {str(last_error)}"
    )


async def send_group_media(
    bot: Bot, chat_ids: Iterable[int | str] | int | str, items: List[dict], caption: str
) -> None:
    """Send a list of prepared items to one or more chats as a group."""
    if isinstance(chat_ids, (int, str)):
        chat_ids = [chat_ids]

    if not items:
        return

    if len(items) == 1:
        item = items[0]
        await send_media_to_telegram(
            bot,
            chat_ids,
            item["temp_path"],
            caption=caption,
            supports_streaming=item.get("media_type") == "video",
        )
        return

    for chat_id in chat_ids:
        for i in range(0, len(items), 10):
            chunk = items[i : i + 10]
            media_group = []
            for idx, it in enumerate(chunk):
                is_first = i == 0 and idx == 0 and bool(caption)
                fh = it["file_obj"]
                fh.seek(0)
                if it["media_type"] == "video":
                    media = InputMediaVideo(
                        fh,
                        supports_streaming=True,
                        caption=caption if is_first else None,
                    )
                else:
                    media = InputMediaPhoto(
                        fh,
                        caption=caption if is_first else None,
                    )
                media_group.append(media)

            await _send_media_group_with_retry(bot, chat_id, media_group)
