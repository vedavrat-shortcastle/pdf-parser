"""
SAN (Standard Algebraic Notation) token normalization and validation.

Handles:
- OCR character confusion ('0-0' vs 'O-O', '0-0-0' vs 'O-O-O', 'o-o')
- Unicode figurine notation (♔, ♕, ♖, ♗, ♘, ♚, etc.)
- Move number prefixes ('1.', '1...', '10. ...')
- Annotation and evaluation glyphs ('?!', '!? ', '?', '!', '??', '!!')
- Capture symbols ('x', 'X', ':', '*')
- Promotion syntax ('e8=Q', 'e8(Q)', 'e8/Q', 'e8Q')
- Game result tokens ('1-0', '0-1', '1/2-1/2', '½-½', '*')
"""

from __future__ import annotations

import re

FIGURINE_MAP: dict[str, str] = {
    "♔": "K",
    "♕": "Q",
    "♖": "R",
    "♗": "B",
    "♘": "N",
    "♙": "P",
    "♚": "K",
    "♛": "Q",
    "♜": "R",
    "♝": "B",
    "♞": "N",
    "♟": "P",
}

_CASTLING_LONG_RE = re.compile(r"^[0oO][—-][0oO][—-][0oO]", re.IGNORECASE)
_CASTLING_SHORT_RE = re.compile(r"^[0oO][—-][0oO]", re.IGNORECASE)
_MOVE_PREFIX_RE = re.compile(r"^(\d+)(\.{1,3})\s*(.*)$")
_EVAL_GLYPH_RE = re.compile(r"([?!]+)$")
_GAME_RESULT_RE = re.compile(r"^(1-0|0-1|1/2-1/2|½-½|\*)$")
_PROMOTION_PAREN_RE = re.compile(r"([a-h][18])\(([QRBNqrbn])\)")
_PROMOTION_SLASH_RE = re.compile(r"([a-h][18])/([QRBNqrbn])")
_PROMOTION_BARE_RE = re.compile(r"([a-h][18])([QRBN])(?=[+#]|\b|$)")

_SAN_REGEX = re.compile(
    r"^(O-O-O|O-O|[KQRBN]?[a-h]?[1-8]?x?[a-h][1-8](=[QRBN])?[+#]?)$"
)


def normalize_figurines(text: str) -> str:
    """Replace Unicode chess figurine characters with ASCII piece letters."""
    for fig, letter in FIGURINE_MAP.items():
        if fig in text:
            # Pawns in SAN don't use 'P' unless disambiguated; figurine pawns are stripped if followed by file
            if letter == "P":
                text = re.sub(rf"{re.escape(fig)}([a-h])", r"\1", text)
                text = text.replace(fig, "")
            else:
                text = text.replace(fig, letter)
    return text


def is_game_result(token: str) -> bool:
    """Check if token is a standard game termination result."""
    return bool(_GAME_RESULT_RE.match(token.strip()))


def normalize_game_result(token: str) -> str:
    """Normalize game result token (e.g. ½-½ -> 1/2-1/2)."""
    t = token.strip()
    if t == "½-½":
        return "1/2-1/2"
    return t


def extract_annotation(token: str) -> tuple[str, str | None]:
    """
    Split evaluation glyphs ('?!', '!', etc.) from the SAN move token,
    preserving check '+' or checkmate '#' on the move.
    """
    m = _EVAL_GLYPH_RE.search(token)
    if m:
        glyph = m.group(1)
        base = token[: m.start()]
        return base, glyph
    return token, None


def normalize_san_token(token: str) -> str:
    """
    Normalize a single move token:
    - Replace figurines
    - Normalize castling (0-0 -> O-O)
    - Normalize capture glyphs (: or * -> x)
    - Normalize promotion format (e8(Q) -> e8=Q)
    """
    t = token.strip().strip(",;")
    if not t:
        return ""

    t = normalize_figurines(t)

    # Castling check with suffixes (+, #)
    suffix = ""
    if t.endswith("+") or t.endswith("#"):
        suffix = t[-1]
        t = t[:-1]

    if _CASTLING_LONG_RE.match(t):
        return f"O-O-O{suffix}"
    if _CASTLING_SHORT_RE.match(t):
        return f"O-O{suffix}"

    t = f"{t}{suffix}"

    # Normalize capture symbols (colon, asterisk, capital X)
    t = re.sub(r"([a-hKQRBN1-8])[*:]", r"\1x", t)
    t = re.sub(r"([a-hKQRBN1-8])X([a-h])", r"\1x\2", t)

    # Promotions: e8(Q) or e8/Q or bare e8Q -> e8=Q
    t = _PROMOTION_PAREN_RE.sub(r"\1=\2", t)
    t = _PROMOTION_SLASH_RE.sub(r"\1=\2", t)
    t = _PROMOTION_BARE_RE.sub(r"\1=\2", t)

    return t


def parse_move_token(token: str) -> tuple[int | None, bool | None, str, str | None]:
    """
    Parse a raw token that may include move numbers and annotations.
    Returns: (move_number, is_black, normalized_san, annotation)
    """
    raw = token.strip()
    move_num = None
    is_black = None
    remainder = raw

    m = _MOVE_PREFIX_RE.match(raw)
    if m:
        num_str, dots, rest = m.groups()
        move_num = int(num_str)
        is_black = len(dots) >= 2
        remainder = rest

    base, annotation = extract_annotation(remainder)
    norm_san = normalize_san_token(base)
    if not is_valid_san_format(norm_san):
        norm_san = ""

    return move_num, is_black, norm_san, annotation


def is_valid_san_format(san: str) -> bool:
    """Check if the string matches valid SAN syntax pattern."""
    return bool(_SAN_REGEX.match(san))
