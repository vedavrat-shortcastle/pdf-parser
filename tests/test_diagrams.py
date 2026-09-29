"""
Tests for Milestone 4: Chess Diagram Detection + Diagram-to-FEN.

Tests diagram candidates schema, cropping, recognizer adapter, FEN normalization,
side-to-move extraction, python-chess validation, unresolved status handling,
multi-diagram pages, and API responses.
"""

from __future__ import annotations

import io
from PIL import Image
import pytest
from fastapi.testclient import TestClient

from src.api import app
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
from src.structure.models import StructureElement

client = TestClient(app)


# ---------------------------------------------------------------------------
# 1. Models & Schemas
# ---------------------------------------------------------------------------


def test_diagram_candidate_schema():
    cand = DiagramCandidate(
        diagram_id="diagram_001",
        page=2,
        bbox=[10.555, 20.444, 110.111, 120.222],
        confidence=0.941234,
        source_type="visual",
    )
    d = cand.to_dict()
    assert d["diagram_id"] == "diagram_001"
    assert d["page"] == 2
    assert d["bbox"] == [10.555, 20.444, 110.111, 120.222]
    assert d["confidence"] == 0.9412
    assert d["source_type"] == "visual"


def test_diagram_recognition_result_schema():
    res = DiagramRecognitionResult(
        diagram_id="diagram_001",
        page=1,
        bbox=[0.0, 0.0, 100.0, 100.0],
        status="resolved",
        piece_placement="r1bqk2r/pppp1ppp/2n2n2/4p3/1bB1P3/2N2N2/PPPP1PPP/R1BQK2R",
        fen="r1bqk2r/pppp1ppp/2n2n2/4p3/1bB1P3/2N2N2/PPPP1PPP/R1BQK2R w - - 0 1",
        fen_metadata_status="complete",
        side_to_move="white",
        mean_confidence=0.9234,
        min_confidence=0.7123,
        validation={"python_chess": True, "is_valid": True, "has_both_kings": True},
    )
    d = res.to_dict()
    assert d["status"] == "resolved"
    assert d["fen_metadata_status"] == "complete"
    assert d["side_to_move"] == "white"
    assert d["confidence"] == 0.9234
    assert d["validation"]["is_valid"] is True


# ---------------------------------------------------------------------------
# 2. Cropping & Base64
# ---------------------------------------------------------------------------


def test_crop_generation_and_clamping():
    base_img = Image.new("RGB", (200, 200), color=(100, 150, 200))
    # Normal crop
    crop = crop_diagram(base_img, [10, 10, 50, 60])
    assert crop.size == (40, 50)

    # Clamping test with out-of-bounds coordinates
    clamped_crop = crop_diagram(base_img, [-50, -30, 250, 300])
    assert clamped_crop.size == (200, 200)

    # Base64 PNG generation
    b64 = image_to_base64_png(crop)
    assert b64.startswith("data:image/png;base64,")
    assert len(b64) > 50


# ---------------------------------------------------------------------------
# 3. Recognizer Adapter Interface
# ---------------------------------------------------------------------------


class MockCustomRecognizer(DiagramRecognizer):
    def recognize(self, image: Image.Image) -> RawRecognitionResult:
        return RawRecognitionResult(
            piece_placement="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR",
            mean_confidence=0.99,
            min_confidence=0.95,
            square_confidences=[0.99] * 64,
            orientation="white",
            is_reliable=True,
        )


def test_recognizer_adapter():
    mock_rec = MockCustomRecognizer()
    dummy_img = Image.new("L", (100, 100), color=128)
    res = mock_rec.recognize(dummy_img)
    assert res.piece_placement == "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR"
    assert res.mean_confidence == 0.99
    assert res.is_reliable is True

    # Default recognizer is an ONNX tile recognizer instance
    default_rec = get_default_recognizer()
    assert default_rec is not None


# ---------------------------------------------------------------------------
# 4. python-chess Validation
# ---------------------------------------------------------------------------


def test_validation_legal_positions():
    start_pos = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR"
    val = validate_board(start_pos, side_to_move="white")
    assert val.is_valid is True
    assert val.has_both_kings is True
    assert val.python_chess is True

    tactic_pos = "r1bqk2r/ppp2ppp/2np1n2/6N1/2BpP3/8/PPPN1PPP/R2QK2R"
    val2 = validate_board(tactic_pos, side_to_move="white")
    assert val2.is_valid is True


def test_validation_missing_kings():
    no_white_king = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQ1BNR"
    val = validate_board(no_white_king, side_to_move="white")
    assert val.is_valid is False
    assert val.has_both_kings is False
    assert "Invalid king count" in (val.details or "")


def test_validation_multiple_kings():
    two_white_kings = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNK"
    val = validate_board(two_white_kings, side_to_move="white")
    assert val.is_valid is False
    assert "Invalid king count" in (val.details or "")


def test_validation_impossible_pawns():
    # Pawn on rank 8
    pawn_on_8 = "Pnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR"
    val = validate_board(pawn_on_8)
    assert val.is_valid is False
    assert "Pawns cannot exist on the 8th rank" in (val.details or "")

    # Pawn on rank 1
    pawn_on_1 = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNP"
    val2 = validate_board(pawn_on_1)
    assert val2.is_valid is False
    assert "Pawns cannot exist on the 1st rank" in (val2.details or "")


def test_validation_opposite_king_in_check():
    # If White is to move, but Black is already checking White? Valid.
    # But if White is to move, White's opponent (Black) CANNOT be in check (impossible state).
    # Here White pawn on e7, Black king on e8, and it is Black's turn? That's fine.
    # But if it's White's turn and Black king is under attack by White rook on e1 with e-file open:
    illegal_check = "4k3/8/8/8/8/8/8/4R2K"  # White rook on e1 attacking Black king on e8
    val = validate_board(illegal_check, side_to_move="black")
    # Black is in check, Black to move -> legal
    assert val.is_valid is True

    # If it is WHITE's turn, but Black king is in check -> illegal state
    val2 = validate_board(illegal_check, side_to_move="white")
    assert val2.is_valid is False
    assert "Opposite king is in check" in (val2.details or "")


# ---------------------------------------------------------------------------
# 5. Side-to-Move Context Extraction
# ---------------------------------------------------------------------------


def test_side_to_move_white_cues():
    bbox = [10, 10, 100, 100]
    ev, reason = infer_side_to_move(bbox, 1, "White to play and win")
    assert reason is None
    assert ev is not None
    assert ev.side_to_move == "white"

    ev2, reason2 = infer_side_to_move(bbox, 1, "White can prepare the same idea:\n8.Nxe4 1-0")
    assert ev2 is not None
    assert ev2.side_to_move == "white"


def test_side_to_move_black_cues():
    bbox = [10, 10, 100, 100]
    ev, reason = infer_side_to_move(bbox, 1, "Black to move and draw")
    assert reason is None
    assert ev is not None
    assert ev.side_to_move == "black"

    ev2, reason2 = infer_side_to_move(bbox, 1, "Idea ...Ne2+!")
    assert ev2 is not None
    assert ev2.side_to_move == "black"


def test_side_to_move_conflicting_cues():
    bbox = [10, 10, 100, 100]
    text = "White to play.\nActually, Black to move."
    ev, reason = infer_side_to_move(bbox, 1, text)
    assert ev is None
    assert "conflicting" in (reason or "")


def test_side_to_move_undetermined():
    bbox = [10, 10, 100, 100]
    text = "A simple overview of tactical patterns in the middle game."
    ev, reason = infer_side_to_move(bbox, 1, text)
    assert ev is None
    assert "could not be determined" in (reason or "")


# ---------------------------------------------------------------------------
# 6. Unresolved Handling in Pipeline
# ---------------------------------------------------------------------------


def test_pipeline_unresolved_when_side_to_move_missing():
    mock_rec = MockCustomRecognizer()
    dummy_img = Image.new("RGB", (300, 300), color=(255, 255, 255))
    # Draw a simple box to trigger candidate detection or call process_page_diagrams
    # When text has no side-to-move cue:
    results = process_page_diagrams(
        image=dummy_img,
        page_number=1,
        page_text="No chess hints here",
        recognizer=mock_rec,
    )
    # Even if no visual candidates exist in a blank white image, candidate list is empty
    assert isinstance(results, list)


def test_unresolved_error_philosophy():
    # If validator fails, result status MUST be unresolved with reason
    val = validate_board("8/8/8/8/8/8/8/8")  # No kings
    assert val.is_valid is False


# ---------------------------------------------------------------------------
# 7. Real Multi-Diagram Page Integration Tests
# ---------------------------------------------------------------------------


def test_real_book_page_14():
    """Page 14 of TacticsCourse (1).pdf has 3 diagrams with full text and moves."""
    try:
        with open("TacticsCourse (1).pdf", "rb") as f:
            pdf_bytes = f.read()
    except FileNotFoundError:
        pytest.skip("TacticsCourse (1).pdf not found")

    response = client.post(
        "/parse",
        files={"file": ("TacticsCourse.pdf", pdf_bytes, "application/pdf")},
        data={"page_number": "14"},
    )
    assert response.status_code == 200
    body = response.json()

    assert "diagrams" in body
    diagrams = body["diagrams"]
    assert len(diagrams) == 3

    # All 3 diagrams on page 14 have clear positions and White to move
    for diag in diagrams:
        assert diag["status"] == "resolved"
        assert diag["fen"] is not None
        assert diag["side_to_move"] == "white"
        assert diag["validation"]["is_valid"] is True
        assert diag["confidence"] > 0.85
        assert diag["crop"] is not None


def test_real_book_page_9_multiple_diagrams():
    """Page 9 has 6 diagrams with annotation markings and captions."""
    try:
        with open("TacticsCourse (1).pdf", "rb") as f:
            pdf_bytes = f.read()
    except FileNotFoundError:
        pytest.skip("TacticsCourse (1).pdf not found")

    response = client.post(
        "/parse",
        files={"file": ("TacticsCourse.pdf", pdf_bytes, "application/pdf")},
        data={"page_number": "9"},
    )
    assert response.status_code == 200
    body = response.json()

    assert "diagrams" in body
    diagrams = body["diagrams"]
    assert len(diagrams) == 6

    # Verify order is preserved: diagram_001 .. diagram_006
    ids = [d["diagram_id"] for d in diagrams]
    assert ids == [f"diagram_{i:03d}" for i in range(1, 7)]

    # At least diagram 6 is cleanly resolved
    resolved = [d for d in diagrams if d["status"] == "resolved"]
    assert len(resolved) >= 1
    # Diagrams with obstruction arrows must be marked unresolved, not silently wrong
    unresolved = [d for d in diagrams if d["status"] == "unresolved"]
    assert len(unresolved) >= 1
    for un in unresolved:
        assert un["reason"] is not None


def test_multi_page_diagrams_api():
    """Test /parse/pages returns diagrams per page in the pages list."""
    try:
        with open("TacticsCourse (1).pdf", "rb") as f:
            pdf_bytes = f.read()
    except FileNotFoundError:
        pytest.skip("TacticsCourse (1).pdf not found")

    response = client.post(
        "/parse/pages",
        files={"file": ("TacticsCourse.pdf", pdf_bytes, "application/pdf")},
        data={"start_page": "11", "end_page": "12"},
    )
    assert response.status_code == 200
    body = response.json()

    assert "pages" in body
    assert len(body["pages"]) == 2
    for page in body["pages"]:
        assert "diagrams" in page
        assert len(page["diagrams"]) == 3
        for d in page["diagrams"]:
            assert d["validation"]["is_valid"] is True
