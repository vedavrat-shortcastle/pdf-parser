"""
Milestone 3: classify page text into structural elements, and detect
when a run of elements (a game, an explanation) continues across a
page boundary rather than starting fresh.

Deliberately heuristic and deterministic — regex/word-shape rules, no
LLM call. The original spec allows an LLM for structure detection
(section 32) but doesn't require one, and this project has no API key
or network access wired up for that; a documented, inspectable
heuristic is the honest choice for this milestone. See README's
"Known limitations" for exactly where these heuristics will get things
wrong (mixed-language books, unusual notation, layouts with running
headers/footers that look like real headings, etc.) — replacing this
with an LLM-assisted classifier is a reasonable next step, not a
requirement.

Nothing here inspects pixels or PDF structure — it only classifies the
*text* already produced by src/pdf/extractor.py (embedded text or OCR
text, whichever the page actually has). Diagram *pixel* detection is
still entirely out of scope (src/diagrams/, not built yet); the
`diagram_candidate_hint` type here is only a textual cue ("White to
play and win") that a diagram likely exists nearby on the page — it is
not a bounding box or a recognized board.
"""

from __future__ import annotations

import re

from src.pdf.models import PageExtraction
from src.structure.models import ContinuationPoint, ElementType, Section, StructureElement

_HEADING_KEYWORD_RE = re.compile(
    r"^(chapter|section|part|puzzle|game|lesson|diagram)\s+\d+", re.IGNORECASE
)
_DIAGRAM_HINT_RE = re.compile(r"\b(white|black)\s+to\s+(play|move|win)\b", re.IGNORECASE)
_MOVE_NUMBER_RE = re.compile(r"\b\d+\.(\.\.)?")
_SAN_TOKEN_RE = re.compile(
    r"^(O-O-O|O-O|[KQRBN]?[a-h]?[1-8]?x?[a-h][1-8](=[QRBN])?[+#]?[!?]{0,2})$"
)
_GAME_RESULT_RE = re.compile(r"(1-0|0-1|1/2-1/2|½-½)\s*$")
_SENTENCE_END_RE = re.compile(r'[.!?]["\')\]]?\s*$')

# A block shorter than this (after stripping) is too little evidence to
# confidently call "explainer" prose — it's more likely a stray page
# number, a running header, or noise. It falls back to "unclassified"
# instead of being guessed at.
_MIN_EXPLAINER_CHARS = 15


def _looks_like_moves(text: str) -> bool:
    tokens = text.split()
    if not tokens:
        return False
    move_number_hits = len(_MOVE_NUMBER_RE.findall(text))
    san_hits = sum(
        1 for t in tokens if _SAN_TOKEN_RE.match(re.sub(r"^\d+\.+", "", t).strip(".,;"))
    )
    if move_number_hits >= 2 and san_hits >= 2:
        return True
    if len(tokens) >= 4 and san_hits / len(tokens) >= 0.4:
        return True
    # Recognize short move continuation lines (e.g. '10...Qxe4 0-1', '8.Nxe4 1-0', 'U 9.Nexc7+')
    if san_hits >= 1 and (move_number_hits >= 1 or _GAME_RESULT_RE.search(text)):
        valid_chess_tokens = 0
        for t in tokens:
            clean = re.sub(r"^\d+\.+", "", t).strip(".,;")
            if not clean:
                if _MOVE_NUMBER_RE.search(t):
                    valid_chess_tokens += 1
            elif _SAN_TOKEN_RE.match(clean) or _GAME_RESULT_RE.match(clean) or clean in ("U", "*"):
                valid_chess_tokens += 1
        if valid_chess_tokens == len(tokens):
            return True
    return False


def _looks_like_heading(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if _HEADING_KEYWORD_RE.match(stripped) and len(stripped) <= 120:
        return True
    words = stripped.split()
    if len(words) > 8 or len(stripped) > 60:
        return False
    letters = [c for c in stripped if c.isalpha()]
    if letters and sum(1 for c in letters if c.isupper()) / len(letters) > 0.8:
        return True
    capitalized = sum(1 for w in words if w[:1].isupper())
    if words and capitalized / len(words) >= 0.8:
        return True
    return False


def classify_text(text: str) -> ElementType:
    """Classify one block of text into a single structural element type."""
    stripped = text.strip()
    if not stripped:
        return "unclassified"
    # Order matters: moves before heading (a short move sequence like
    # "1.e4 e5" could otherwise look like a title-case-ish short line),
    # and heading before explainer/diagram-hint (a heading is the
    # strongest, most specific signal when it matches).
    if _looks_like_moves(stripped):
        return "moves"
    if _looks_like_heading(stripped):
        return "heading"
    if _DIAGRAM_HINT_RE.search(stripped):
        return "diagram_candidate_hint"
    if len(stripped) >= _MIN_EXPLAINER_CHARS:
        return "explainer"
    return "unclassified"


def classify_page(page: PageExtraction) -> list[StructureElement]:
    """
    Classify every text block on one already-extracted page.

    Uses embedded text blocks when the page has them; falls back to OCR
    line blocks otherwise. Never mixes the two for one page — matches
    the same "keep sources distinct" principle as PageExtraction itself.
    """
    elements: list[StructureElement] = []

    if page.has_embedded_text and page.blocks:
        for index, block in enumerate(page.blocks):
            elements.append(
                StructureElement(
                    element_type=classify_text(block.text),
                    text=block.text,
                    page_number=page.page_number,
                    source="embedded",
                    index_on_page=index,
                    bbox=block.bbox.as_list(),
                )
            )
    elif page.ocr_used and page.ocr is not None:
        for index, ocr_block in enumerate(page.ocr.blocks):
            elements.append(
                StructureElement(
                    element_type=classify_text(ocr_block.text),
                    text=ocr_block.text,
                    page_number=page.page_number,
                    source="ocr",
                    index_on_page=index,
                    bbox=list(ocr_block.bbox),
                )
            )

    return elements


_FAMILY_OF: dict[ElementType, str] = {"moves": "moves", "explainer": "explainer"}


def _looks_finished(element: StructureElement) -> bool:
    """
    Best-effort guess at whether an element's content looks complete on
    its own page, vs. plausibly cut off mid-thought/mid-game. This is a
    heuristic signal for continuation *confidence*, not a validated
    fact — see ContinuationConfidence in structure/models.py.
    """
    text = element.text.strip()
    if element.element_type == "moves":
        return bool(_GAME_RESULT_RE.search(text)) or text.endswith("#")
    if element.element_type == "explainer":
        return bool(_SENTENCE_END_RE.search(text))
    return True


def detect_sections(elements_by_page: dict[int, list[StructureElement]]) -> list[Section]:
    """
    Walk a page range's elements in order and group consecutive
    same-family ("moves" or "explainer") elements into Sections,
    recording a ContinuationPoint wherever such a run crosses a page
    boundary.

    A heading, a diagram_candidate_hint, or an unclassified block
    always breaks a running section — those types have no family and
    are never merged with anything. This mirrors the spec's requirement
    (section 20) to never guess/merge past a clear structural boundary.
    """
    ordered_pages = sorted(elements_by_page)
    flat: list[StructureElement] = []
    for page_number in ordered_pages:
        flat.extend(elements_by_page[page_number])

    sections: list[Section] = []
    current_family: str | None = None
    current_elements: list[StructureElement] = []
    continuation_points: list[ContinuationPoint] = []

    def flush() -> None:
        nonlocal current_elements, continuation_points
        if current_elements:
            page_start = current_elements[0].page_number
            page_end = current_elements[-1].page_number
            preview = " ".join(e.text for e in current_elements).strip()[:120]
            sections.append(
                Section(
                    family=current_family,  # type: ignore[arg-type]
                    page_start=page_start,
                    page_end=page_end,
                    element_count=len(current_elements),
                    spans_pages=page_end > page_start,
                    continuation_points=list(continuation_points),
                    preview_text=preview,
                )
            )
        current_elements = []
        continuation_points = []

    for element in flat:
        family = _FAMILY_OF.get(element.element_type)

        if family is None:
            flush()
            current_family = None
            continue

        if family != current_family:
            flush()
            current_family = family
            current_elements = [element]
            continue

        previous = current_elements[-1]
        if element.page_number != previous.page_number:
            confidence: str = "confirmed" if not _looks_finished(previous) else "same_type_adjacent"
            continuation_points.append(
                ContinuationPoint(
                    from_page=previous.page_number,
                    to_page=element.page_number,
                    confidence=confidence,  # type: ignore[arg-type]
                )
            )
        current_elements.append(element)

    flush()
    return sections
