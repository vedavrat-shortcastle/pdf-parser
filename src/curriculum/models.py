"""
Curriculum and ChessMethod Export Data Models.

Implements the hierarchical curriculum structure:
Book → Level → Chapter → Lesson → Activity
with explicit human-review flagging for unresolved items.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


@dataclass
class Activity:
    """An individual instructional unit (game replay, tactical puzzle, or explainer)."""

    id: str
    activity_type: Literal["game", "puzzle", "explainer"]
    title: str
    page_number: int
    fen: str
    pgn: str
    moves: list[str] = field(default_factory=list)
    solution: list[str] = field(default_factory=list)
    instructions: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    diagram_id: str | None = None
    resolved: bool = True
    needs_review: bool = False
    review_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_chessmethod_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.activity_type,
            "title": self.title,
            "page": self.page_number,
            "fen": self.fen,
            "pgn": self.pgn,
            "moves": self.moves,
            "solution": self.solution,
            "instructions": self.instructions,
            "metadata": self.metadata,
            "diagram_id": self.diagram_id,
            "status": "resolved" if self.resolved else "unresolved",
            "needs_review": self.needs_review,
            "review_reason": self.review_reason,
        }


@dataclass
class Lesson:
    """A subsection or specific tactical theme within a chapter (e.g. 3.1 Forks)."""

    id: str
    number: str
    title: str
    page_start: int
    page_end: int
    summary: str = ""
    activities: list[Activity] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "number": self.number,
            "title": self.title,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "summary": self.summary,
            "activities": [a.to_dict() for a in self.activities],
        }

    def to_chessmethod_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "lesson_number": self.number,
            "title": self.title,
            "pages": {"start": self.page_start, "end": self.page_end},
            "summary": self.summary,
            "activities_count": len(self.activities),
            "activities": [a.to_chessmethod_json() for a in self.activities],
        }


@dataclass
class Chapter:
    """A major topic / chapter of the book (e.g. Chapter 3: One-move ideas)."""

    id: str
    number: int
    title: str
    page_start: int
    page_end: int
    lessons: list[Lesson] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "number": self.number,
            "title": self.title,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "lessons": [l.to_dict() for l in self.lessons],
        }

    def to_chessmethod_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "chapter_number": self.number,
            "title": self.title,
            "pages": {"start": self.page_start, "end": self.page_end},
            "lessons_count": len(self.lessons),
            "lessons": [l.to_chessmethod_json() for l in self.lessons],
        }


@dataclass
class Level:
    """A curriculum level tier grouping related chapters."""

    id: str
    title: str
    chapters: list[Chapter] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "chapters": [c.to_dict() for c in self.chapters],
        }

    def to_chessmethod_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "level_name": self.title,
            "chapters_count": len(self.chapters),
            "chapters": [c.to_chessmethod_json() for c in self.chapters],
        }


@dataclass
class BookCurriculum:
    """The root curriculum container for an entire parsed book."""

    book_title: str
    source_filename: str
    total_pages: int
    total_chapters: int
    total_lessons: int
    total_activities: int
    resolved_activities: int
    needs_review_count: int
    levels: list[Level] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "book_title": self.book_title,
            "source_filename": self.source_filename,
            "total_pages": self.total_pages,
            "total_chapters": self.total_chapters,
            "total_lessons": self.total_lessons,
            "total_activities": self.total_activities,
            "resolved_activities": self.resolved_activities,
            "needs_review_count": self.needs_review_count,
            "levels": [lvl.to_dict() for lvl in self.levels],
        }

    def to_chessmethod_json(self) -> dict[str, Any]:
        resolution_rate = (
            (self.resolved_activities / self.total_activities * 100.0)
            if self.total_activities > 0
            else 100.0
        )
        return {
            "$schema": "https://chessmethod.com/schemas/curriculum-v1.json",
            "format": "ChessMethod-Curriculum",
            "version": "1.0",
            "book": {
                "title": self.book_title,
                "source": self.source_filename,
                "page_count": self.total_pages,
            },
            "curriculum_stats": {
                "total_chapters": self.total_chapters,
                "total_lessons": self.total_lessons,
                "total_activities": self.total_activities,
                "resolved_activities": self.resolved_activities,
                "needs_review_count": self.needs_review_count,
                "resolution_rate_percent": round(resolution_rate, 1),
            },
            "levels": [lvl.to_chessmethod_json() for lvl in self.levels],
        }
