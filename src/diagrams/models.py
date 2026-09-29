"""
Data models for Milestone 4: Chess Diagram Detection + Diagram-to-FEN.

Defines schemas for diagram candidate detection, crop representations,
side-to-move extraction evidence, python-chess validation, and recognition
results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

RecognitionStatus = Literal["resolved", "unresolved"]
SideToMove = Literal["white", "black"]
FenMetadataStatus = Literal["complete", "partial", "unknown"]


@dataclass
class DiagramCandidate:
    """A detected region on a page that is likely a chessboard diagram."""

    diagram_id: str
    page: int
    bbox: list[float]  # [x0, y0, x1, y1]
    confidence: float
    source_type: str = "visual"  # "visual" or "font_block"
    crop_base64_png: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "diagram_id": self.diagram_id,
            "page": self.page,
            "bbox": self.bbox,
            "confidence": round(self.confidence, 4),
            "source_type": self.source_type,
            "crop_base64_png": self.crop_base64_png,
        }


@dataclass
class SideToMoveEvidence:
    """Document/context evidence used to determine the side to move."""

    side_to_move: SideToMove | None
    text: str
    page: int
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "side_to_move": self.side_to_move,
            "text": self.text,
            "page": self.page,
            "confidence": round(self.confidence, 4),
        }


@dataclass
class ValidationResult:
    """Result of python-chess legality and structural validation."""

    python_chess: bool
    is_valid: bool
    has_both_kings: bool
    details: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "python_chess": self.python_chess,
            "is_valid": self.is_valid,
            "has_both_kings": self.has_both_kings,
            "details": self.details,
        }


@dataclass
class DiagramRecognitionResult:
    """
    Final recognition output for a detected diagram.

    Adheres strictly to the error philosophy: unresolved is better than
    silently wrong. If piece recognition is uncertain, side to move is
    missing, or python-chess validation fails, status is marked 'unresolved'.
    """

    diagram_id: str
    page: int
    bbox: list[float]
    status: RecognitionStatus
    crop_base64_png: str | None = None
    piece_placement: str | None = None
    fen: str | None = None
    fen_metadata_status: FenMetadataStatus = "unknown"
    side_to_move: SideToMove | None = None
    side_to_move_source: dict[str, Any] | None = None
    reason: str | None = None
    mean_confidence: float | None = None
    min_confidence: float | None = None
    square_confidences: list[float] | None = None
    validation: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "diagram_id": self.diagram_id,
            "page": self.page,
            "bbox": self.bbox,
            "status": self.status,
            "crop": self.crop_base64_png,
            "crop_base64_png": self.crop_base64_png,
            "piece_placement": self.piece_placement,
            "fen": self.fen,
            "fen_metadata_status": self.fen_metadata_status,
            "side_to_move": self.side_to_move,
            "side_to_move_source": self.side_to_move_source,
            "reason": self.reason,
            "confidence": round(self.mean_confidence, 4) if self.mean_confidence is not None else None,
            "mean_confidence": round(self.mean_confidence, 4) if self.mean_confidence is not None else None,
            "min_confidence": round(self.min_confidence, 4) if self.min_confidence is not None else None,
            "square_confidences": [round(c, 4) for c in self.square_confidences] if self.square_confidences else None,
            "validation": self.validation,
        }
