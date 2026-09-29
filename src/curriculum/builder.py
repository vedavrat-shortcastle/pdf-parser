"""
Curriculum Builder: transforms page extractions, diagrams, and games
into a book-order-preserving hierarchical curriculum:
Book → Level → Chapter → Lesson → Activity
"""

from __future__ import annotations

import base64
import io
import logging
import re
from typing import Any

from PIL import Image

from src.chess.pipeline import process_page_chess
from src.curriculum.models import (
    Activity,
    BookCurriculum,
    Chapter,
    Lesson,
    Level,
)
from src.diagrams.pipeline import process_page_diagrams
from src.pdf.extractor import extract_pdf_page, get_pdf_page_count
from src.structure.detector import classify_page

logger = logging.getLogger(__name__)

_CHAPTER_RE = re.compile(r"^(?:Chapter\s+)?(\d+)\s+([A-Za-z].*)$", re.IGNORECASE)
_LESSON_RE = re.compile(r"^(\d+\.\d+)\s+([A-Za-z].*)$", re.IGNORECASE)


def _detect_heading_in_text(text: str) -> tuple[str | None, str | None, str | None]:
    """
    Detect if any line in text represents a Chapter or Lesson heading.
    Returns: (type, number_str, title_str) where type is 'chapter' or 'lesson' or None.
    """
    for line in text.splitlines():
        line = line.strip()
        if not line or len(line) > 90:
            continue
        if line.startswith("1.") or line.startswith("cuu") or "–" in line:
            continue

        m_les = _LESSON_RE.match(line)
        if m_les:
            num, title = m_les.groups()
            return "lesson", num, title.strip()

        m_chap = _CHAPTER_RE.match(line)
        if m_chap:
            num, title = m_chap.groups()
            t_strip = title.strip()
            # Avoid single move results or game lines
            if not t_strip.startswith("Qx") and not t_strip.startswith("0-") and not t_strip.startswith("1-"):
                return "chapter", num, t_strip

    return None, None, None


def assemble_curriculum_from_pages(
    pages_data: list[dict[str, Any]],
    filename: str,
    book_title: str | None = None,
) -> BookCurriculum:
    """
    Assemble processed pages (with structure_elements, diagrams, games)
    into a structured BookCurriculum hierarchy.
    """
    title = book_title or filename.replace(".pdf", "").replace("_", " ").title()

    chapters: list[Chapter] = []
    current_chapter: Chapter | None = None
    current_lesson: Lesson | None = None

    def ensure_chapter(chap_num: int, chap_title: str, page_num: int) -> Chapter:
        nonlocal current_chapter, current_lesson
        if current_chapter is None or current_chapter.number != chap_num:
            current_chapter = Chapter(
                id=f"chap_{chap_num}",
                number=chap_num,
                title=chap_title,
                page_start=page_num,
                page_end=page_num,
                lessons=[],
            )
            chapters.append(current_chapter)
            current_lesson = None
        return current_chapter

    def ensure_lesson(les_num: str, les_title: str, page_num: int) -> Lesson:
        nonlocal current_chapter, current_lesson
        if current_chapter is None:
            ensure_chapter(1, "Introduction / Fundamentals", page_num)

        if current_lesson is None or current_lesson.number != les_num:
            current_lesson = Lesson(
                id=f"les_{les_num.replace('.', '_')}",
                number=les_num,
                title=les_title,
                page_start=page_num,
                page_end=page_num,
                summary="",
                activities=[],
            )
            current_chapter.lessons.append(current_lesson)
        return current_lesson

    for p_data in pages_data:
        p_num = p_data.get("page_number", 1)
        p_text = p_data.get("text", "")
        games = p_data.get("games", [])
        diagrams = p_data.get("diagrams", [])

        # Check for chapter or lesson headings on this page
        h_type, h_num, h_title = _detect_heading_in_text(p_text)
        if h_type == "chapter" and h_num and h_title:
            try:
                c_num = int(h_num)
                ensure_chapter(c_num, h_title, p_num)
            except ValueError:
                pass
        elif h_type == "lesson" and h_num and h_title:
            ensure_lesson(h_num, h_title, p_num)

        # Make sure default containers exist if no heading on page
        if current_chapter is None:
            ensure_chapter(1, "Chapter 1: Fundamentals", p_num)
        if current_lesson is None:
            ensure_lesson(f"{current_chapter.number}.1", "Overview", p_num)

        # Update page range bounds
        current_chapter.page_end = max(current_chapter.page_end, p_num)
        current_lesson.page_end = max(current_lesson.page_end, p_num)

        # Convert games & puzzles on this page into Activities
        for g_idx, g in enumerate(games):
            g_meta = g.get("metadata", {})
            g_replay = g.get("replay", {})
            g_id = g.get("game_id", f"p{p_num}_g{g_idx+1}")
            g_kind = g.get("kind", "game")
            g_title = g_meta.get("title") or (
                f"{g_meta.get('white')} vs {g_meta.get('black')}"
                if g_meta.get("white") and g_meta.get("black")
                else f"Exercise {g_idx + 1}"
            )

            is_resolved = bool(g_replay.get("resolved", False))
            failing_reason = g_replay.get("unresolved_reason")
            moves = [m.get("san") for m in g_replay.get("half_moves", []) if m.get("san")]
            initial_fen = g_replay.get("initial_fen", "")

            # Match with diagram if any
            diag_id = None
            diag_matches = g_replay.get("diagram_matches", [])
            if diag_matches:
                diag_id = diag_matches[0].get("diagram_id")

            act = Activity(
                id=f"act_{g_id}",
                activity_type="game" if g_kind == "game" else "puzzle",
                title=g_title,
                page_number=p_num,
                fen=initial_fen,
                pgn=g.get("pgn", ""),
                moves=moves,
                solution=moves if g_kind == "puzzle" else [],
                instructions=f"{g_title} (Page {p_num})",
                metadata=g_meta,
                diagram_id=diag_id,
                resolved=is_resolved,
                needs_review=not is_resolved,
                review_reason=failing_reason,
            )
            current_lesson.activities.append(act)

    # Calculate metrics
    total_activities = sum(
        len(les.activities)
        for chap in chapters
        for les in chap.lessons
    )
    resolved_activities = sum(
        1
        for chap in chapters
        for les in chap.lessons
        for a in les.activities
        if a.resolved
    )
    needs_review_count = total_activities - resolved_activities
    total_lessons = sum(len(chap.lessons) for chap in chapters)

    level = Level(
        id="level_default",
        title="Comprehensive Tactics Curriculum",
        chapters=chapters,
    )

    return BookCurriculum(
        book_title=title,
        source_filename=filename,
        total_pages=len(pages_data),
        total_chapters=len(chapters),
        total_lessons=total_lessons,
        total_activities=total_activities,
        resolved_activities=resolved_activities,
        needs_review_count=needs_review_count,
        levels=[level],
    )


def build_curriculum_from_pdf(
    file_bytes: bytes,
    filename: str,
    start_page: int = 1,
    end_page: int | None = None,
) -> BookCurriculum:
    """
    End-to-end pipeline: extracts pages from PDF, runs OCR (if needed),
    detects diagrams, replays moves, and builds the full BookCurriculum.
    """
    total_pdf_pages = get_pdf_page_count(file_bytes, filename)
    last_page = min(end_page or total_pdf_pages, total_pdf_pages)

    pages_data: list[dict[str, Any]] = []

    for p in range(start_page, last_page + 1):
        try:
            ext = extract_pdf_page(file_bytes, filename, p)
            elements = classify_page(ext)

            diag_dicts: list[dict[str, Any]] = []
            if ext.image_base64_png:
                img_bytes = base64.b64decode(ext.image_base64_png)
                page_img = Image.open(io.BytesIO(img_bytes))
                diagrams = process_page_diagrams(
                    image=page_img,
                    page_number=p,
                    page_text=ext.text,
                    page_extraction=ext,
                    structure_elements=elements,
                )
                diag_dicts = [d.to_dict() for d in diagrams]

            games = process_page_chess(ext, elements, diag_dicts)
            game_dicts = [g.to_dict() for g in games]

            pages_data.append(
                {
                    "page_number": p,
                    "text": ext.text,
                    "structure_elements": [e.to_dict() for e in elements],
                    "diagrams": diag_dicts,
                    "games": game_dicts,
                }
            )
        except Exception as exc:
            logger.warning("Error processing page %s during curriculum build: %s", p, exc)

    return assemble_curriculum_from_pages(
        pages_data=pages_data,
        filename=filename,
    )
