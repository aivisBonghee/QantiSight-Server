import json
import glob
import logging
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image

logger = logging.getLogger(__name__)

MODEL_TMP_DIR = "/model_tmp"
GRID_WIDTH = 256
MIN_DENSITY_THRESHOLD = 0.02


def _jet_color(v: float) -> Tuple[int, int, int]:
    if v < 0.25:
        r, g, b = 0, int(255 * v * 4), 255
    elif v < 0.5:
        r, g, b = 0, 255, int(255 * (1 - (v - 0.25) * 4))
    elif v < 0.75:
        r, g, b = int(255 * (v - 0.5) * 4), 255, 0
    else:
        r, g, b = 255, int(255 * (1 - (v - 0.75) * 4)), 0
    return (r, g, b)


def generate_heatmap_from_json(json_path: str, output_path: str) -> bool:
    with open(json_path) as f:
        data = json.load(f)

    images = data.get("images")
    if not images:
        logger.warning(f"No 'images' key in {json_path}")
        return False

    img_info = images[0]
    slide_w = img_info.get("width", 0)
    slide_h = img_info.get("height", 0)
    if slide_w <= 0 or slide_h <= 0:
        logger.warning(f"Invalid slide dimensions in {json_path}: {slide_w}x{slide_h}")
        return False

    annotations = data.get("annotations", [])
    if not annotations:
        return False

    aspect = slide_h / slide_w
    grid_w = GRID_WIDTH
    grid_h = max(1, int(grid_w * aspect))
    bin_w = slide_w / grid_w
    bin_h = slide_h / grid_h

    tumor_anns = [a for a in annotations if "bbox" in a and not a.get("was_nonT", True)]
    if not tumor_anns:
        logger.info(f"No tumor cells found in {json_path}")
        return False

    density = [[0] * grid_w for _ in range(grid_h)]

    for ann in tumor_anns:
        x, y, w, h = ann["bbox"]
        cx, cy = x + w / 2, y + h / 2
        gx = min(int(cx / bin_w), grid_w - 1)
        gy = min(int(cy / bin_h), grid_h - 1)
        density[gy][gx] += 1

    max_val = max(max(row) for row in density)
    if max_val == 0:
        return False

    img = Image.new("RGBA", (grid_w, grid_h), (0, 0, 0, 0))
    pixels = img.load()

    for gy in range(grid_h):
        for gx in range(grid_w):
            v = density[gy][gx] / max_val
            if v < MIN_DENSITY_THRESHOLD:
                continue
            r, g, b = _jet_color(v)
            alpha = int(160 * min(v * 2.5, 1.0))
            pixels[gx, gy] = (r, g, b, alpha)

    thumb_w = 512
    thumb_h = max(1, int(thumb_w * aspect))
    resample = getattr(Image, "Resampling", Image).BILINEAR
    img = img.resize((thumb_w, thumb_h), resample)
    img.save(output_path, "PNG")
    return True


def _compute_cell_ratio(json_path: str) -> Optional[float]:
    try:
        with open(json_path) as f:
            data = json.load(f)
        annotations = data.get("annotations", [])
        if not annotations:
            return None
        total = len([a for a in annotations if "bbox" in a])
        tumor = len([a for a in annotations if "bbox" in a and not a.get("was_nonT", True)])
        if total == 0:
            return None
        return round(tumor / total, 4)
    except Exception as e:
        logger.warning(f"Cell ratio computation failed: {e}")
        return None


def find_and_generate_heatmap(filename: str, case_id: str, uploads_dir: str) -> dict:
    result = {"heatmap": None, "cell_ratio": None}
    pattern = f"{MODEL_TMP_DIR}/lesion_*/{filename}*.json"
    matches = glob.glob(pattern)

    if not matches:
        logger.debug(f"No detection JSON found for {filename}")
        return result

    json_path = matches[0]
    result["cell_ratio"] = _compute_cell_ratio(json_path)

    heatmap_filename = f"heatmap_{case_id}.png"
    output_path = str(Path(uploads_dir) / heatmap_filename)

    try:
        if generate_heatmap_from_json(json_path, output_path):
            logger.info(f"Heatmap generated: {heatmap_filename}")
            result["heatmap"] = heatmap_filename
    except Exception as e:
        logger.error(f"Heatmap generation failed for {case_id}: {e}")

    return result
