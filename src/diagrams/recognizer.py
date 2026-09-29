"""
Adapter interface for board-to-FEN recognition.

Decouples the parser pipeline from specific computer vision models or ONNX
providers, allowing switching or upgrading models without changing the API
or diagram detection logic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

from PIL import Image

if TYPE_CHECKING:
    pass


@dataclass
class RawRecognitionResult:
    """Raw piece-placement prediction emitted by a recognizer adapter."""

    piece_placement: str
    mean_confidence: float
    min_confidence: float
    square_confidences: list[float]
    orientation: str = "white"
    is_reliable: bool = True


class DiagramRecognizer(ABC):
    """Abstract base class for all chessboard recognizers."""

    @abstractmethod
    def recognize(self, image: Image.Image) -> RawRecognitionResult:
        """
        Recognize an 8x8 chessboard from an image crop.

        Args:
            image: Cropped PIL Image containing a chessboard diagram.

        Returns:
            RawRecognitionResult with predicted piece_placement and confidences.
        """
        pass


_default_recognizer: DiagramRecognizer | None = None


def get_default_recognizer() -> DiagramRecognizer:
    """Returns a singleton instance of the default recognizer."""
    global _default_recognizer
    if _default_recognizer is None:
        from src.diagrams.providers.onnx_provider import OnnxTileRecognizer

        _default_recognizer = OnnxTileRecognizer()
    return _default_recognizer
