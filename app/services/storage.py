import os
import logging

from fastapi import UploadFile
from PIL import Image

logger = logging.getLogger(__name__)

CHUNK_SIZE = 100 * 1024 * 1024  # 100MB

WSI_EXTENSIONS = {".svs", ".ndpi", ".mrxs", ".scn", ".bif", ".vsi", ".tiff", ".tif"}


async def save_image(file: UploadFile, upload_dir: str, filename: str) -> str:
    path = os.path.join(upload_dir, filename)
    with open(path, "wb") as f:
        while True:
            chunk = await file.read(CHUNK_SIZE)
            if not chunk:
                break
            f.write(chunk)
    return path


def generate_thumbnail(image_path: str, thumb_dir: str, filename: str, size: tuple = (512, 512)) -> str:
    thumb_path = os.path.join(thumb_dir, filename)
    ext = os.path.splitext(image_path)[1].lower()

    if ext in WSI_EXTENSIONS:
        try:
            return _openslide_thumbnail(image_path, thumb_path, size)
        except Exception as e:
            logger.warning(f"OpenSlide thumbnail failed: {e}")
            return ""

    try:
        with Image.open(image_path) as img:
            img.thumbnail(size, Image.LANCZOS)
            img.save(thumb_path, "PNG", quality=85)
        return thumb_path
    except Exception as e:
        logger.warning(f"PIL thumbnail failed: {e}")
        return ""


def _openslide_thumbnail(image_path: str, thumb_path: str, size: tuple) -> str:
    import openslide
    slide = openslide.OpenSlide(image_path)
    thumb = slide.get_thumbnail(size)
    thumb.save(thumb_path, "PNG", quality=85)
    slide.close()
    logger.info(f"OpenSlide thumbnail created: {thumb_path}")
    return thumb_path
