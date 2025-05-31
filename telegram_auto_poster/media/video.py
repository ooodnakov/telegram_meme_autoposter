import asyncio
import json
import os
import random
import tempfile
from pathlib import Path
from loguru import logger

from ..utils.storage import storage, VIDEOS_BUCKET, DOWNLOADS_BUCKET


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


async def add_watermark_to_video(input_filename: str, output_filename: str) -> str:
    """Add watermark to a video with bouncing animation.

    Args:
        input_filename: Path to the local file or object name in MinIO
        output_filename: Name for the output file in MinIO

    Returns:
        output_filename: Name of the processed video in MinIO
    """
    # Create temporary files for processing
    temp_input = None
    temp_output = None

    try:
        # Check if input file is already in MinIO
        if not os.path.exists(input_filename):
            # Download from MinIO
            temp_input = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
            temp_input.close()
            storage.download_file(
                object_name=os.path.basename(input_filename),
                bucket=DOWNLOADS_BUCKET,
                file_path=temp_input.name,
            )
            input_path = temp_input.name
        else:
            # Use local file
            input_path = input_filename

        # Create temporary output file
        temp_output = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
        temp_output.close()
        output_path = temp_output.name

        watermark_path = str(Path("wm.png").expanduser())

        # 1. Get video dimensions
        v_w, v_h = await _probe_video_size(input_path)

        # 2. Calculate final watermark width
        wm_w = int(min(v_w, v_h) * random.randint(15, 25) / 100)

        # Define diagonal bouncing movement for watermark
        speed = 100
        filter_complex = (
            f"[1]scale={wm_w}:{wm_w}[wm];"
            f"[0][wm]overlay=x='if(gt(mod(t*{speed},2*({v_w}-{wm_w})),({v_w}-{wm_w})), "
            f"2*({v_w}-{wm_w})-mod(t*{speed},2*({v_w}-{wm_w})), mod(t*{speed},2*({v_w}-{wm_w})))':"
            f"y='if(gt(mod(t*{speed},2*({v_h}-{wm_w})),({v_h}-{wm_w})), "
            f"2*({v_h}-{wm_w})-mod(t*{speed},2*({v_h}-{wm_w})), mod(t*{speed},2*({v_h}-{wm_w})))'"
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

        logger.info("Running ffmppeg cmd: {}", " ".join(cmd))
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        _, err = await proc.communicate()

        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg error:\n{err.decode()}")

        # Upload the processed file to MinIO
        output_object = os.path.basename(output_filename)
        storage.upload_file(output_path, VIDEOS_BUCKET, output_object)

        # Delete original file from MinIO if it exists
        if not os.path.exists(input_filename):
            storage.delete_file(os.path.basename(input_filename), DOWNLOADS_BUCKET)
        else:
            # Remove local file if it's not a temp file
            if os.path.exists(input_filename):
                os.remove(input_filename)

        logger.info(
            f"Processed video and saved to MinIO: {VIDEOS_BUCKET}/{output_object}"
        )
        return output_filename

    finally:
        # Clean up temporary files
        if temp_input and os.path.exists(temp_input.name):
            os.unlink(temp_input.name)

        if temp_output and os.path.exists(temp_output.name):
            os.unlink(temp_output.name)
