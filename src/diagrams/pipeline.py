"""
Milestone 4 coordinator pipeline: Page -> Diagram Detection -> Crop -> Recognition -> FEN -> Validation.

Consumes outputs from Stage 1 (PDF/image extraction), Stage 2 (OCR), and
Milestone 3 (structure elements), detects and processes diagrams on the page,
and returns structured diagram recognition results.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PIL import Image

from src.diagrams.context import infer_side_to_move
from src.diagrams.cropper import crop_diagram, image_to_base64_png
from src.diagrams.detector import detect_diagrams
from src.diagrams.models import DiagramRecognitionResult, RecognitionStatus
from src.diagrams.recognizer import DiagramRecognizer, get_default_recognizer
from src.diagrams.validators import validate_board

if TYPE_CHECKING:
    from src.pdf.models import PageExtraction
    from src.structure.models import StructureElement


def process_page_diagrams(
    image: Image.Image,
    page_number: int = 1,
    page_text: str = "",
    page_extraction: PageExtraction | None = None,
    structure_elements: list[StructureElement] | None = None,
    recognizer: DiagramRecognizer | None = None,
    include_crop_image: bool = True,
) -> list[DiagramRecognitionResult]:
    """
    Run full diagram processing pipeline for a single page.

    Args:
        image: Rendered PIL Image of the page.
        page_number: 1-indexed page number.
        page_text: Embedded or OCR text from the page.
        page_extraction: Optional PageExtraction model.
        structure_elements: Optional classified structure elements (M3).
        recognizer: Optional custom recognizer (defaults to OnnxTileRecognizer).
        include_crop_image: Whether to encode the cropped board as base64 PNG.

    Returns:
        List of DiagramRecognitionResult objects in natural reading order.
    """
    engine = recognizer or get_default_recognizer()

    candidates = detect_diagrams(
        image=image,
        page_number=page_number,
        page_extraction=page_extraction,
    )

    results: list[DiagramRecognitionResult] = []

    for cand in candidates:
        crop = crop_diagram(image, cand.bbox)
        crop_b64 = image_to_base64_png(crop) if include_crop_image else None

        # 1. Recognize piece placement
        rec = engine.recognize(crop)

        # 2. Extract side to move from surrounding structure / text
        side_evidence, side_fail_reason = infer_side_to_move(
            diagram_bbox=cand.bbox,
            page_number=page_number,
            page_text=page_text,
            structure_elements=structure_elements,
        )

        side_to_move = side_evidence.side_to_move if side_evidence else None
        side_source = side_evidence.to_dict() if side_evidence else None

        # 3. Validate with python-chess
        val = validate_board(rec.piece_placement, side_to_move=side_to_move)

        # 4. Determine resolution status and reason
        status: RecognitionStatus = "resolved"
        reason: str | None = None
        fen: str | None = None
        metadata_status = "unknown"

        if not val.is_valid:
            status = "unresolved"
            reason = f"FEN validation failed: {val.details}"
        elif rec.mean_confidence < 0.70 or rec.min_confidence < 0.20:
            status = "unresolved"
            reason = f"Low recognition confidence (mean: {rec.mean_confidence:.2f}, min: {rec.min_confidence:.2f})"
        elif not side_to_move:
            status = "unresolved"
            reason = side_fail_reason or "side to move could not be determined"
            metadata_status = "partial"
            fen = None
        else:
            status = "resolved"
            turn_code = "w" if side_to_move == "white" else "b"
            fen = f"{rec.piece_placement} {turn_code} - - 0 1"
            metadata_status = "complete"

        results.append(
            DiagramRecognitionResult(
                diagram_id=cand.diagram_id,
                page=page_number,
                bbox=cand.bbox,
                status=status,
                crop_base64_png=crop_b64,
                piece_placement=rec.piece_placement,
                fen=fen,
                fen_metadata_status=metadata_status,
                side_to_move=side_to_move,
                side_to_move_source=side_source,
                reason=reason,
                mean_confidence=rec.mean_confidence,
                min_confidence=rec.min_confidence,
                square_confidences=rec.square_confidences,
                validation=val.to_dict(),
            )
        )

    return results
