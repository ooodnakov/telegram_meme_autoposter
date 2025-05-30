import os
from random import randint
import piexif
from PIL import Image
from PIL.ImageFile import ImageFile


async def add_watermark_to_image(input_filename: str, output_filename: str):
    """Add watermark to an image and save it with EXIF data."""
    base: ImageFile = Image.open(input_filename)
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
    base.save(output_filename, exif=exif_bytes)
    os.remove(input_filename)
