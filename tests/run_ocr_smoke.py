"""
Plain-Python mirror of tests/test_ocr.py's assertions, for environments
without pytest installed. This is NOT a replacement for running
`pytest tests/test_ocr.py -v` on your Mac — it exists because the
sandbox that wrote this code has `tesseract` + `pytesseract` but not
`pytest`, and running this file (`python3 tests/run_ocr_smoke.py` from
the project root) is how those assertions were actually executed and
verified before this milestone was reported as done.
"""

from __future__ import annotations

import sys
import traceback

from PIL import Image, ImageDraw, ImageFont

from src.ocr.tesseract import OcrError, OcrResult, is_tesseract_available, run_ocr


def _text_image(lines, size=(700, 260)):
    image = Image.new("RGB", size, color=(255, 255, 255))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.load_default(size=28)
    except TypeError:  # older Pillow without the size= parameter
        font = ImageFont.load_default()
    y = 20
    for line in lines:
        draw.text((20, y), line, fill=(0, 0, 0), font=font)
        y += 50
    return image


def test_module_imports_and_reports_availability():
    assert isinstance(is_tesseract_available(), bool)
    assert is_tesseract_available() is True, "expected tesseract to be available in this sandbox"


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
    image = _text_image(["one two three four five", "six seven eight nine ten"])
    result = run_ocr(image)
    assert len(result.blocks) <= 2
    assert result.word_count >= 8


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


def test_run_ocr_raises_on_none_image():
    try:
        run_ocr(None)
    except OcrError:
        pass
    else:
        raise AssertionError("expected OcrError for None image")


def main() -> int:
    tests = [
        test_module_imports_and_reports_availability,
        test_run_ocr_returns_expected_structure,
        test_run_ocr_groups_by_line_not_just_words,
        test_run_ocr_accepts_grayscale_image,
        test_run_ocr_on_blank_image_succeeds_with_no_text,
        test_run_ocr_raises_on_none_image,
    ]
    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
        except Exception:
            failed += 1
            print(f"FAIL: {test.__name__}")
            traceback.print_exc()
        else:
            passed += 1
            print(f"PASS: {test.__name__}")
    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
