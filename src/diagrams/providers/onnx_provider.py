"""
ONNX tile-based chessboard recognizer provider.

Utilizes the compact CNN (330k parameters, 1.3 MB) from scoriiu/fenshot,
running locally and offline via onnxruntime. Slices the board into 64 normalized
32x32 tiles, infers piece probabilities, resolves board orientation, and
arbitrates grid alignment to maximize confidence.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import numpy as np
import onnxruntime as ort
from PIL import Image

from src.diagrams.recognizer import DiagramRecognizer, RawRecognitionResult

LABELS = "1KQRBNPkqrbnp"
CONFIDENCE_FLOOR = 0.70
BOARD_PX = 256
TILE_PX = 32
DEFAULT_MODEL_PATH = Path(__file__).resolve().parent.parent / "assets" / "chess-tiles-v2.onnx"


def _probs_to_placement(probs: np.ndarray) -> tuple[str, list[float], float, float]:
    """
    Convert model output probabilities (shape 64, 13) to FEN placement string
    and confidence scores.
    """
    names: list[str] = []
    confs: list[float] = []

    for i in range(64):
        best_idx = int(np.argmax(probs[i]))
        best_conf = float(probs[i, best_idx])
        names.append(LABELS[best_idx])
        confs.append(best_conf)

    ranks: list[str] = []
    for r in range(7, -1, -1):
        rank_str = "".join(names[r * 8 : r * 8 + 8])
        rank_str = re.sub(r"1+", lambda m: str(len(m.group(0))), rank_str)
        ranks.append(rank_str)

    placement = "/".join(ranks)
    mean_conf = float(np.mean(confs))
    min_conf = float(np.min(confs))
    return placement, confs, mean_conf, min_conf


def _flip_placement(placement: str) -> str:
    """Flip placement 180 degrees (Black at bottom -> White at bottom)."""
    ranks = placement.split("/")
    reversed_ranks = [r[::-1] for r in reversed(ranks)]
    return "/".join(reversed_ranks)


def _resolve_orientation(placement: str) -> tuple[str, str]:
    """
    Determine board orientation from pawn-advance direction.
    White pawns advance up (ranks 2 -> 8), black pawns advance down (ranks 7 -> 1).
    """
    ranks = placement.split("/")
    white_ranks: list[int] = []
    black_ranks: list[int] = []

    for i, rank_str in enumerate(ranks):
        rank_num = 8 - i
        for ch in rank_str:
            if ch == "P":
                white_ranks.append(rank_num)
            elif ch == "p":
                black_ranks.append(rank_num)

    if not white_ranks or not black_ranks:
        return placement, "white"

    mean_white = sum(white_ranks) / len(white_ranks)
    mean_black = sum(black_ranks) / len(black_ranks)

    # In natural orientation, white pawns sit on lower ranks than black pawns
    if mean_white > mean_black:
        flipped = _flip_placement(placement)
        return flipped, "black"

    return placement, "white"


def _extract_tiles_array(img: Image.Image) -> np.ndarray:
    """
    Resize board crop to 256x256, normalize to [0, 1], and slice 64 32x32 tiles.
    Tile order: tile k = rank * 8 + file with A1 at bottom-left.
    """
    gray = img.convert("L")
    resized = gray.resize((BOARD_PX, BOARD_PX), Image.Resampling.BILINEAR)
    board_arr = np.array(resized, dtype=np.float32) / 255.0

    tiles = np.zeros((64, TILE_PX * TILE_PX), dtype=np.float32)
    for rank in range(8):
        for file in range(8):
            k = rank * 8 + file
            src_y0 = (7 - rank) * TILE_PX
            src_x0 = file * TILE_PX
            tile_patch = board_arr[src_y0 : src_y0 + TILE_PX, src_x0 : src_x0 + TILE_PX]
            tiles[k] = tile_patch.flatten()

    return tiles


class OnnxTileRecognizer(DiagramRecognizer):
    """Local CNN recognizer using ONNX runtime."""

    def __init__(self, model_path: str | Path | None = None) -> None:
        self.model_path = Path(model_path or DEFAULT_MODEL_PATH)
        if not self.model_path.exists():
            raise FileNotFoundError(f"ONNX model file not found at: {self.model_path}")

        opts = ort.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 2
        self.session = ort.InferenceSession(
            str(self.model_path), sess_options=opts, providers=["CPUExecutionProvider"]
        )

    def _infer_image(self, img: Image.Image) -> tuple[str, list[float], float, float]:
        tiles = _extract_tiles_array(img)
        outputs = self.session.run(["probs"], {"tiles": tiles})
        probs = outputs[0]
        return _probs_to_placement(probs)

    def recognize(self, image: Image.Image) -> RawRecognitionResult:
        """
        Recognize chessboard with alignment arbitration.
        Evaluates raw crop alongside slight border-inset candidates (to handle
        printed book diagram border lines) and selects the candidate with
        highest mean piece confidence.
        """
        w, h = image.size
        candidates = [image]

        # Multi-candidate alignment: test 2px and 4px insets if diagram is large enough
        if w >= 80 and h >= 80:
            for inset in [2, 4]:
                if w > 2 * inset + 40 and h > 2 * inset + 40:
                    candidates.append(image.crop((inset, inset, w - inset, h - inset)))

        best_result: tuple[str, list[float], float, float] | None = None

        for cand in candidates:
            res = self._infer_image(cand)
            placement, confs, mean_c, min_c = res
            if best_result is None or mean_c > best_result[2]:
                best_result = res

        assert best_result is not None
        placement, confs, mean_conf, min_conf = best_result

        # Resolve board orientation
        placement, orientation = _resolve_orientation(placement)

        is_reliable = min_conf >= CONFIDENCE_FLOOR

        return RawRecognitionResult(
            piece_placement=placement,
            mean_confidence=mean_conf,
            min_confidence=min_conf,
            square_confidences=confs,
            orientation=orientation,
            is_reliable=is_reliable,
        )
