"""
Rendering a PDF page to a raster image.

Split out from extractor.py so that later stages (e.g. diagram
recognition, which will want to crop specific regions of the rendered
page at a possibly different DPI) have one obvious place to reuse this
instead of duplicating pixmap logic.
"""

from __future__ import annotations

import io

import pymupdf
from PIL import Image

from src.config import PAGE_RENDER_DPI


def render_page_to_image(page: "pymupdf.Page", dpi: int = PAGE_RENDER_DPI) -> Image.Image:
    """Render one PyMuPDF page to a Pillow Image at the given DPI.

    Goes through PNG bytes rather than Image.frombytes on the raw
    pixmap samples, since that stays correct regardless of the
    pixmap's colorspace/alpha channel count.
    """
    zoom = dpi / 72.0  # PDF units are 1/72 inch
    matrix = pymupdf.Matrix(zoom, zoom)
    pixmap = page.get_pixmap(matrix=matrix)
    return Image.open(io.BytesIO(pixmap.tobytes("png")))
