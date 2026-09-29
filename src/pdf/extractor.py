"""
Stage 1 extraction: PDF pages and single images -> PageExtraction.

Milestone 2 adds OCR into this same flow (see src/ocr/tesseract.py):
- PDF page: if the embedded text is missing or clearly insufficient
  (see config.MIN_SUFFICIENT_EMBEDDED_TEXT_CHARS), OCR also runs on the
  rendered page image. The embedded text (if any) is never overwritten
  or discarded — `text` stays whatever PyMuPDF found, and OCR's output
  lives separately under `ocr`.
- Image upload (PNG/JPG/JPEG/WEBP): always OCR'd directly, since there
  is never an embedded text layer to fall back on.

Dependency note (see requirements.txt): this module imports `pymupdf`
(the modern package name for what used to be `import fitz`). It is NOT
installed in the environment this code was authored in, so this module
has been written carefully and read over for correctness, but it has
NOT been executed end-to-end against a real PDF. Run the tests in
tests/test_pdf_extractor.py on your Mac (after `pip install -r
requirements.txt`) before trusting it on a real book. (The OCR side,
src/ocr/tesseract.py, WAS actually run and tested in this environment —
see README.)

Everything here operates on in-memory bytes. Nothing is written to disk
and nothing is persisted — see src/config.py and the README's
"No Database / No Persistent Storage" section.
"""

from __future__ import annotations

import base64
import io
import os

import pymupdf
from PIL import Image

from src.config import MIN_SUFFICIENT_EMBEDDED_TEXT_CHARS, OCR_LANGUAGE
from src.ocr.tesseract import OcrError, run_ocr
from src.pdf.models import BoundingBox, PageExtraction, TextBlock
from src.pdf.renderer import render_page_to_image


class ExtractionError(ValueError):
    """Raised for problems with the uploaded file itself (bad PDF, bad
    page number, unreadable image) so the API layer can turn these into
    clean 4xx responses instead of 500s."""


def _image_to_base64_png(image: Image.Image) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def extract_pdf_page(
    pdf_bytes: bytes,
    filename: str,
    page_number: int,
) -> PageExtraction:
    """
    Extract embedded text, text blocks (with bounding boxes), and a
    rendered page image for one 1-indexed page of a PDF.

    Raises ExtractionError if the PDF can't be opened or the page
    number is out of range.
    """
    try:
        document = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:  # pymupdf raises its own exception types
        raise ExtractionError(f"Could not open '{filename}' as a PDF: {exc}") from exc

    try:
        page_count = document.page_count
        if page_count == 0:
            raise ExtractionError(f"'{filename}' has no pages.")
        if not (1 <= page_number <= page_count):
            raise ExtractionError(
                f"Page {page_number} is out of range for '{filename}' "
                f"(it has {page_count} page(s))."
            )

        page = document.load_page(page_number - 1)  # pymupdf is 0-indexed
        rect = page.rect

        # Embedded text, in reading order as PyMuPDF determines it.
        full_text = page.get_text("text")

        # Text blocks with bounding boxes. get_text("blocks") returns
        # tuples: (x0, y0, x1, y1, text, block_no, block_type).
        raw_blocks = page.get_text("blocks")
        blocks: list[TextBlock] = []
        for raw in raw_blocks:
            x0, y0, x1, y1, block_text, block_no = raw[0], raw[1], raw[2], raw[3], raw[4], raw[5]
            block_text = block_text.strip()
            if not block_text:
                continue  # skip empty layout blocks (images, whitespace)
            blocks.append(
                TextBlock(
                    text=block_text,
                    bbox=BoundingBox(x0=x0, y0=y0, x1=x1, y1=y1),
                    block_index=int(block_no),
                )
            )

        # Rendered page image, for the UI and for later diagram/OCR stages.
        rendered_image = render_page_to_image(page)

        warnings: list[str] = []
        has_embedded_text = len(full_text.strip()) > 0
        if not has_embedded_text:
            warnings.append(
                "No embedded text found on this page. It may be a scanned "
                "page — running OCR on the rendered image instead."
            )

        # Milestone 2: OCR runs alongside embedded text extraction when
        # that text is missing or too short to be useful on its own
        # (e.g. a scanned page whose only real PDF text is a running
        # header/page number). Embedded text, if any, is kept as-is in
        # `text` either way — OCR output lives separately in `ocr`.
        ocr_used = False
        ocr_result = None
        if len(full_text.strip()) < MIN_SUFFICIENT_EMBEDDED_TEXT_CHARS:
            try:
                ocr_result = run_ocr(rendered_image, language=OCR_LANGUAGE)
                ocr_used = True
            except OcrError as exc:
                warnings.append(f"OCR was attempted but failed: {exc}")

        return PageExtraction(
            filename=filename,
            source_kind="pdf",
            page_number=page_number,
            page_count=page_count,
            width=rect.width,
            height=rect.height,
            text=full_text,
            blocks=blocks,
            has_embedded_text=has_embedded_text,
            image_base64_png=_image_to_base64_png(rendered_image),
            warnings=warnings,
            ocr_used=ocr_used,
            ocr=ocr_result,
        )
    finally:
        document.close()


def extract_image_page(image_bytes: bytes, filename: str) -> PageExtraction:
    """
    Handle a single uploaded PNG/JPG/JPEG/WEBP as a one-page "document".

    There is no embedded text layer in a raw image, so `text` is always
    empty and `has_embedded_text` is always False. Milestone 2: OCR
    always runs directly on the image (there's nothing to fall back on
    if it fails, unlike a PDF page which at least might have embedded
    text) — a failure is recorded as a warning rather than raised, so
    the caller still gets the page image and metadata back.
    """
    try:
        image = Image.open(io.BytesIO(image_bytes))
        image.load()  # force decode now, so bad files fail here, not later
    except Exception as exc:
        raise ExtractionError(f"Could not open '{filename}' as an image: {exc}") from exc

    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")

    warnings = [
        "Uploaded as a raw image: there is no embedded text layer. "
        "OCR ran directly on the image instead."
    ]

    ocr_used = False
    ocr_result = None
    try:
        ocr_result = run_ocr(image, language=OCR_LANGUAGE)
        ocr_used = True
    except OcrError as exc:
        warnings.append(f"OCR was attempted but failed: {exc}")

    return PageExtraction(
        filename=filename,
        source_kind="image",
        page_number=1,
        page_count=1,
        width=float(image.width),
        height=float(image.height),
        text="",
        blocks=[],
        has_embedded_text=False,
        image_base64_png=_image_to_base64_png(image),
        warnings=warnings,
        ocr_used=ocr_used,
        ocr=ocr_result,
    )


def get_pdf_page_count(pdf_bytes: bytes, filename: str) -> int:
    """Open a PDF just long enough to report how many pages it has."""
    try:
        document = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        raise ExtractionError(f"Could not open '{filename}' as a PDF: {exc}") from exc
    try:
        return document.page_count
    finally:
        document.close()


def guess_source_kind(filename: str) -> str:
    """Return 'pdf' or 'image' based on the file extension, or raise."""
    from src.config import ALLOWED_IMAGE_EXTENSIONS, ALLOWED_PDF_EXTENSIONS

    ext = os.path.splitext(filename)[1].lower()
    if ext in ALLOWED_PDF_EXTENSIONS:
        return "pdf"
    if ext in ALLOWED_IMAGE_EXTENSIONS:
        return "image"
    raise ExtractionError(
        f"Unsupported file type '{ext}'. Allowed: "
        f"{sorted(ALLOWED_PDF_EXTENSIONS | ALLOWED_IMAGE_EXTENSIONS)}"
    )
