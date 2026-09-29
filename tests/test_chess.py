"""
Tests for Milestone 5: Move OCR + SAN normalization + PGN reconstruction and python-chess replay.
"""

from __future__ import annotations

import os

import chess
from fastapi.testclient import TestClient

from src.api import app
from src.chess.extractor import extract_games_from_page
from src.chess.models import GameMetadata, HalfMove
from src.chess.pgn import build_pgn
from src.chess.pgn_adapter import parse_game_text
from src.chess.replay import replay_moves
from src.chess.san import (
    extract_annotation,
    is_game_result,
    is_valid_san_format,
    normalize_game_result,
    normalize_san_token,
    parse_move_token,
)
from src.pdf.extractor import extract_pdf_page
from src.structure.detector import classify_page

client = TestClient(app)
SAMPLE_BOOK = os.path.join(os.path.dirname(__file__), "..", "TacticsCourse (1).pdf")


# 1. SAN Normalization & Parsing
def test_san_castling_normalization():
    assert normalize_san_token("0-0") == "O-O"
    assert normalize_san_token("0-0-0") == "O-O-O"
    assert normalize_san_token("o-o") == "O-O"
    assert normalize_san_token("0-0+") == "O-O+"
    assert normalize_san_token("0-0-0#") == "O-O-O#"


def test_san_figurines_normalization():
    assert normalize_san_token("♘f3") == "Nf3"
    assert normalize_san_token("♗c4") == "Bc4"
    assert normalize_san_token("♖e1") == "Re1"
    assert normalize_san_token("♕xd8+") == "Qxd8+"
    assert normalize_san_token("♚e8") == "Ke8"


def test_san_captures_and_promotions():
    assert normalize_san_token("N*c3") == "Nxc3"
    assert normalize_san_token("B:f7+") == "Bxf7+"
    assert normalize_san_token("e8(Q)") == "e8=Q"
    assert normalize_san_token("d8/Q+") == "d8=Q+"
    assert normalize_san_token("a8Q#") == "a8=Q#"


def test_san_annotations_extraction():
    base, annot = extract_annotation("Ng5?!")
    assert base == "Ng5"
    assert annot == "?!"

    base, annot = extract_annotation("Nxf7!")
    assert base == "Nxf7"
    assert annot == "!"

    base, annot = extract_annotation("Bb4+")
    assert base == "Bb4+"
    assert annot is None


def test_parse_move_token():
    mn, is_b, san, ann = parse_move_token("1.e4")
    assert mn == 1
    assert is_b is False
    assert san == "e4"
    assert ann is None

    mn, is_b, san, ann = parse_move_token("9...Nxd2")
    assert mn == 9
    assert is_b is True
    assert san == "Nxd2"
    assert ann is None

    mn, is_b, san, ann = parse_move_token("5.Ng5?!")
    assert mn == 5
    assert is_b is False
    assert san == "Ng5"
    assert ann == "?!"

    # Non-SAN words are filtered to empty string
    mn, is_b, san, ann = parse_move_token("After")
    assert san == ""


def test_game_result_recognition():
    assert is_game_result("1-0") is True
    assert is_game_result("0-1") is True
    assert is_game_result("1/2-1/2") is True
    assert is_game_result("½-½") is True
    assert is_game_result("*") is True
    assert is_game_result("e4") is False

    assert normalize_game_result("½-½") == "1/2-1/2"


# 2. python-chess Replay
def test_replay_legal_game():
    # Scholar's mate
    moves = [
        {"san": "e4", "raw_token": "1.e4"},
        {"san": "e5", "raw_token": "e5"},
        {"san": "Bc4", "raw_token": "2.Bc4"},
        {"san": "Nc6", "raw_token": "Nc6"},
        {"san": "Qh5", "raw_token": "3.Qh5"},
        {"san": "Nf6", "raw_token": "Nf6"},
        {"san": "Qxf7#", "raw_token": "4.Qxf7#"},
    ]
    res = replay_moves(moves)
    assert res.resolved is True
    assert res.ply_count == 7
    assert res.failing_move is None
    assert res.half_moves[-1].san == "Qxf7#"
    assert res.final_fen.startswith("r1bqkb1r/pppp1Qpp/2n2n2/4p3/2B1P3/8/")


def test_replay_illegal_move_diagnostics():
    moves = [
        {"san": "e4", "raw_token": "1.e4"},
        {"san": "e5", "raw_token": "e5"},
        {"san": "Ke2", "raw_token": "2.Ke2"},  # Legal Ke2
        {"san": "Ke7", "raw_token": "Ke7"},  # Legal Ke7
        {"san": "Nxe5", "raw_token": "3.Nxe5"},  # Illegal: white knight on b1 or g1 cannot reach e5!
    ]
    res = replay_moves(moves)
    assert res.resolved is False
    assert res.failing_move == "Nxe5"
    assert res.failing_ply == 5
    assert "Cannot play 'Nxe5'" in (res.unresolved_reason or "")
    assert res.ply_count == 4


def test_puzzle_replay_from_custom_fen():
    # Back-rank mate puzzle
    fen = "6k1/5ppp/8/8/8/8/8/4R1K1 w - - 0 1"
    moves = [{"san": "Re8#", "raw_token": "1.Re8#"}]
    res = replay_moves(moves, initial_fen=fen)
    assert res.resolved is True
    assert res.ply_count == 1
    assert res.half_moves[0].uci == "e1e8"


def test_diagram_matching_during_replay():
    # Play 1.e4 e5 2.Nf3 Nc6 3.Bc4
    moves = [
        {"san": "e4"}, {"san": "e5"},
        {"san": "Nf3"}, {"san": "Nc6"},
        {"san": "Bc4"},
    ]
    # Target position after 3.Bc4
    target_fen = "r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3"
    candidate_diagrams = [
        {"diagram_id": "diag_01", "fen": target_fen, "index_on_page": 0}
    ]
    res = replay_moves(moves, candidate_diagrams=candidate_diagrams)
    assert res.resolved is True
    assert len(res.diagram_matches) == 1
    assert res.diagram_matches[0]["diagram_id"] == "diag_01"
    assert res.diagram_matches[0]["ply"] == 5


# 3. PGN Generation & Adapter
def test_build_pgn():
    meta = GameMetadata(
        title="Test Game",
        white="Player White",
        black="Player Black",
        date="2024.01.01",
        site="Online",
        eco="C50",
        result="1-0",
    )
    moves = [
        HalfMove(ply=1, move_number=1, turn="white", raw_token="1.e4", san="e4", uci="e2e4", fen_after=""),
        HalfMove(ply=2, move_number=1, turn="black", raw_token="e5", san="e5", uci="e7e5", fen_after=""),
    ]
    pgn_str = build_pgn(meta, moves)
    assert '[Event "Test Game"]' in pgn_str
    assert '[White "Player White"]' in pgn_str
    assert '[Black "Player Black"]' in pgn_str
    assert '[ECO "C50"]' in pgn_str
    assert "1.e4 e5 1-0" in pgn_str


def test_pgn_adapter_fallback():
    pgn_sample = """[Event "Sample"]
[Site "Paris"]
[Date "1924.??.??"]
[White "Alekhine"]
[Black "Capablanca"]
[Result "1/2-1/2"]

1. d4 Nf6 2. c4 e6 1/2-1/2
"""
    parsed = parse_game_text(pgn_sample)
    assert parsed["is_valid"] is True
    assert parsed["headers"]["White"] == "Alekhine"
    assert parsed["headers"]["Black"] == "Capablanca"
    assert parsed["result"] == "1/2-1/2"
    assert len(parsed["moves"]) == 4


# 4. Real Book Integration Tests (TacticsCourse.pdf)
def test_real_book_page_14_three_games():
    if not os.path.exists(SAMPLE_BOOK):
        return

    with open(SAMPLE_BOOK, "rb") as f:
        pdf_bytes = f.read()

    ext = extract_pdf_page(pdf_bytes, "TacticsCourse (1).pdf", 14)
    elements = classify_page(ext)
    games = extract_games_from_page(ext, elements)

    assert len(games) == 3
    # Game 1: A right fork
    g1 = games[0]
    assert g1.metadata.title == "A right fork"
    assert "John Head" in (g1.metadata.white or "")
    assert "Richard Bladek" in (g1.metadata.black or "")
    assert g1.metadata.eco == "C55"
    assert g1.replay.resolved is True
    assert g1.replay.ply_count == 17

    # Game 2: An ancient Queen fork
    g2 = games[1]
    assert g2.metadata.title == "An ancient Queen fork"
    assert "Greco" in (g2.metadata.white or "")
    assert g2.metadata.eco == "C41"
    assert g2.replay.resolved is True
    assert g2.replay.ply_count == 11

    # Game 3: Setting up a fork
    g3 = games[2]
    assert g3.metadata.title == "Setting up a fork"
    assert "Morgado" in (g3.metadata.white or "")
    assert g3.metadata.eco == "C42"
    assert g3.replay.resolved is True
    assert g3.replay.ply_count == 15


def test_real_book_page_11_games():
    if not os.path.exists(SAMPLE_BOOK):
        return

    with open(SAMPLE_BOOK, "rb") as f:
        pdf_bytes = f.read()

    ext = extract_pdf_page(pdf_bytes, "TacticsCourse (1).pdf", 11)
    elements = classify_page(ext)
    games = extract_games_from_page(ext, elements)

    assert len(games) == 3
    assert all(g.replay.resolved for g in games)


# 5. API Integration
def test_api_parse_includes_games():
    if not os.path.exists(SAMPLE_BOOK):
        return

    with open(SAMPLE_BOOK, "rb") as f:
        file_bytes = f.read()

    response = client.post(
        "/parse",
        files={"file": ("book.pdf", file_bytes, "application/pdf")},
        data={"page_number": 14},
    )
    assert response.status_code == 200
    data = response.json()
    assert "games" in data
    assert len(data["games"]) == 3
    for g in data["games"]:
        assert "game_id" in g
        assert "replay" in g
        assert g["replay"]["resolved"] is True
        assert "pgn" in g


def test_api_parse_pages_includes_games():
    if not os.path.exists(SAMPLE_BOOK):
        return

    with open(SAMPLE_BOOK, "rb") as f:
        file_bytes = f.read()

    response = client.post(
        "/parse/pages",
        files={"file": ("book.pdf", file_bytes, "application/pdf")},
        data={"start_page": 11, "end_page": 12},
    )
    assert response.status_code == 200
    data = response.json()
    assert "pages" in data
    assert len(data["pages"]) == 2
    for page in data["pages"]:
        assert "games" in page
        assert len(page["games"]) >= 1
