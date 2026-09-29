"""
Data model for Milestone 3 structure detection.

An `element` is one classified chunk of text on a page (heading, a run
of chess moves, explanatory prose, ...). A `Section` groups consecutive
elements of the same kind across one or more pages — this is the
cross-page continuity piece: a game or an explanation that runs past a
page break becomes ONE Section with page_start < page_end, not two
unrelated per-page fragments.

This module has no dependency on PyMuPDF or FastAPI, only on plain
Python and src.pdf.models' TextBlock/PageExtraction shapes — so it can
(and was) tested directly with hand-built PageExtraction objects, no
PDF file required.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

# "unclassified" is deliberately a real, distinct outcome — a block that
# doesn't confidently match anything else is left unclassified rather
# than forced into the closest-looking category, per the project's
# unresolved-first philosophy (see README / original spec section 21,
# written for chess validation but applied here too).
ElementType = Literal["heading", "moves", "explainer", "diagram_candidate_hint", "unclassified"]
ElementSource = Literal["embedded", "ocr"]
SectionFamily = Literal["moves", "explainer"]
ContinuationConfidence = Literal["confirmed", "same_type_adjacent"]


@dataclass
class StructureElement:
    """One classified block of text on one page."""

    element_type: ElementType
    text: str
    page_number: int
    source: ElementSource  # "embedded" (PyMuPDF text) or "ocr" (Tesseract)
    index_on_page: int
    bbox: list[float] | None = None

    def to_dict(self) -> dict:
        return {
            "element_type": self.element_type,
            "text": self.text,
            "page_number": self.page_number,
            "source": self.source,
            "index_on_page": self.index_on_page,
            "bbox": self.bbox,
        }


@dataclass
class ContinuationPoint:
    """One page-boundary crossing inside a Section."""

    from_page: int
    to_page: int
    confidence: ContinuationConfidence

    def to_dict(self) -> dict:
        return {
            "from_page": self.from_page,
            "to_page": self.to_page,
            "confidence": self.confidence,
        }


@dataclass
class Section:
    """
    A run of consecutive same-family elements, possibly spanning
    multiple pages. `spans_pages=True` plus a non-empty
    `continuation_points` is the actual cross-page-continuity signal
    this milestone exists to produce.
    """

    family: SectionFamily
    page_start: int
    page_end: int
    element_count: int
    spans_pages: bool
    continuation_points: list[ContinuationPoint] = field(default_factory=list)
    preview_text: str = ""

    def to_dict(self) -> dict:
        return {
            "family": self.family,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "element_count": self.element_count,
            "spans_pages": self.spans_pages,
            "continuation_points": [c.to_dict() for c in self.continuation_points],
            "preview_text": self.preview_text,
        }
