import asyncio
import json
import os
import random
import tempfile
from pathlib import Path

from loguru import logger

from telegram_auto_poster.config import (
    BUCKET_MAIN,
    VIDEOS_PATH,
    WATERMARK_MAX_SPEED,
    WATERMARK_MIN_SPEED,
)
from telegram_auto_poster.utils.general import MinioError
from telegram_auto_poster.utils.storage import storage


async def _probe_video_size(path: str) -> tuple[int, int]:
    """Returns (width, height) of the first video stream."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "json",
        path,
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    out, _ = await proc.communicate()
    info = json.loads(out)
    w = info["streams"][0]["width"]
    h = info["streams"][0]["height"]
    return w, h


async def add_watermark_to_video(
    input_path: str,
    output_filename: str,
    user_metadata: dict | None = None,
    media_hash: str | None = None,
    group_id: str | None = None,
) -> str:
    """Add watermark to a video with bouncing animation.

    Args:
        input_path: Path to the local file
        output_filename: Name for the output file in MinIO

    Returns:
        output_filename: Name of the processed video in MinIO
    """
    # Create temporary file for the output
    temp_output = None

    try:
        # Create temporary output file
        temp_output = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
        temp_output.close()
        output_path = temp_output.name

        watermark_path = str(Path("wm.png").expanduser())

        # 1. Get video dimensions
        v_w, v_h = await _probe_video_size(input_path)

        # 2. Calculate final watermark width
        wm_w = int(min(v_w, v_h) * random.randint(15, 25) / 100)

        # Define diagonal bouncing movement for watermark. Use independent speeds for
        # the horizontal and vertical directions to mimic the CSS animation where the
        # durations differ, producing a less predictable path.
        speed_x = random.randint(WATERMARK_MIN_SPEED, WATERMARK_MAX_SPEED)
        speed_y = random.randint(WATERMARK_MIN_SPEED, WATERMARK_MAX_SPEED)
        filter_complex = (
            f"[1]scale={wm_w}:{wm_w}[wm];"
            f"[0][wm]overlay=x='if(gt(mod(t*{speed_x},2*({v_w}-{wm_w})),({v_w}-{wm_w})), "
            f"2*({v_w}-{wm_w})-mod(t*{speed_x},2*({v_w}-{wm_w})), mod(t*{speed_x},2*({v_w}-{wm_w})))':"
            f"y='if(gt(mod(t*{speed_y},2*({v_h}-{wm_w})),({v_h}-{wm_w})), "
            f"2*({v_h}-{wm_w})-mod(t*{speed_y},2*({v_h}-{wm_w})), mod(t*{speed_y},2*({v_h}-{wm_w})))'"
        )

        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            input_path,
            "-i",
            watermark_path,
            "-metadata",
            "title=t.me/ooodnakov_memes",
            "-metadata",
            "comment=t.me/ooodnakov_memes",
            "-metadata",
            "copyright=t.me/ooodnakov_memes",
            "-metadata",
            "description=t.me/ooodnakov_memes",
            "-filter_complex",
            filter_complex,
            "-c:v",
            "libx264",
            "-preset",
            "slow",
            "-crf",
            "18",
            "-c:a",
            "copy",
            output_path,
        ]

        logger.info(f"Running ffmppeg command on video {input_path}")
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        _, err = await proc.communicate()

        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg error:\n{err.decode()}")

        # Upload the processed file to MinIO, preserving submission metadata
        output_object = os.path.basename(output_filename)
        meta = user_metadata
        if not meta:
            original_name = os.path.basename(input_path)
            meta = await storage.get_submission_metadata(original_name)
        uploaded = await storage.upload_file(
            output_path,
            BUCKET_MAIN,
            VIDEOS_PATH + "/" + output_object,
            user_id=meta.get("user_id") if meta else None,
            chat_id=meta.get("chat_id") if meta else None,
            message_id=meta.get("message_id") if meta else None,
            media_hash=media_hash,
            group_id=group_id,
        )
        if not uploaded:
            raise MinioError(
                f"Failed to upload processed video to MinIO: {output_object}"
            )
        logger.debug(
            f"Uploaded processed video to MinIO: {BUCKET_MAIN}/{VIDEOS_PATH}/{output_object}"
        )

        # The original local file is a temporary file and will be cleaned up
        # by the calling function (handle_photo or handle_video)

        logger.info(
            f"Processed video and saved to MinIO: {BUCKET_MAIN}/{VIDEOS_PATH}/{output_object}"
        )
        return output_filename

    finally:
        # Clean up temporary output file
        if temp_output and os.path.exists(temp_output.name):
            os.unlink(temp_output.name)
