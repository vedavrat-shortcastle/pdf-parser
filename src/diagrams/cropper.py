"""
In-memory diagram cropping and serialization helpers.

Clamps bounding boxes to image dimensions and provides base64 PNG formatting
for API responses and UI debug inspection. Does not persist images to disk.
"""

from __future__ import annotations

import base64
import io

from PIL import Image


def crop_diagram(image: Image.Image, bbox: list[float]) -> Image.Image:
    """
    Crop diagram region from page image, with boundary clamping.

    Args:
        image: Source PIL Image.
        bbox: [x0, y0, x1, y1] coordinates.

    Returns:
        Cropped PIL Image in memory.
    """
    w, h = image.size
    x0 = max(0, min(w - 1, int(round(bbox[0]))))
    y0 = max(0, min(h - 1, int(round(bbox[1]))))
    x1 = max(x0 + 1, min(w, int(round(bbox[2]))))
    y1 = max(y0 + 1, min(h, int(round(bbox[3]))))

    return image.crop((x0, y0, x1, y1))


def image_to_base64_png(image: Image.Image) -> str:
    """Encode PIL Image to a base64 PNG data URI string."""
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    b64_data = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64_data}"
