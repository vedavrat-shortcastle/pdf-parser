"""
Side-to-move and FEN metadata extraction from document context and M3 structure.

Adheres strictly to the error philosophy: never guess side to move, castling rights,
or move clocks. Only extracts side to move when explicit contextual evidence
exists in surrounding text or structure elements.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from src.diagrams.models import SideToMove, SideToMoveEvidence

if TYPE_CHECKING:
    from src.structure.models import StructureElement

# Explicit regex patterns for side to move
_WHITE_CUES = [
    re.compile(r"\bwhite\s+to\s+(?:play|move|win|draw)\b", re.IGNORECASE),
    re.compile(r"\bwhite\s+plays\b", re.IGNORECASE),
    re.compile(r"\bwhite\s+can\b", re.IGNORECASE),
    re.compile(r"\bwhite\s+wins\b", re.IGNORECASE),
    re.compile(r"\bWhite\b.*?\b(?:1-0)\b"),
]

_BLACK_CUES = [
    re.compile(r"\bblack\s+to\s+(?:play|move|win|draw)\b", re.IGNORECASE),
    re.compile(r"\bblack\s+plays\b", re.IGNORECASE),
    re.compile(r"\bblack\s+can\b", re.IGNORECASE),
    re.compile(r"\bblack\s+wins\b", re.IGNORECASE),
    re.compile(r"\bBlack\b.*?\b(?:0-1)\b"),
]

# Chess move cues: "...Ne2+!" or "9...Nxd2" indicates Black to play
_BLACK_ELLIPSIS_MOVE = re.compile(r"(?:\d+\.{3}|\.{3})\s*[KQRBN]?[a-h]?[1-8]?x?[a-h][1-8]")

# White move starting line: "8.Nxf7" or "5.Qa4+" without leading ellipsis
_WHITE_MOVE_START = re.compile(r"(?:^|\n)\s*(\d+)\.\s*[KQRBN]?[a-h]?[1-8]?x?[a-h][1-8]")


def infer_side_to_move(
    diagram_bbox: list[float],
    page_number: int,
    page_text: str,
    structure_elements: list[StructureElement] | None = None,
) -> tuple[SideToMoveEvidence | None, str | None]:
    """
    Infer side to move from surrounding document structure and text.

    Args:
        diagram_bbox: [x0, y0, x1, y1] bounding box of the diagram.
        page_number: 1-indexed page number.
        page_text: Full text extracted from the page.
        structure_elements: Optional M3 structure elements on the page.

    Returns:
        tuple of (SideToMoveEvidence or None, failure_reason or None).
        If evidence conflicts, returns (None, "conflicting side-to-move evidence").
        If no evidence found, returns (None, "side to move could not be determined").
    """
    found_white: list[str] = []
    found_black: list[str] = []

    # 1. Inspect M3 structure elements (especially diagram hints)
    if structure_elements:
        for elem in structure_elements:
            t = elem.text.strip()
            if any(cue.search(t) for cue in _WHITE_CUES):
                found_white.append(t)
            if any(cue.search(t) for cue in _BLACK_CUES):
                found_black.append(t)

    # 2. Inspect page text
    for line in page_text.splitlines():
        line_clean = line.strip()
        if not line_clean:
            continue
        if any(cue.search(line_clean) for cue in _WHITE_CUES):
            found_white.append(line_clean)
        if any(cue.search(line_clean) for cue in _BLACK_CUES):
            found_black.append(line_clean)
        if _BLACK_ELLIPSIS_MOVE.search(line_clean):
            found_black.append(line_clean)

    # 3. If surrounding text contains next-move pattern
    if not found_white and not found_black:
        # Check moves under diagram
        wm = _WHITE_MOVE_START.search(page_text)
        if wm:
            found_white.append(wm.group(0).strip())

    # Check for conflicts
    if found_white and found_black:
        return None, "conflicting side-to-move evidence found in document context"

    if found_white:
        evidence_text = found_white[0]
        return (
            SideToMoveEvidence(
                side_to_move="white",
                text=evidence_text,
                page=page_number,
                confidence=0.95,
            ),
            None,
        )

    if found_black:
        evidence_text = found_black[0]
        return (
            SideToMoveEvidence(
                side_to_move="black",
                text=evidence_text,
                page=page_number,
                confidence=0.95,
            ),
            None,
        )

    return None, "side to move could not be determined from context"
