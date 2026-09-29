"""
Tests for Final Phase: Curriculum Hierarchy Assembly & ChessMethod JSON Export.
"""

from __future__ import annotations

import json
import os

from fastapi.testclient import TestClient

from src.api import app
from src.curriculum.builder import (
    _detect_heading_in_text,
    assemble_curriculum_from_pages,
    build_curriculum_from_pdf,
)
from src.curriculum.exporter import export_chessmethod_curriculum
from src.curriculum.models import (
    Activity,
    BookCurriculum,
    Chapter,
    Lesson,
    Level,
)

client = TestClient(app)
SAMPLE_BOOK = os.path.join(os.path.dirname(__file__), "..", "TacticsCourse (1).pdf")


def test_detect_heading_in_text():
    h_type, num, title = _detect_heading_in_text("3 One-move ideas\nSome intro text")
    assert h_type == "chapter"
    assert num == "3"
    assert title == "One-move ideas"

    h_type, num, title = _detect_heading_in_text("3.1 Forks\nWhite to move")
    assert h_type == "lesson"
    assert num == "3.1"
    assert title == "Forks"

    h_type, num, title = _detect_heading_in_text("1.e4 e5 2.Nf3 Nc6\n3.Bc4")
    assert h_type is None


def test_curriculum_models_and_json_schema():
    act1 = Activity(
        id="act_01",
        activity_type="game",
        title="Bargain",
        page_number=11,
        fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        pgn='[Event "Bargain"]\n1. e4 e5 0-1',
        moves=["e4", "e5"],
        solution=[],
        instructions="Simler,K vs Avguarde",
        metadata={"white": "Simler,K", "black": "Avguarde", "eco": "C55"},
        resolved=True,
        needs_review=False,
    )
    act2 = Activity(
        id="act_02",
        activity_type="puzzle",
        title="The knight fork",
        page_number=13,
        fen="r1bqk2r/ppp2ppp/2np1n2/6N1/2BpP3/8/PPPN1PPP/R2QK2R w KQkq - 0 8",
        pgn="",
        moves=["Nexc7+"],
        solution=["Nexc7+"],
        instructions="White to play and win",
        metadata={},
        resolved=False,
        needs_review=True,
        review_reason="Starting board had visual overlay markings",
    )

    lesson = Lesson(
        id="les_3_1",
        number="3.1",
        title="Forks",
        page_start=11,
        page_end=13,
        summary="A fork occurs when one piece attacks multiple pieces at once.",
        activities=[act1, act2],
    )

    chapter = Chapter(
        id="chap_3",
        number=3,
        title="One-move ideas",
        page_start=11,
        page_end=13,
        lessons=[lesson],
    )

    level = Level(
        id="level_01",
        title="Foundations",
        chapters=[chapter],
    )

    curriculum = BookCurriculum(
        book_title="Tactics Course",
        source_filename="TacticsCourse.pdf",
        total_pages=3,
        total_chapters=1,
        total_lessons=1,
        total_activities=2,
        resolved_activities=1,
        needs_review_count=1,
        levels=[level],
    )

    cm_json = curriculum.to_chessmethod_json()
    assert cm_json["format"] == "ChessMethod-Curriculum"
    assert cm_json["book"]["title"] == "Tactics Course"
    assert cm_json["curriculum_stats"]["total_activities"] == 2
    assert cm_json["curriculum_stats"]["resolved_activities"] == 1
    assert cm_json["curriculum_stats"]["needs_review_count"] == 1
    assert cm_json["curriculum_stats"]["resolution_rate_percent"] == 50.0

    # Test JSON string export
    exported_str = export_chessmethod_curriculum(curriculum)
    loaded = json.loads(exported_str)
    assert loaded["curriculum_stats"]["total_lessons"] == 1
    assert loaded["levels"][0]["chapters"][0]["lessons"][0]["activities"][1]["needs_review"] is True


def test_build_curriculum_from_pdf_sample_pages():
    if not os.path.exists(SAMPLE_BOOK):
        return

    with open(SAMPLE_BOOK, "rb") as f:
        pdf_bytes = f.read()

    # Process pages 10 to 14
    curriculum = build_curriculum_from_pdf(
        file_bytes=pdf_bytes,
        filename="TacticsCourse.pdf",
        start_page=10,
        end_page=14,
    )

    assert curriculum.total_pages == 5
    assert curriculum.total_chapters >= 1
    assert curriculum.total_lessons >= 2
    assert curriculum.total_activities >= 10
    assert curriculum.resolved_activities >= 9

    # Verify ChessMethod export
    cm_json = curriculum.to_chessmethod_json()
    assert "levels" in cm_json
    assert len(cm_json["levels"]) >= 1


def test_api_build_curriculum_endpoint():
    if not os.path.exists(SAMPLE_BOOK):
        return

    with open(SAMPLE_BOOK, "rb") as f:
        pdf_bytes = f.read()

    response = client.post(
        "/build-curriculum",
        files={"file": ("test_book.pdf", pdf_bytes, "application/pdf")},
        data={"start_page": 11, "end_page": 12, "book_title": "Custom Tactics Title"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "curriculum" in data
    assert "chessmethod_json" in data
    assert data["curriculum"]["book_title"] == "Custom Tactics Title"
    assert data["curriculum"]["total_pages"] == 2
    assert data["curriculum"]["total_activities"] >= 4
    assert data["chessmethod_json"]["format"] == "ChessMethod-Curriculum"
