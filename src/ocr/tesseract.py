"""
Local OCR via Tesseract (through pytesseract), for pages/images with no
usable embedded text layer.

Mac dependency (system binary, not a pip package):

    brew install tesseract

This module was authored in a sandbox that, unlike the one Stage 1 was
built in, DOES have `tesseract` and `pytesseract` available — so unlike
Stage 1's extractor.py, the functions here have actually been executed
against real generated test images (see tests/test_ocr.py and the "what
was tested" note in README.md). It has NOT been run against a real
scanned chess-book page, only synthetic text images, so treat book-page
accuracy as unverified until you try it on one.

No models are downloaded at runtime — Tesseract's trained-data files
are installed once, locally, by `brew install tesseract` (or by
installing an additional `tesseract-lang` language file), and this
module only ever calls the local binary through pytesseract.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from PIL import Image

try:
    import pytesseract
except ImportError:  # pragma: no cover - exercised only if pytesseract itself is missing
    pytesseract = None  # type: ignore[assignment]


class OcrError(RuntimeError):
    """
    Raised when Tesseract itself could not be run at all — the binary is
    missing/not on PATH, pytesseract isn't installed, or the engine
    raised an unexpected error.

    This is deliberately NOT raised when OCR runs successfully but finds
    no text (a blank or purely graphical page) — that's a normal result
    (OcrResult with empty text/blocks), not a failure.
    """


@dataclass
class OcrBlock:
    """
    One OCR'd line of text (line-level grouping — see module docstring
    and README for why line-level was chosen over word-level or a
    single whole-page block).
    """

    text: str
    bbox: list[float]  # [x0, y0, x1, y1], pixel coords of the image OCR ran on
    confidence: float | None  # mean of this line's word confidences, 0-100; None if unavailable
    line_index: int

    def to_dict(self) -> dict:
        return {
            "line_index": self.line_index,
            "text": self.text,
            "bbox": self.bbox,
            "confidence": self.confidence,
        }


@dataclass
class OcrResult:
    """Everything Milestone 2 knows after running OCR on one page image."""

    text: str
    blocks: list[OcrBlock] = field(default_factory=list)
    mean_confidence: float | None = None
    word_count: int = 0
    line_count: int = 0
    engine: str = "tesseract"
    language: str = "eng"
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "blocks": [b.to_dict() for b in self.blocks],
            "mean_confidence": self.mean_confidence,
            "word_count": self.word_count,
            "line_count": self.line_count,
            "engine": self.engine,
            "language": self.language,
            "warnings": self.warnings,
        }


def is_tesseract_available() -> bool:
    """
    Best-effort check for whether OCR can actually run in this
    environment. Useful for a startup/health check; not required
    before calling run_ocr (which raises a clear OcrError anyway).
    """
    if pytesseract is None:
        return False
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def run_ocr(image: Image.Image, language: str = "eng") -> OcrResult:
    """
    Run local Tesseract OCR on a Pillow image and return line-grouped
    text with bounding boxes and per-line confidence.

    Groups Tesseract's word-level output by (block_num, par_num,
    line_num) into lines, because individual word boxes are far noisier
    to read/debug in a UI than one box per line of text, and a whole
    "block" from Tesseract can span unrelated paragraphs on a book page.
    Line-level is the middle ground the project spec asked for.

    Raises OcrError if Tesseract can't be run at all (see class
    docstring). Never raises just because no text was found.
    """
    if pytesseract is None:
        raise OcrError(
            "pytesseract is not installed. Run `pip install -r requirements.txt` "
            "in your virtualenv."
        )

    if image is None:
        raise OcrError("run_ocr was given no image.")

    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")

    try:
        data = pytesseract.image_to_data(
            image, lang=language, output_type=pytesseract.Output.DICT
        )
    except Exception as exc:
        # pytesseract raises TesseractNotFoundError (a subclass of
        # EnvironmentError) when the `tesseract` binary itself is
        # missing; everything else is some other engine failure. Both
        # are "OCR could not run", so both become OcrError here — the
        # caller (extractor.py) decides whether that's fatal for the
        # whole request or just a warning.
        raise OcrError(f"Tesseract OCR failed to run: {exc}") from exc

    lines: dict[tuple[int, int, int], dict] = {}
    entry_count = len(data.get("text", []))

    for i in range(entry_count):
        word_text = (data["text"][i] or "").strip()
        if not word_text:
            continue

        try:
            confidence = float(data["conf"][i])
        except (TypeError, ValueError):
            confidence = -1.0

        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        x, y = data["left"][i], data["top"][i]
        w, h = data["width"][i], data["height"][i]

        line = lines.setdefault(
            key,
            {"words": [], "x0": x, "y0": y, "x1": x + w, "y1": y + h, "confidences": []},
        )
        line["words"].append(word_text)
        line["x0"] = min(line["x0"], x)
        line["y0"] = min(line["y0"], y)
        line["x1"] = max(line["x1"], x + w)
        line["y1"] = max(line["y1"], y + h)
        if confidence >= 0:
            line["confidences"].append(confidence)

    blocks: list[OcrBlock] = []
    all_line_confidences: list[float] = []
    word_count = 0

    # Sorting by (block_num, par_num, line_num) reproduces Tesseract's
    # own reading order for the common single-column case. It is NOT
    # guaranteed correct for multi-column layouts — see README's
    # "Known OCR limitations".
    for index, key in enumerate(sorted(lines.keys())):
        line = lines[key]
        line_text = " ".join(line["words"])
        word_count += len(line["words"])
        mean_conf = (
            sum(line["confidences"]) / len(line["confidences"])
            if line["confidences"]
            else None
        )
        if mean_conf is not None:
            all_line_confidences.append(mean_conf)

        blocks.append(
            OcrBlock(
                text=line_text,
                bbox=[float(line["x0"]), float(line["y0"]), float(line["x1"]), float(line["y1"])],
                confidence=mean_conf,
                line_index=index,
            )
        )

    full_text = "\n".join(block.text for block in blocks)
    mean_confidence = (
        sum(all_line_confidences) / len(all_line_confidences)
        if all_line_confidences
        else None
    )

    warnings: list[str] = []
    if not blocks:
        warnings.append("OCR ran successfully but found no recognizable text on this page.")

    return OcrResult(
        text=full_text,
        blocks=blocks,
        mean_confidence=mean_confidence,
        word_count=word_count,
        line_count=len(blocks),
        engine="tesseract",
        language=language,
        warnings=warnings,
    )
