"""
Legal chess move replay engine backed by python-chess.

Validates candidate move sequences, executes them ply-by-ply, tracks
intermediate FEN positions, correlates board states with detected
diagram FENs, and emits detailed diagnostics for any illegal or ambiguous moves.
"""

from __future__ import annotations

import logging
from typing import Any

import chess

from src.chess.models import HalfMove, ReplayResult

logger = logging.getLogger(__name__)


def _extract_placement(fen: str) -> str:
    """Extract the 8-rank piece placement component from a FEN string."""
    return fen.strip().split()[0] if fen else ""


def replay_moves(
    moves: list[dict[str, Any]],
    initial_fen: str | None = None,
    candidate_diagrams: list[dict[str, Any]] | None = None,
) -> ReplayResult:
    """
    Replay a sequence of parsed move dicts on a python-chess board.

    Each dict in `moves` can contain:
      - 'san': str (e.g. 'e4', 'Nf3', 'Bb4+')
      - 'raw_token': str (optional original token)
      - 'move_number': int | None
      - 'turn': 'white' | 'black' | None
      - 'annotation': str | None
      - 'comment': str | None
      - 'diagram_anchor': bool

    candidate_diagrams: list of dicts with 'fen', 'index_on_page', 'bbox', etc.
    """
    start_fen = initial_fen or chess.STARTING_FEN

    try:
        board = chess.Board(start_fen)
    except ValueError as exc:
        return ReplayResult(
            resolved=False,
            unresolved_reason=f"Invalid starting FEN '{start_fen}': {exc}",
            initial_fen=start_fen,
            final_fen=start_fen,
        )

    half_moves: list[HalfMove] = []
    diagram_matches: list[dict[str, Any]] = []

    # Check if initial position matches a diagram
    if candidate_diagrams:
        initial_placement = _extract_placement(start_fen)
        for diag in candidate_diagrams:
            diag_fen = diag.get("candidate_fen") or diag.get("fen", "")
            if diag_fen and _extract_placement(diag_fen) == initial_placement:
                diagram_matches.append(
                    {
                        "diagram_id": diag.get("diagram_id"),
                        "diagram_index": diag.get("index_on_page"),
                        "ply": 0,
                        "fen": start_fen,
                        "match_type": "initial_position",
                    }
                )

    for i, item in enumerate(moves):
        san = item.get("san", "").strip()
        raw_token = item.get("raw_token", san)
        annotation = item.get("annotation")
        comment = item.get("comment")
        diagram_anchor = bool(item.get("diagram_anchor", False))

        if not san:
            continue

        ply = len(half_moves) + 1
        turn_str: str = "white" if board.turn == chess.WHITE else "black"
        move_num = board.fullmove_number

        try:
            parsed_move = board.parse_san(san)
        except (chess.IllegalMoveError, chess.AmbiguousMoveError, chess.InvalidMoveError, ValueError) as exc:
            unresolved_reason = (
                f"Cannot play '{san}' at ply {ply} (move {move_num}, {turn_str}): {exc}"
            )
            # Record failed half-move for transparent UI inspection
            half_moves.append(
                HalfMove(
                    ply=ply,
                    move_number=move_num,
                    turn=turn_str,  # type: ignore[arg-type]
                    raw_token=raw_token,
                    san=san,
                    uci="",
                    fen_after=board.fen(),
                    is_legal=False,
                    annotation=annotation,
                    comment=comment,
                    diagram_anchor=diagram_anchor,
                )
            )
            return ReplayResult(
                resolved=False,
                unresolved_reason=unresolved_reason,
                failing_move=san,
                failing_ply=ply,
                ply_count=len(half_moves) - 1,
                half_moves=half_moves,
                initial_fen=start_fen,
                final_fen=board.fen(),
                diagram_matches=diagram_matches,
            )

        uci = parsed_move.uci()
        board.push(parsed_move)
        fen_after = board.fen()
        post_placement = board.board_fen()

        # Bidirectional diagram check: does board match a detected diagram?
        if candidate_diagrams:
            for diag in candidate_diagrams:
                diag_fen = diag.get("candidate_fen") or diag.get("fen", "")
                if diag_fen and _extract_placement(diag_fen) == post_placement:
                    match_record = {
                        "diagram_id": diag.get("diagram_id"),
                        "diagram_index": diag.get("index_on_page"),
                        "ply": ply,
                        "fen": fen_after,
                        "match_type": "post_move",
                    }
                    if match_record not in diagram_matches:
                        diagram_matches.append(match_record)

        half_moves.append(
            HalfMove(
                ply=ply,
                move_number=move_num,
                turn=turn_str,  # type: ignore[arg-type]
                raw_token=raw_token,
                san=san,
                uci=uci,
                fen_after=fen_after,
                is_legal=True,
                annotation=annotation,
                comment=comment,
                diagram_anchor=diagram_anchor,
            )
        )

    return ReplayResult(
        resolved=True,
        unresolved_reason=None,
        failing_move=None,
        failing_ply=None,
        ply_count=len(half_moves),
        half_moves=half_moves,
        initial_fen=start_fen,
        final_fen=board.fen(),
        diagram_matches=diagram_matches,
    )
