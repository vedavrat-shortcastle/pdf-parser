"""
Data models for Milestone 5: Move parsing, SAN normalization,
PGN reconstruction, and python-chess game replay.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class HalfMove:
    """A single half-move (ply) in a game or tactical puzzle."""

    ply: int
    move_number: int
    turn: Literal["white", "black"]
    raw_token: str
    san: str
    uci: str
    fen_after: str
    is_legal: bool = True
    annotation: str | None = None
    comment: str | None = None
    diagram_anchor: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GameMetadata:
    """Standard PGN Seven Tag Roster metadata + extra book context."""

    title: str | None = None
    white: str | None = None
    black: str | None = None
    date: str | None = None
    site: str | None = None
    event: str | None = None
    round: str | None = None
    eco: str | None = None
    result: str = "*"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReplayResult:
    """Outcome of replaying a candidate move sequence on python-chess."""

    resolved: bool
    unresolved_reason: str | None = None
    failing_move: str | None = None
    failing_ply: int | None = None
    ply_count: int = 0
    half_moves: list[HalfMove] = field(default_factory=list)
    initial_fen: str = ""
    final_fen: str = ""
    diagram_matches: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "resolved": self.resolved,
            "unresolved_reason": self.unresolved_reason,
            "failing_move": self.failing_move,
            "failing_ply": self.failing_ply,
            "ply_count": self.ply_count,
            "half_moves": [m.to_dict() for m in self.half_moves],
            "initial_fen": self.initial_fen,
            "final_fen": self.final_fen,
            "diagram_matches": self.diagram_matches,
        }


@dataclass
class GameOrPuzzle:
    """A reconstructed chess game or tactical puzzle."""

    game_id: str
    kind: Literal["game", "puzzle"]
    page_number: int
    metadata: GameMetadata
    replay: ReplayResult
    pgn: str
    source_element_indices: list[int] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "game_id": self.game_id,
            "kind": self.kind,
            "page_number": self.page_number,
            "metadata": self.metadata.to_dict(),
            "replay": self.replay.to_dict(),
            "pgn": self.pgn,
            "source_element_indices": self.source_element_indices,
        }
