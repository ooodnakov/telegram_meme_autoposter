import os
import tempfile
from random import randint
import piexif
from PIL import Image
from PIL.ImageFile import ImageFile
from loguru import logger

from ..utils.storage import storage, PHOTOS_BUCKET, DOWNLOADS_BUCKET


async def add_watermark_to_image(input_filename: str, output_filename: str):
    """Add watermark to an image and save it with EXIF data.

    Args:
        input_filename: Path to the local file or object name in MinIO
        output_filename: Name for the output file in MinIO
    """
    # Create temporary files for processing
    temp_input = None
    temp_output = None

    try:
        # Check if input file is already in MinIO
        if not os.path.exists(input_filename):
            # Download from MinIO
            temp_input = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
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
        temp_output = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
        temp_output.close()
        output_path = temp_output.name

        # Process the image
        base: ImageFile = Image.open(input_path)
        overlay = Image.open("wm.jpg").resize(
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

        # Upload the processed file to MinIO
        output_object = os.path.basename(output_filename)
        storage.upload_file(output_path, PHOTOS_BUCKET, output_object)

        # Delete original file from MinIO if it exists
        if not os.path.exists(input_filename):
            storage.delete_file(os.path.basename(input_filename), DOWNLOADS_BUCKET)
        else:
            # Remove local file if it's not a temp file
            if os.path.exists(input_filename):
                os.remove(input_filename)

        logger.info(
            f"Processed image and saved to MinIO: {PHOTOS_BUCKET}/{output_object}"
        )

    finally:
        # Clean up temporary files
        if temp_input and os.path.exists(temp_input.name):
            os.unlink(temp_input.name)

        if temp_output and os.path.exists(temp_output.name):
            os.unlink(temp_output.name)
