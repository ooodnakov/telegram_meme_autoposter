import asyncio
import json
import os
import random
from pathlib import Path
from loguru import logger


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
    """Add watermark to a video with bouncing animation."""
    watermark_path = str(Path("wm.png").expanduser())

    # 1. Get video dimensions
    v_w, v_h = await _probe_video_size(input_filename)

    # 2. Calculate final watermark width
    wm_w = int(min(v_w, v_h) * random.randint(15, 25) / 100)

    # 3. Calculate random coordinates for top-left corner
    max_x = max(v_w - wm_w, 0)
    max_y = max(v_h - wm_w, 0)
    pos_x = random.randint(0, max_x)
    pos_y = random.randint(0, max_y)

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
        input_filename,
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
        output_filename,
    ]

    logger.info("Running ffmppeg cmd: {}", " ".join(cmd))
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    _, err = await proc.communicate()

    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg error:\n{err.decode()}")

    logger.info("Finished processing {}", output_filename)
    os.remove(input_filename)
    return output_filename
