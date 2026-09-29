"""
Stage 1 intermediate representation.

These are plain dataclasses (not a database ORM — there is no database in
this project). They describe exactly what M1 extracts from one page:
embedded text, text blocks with bounding boxes, and a rendered image of
the page, plus enough metadata to know where it came from.

Later stages (OCR, structure detection, diagram recognition, FEN
extraction, ...) will add new modules and new models under src/ocr,
src/structure, src/diagrams, src/chess, etc. They should not need to
change this file — TextBlock / PageExtraction are meant to be a stable
foundation that later layers build on top of, not replace.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from src.ocr.tesseract import OcrResult

SourceKind = Literal["pdf", "image"]


@dataclass
class BoundingBox:
    """A rectangle in PDF/page coordinate space: (x0, y0, x1, y1)."""

    x0: float
    y0: float
    x1: float
    y1: float

    def as_list(self) -> list[float]:
        return [self.x0, self.y0, self.x1, self.y1]


@dataclass
class TextBlock:
    """One block of text as reported by the PDF's layout, with its bbox."""

    text: str
    bbox: BoundingBox
    block_index: int

    def to_dict(self) -> dict:
        return {
            "block_index": self.block_index,
            "text": self.text,
            "bbox": self.bbox.as_list(),
        }


@dataclass
class PageExtraction:
    """
    Everything Stage 1 knows about a single page after extraction.

    `has_embedded_text` distinguishes a digital PDF page (text came
    straight out of the PDF) from a scanned page or an uploaded image,
    where `text` is empty and OCR (a later stage) will be required.
    This flag exists so later stages never need to guess why text is
    empty — it's recorded explicitly here instead of inferred.
    """

    filename: str
    source_kind: SourceKind
    page_number: int  # 1-indexed
    page_count: int  # total pages in the source (1 for a bare image)
    width: float
    height: float
    text: str
    blocks: list[TextBlock] = field(default_factory=list)
    has_embedded_text: bool = False
    image_base64_png: str = ""
    warnings: list[str] = field(default_factory=list)
    # Milestone 2 (OCR). `ocr_used` is explicit rather than inferred from
    # `ocr is not None`, so the API/UI can distinguish "OCR wasn't
    # needed" from "OCR was attempted and failed" (see extractor.py).
    ocr_used: bool = False
    ocr: OcrResult | None = None

    def to_dict(self) -> dict:
        return {
            "filename": self.filename,
            "source_kind": self.source_kind,
            "page_number": self.page_number,
            "page_count": self.page_count,
            "width": self.width,
            "height": self.height,
            "text": self.text,
            "blocks": [b.to_dict() for b in self.blocks],
            "has_embedded_text": self.has_embedded_text,
            "image_base64_png": self.image_base64_png,
            "warnings": self.warnings,
            "ocr_used": self.ocr_used,
            "ocr": self.ocr.to_dict() if self.ocr is not None else None,
            # Fields reserved for future stages. Present (and empty) now so
            # the frontend and API consumers can code against a stable
            # shape without a breaking change later.
            "structure_elements": None,
            "diagrams": None,
        }
