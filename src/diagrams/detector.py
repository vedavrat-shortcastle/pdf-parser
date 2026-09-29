"""
Dedicated chess diagram detector for Milestone 4.

Identifies chessboard regions on rendered pages or uploaded images.
Combines:
  1. Visual geometric detection (OpenCV contours, square aspect ratio, area constraints)
  2. Grid/checkerboard pattern verification (gradient peak analysis)
  3. Text/font structure hints when available (e.g. chess font symbols in embedded text)

Supports multiple diagrams per page and preserves natural reading order.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import cv2
import numpy as np
from PIL import Image

from src.diagrams.models import DiagramCandidate

if TYPE_CHECKING:
    from src.pdf.models import PageExtraction

_CHESS_FONT_HINT_RE = re.compile(r"cuuuuuuuuC|[rDbkq1-8]{8}", re.IGNORECASE)


def _compute_iou(b1: list[float], b2: list[float]) -> float:
    """Compute Intersection over Union between two bounding boxes [x0, y0, x1, y1]."""
    ix0 = max(b1[0], b2[0])
    iy0 = max(b1[1], b2[1])
    ix1 = min(b1[2], b2[2])
    iy1 = min(b1[3], b2[3])

    iw = max(0.0, ix1 - ix0)
    ih = max(0.0, iy1 - iy0)
    inter_area = iw * ih

    area1 = (b1[2] - b1[0]) * (b1[3] - b1[1])
    area2 = (b2[2] - b2[0]) * (b2[3] - b2[1])

    denom = area1 + area2 - inter_area
    return inter_area / denom if denom > 0 else 0.0


def _has_grid_pattern(gray_crop: np.ndarray) -> bool:
    """
    Verify that a candidate region contains internal grid/line structure
    consistent with a chessboard, preventing plain text blocks or solid
    illustrations from being misidentified.
    """
    h, w = gray_crop.shape
    if h < 64 or w < 64:
        return False

    gy = np.gradient(gray_crop.astype(np.float32), axis=0)
    gx = np.gradient(gray_crop.astype(np.float32), axis=1)

    pos_y = np.maximum(0, gy).sum(axis=1)
    neg_y = np.maximum(0, -gy).sum(axis=1)
    hough_y = pos_y * neg_y

    pos_x = np.maximum(0, gx).sum(axis=0)
    neg_x = np.maximum(0, -gx).sum(axis=0)
    hough_x = pos_x * neg_x

    def count_peaks(sig: np.ndarray) -> int:
        if sig.max() <= 0:
            return 0
        norm = sig / sig.max()
        peaks = 0
        for i in range(1, len(norm) - 1):
            if norm[i] > 0.12 and norm[i] > norm[i - 1] and norm[i] > norm[i + 1]:
                peaks += 1
        return peaks

    peaks_y = count_peaks(hough_y)
    peaks_x = count_peaks(hough_x)

    return peaks_y >= 4 and peaks_x >= 4


def detect_diagrams(
    image: Image.Image,
    page_number: int = 1,
    page_extraction: PageExtraction | None = None,
) -> list[DiagramCandidate]:
    """
    Detect chessboard diagram bounding boxes on a page.

    Args:
        image: Rendered PIL Image of the page.
        page_number: 1-indexed page number.
        page_extraction: Optional PageExtraction containing embedded text / OCR blocks.

    Returns:
        List of DiagramCandidate objects sorted in natural reading order.
    """
    img_w, img_h = image.size
    font_candidates: list[list[float]] = []

    # 1. Structure hints from embedded text if available
    if page_extraction and page_extraction.blocks:
        sx = img_w / float(page_extraction.width) if page_extraction.width > 0 else 1.0
        sy = img_h / float(page_extraction.height) if page_extraction.height > 0 else 1.0

        for block in page_extraction.blocks:
            if _CHESS_FONT_HINT_RE.search(block.text):
                bx0, by0, bx1, by1 = block.bbox.as_list()
                bw = bx1 - bx0
                bh = by1 - by0
                aspect = bw / bh if bh > 0 else 0
                if 0.70 <= aspect <= 1.30 and bw >= 80 and bh >= 80:
                    px0 = max(0.0, bx0 * sx)
                    py0 = max(0.0, by0 * sy)
                    px1 = min(float(img_w), bx1 * sx)
                    py1 = min(float(img_h), by1 * sy)
                    font_candidates.append([px0, py0, px1, py1])

    # 2. Visual geometric detection via OpenCV
    cv_img = cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)

    _, thresh = cv2.threshold(gray, 215, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    min_dim = min(img_w, img_h) * 0.12
    max_dim = min(img_w, img_h) * 0.85

    visual_candidates: list[tuple[list[float], float]] = []

    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        aspect = w / float(h) if h > 0 else 0
        if 0.88 <= aspect <= 1.12 and min_dim <= w <= max_dim and min_dim <= h <= max_dim:
            crop_patch = gray[y : y + h, x : x + w]
            if _has_grid_pattern(crop_patch):
                # Check if this visual candidate overlaps with a font block hint
                conf = 0.90
                for fbox in font_candidates:
                    if _compute_iou([x, y, x + w, y + h], fbox) > 0.30:
                        conf = 0.98
                        break
                visual_candidates.append(([float(x), float(y), float(x + w), float(y + h)], conf))

    # 3. Deduplicate nested contours (e.g. outer double border vs inner border)
    # Sort largest area first
    visual_candidates.sort(key=lambda c: (c[0][2] - c[0][0]) * (c[0][3] - c[0][1]), reverse=True)
    deduped: list[tuple[list[float], float]] = []

    for cand_bbox, conf in visual_candidates:
        overlap = False
        for existing_bbox, _ in deduped:
            if _compute_iou(cand_bbox, existing_bbox) > 0.50:
                overlap = True
                break
        if not overlap:
            deduped.append((cand_bbox, conf))

    # If no visual candidates were found at all on this page, fall back to font candidates that are reasonably sized
    if not deduped:
        for fbox in font_candidates:
            fw = fbox[2] - fbox[0]
            fh = fbox[3] - fbox[1]
            if min_dim <= fw <= max_dim and min_dim <= fh <= max_dim and 0.80 <= (fw / fh) <= 1.25:
                inset_box = [fbox[0] + fw * 0.08, fbox[1] + fh * 0.08, fbox[2] - fw * 0.02, fbox[3] - fh * 0.05]
                deduped.append((inset_box, 0.85))

    # 4. Sort in natural reading order: top-to-bottom, left-to-right
    deduped.sort(key=lambda c: (round(c[0][1] / 100.0), c[0][0]))

    results: list[DiagramCandidate] = []
    for idx, (bbox, conf) in enumerate(deduped):
        diag_id = f"diagram_{idx + 1:03d}"
        results.append(
            DiagramCandidate(
                diagram_id=diag_id,
                page=page_number,
                bbox=[round(coord, 1) for coord in bbox],
                confidence=conf,
                source_type="visual",
            )
        )

    return results
