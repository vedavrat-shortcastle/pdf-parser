"""
Tests for src/pdf/extractor.py.

These were WRITTEN but NOT RUN in the environment that authored them —
pymupdf is not installed there (no network access to pip install it).
Run them on your Mac after `pip install -r requirements.txt`:

    pytest tests/test_pdf_extractor.py -v

Rather than shipping a binary PDF fixture, these tests build a small
PDF in-memory with PyMuPDF itself (`pymupdf.open()` with no stream
creates a new empty document you can add pages/text to). That keeps
the repo free of binary test fixtures and makes the test fully
self-contained.
"""

from __future__ import annotations

import io

import pymupdf
import pytest
from PIL import Image

from src.pdf.extractor import (
    ExtractionError,
    extract_image_page,
    extract_pdf_page,
    get_pdf_page_count,
    guess_source_kind,
)


def _make_test_pdf(page_texts: list[str]) -> bytes:
    """Build a minimal in-memory PDF with one page per string in page_texts."""
    document = pymupdf.open()
    for text in page_texts:
        page = document.new_page(width=595, height=842)  # A4-ish, in points
        page.insert_text((72, 72), text, fontsize=14)
    pdf_bytes = document.tobytes()
    document.close()
    return pdf_bytes


def _make_blank_pdf(num_pages: int) -> bytes:
    document = pymupdf.open()
    for _ in range(num_pages):
        document.new_page(width=595, height=842)
    pdf_bytes = document.tobytes()
    document.close()
    return pdf_bytes


def _make_test_image_bytes(fmt: str = "PNG") -> bytes:
    image = Image.new("RGB", (200, 100), color=(255, 255, 255))
    buffer = io.BytesIO()
    image.save(buffer, format=fmt)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# 1. PDF opening
# ---------------------------------------------------------------------------

def test_opens_valid_pdf():
    pdf_bytes = _make_test_pdf(["Hello, chess book."])
    extraction = extract_pdf_page(pdf_bytes, "book.pdf", 1)
    assert extraction.filename == "book.pdf"
    assert extraction.source_kind == "pdf"


def test_rejects_garbage_bytes_as_pdf():
    with pytest.raises(ExtractionError):
        extract_pdf_page(b"this is not a pdf", "fake.pdf", 1)


# ---------------------------------------------------------------------------
# 2. Page range validation
# ---------------------------------------------------------------------------

def test_page_number_out_of_range_raises():
    pdf_bytes = _make_test_pdf(["Only page."])
    with pytest.raises(ExtractionError):
        extract_pdf_page(pdf_bytes, "book.pdf", 2)


def test_page_number_zero_raises():
    pdf_bytes = _make_test_pdf(["Only page."])
    with pytest.raises(ExtractionError):
        extract_pdf_page(pdf_bytes, "book.pdf", 0)


def test_get_pdf_page_count():
    pdf_bytes = _make_blank_pdf(5)
    assert get_pdf_page_count(pdf_bytes, "book.pdf") == 5


# ---------------------------------------------------------------------------
# 3. Embedded text extraction
# ---------------------------------------------------------------------------

def test_extracts_embedded_text():
    pdf_bytes = _make_test_pdf(["Chapter 1: The Pin"])
    extraction = extract_pdf_page(pdf_bytes, "book.pdf", 1)
    assert "Chapter 1" in extraction.text
    assert extraction.has_embedded_text is True


def test_correct_page_selected_among_several():
    pdf_bytes = _make_test_pdf(["Page one text", "Page two text", "Page three text"])
    extraction = extract_pdf_page(pdf_bytes, "book.pdf", 2)
    assert "Page two" in extraction.text
    assert "Page one" not in extraction.text
    assert extraction.page_number == 2
    assert extraction.page_count == 3


def test_blank_page_has_no_embedded_text_and_warns():
    pdf_bytes = _make_blank_pdf(1)
    extraction = extract_pdf_page(pdf_bytes, "book.pdf", 1)
    assert extraction.has_embedded_text is False
    assert any("OCR" in w for w in extraction.warnings)
    # Milestone 2: a blank/scanned page should trigger OCR automatically.
    assert extraction.ocr_used is True
    assert extraction.ocr is not None
    assert extraction.ocr.text == ""  # nothing to find on a blank page


def test_page_with_ample_embedded_text_skips_ocr():
    pdf_bytes = _make_test_pdf(["This page has plenty of real embedded PDF text on it."])
    extraction = extract_pdf_page(pdf_bytes, "book.pdf", 1)
    assert extraction.has_embedded_text is True
    assert extraction.ocr_used is False
    assert extraction.ocr is None


# ---------------------------------------------------------------------------
# 4. Image rendering
# ---------------------------------------------------------------------------

def test_rendered_image_is_present_and_decodable():
    pdf_bytes = _make_test_pdf(["Some text to render"])
    extraction = extract_pdf_page(pdf_bytes, "book.pdf", 1)
    assert extraction.image_base64_png  # non-empty
    import base64

    raw = base64.b64decode(extraction.image_base64_png)
    image = Image.open(io.BytesIO(raw))
    assert image.format == "PNG"
    assert image.width > 0 and image.height > 0


# ---------------------------------------------------------------------------
# 5. Text blocks / bounding boxes
# ---------------------------------------------------------------------------

def test_text_blocks_have_bounding_boxes():
    pdf_bytes = _make_test_pdf(["A block of text for bbox testing."])
    extraction = extract_pdf_page(pdf_bytes, "book.pdf", 1)
    assert len(extraction.blocks) >= 1
    block = extraction.blocks[0]
    bbox = block.bbox.as_list()
    assert len(bbox) == 4
    # x1 > x0 and y1 > y0 for a real (non-degenerate) box
    assert bbox[2] > bbox[0]
    assert bbox[3] > bbox[1]


# ---------------------------------------------------------------------------
# Image upload path (PNG/JPG/JPEG/WEBP)
# ---------------------------------------------------------------------------

def test_extract_image_page_png():
    image_bytes = _make_test_image_bytes("PNG")
    extraction = extract_image_page(image_bytes, "diagram.png")
    assert extraction.source_kind == "image"
    assert extraction.page_number == 1
    assert extraction.page_count == 1
    assert extraction.has_embedded_text is False
    assert extraction.image_base64_png
    # Milestone 2: image uploads always OCR directly.
    assert extraction.ocr_used is True
    assert extraction.ocr is not None


def test_extract_image_page_rejects_garbage():
    with pytest.raises(ExtractionError):
        extract_image_page(b"not an image", "fake.png")


# ---------------------------------------------------------------------------
# guess_source_kind
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "filename,expected",
    [
        ("book.pdf", "pdf"),
        ("BOOK.PDF", "pdf"),
        ("page.png", "image"),
        ("page.jpg", "image"),
        ("page.jpeg", "image"),
        ("page.webp", "image"),
    ],
)
def test_guess_source_kind(filename, expected):
    assert guess_source_kind(filename) == expected


def test_guess_source_kind_rejects_unknown_extension():
    with pytest.raises(ExtractionError):
        guess_source_kind("book.epub")
