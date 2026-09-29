"""
Tests for src/api.py.

WRITTEN but NOT RUN here (fastapi/httpx are not installed in this
authoring environment — no network access to pip install them). Run on
your Mac with:

    pytest tests/test_api.py -v
"""

from __future__ import annotations

import io

import pymupdf
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from src.api import app

client = TestClient(app)


def _make_test_pdf(page_texts: list[str]) -> bytes:
    document = pymupdf.open()
    for text in page_texts:
        page = document.new_page(width=595, height=842)
        page.insert_text((72, 72), text, fontsize=14)
    pdf_bytes = document.tobytes()
    document.close()
    return pdf_bytes


def _make_blank_pdf(num_pages: int = 1) -> bytes:
    document = pymupdf.open()
    for _ in range(num_pages):
        document.new_page(width=595, height=842)
    pdf_bytes = document.tobytes()
    document.close()
    return pdf_bytes


def _make_test_image_bytes() -> bytes:
    image = Image.new("RGB", (150, 80), color=(10, 20, 30))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "/parse" in body["implemented_endpoints"]


def test_parse_pdf_page():
    # Long enough to clearly clear MIN_SUFFICIENT_EMBEDDED_TEXT_CHARS (20
    # chars) so this test actually exercises the "skip OCR" path rather
    # than accidentally tripping the "text too short, run OCR too" path.
    pdf_bytes = _make_test_pdf(
        [
            "Chapter 1: An opening chapter with enough real text on it.",
            "Chapter 2: A second chapter with plenty of embedded PDF text.",
        ]
    )
    response = client.post(
        "/parse",
        files={"file": ("book.pdf", pdf_bytes, "application/pdf")},
        data={"page_number": "2"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["page_number"] == 2
    assert body["page_count"] == 2
    assert "Chapter 2" in body["text"]
    assert body["image_base64_png"]
    # Real embedded text on the page is long enough to skip OCR (see
    # config.MIN_SUFFICIENT_EMBEDDED_TEXT_CHARS).
    assert body["has_embedded_text"] is True
    assert body["ocr_used"] is False
    assert body["ocr"] is None
    # Milestone 3: /parse now classifies structure on this one page (no
    # cross-page context — that's what /parse/pages is for).
    assert isinstance(body["structure_elements"], list)
    assert len(body["structure_elements"]) >= 1
    assert body["structure_elements"][0]["element_type"] == "heading"


def test_parse_defaults_to_page_1():
    pdf_bytes = _make_test_pdf(["Only page here"])
    response = client.post(
        "/parse",
        files={"file": ("book.pdf", pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 200
    assert response.json()["page_number"] == 1


def test_parse_page_out_of_range_returns_400():
    pdf_bytes = _make_test_pdf(["Only page here"])
    response = client.post(
        "/parse",
        files={"file": ("book.pdf", pdf_bytes, "application/pdf")},
        data={"page_number": "99"},
    )
    assert response.status_code == 400


def test_parse_image_upload():
    image_bytes = _make_test_image_bytes()
    response = client.post(
        "/parse",
        files={"file": ("diagram.png", image_bytes, "image/png")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["source_kind"] == "image"
    assert body["page_count"] == 1
    # Image uploads never have embedded text and always attempt OCR.
    assert body["has_embedded_text"] is False
    assert body["ocr_used"] is True
    assert body["ocr"] is not None
    assert "text" in body["ocr"] and "blocks" in body["ocr"]


def test_parse_pdf_page_with_no_embedded_text_runs_ocr():
    """
    Milestone 2, item 10 requirement: "API response when embedded text
    is absent." A blank PDF page has no embedded text at all, so OCR
    should run on the rendered page image and populate `ocr`, while
    `has_embedded_text` stays False and `text` stays empty.
    """
    pdf_bytes = _make_blank_pdf(1)
    response = client.post(
        "/parse",
        files={"file": ("scanned.pdf", pdf_bytes, "application/pdf")},
        data={"page_number": "1"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["has_embedded_text"] is False
    assert body["text"] == ""
    assert body["ocr_used"] is True
    assert body["ocr"] is not None
    assert body["ocr"]["engine"] == "tesseract"
    # A blank page's OCR text should be empty, not raise an error.
    assert body["ocr"]["text"] == ""


def test_parse_rejects_unsupported_extension():
    response = client.post(
        "/parse",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 400


def test_parse_rejects_empty_file():
    response = client.post(
        "/parse",
        files={"file": ("book.pdf", b"", "application/pdf")},
    )
    assert response.status_code == 400


def test_pdf_page_count_endpoint():
    pdf_bytes = _make_test_pdf(["a", "b", "c"])
    response = client.post(
        "/pdf/page-count",
        files={"file": ("book.pdf", pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 200
    assert response.json()["page_count"] == 3


# ---------------------------------------------------------------------------
# /parse/pages — Milestone 3: cross-page continuity
# ---------------------------------------------------------------------------

def test_parse_pages_detects_game_spanning_two_pages():
    pdf_bytes = _make_test_pdf(
        [
            "Chapter 3: The Italian Game",
            "1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 4. c3 Nf6 5. d3 d6",
            "6. O-O O-O 7. Re1 a6 1-0",
        ]
    )
    response = client.post(
        "/parse/pages",
        files={"file": ("book.pdf", pdf_bytes, "application/pdf")},
        data={"start_page": "2", "end_page": "3"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["start_page"] == 2
    assert body["end_page"] == 3
    assert len(body["pages"]) == 2
    for page in body["pages"]:
        assert isinstance(page["structure_elements"], list)

    moves_sections = [s for s in body["sections"] if s["family"] == "moves"]
    assert len(moves_sections) == 1
    assert moves_sections[0]["spans_pages"] is True
    assert moves_sections[0]["page_start"] == 2
    assert moves_sections[0]["page_end"] == 3
    assert moves_sections[0]["continuation_points"][0]["confidence"] == "confirmed"


def test_parse_pages_rejects_image_upload():
    image_bytes = _make_test_image_bytes()
    response = client.post(
        "/parse/pages",
        files={"file": ("diagram.png", image_bytes, "image/png")},
        data={"start_page": "1", "end_page": "1"},
    )
    assert response.status_code == 400


def test_parse_pages_rejects_range_over_the_cap():
    from src.config import MAX_PAGE_RANGE
    pdf_bytes = _make_test_pdf([f"Page {i}" * 5 for i in range(1, 8)])
    response = client.post(
        "/parse/pages",
        files={"file": ("book.pdf", pdf_bytes, "application/pdf")},
        data={"start_page": "1", "end_page": str(MAX_PAGE_RANGE + 5)},
    )
    assert response.status_code == 400


def test_parse_pages_rejects_invalid_range():
    pdf_bytes = _make_test_pdf(["one", "two"])
    response = client.post(
        "/parse/pages",
        files={"file": ("book.pdf", pdf_bytes, "application/pdf")},
        data={"start_page": "2", "end_page": "1"},  # end before start
    )
    assert response.status_code == 400
