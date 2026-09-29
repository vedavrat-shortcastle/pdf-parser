"""
Chess processing package (Milestone 5).

Provides:
- Models: GameOrPuzzle, ReplayResult, HalfMove, GameMetadata
- SAN normalization & extraction
- python-chess legal replay engine
- PGN generation & adapter
- High-level pipeline coordinator: process_page_chess
"""

from src.chess.extractor import extract_games_from_page
from src.chess.models import GameMetadata, GameOrPuzzle, HalfMove, ReplayResult
from src.chess.pgn import build_pgn
from src.chess.pgn_adapter import parse_game_text
from src.chess.pipeline import process_page_chess
from src.chess.replay import replay_moves
from src.chess.san import (
    extract_annotation,
    is_game_result,
    is_valid_san_format,
    normalize_game_result,
    normalize_san_token,
    parse_move_token,
)

__all__ = [
    "GameMetadata",
    "GameOrPuzzle",
    "HalfMove",
    "ReplayResult",
    "build_pgn",
    "parse_game_text",
    "extract_games_from_page",
    "process_page_chess",
    "replay_moves",
    "extract_annotation",
    "is_game_result",
    "is_valid_san_format",
    "normalize_game_result",
    "normalize_san_token",
    "parse_move_token",
]
