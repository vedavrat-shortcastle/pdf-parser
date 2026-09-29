"""
Tests for src/ocr/tesseract.py.

Unlike Stage 1's PDF tests, these WERE actually exercised in the
environment that wrote them — `tesseract` and `pytesseract` are both
available there, just not `pytest` itself. See
tests/run_ocr_smoke.py, a plain-Python script with the same assertions
as this file, run directly with `python3` as a substitute for pytest in
that environment. Run this actual file with pytest on your Mac:

    pytest tests/test_ocr.py -v
"""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont
import pytest

from src.ocr.tesseract import OcrError, OcrResult, is_tesseract_available, run_ocr


def _text_image(lines: list[str], size=(700, 260)) -> Image.Image:
    image = Image.new("RGB", size, color=(255, 255, 255))
    draw = ImageDraw.Draw(image)
    # A larger font than PIL's tiny built-in default noticeably improves
    # Tesseract's accuracy on synthetic test images. load_default(size=...)
    # (Pillow >= 10.1) is used instead of a system font path so this test
    # doesn't depend on which fonts happen to be installed on a given
    # machine.
    try:
        font = ImageFont.load_default(size=28)
    except TypeError:  # older Pillow without the size= parameter
        font = ImageFont.load_default()
    y = 20
    for line in lines:
        draw.text((20, y), line, fill=(0, 0, 0), font=font)
        y += 50
    return image


# ---------------------------------------------------------------------------
# OCR module import
# ---------------------------------------------------------------------------

def test_module_imports_and_reports_availability():
    # Actually exercised: True in the authoring sandbox (tesseract 5.3.4
    # installed). On your Mac this should also be True once
    # `brew install tesseract` has been run.
    assert isinstance(is_tesseract_available(), bool)


# ---------------------------------------------------------------------------
# OCR output structure
# ---------------------------------------------------------------------------

def test_run_ocr_returns_expected_structure():
    image = _text_image(["Chapter 1: The Pin", "White to play and win"])
    result = run_ocr(image)

    assert isinstance(result, OcrResult)
    assert isinstance(result.text, str)
    assert isinstance(result.blocks, list)
    assert result.engine == "tesseract"
    assert result.language == "eng"
    assert result.word_count >= 1
    assert result.line_count == len(result.blocks)

    for block in result.blocks:
        assert isinstance(block.text, str) and block.text
        assert isinstance(block.bbox, list) and len(block.bbox) == 4
        x0, y0, x1, y1 = block.bbox
        assert x1 > x0 and y1 > y0
        assert block.confidence is None or 0 <= block.confidence <= 100

    d = result.to_dict()
    for key in ("text", "blocks", "mean_confidence", "word_count", "line_count", "engine", "language", "warnings"):
        assert key in d


def test_run_ocr_groups_by_line_not_just_words():
    # Two distinct lines of text should produce (at most) two blocks,
    # not one block per word.
    image = _text_image(["one two three four five", "six seven eight nine ten"])
    result = run_ocr(image)
    assert len(result.blocks) <= 2
    assert result.word_count >= 8  # allow some OCR misses on the default bitmap font


# ---------------------------------------------------------------------------
# Image input
# ---------------------------------------------------------------------------

def test_run_ocr_accepts_grayscale_image():
    image = Image.new("L", (200, 100), color=255)
    result = run_ocr(image)
    assert isinstance(result, OcrResult)


def test_run_ocr_on_blank_image_succeeds_with_no_text():
    blank = Image.new("RGB", (300, 150), color=(255, 255, 255))
    result = run_ocr(blank)
    assert result.text == ""
    assert result.blocks == []
    assert any("no recognizable text" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# Empty / invalid input
# ---------------------------------------------------------------------------

def test_run_ocr_raises_on_none_image():
    with pytest.raises(OcrError):
        run_ocr(None)
