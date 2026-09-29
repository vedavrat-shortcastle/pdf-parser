"""
PGN Parser Adapter.

Follows docs/PGN_PARSER_ADAPTER.md:
Soft-imports Part 1's `annotation agent` `parse_pgn_text(...)` if available,
and cleanly falls back to `python-chess` when it is not.
"""

from __future__ import annotations

import io
import logging
from typing import Any

import chess.pgn

logger = logging.getLogger(__name__)

# Attempt soft import of Part 1 parser if configured on sys.path
_HAS_EXTERNAL_PARSER = False
_external_parse_pgn_text = None

try:
    from pgn_parser import parse_pgn_text as _ext_parser  # type: ignore[import-not-found]
    _external_parse_pgn_text = _ext_parser
    _HAS_EXTERNAL_PARSER = True
    logger.info("Loaded external PGN parser from annotation agent.")
except ImportError:
    pass


def parse_game_text(pgn_text: str) -> dict[str, Any]:
    """
    Parse a PGN string into a structured game dict.
    Delegates to external parser if available; otherwise uses python-chess.
    """
    if _HAS_EXTERNAL_PARSER and _external_parse_pgn_text is not None:
        try:
            return _external_parse_pgn_text(pgn_text)
        except Exception as exc:
            logger.warning("External PGN parser failed: %s; falling back to python-chess", exc)

    # Standard python-chess fallback
    game = chess.pgn.read_game(io.StringIO(pgn_text))
    if game is None:
        return {
            "headers": {},
            "moves": [],
            "result": "*",
            "is_valid": False,
        }

    headers = dict(game.headers)
    moves = []
    board = game.board()
    for node in game.mainline():
        moves.append(
            {
                "san": node.san(),
                "uci": node.move.uci(),
                "fen": node.board().fen(),
                "comment": node.comment,
            }
        )

    return {
        "headers": headers,
        "moves": moves,
        "result": headers.get("Result", "*"),
        "is_valid": True,
    }
