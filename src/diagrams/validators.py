"""
Legality and state validation using python-chess.

Validates candidate board positions according to FEN syntax and the rules of chess:
  - Exactly one white king and one black king
  - No impossible pawn placements (1st or 8th rank)
  - Valid python-chess Board construction
  - Legality checks (e.g. side not to move cannot be in check)
"""

from __future__ import annotations

import chess

from src.diagrams.models import ValidationResult


def validate_board(piece_placement: str, side_to_move: str | None = None) -> ValidationResult:
    """
    Validate a candidate piece placement string with python-chess.

    Args:
        piece_placement: Bare piece placement portion of FEN (e.g. 'r1bqk2r/...').
        side_to_move: 'white', 'black', or None.

    Returns:
        ValidationResult with python_chess flag, is_valid boolean, and details.
    """
    if not piece_placement or not isinstance(piece_placement, str):
        return ValidationResult(
            python_chess=False,
            is_valid=False,
            has_both_kings=False,
            details="Piece placement string is empty or invalid",
        )

    ranks = piece_placement.split("/")
    if len(ranks) != 8:
        return ValidationResult(
            python_chess=False,
            is_valid=False,
            has_both_kings=False,
            details=f"Placement has {len(ranks)} ranks (expected exactly 8)",
        )

    # 1. King counts
    white_kings = sum(r.count("K") for r in ranks)
    black_kings = sum(r.count("k") for r in ranks)
    has_both_kings = white_kings == 1 and black_kings == 1
    if not has_both_kings:
        return ValidationResult(
            python_chess=False,
            is_valid=False,
            has_both_kings=False,
            details=f"Invalid king count: {white_kings} White, {black_kings} Black (expected exactly 1 each)",
        )

    # 2. Pawn placement constraints
    # ranks[0] is rank 8, ranks[7] is rank 1
    if "P" in ranks[0] or "p" in ranks[0]:
        return ValidationResult(
            python_chess=False,
            is_valid=False,
            has_both_kings=True,
            details="Pawns cannot exist on the 8th rank",
        )
    if "P" in ranks[7] or "p" in ranks[7]:
        return ValidationResult(
            python_chess=False,
            is_valid=False,
            has_both_kings=True,
            details="Pawns cannot exist on the 1st rank",
        )

    # 3. Construct test FEN for python-chess
    turn_char = "w" if side_to_move != "black" else "b"
    test_fen = f"{piece_placement} {turn_char} - - 0 1"

    try:
        board = chess.Board(test_fen)
    except Exception as exc:
        return ValidationResult(
            python_chess=False,
            is_valid=False,
            has_both_kings=True,
            details=f"python-chess construction error: {exc}",
        )

    # 4. Check legality
    status = board.status()
    if status == chess.STATUS_VALID or board.is_valid():
        return ValidationResult(
            python_chess=True,
            is_valid=True,
            has_both_kings=True,
            details="Valid legal position",
        )

    # Translate status flags
    errors: list[str] = []
    if status & chess.STATUS_OPPOSITE_CHECK:
        errors.append("Opposite king is in check")
    if status & chess.STATUS_TOO_MANY_KINGS:
        errors.append("Too many kings")
    if status & chess.STATUS_NO_WHITE_KING:
        errors.append("No white king")
    if status & chess.STATUS_NO_BLACK_KING:
        errors.append("No black king")
    if status & chess.STATUS_TOO_MANY_WHITE_PAWNS:
        errors.append("Too many white pawns")
    if status & chess.STATUS_TOO_MANY_BLACK_PAWNS:
        errors.append("Too many black pawns")
    if status & chess.STATUS_PAWNS_ON_BACKRANK:
        errors.append("Pawns on back rank (1st or 8th)")

    err_msg = "; ".join(errors) if errors else f"Status code {status}"
    return ValidationResult(
        python_chess=True,
        is_valid=False,
        has_both_kings=True,
        details=f"python-chess validation failed: {err_msg}",
    )
