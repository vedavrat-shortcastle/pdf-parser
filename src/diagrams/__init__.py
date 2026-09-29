"""
Milestone 4: Chess Diagram Detection + Diagram-to-FEN.

Detects chessboard diagrams on PDF or image pages, crops them in memory,
classifies piece placement with local ONNX inference, infers side-to-move
from document context, and validates position legality with python-chess.
"""

from src.diagrams.context import infer_side_to_move
from src.diagrams.cropper import crop_diagram, image_to_base64_png
from src.diagrams.detector import detect_diagrams
from src.diagrams.models import (
    DiagramCandidate,
    DiagramRecognitionResult,
    SideToMoveEvidence,
    ValidationResult,
)
from src.diagrams.pipeline import process_page_diagrams
from src.diagrams.recognizer import DiagramRecognizer, RawRecognitionResult, get_default_recognizer
from src.diagrams.validators import validate_board

__all__ = [
    "DiagramCandidate",
    "DiagramRecognitionResult",
    "SideToMoveEvidence",
    "ValidationResult",
    "DiagramRecognizer",
    "RawRecognitionResult",
    "get_default_recognizer",
    "detect_diagrams",
    "crop_diagram",
    "image_to_base64_png",
    "infer_side_to_move",
    "validate_board",
    "process_page_diagrams",
]
