"""
Standard PGN generation and formatting.

Generates Seven Tag Roster, SetUp/FEN tags for custom positions,
and formatted move text with annotations and game results.
"""

from __future__ import annotations

import chess

from src.chess.models import GameMetadata, HalfMove


def build_pgn(
    metadata: GameMetadata,
    half_moves: list[HalfMove],
    initial_fen: str | None = None,
) -> str:
    """Generate valid standard PGN string for a game or puzzle."""
    headers: list[tuple[str, str]] = [
        ("Event", metadata.event or metadata.title or "?"),
        ("Site", metadata.site or "?"),
        ("Date", metadata.date or "????.??.??"),
        ("Round", metadata.round or "?"),
        ("White", metadata.white or "?"),
        ("Black", metadata.black or "?"),
        ("Result", metadata.result or "*"),
    ]

    if metadata.eco:
        headers.append(("ECO", metadata.eco))

    if initial_fen and initial_fen != chess.STARTING_FEN:
        headers.append(("SetUp", "1"))
        headers.append(("FEN", initial_fen))

    lines: list[str] = [f'[{key} "{value}"]' for key, value in headers]
    lines.append("")

    # Format move text
    move_tokens: list[str] = []
    for m in half_moves:
        ann = m.annotation or ""
        if m.turn == "white":
            move_tokens.append(f"{m.move_number}.{m.san}{ann}")
        else:
            # If black move follows white directly, don't repeat number unless first move
            if not move_tokens or move_tokens[-1].endswith("..."):
                move_tokens.append(f"{m.move_number}...{m.san}{ann}")
            else:
                move_tokens.append(f"{m.san}{ann}")

        if m.comment:
            move_tokens.append(f"{{{m.comment}}}")

    if metadata.result:
        move_tokens.append(metadata.result)

    # Wrap tokens into ~80 character lines
    current_line = ""
    for tok in move_tokens:
        if not current_line:
            current_line = tok
        elif len(current_line) + 1 + len(tok) <= 80:
            current_line += " " + tok
        else:
            lines.append(current_line)
            current_line = tok

    if current_line:
        lines.append(current_line)

    return "\n".join(lines)
