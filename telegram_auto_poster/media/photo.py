import os
import tempfile
from random import randint

import piexif
from loguru import logger
from PIL import Image
from PIL.ImageFile import ImageFile

from telegram_auto_poster.config import BUCKET_MAIN, PHOTOS_PATH
from telegram_auto_poster.utils.general import MinioError
from telegram_auto_poster.utils.storage import storage


async def add_watermark_to_image(
    input_path: str,
    output_filename: str,
    user_metadata: dict | None = None,
    media_hash: str | None = None,
    group_id: str | None = None,
):
    """Add watermark to an image and save it with EXIF data.

    Args:
        input_path: Path to the local file
        output_filename: Name for the output file in MinIO
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

        exif_dict = {}
        exif_dict["0th"] = {}
        exif_dict["0th"][piexif.ImageIFD.Artist] = "t.me/ooodnakov_memes"
        exif_dict["0th"][piexif.ImageIFD.ImageDescription] = "t.me/ooodnakov_memes"
        exif_dict["0th"][piexif.ImageIFD.Copyright] = "t.me/ooodnakov_memes"

        # Convert the modified EXIF data to bytes
        exif_bytes = piexif.dump(exif_dict)
        base.save(output_path, exif=exif_bytes)

        # Upload the processed file to MinIO, preserving submission metadata
        output_object = os.path.basename(output_filename)
        # Prefer provided metadata; fallback to looking up by temp input name
        meta = user_metadata
        if not meta:
            original_name = os.path.basename(input_path)
            meta = await storage.get_submission_metadata(original_name)
        uploaded = await storage.upload_file(
            output_path,
            BUCKET_MAIN,
            PHOTOS_PATH + "/" + output_object,
            user_id=meta.get("user_id") if meta else None,
            chat_id=meta.get("chat_id") if meta else None,
            message_id=meta.get("message_id") if meta else None,
            media_hash=media_hash,
            group_id=group_id,
        )
        if not uploaded:
            raise MinioError(
                f"Failed to upload processed image to MinIO: {output_object}"
            )
        logger.debug(
            f"Uploaded processed image to MinIO: {BUCKET_MAIN}/{PHOTOS_PATH}/{output_object}"
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
