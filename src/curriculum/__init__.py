"""
Curriculum assembly and ChessMethod export package (Final Phase).

Provides:
- Hierarchical models: BookCurriculum, Level, Chapter, Lesson, Activity
- Builders: assemble_curriculum_from_pages, build_curriculum_from_pdf
- Exporters: export_chessmethod_curriculum, save_chessmethod_json
"""

from src.curriculum.builder import (
    assemble_curriculum_from_pages,
    build_curriculum_from_pdf,
)
from src.curriculum.exporter import (
    export_chessmethod_curriculum,
    save_chessmethod_json,
)
from src.curriculum.models import (
    Activity,
    BookCurriculum,
    Chapter,
    Lesson,
    Level,
)

__all__ = [
    "Activity",
    "Lesson",
    "Chapter",
    "Level",
    "BookCurriculum",
    "assemble_curriculum_from_pages",
    "build_curriculum_from_pdf",
    "export_chessmethod_curriculum",
    "save_chessmethod_json",
]
