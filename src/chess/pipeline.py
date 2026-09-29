"""
Top-level pipeline coordinator for chess move extraction, replay,
and game/puzzle reconstruction.
"""

from __future__ import annotations

import logging
from typing import Any

from src.chess.extractor import extract_games_from_page
from src.chess.models import GameOrPuzzle
from src.pdf.models import PageExtraction
from src.structure.models import StructureElement

logger = logging.getLogger(__name__)


def process_page_chess(
    page_extraction: PageExtraction,
    structure_elements: list[StructureElement],
    diagrams: list[dict[str, Any]] | None = None,
) -> list[GameOrPuzzle]:
    """
    High-level entry point for Milestone 5.

    Takes a page's extraction, classified structure elements, and detected diagrams (M4),
    extracts all chess games and tactical puzzles, validates their legality via python-chess,
    correlates diagram positions, and formats standard PGN.
    """
    try:
        games = extract_games_from_page(
            page_extraction=page_extraction,
            structure_elements=structure_elements,
            diagrams=diagrams,
        )
        return games
    except Exception as exc:
        logger.exception("Failed to process chess games on page %s: %s", page_extraction.page_number, exc)
        return []
