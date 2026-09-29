"""
Tests for src/structure/detector.py and src/structure/models.py.

Unlike Stage 1's PDF tests, these need NO PyMuPDF at all — PageExtraction,
TextBlock, and BoundingBox are plain dataclasses that can be hand-built
directly, so this suite was actually exercised in the authoring
environment (see tests/run_structure_smoke.py, a plain-Python mirror
run because `pytest` itself isn't installed there — see README).

Run this file for real with pytest on your Mac:

    pytest tests/test_structure.py -v
"""

from __future__ import annotations

import pytest

from src.pdf.models import BoundingBox, PageExtraction, TextBlock
from src.structure.detector import classify_page, classify_text, detect_sections


def _block(text: str, index: int = 0) -> TextBlock:
    return TextBlock(text=text, bbox=BoundingBox(0, 0, 10, 10), block_index=index)


def _page(page_number: int, page_count: int, blocks: list[TextBlock]) -> PageExtraction:
    return PageExtraction(
        filename="book.pdf",
        source_kind="pdf",
        page_number=page_number,
        page_count=page_count,
        width=595,
        height=842,
        text="...",
        has_embedded_text=True,
        blocks=blocks,
    )


# ---------------------------------------------------------------------------
# classify_text
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "text,expected",
    [
        ("Chapter 1: The Pin", "heading"),
        ("1. e4 e5 2. Nf3 Nc6 3. Bb5 a6", "moves"),
        ("White to play and win.", "diagram_candidate_hint"),
        (
            "A pin occurs when a piece cannot move without exposing a more "
            "valuable piece behind it.",
            "explainer",
        ),
        ("37", "unclassified"),
        ("", "unclassified"),
    ],
)
def test_classify_text(text, expected):
    assert classify_text(text) == expected


# ---------------------------------------------------------------------------
# classify_page
# ---------------------------------------------------------------------------

def test_classify_page_embedded_text():
    page = _page(
        1,
        1,
        [
            _block("Chapter 3: The Italian Game", 0),
            _block("1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5", 1),
        ],
    )
    elements = classify_page(page)
    assert [e.element_type for e in elements] == ["heading", "moves"]
    assert all(e.source == "embedded" for e in elements)
    assert all(e.bbox == [0, 0, 10, 10] for e in elements)


def test_classify_page_falls_back_to_ocr():
    from src.ocr.tesseract import OcrBlock, OcrResult

    page = PageExtraction(
        filename="scan.pdf",
        source_kind="pdf",
        page_number=1,
        page_count=1,
        width=595,
        height=842,
        text="",
        has_embedded_text=False,
        ocr_used=True,
        ocr=OcrResult(
            text="Puzzle 12\nWhite to play and win",
            blocks=[
                OcrBlock(text="Puzzle 12", bbox=[10, 10, 80, 30], confidence=90.0, line_index=0),
                OcrBlock(
                    text="White to play and win",
                    bbox=[10, 35, 200, 55],
                    confidence=85.0,
                    line_index=1,
                ),
            ],
        ),
    )
    elements = classify_page(page)
    assert all(e.source == "ocr" for e in elements)
    assert elements[0].element_type == "heading"
    assert elements[1].element_type == "diagram_candidate_hint"


def test_classify_page_empty_when_no_text_at_all():
    page = _page(1, 1, [])
    assert classify_page(page) == []


# ---------------------------------------------------------------------------
# detect_sections — cross-page continuity
# ---------------------------------------------------------------------------

def test_unfinished_game_merges_across_page_break_with_confirmed_confidence():
    page1 = _page(
        1,
        2,
        [
            _block("Chapter 3: The Italian Game", 0),
            _block("1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 4. c3 Nf6", 1),
        ],
    )
    page2 = _page(
        2,
        2,
        [
            _block("5. d3 d6 6. O-O O-O 7. Re1 a6 1-0", 0),
            _block(
                "White wins a nice attacking game here, using the bishop pair well.",
                1,
            ),
        ],
    )
    elements_by_page = {1: classify_page(page1), 2: classify_page(page2)}
    sections = detect_sections(elements_by_page)

    moves_sections = [s for s in sections if s.family == "moves"]
    assert len(moves_sections) == 1
    section = moves_sections[0]
    assert section.page_start == 1
    assert section.page_end == 2
    assert section.spans_pages is True
    assert len(section.continuation_points) == 1
    assert section.continuation_points[0].confidence == "confirmed"


def test_finished_explainer_merging_gets_weaker_confidence():
    page1 = _page(
        1,
        3,
        [_block("The knight is a tricky piece that jumps over other pieces on the board.", 0)],
    )
    page2 = _page(
        2,
        3,
        [_block("Bishops move diagonally and are especially strong in open positions.", 0)],
    )
    elements_by_page = {1: classify_page(page1), 2: classify_page(page2)}
    sections = detect_sections(elements_by_page)

    assert len(sections) == 1
    assert sections[0].spans_pages is True
    assert sections[0].continuation_points[0].confidence == "same_type_adjacent"


def test_heading_breaks_section_continuity():
    page1 = _page(
        1,
        2,
        [_block("The knight is a tricky piece that jumps over other pieces on the board.", 0)],
    )
    page2 = _page(
        2,
        2,
        [
            _block("Chapter 4: Endgames", 0),
            _block("Endgame technique separates strong players from weak ones in practice.", 1),
        ],
    )
    elements_by_page = {1: classify_page(page1), 2: classify_page(page2)}
    sections = detect_sections(elements_by_page)

    explainer_sections = [s for s in sections if s.family == "explainer"]
    assert len(explainer_sections) == 2
    assert all(not s.spans_pages for s in explainer_sections)
    assert all(s.continuation_points == [] for s in explainer_sections)


def test_detect_sections_on_empty_input():
    assert detect_sections({}) == []
