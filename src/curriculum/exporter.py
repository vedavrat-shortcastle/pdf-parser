"""
ChessMethod JSON Curriculum Exporter.

Serializes BookCurriculum objects into the standard ChessMethod export JSON schema.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.curriculum.models import BookCurriculum


def export_chessmethod_curriculum(curriculum: BookCurriculum, indent: int = 2) -> str:
    """Serialize a BookCurriculum instance into standard ChessMethod JSON string."""
    data = curriculum.to_chessmethod_json()
    return json.dumps(data, indent=indent, ensure_ascii=False)


def save_chessmethod_json(curriculum: BookCurriculum, target_path: str | Path) -> Path:
    """Save ChessMethod JSON export to a file on disk."""
    path = Path(target_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    json_str = export_chessmethod_curriculum(curriculum)
    path.write_text(json_str, encoding="utf-8")
    return path
