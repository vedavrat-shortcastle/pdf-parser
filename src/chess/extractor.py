"""
Extraction of chess games, tactical puzzles, and move sequences from
page structure elements and OCR/embedded text.
"""

from __future__ import annotations

import re
from typing import Any

import chess

from src.chess.models import GameMetadata, GameOrPuzzle
from src.chess.pgn import build_pgn
from src.chess.replay import replay_moves
from src.chess.san import is_game_result, normalize_game_result, parse_move_token
from src.pdf.models import PageExtraction
from src.structure.models import StructureElement

# Strict player regex: letters, periods, commas, spaces, apostrophes, hyphens, and optional [ECO]
_PLAYER_LINE_RE = re.compile(
    r"^([A-Za-z,.\s\'-]+?)\s*[-–—]\s*([A-Za-z,.\s\'-]+?)(?:\s*\[([A-E]\d{2})\])?$"
)
_ECO_ONLY_RE = re.compile(r"^([A-Za-z0-9,.\s\'-]+?)\s*\[([A-E]\d{2})\]$")
_YEAR_RE = re.compile(r"\b(1[789]\d\d|20\d\d)\b")
_MOVE_START_RE = re.compile(r"\b1\s*\.\s*[a-hKQRBN]")
_DIAGRAM_FONT_START_RE = re.compile(r"^cuuuuuuuuC", re.IGNORECASE)


def strip_diagram_font_lines(text: str) -> str:
    """Remove font-based diagram representations from text blocks."""
    lines = text.splitlines()
    clean: list[str] = []
    in_diagram_font = False
    for line in lines:
        stripped = line.strip()
        if _DIAGRAM_FONT_START_RE.match(stripped):
            in_diagram_font = True
            continue
        if in_diagram_font:
            if stripped.startswith("v,.") or stripped.startswith("v"):
                in_diagram_font = False
            continue
        clean.append(line)
    return "\n".join(clean)


def fix_hyphenated_moves(text: str) -> str:
    """Fix moves or castling tokens split across line breaks (e.g. 10.0-\n0 or e-\n4)."""
    # Castling hyphenation: 0-\n0 or O-\nO
    text = re.sub(r"([0oO])-\s*\n\s*([0oO])", r"\1-\2", text)
    # Piece / pawn hyphenation: e.g. Nf-\n3
    text = re.sub(r"([a-hKQRBN])-\s*\n\s*([a-hKQRBN1-8])", r"\1\2", text)
    return text


def parse_metadata_from_text(text: str) -> GameMetadata:
    """Extract game metadata (title, white, black, eco, date, site) from text lines."""
    clean_text = strip_diagram_font_lines(text)
    lines = [line.strip() for line in clean_text.splitlines() if line.strip()]
    metadata = GameMetadata()

    for i, line in enumerate(lines):
        if is_game_result(line) or _MOVE_START_RE.search(line) or line.startswith("cuu"):
            continue

        m = _PLAYER_LINE_RE.match(line)
        if m:
            w, b, eco = m.groups()
            w_strip, b_strip = w.strip(), b.strip()
            # Must not be single characters or noise
            if len(w_strip) >= 2 and len(b_strip) >= 2:
                metadata.white = w_strip
                metadata.black = b_strip
                if eco:
                    metadata.eco = eco
                # Title might be the preceding line
                if i > 0 and len(lines[i - 1]) <= 60 and not lines[i - 1].startswith("cuu"):
                    metadata.title = lines[i - 1]
                # Site / Date might be following line
                if i + 1 < len(lines):
                    next_line = lines[i + 1]
                    year_m = _YEAR_RE.search(next_line)
                    if year_m:
                        metadata.date = year_m.group(1)
                    metadata.site = next_line
                continue

        eco_m = _ECO_ONLY_RE.match(line)
        if eco_m and not metadata.eco:
            title_part, eco = eco_m.groups()
            metadata.title = title_part.strip()
            metadata.eco = eco

    return metadata


def parse_moves_from_text(text: str) -> tuple[list[dict[str, Any]], str]:
    """
    Extract raw move tokens, handle anchor points ('U'), and extract result token.
    Returns: (parsed_moves_list, result_string)
    """
    clean_text = fix_hyphenated_moves(strip_diagram_font_lines(text))
    raw_tokens = clean_text.split()
    parsed: list[dict[str, Any]] = []
    result = "*"

    for tok in raw_tokens:
        tok_clean = tok.strip()
        if not tok_clean:
            continue
        if is_game_result(tok_clean):
            result = normalize_game_result(tok_clean)
            continue
        if tok_clean == "U":
            if parsed:
                parsed[-1]["diagram_anchor"] = True
            continue

        move_num, is_black, san, annotation = parse_move_token(tok_clean)
        if san:
            parsed.append(
                {
                    "san": san,
                    "raw_token": tok_clean,
                    "move_number": move_num,
                    "turn": "black" if is_black else "white" if is_black is not None else None,
                    "annotation": annotation,
                    "diagram_anchor": False,
                }
            )

    return parsed, result


def extract_games_from_page(
    page_extraction: PageExtraction,
    structure_elements: list[StructureElement],
    diagrams: list[dict[str, Any]] | None = None,
) -> list[GameOrPuzzle]:
    """
    Identify and extract all games and tactical puzzles on a page.
    Replays legal moves, aligns intermediate positions with diagrams,
    and produces validated GameOrPuzzle models.
    """
    candidate_diagrams = diagrams or []
    games: list[GameOrPuzzle] = []

    # Partition structure elements into game/puzzle candidates
    element_groups: list[list[StructureElement]] = []
    cur_group: list[StructureElement] = []

    for el in structure_elements:
        text = strip_diagram_font_lines(el.text).strip()
        if not text:
            continue

        first_line = text.splitlines()[0]
        is_new_game = False

        if any(e.element_type == "moves" for e in cur_group):
            # If current group already contains moves, check if a new game header or move 1 begins
            if _MOVE_START_RE.search(text) or _PLAYER_LINE_RE.match(first_line):
                is_new_game = True
            elif len(text.splitlines()) > 1 and _PLAYER_LINE_RE.match(text.splitlines()[1]):
                is_new_game = True

        if is_new_game and cur_group:
            element_groups.append(cur_group)
            cur_group = []

        cur_group.append(el)

    if cur_group:
        element_groups.append(cur_group)

    for grp in element_groups:
        moves_list: list[dict[str, Any]] = []
        metadata = GameMetadata()
        combined_text = "\n".join(e.text for e in grp)
        meta = parse_metadata_from_text(combined_text)
        metadata.title = meta.title
        metadata.white = meta.white
        metadata.black = meta.black
        metadata.eco = meta.eco
        metadata.date = meta.date
        metadata.site = meta.site

        source_indices: list[int] = [e.index_on_page for e in grp]

        for el in grp:
            clean_text = strip_diagram_font_lines(el.text).strip()
            if not clean_text:
                continue

            # Only extract moves from 'moves' blocks or short move lines
            if el.element_type == "moves":
                el_moves, el_res = parse_moves_from_text(clean_text)
                moves_list.extend(el_moves)
                if el_res != "*":
                    metadata.result = el_res
            elif el.element_type == "explainer":
                # Check if this explainer contains a standalone move sequence (e.g. U 9.Nexc7+)
                # or continuation line like 9...Nxd2 0-1
                tokens = clean_text.split()
                has_move_num = any(re.match(r"^\d+\.", t) for t in tokens) or "U" in tokens
                has_res = any(is_game_result(t) for t in tokens)
                if has_move_num or has_res:
                    el_moves, el_res = parse_moves_from_text(clean_text)
                    if el_moves:
                        moves_list.extend(el_moves)
                    if el_res != "*":
                        metadata.result = el_res

        if not moves_list:
            continue

        # Determine starting FEN: starting position vs puzzle position
        first_move = moves_list[0]
        starts_at_first_move = (
            first_move.get("move_number") == 1
            and first_move.get("turn") != "black"
        )

        initial_fen = chess.STARTING_FEN if starts_at_first_move else ""
        kind: str = "game" if starts_at_first_move else "puzzle"

        # If it doesn't start at move 1, attempt to find a matching diagram as starting position
        if not starts_at_first_move and candidate_diagrams:
            for diag in candidate_diagrams:
                diag_fen = diag.get("candidate_fen") or diag.get("fen")
                if diag_fen:
                    test_replay = replay_moves([moves_list[0]], initial_fen=diag_fen)
                    if test_replay.resolved:
                        initial_fen = diag_fen
                        break

        replay = replay_moves(
            moves_list,
            initial_fen=initial_fen or chess.STARTING_FEN,
            candidate_diagrams=candidate_diagrams,
        )

        pgn_text = build_pgn(metadata, replay.half_moves, initial_fen=replay.initial_fen)
        game_id = f"p{page_extraction.page_number}_g{len(games) + 1}"

        games.append(
            GameOrPuzzle(
                game_id=game_id,
                kind=kind,  # type: ignore[arg-type]
                page_number=page_extraction.page_number,
                metadata=metadata,
                replay=replay,
                pgn=pgn_text,
                source_element_indices=source_indices,
            )
        )

    return games
