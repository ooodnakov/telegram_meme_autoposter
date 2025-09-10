"""Image processing helpers for watermarking and uploading photos."""

import os
import tempfile
from random import randint

import piexif
from loguru import logger
from PIL import Image
from PIL.ImageFile import ImageFile

from telegram_auto_poster.config import BUCKET_MAIN, PHOTOS_PATH
from telegram_auto_poster.media import upload_processed_media


async def add_watermark_to_image(
    input_path: str,
    output_filename: str,
    user_metadata: dict | None = None,
    media_hash: str | None = None,
    group_id: str | None = None,
) -> None:
    """Add a semi-transparent watermark to an image and upload it.

    Args:
        input_path: Path to the local file.
        output_filename: Name for the output file in MinIO.
        user_metadata: Optional submission metadata to attach to the upload.
        media_hash: Optional hash used for deduplication.
        group_id: Optional album identifier for media groups.

    Returns:
        None

    """
    # Create temporary file for the output
    temp_output = None

    try:
        # Create temporary output file
        temp_output = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
        temp_output.close()
        output_path = temp_output.name

        # Process the image
        base: ImageFile = Image.open(input_path)
        overlay = Image.open("wm.png").resize(
            [int(base.size[0] * 0.1)] * 2, Image.Resampling.NEAREST
        )
        overlay.putalpha(40)

        position = (
            randint(0, base.width - overlay.width),
            randint(0, base.height - overlay.height),
        )

        base.paste(overlay, position, overlay)

        exif_dict: dict[str, dict[int, str]] = {}
        exif_dict["0th"] = {}
        exif_dict["0th"][piexif.ImageIFD.Artist] = "t.me/ooodnakov_memes"
        exif_dict["0th"][piexif.ImageIFD.ImageDescription] = "t.me/ooodnakov_memes"
        exif_dict["0th"][piexif.ImageIFD.Copyright] = "t.me/ooodnakov_memes"

        # Convert the modified EXIF data to bytes
        exif_bytes = piexif.dump(exif_dict)
        base.save(output_path, exif=exif_bytes)

        output_object = os.path.basename(output_filename)
        await upload_processed_media(
            output_path,
            bucket=BUCKET_MAIN,
            object_name=f"{PHOTOS_PATH}/{output_object}",
            user_metadata=user_metadata,
            original_name=input_path,
            media_hash=media_hash,
            group_id=group_id,
            media_label="image",
        )

        # The original local file is a temporary file and will be cleaned up
        # by the calling function (handle_photo or handle_video)

        logger.info(
            f"Processed image and saved to MinIO: {BUCKET_MAIN}/{PHOTOS_PATH}/{output_object}"
        )

    finally:
        # Clean up temporary output file
        if temp_output and os.path.exists(temp_output.name):
            os.unlink(temp_output.name)
