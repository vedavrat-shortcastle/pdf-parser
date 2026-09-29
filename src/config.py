"""
Central configuration for the Parsing Agent backend.

Kept intentionally tiny for Stage 1. Nothing here talks to a database,
because this project does not use one (see README: "No Database").
"""

from __future__ import annotations

# Maximum upload size accepted by /parse, in bytes. Prevents someone from
# accidentally (or not) sending a 2 GB file into memory.
MAX_UPLOAD_BYTES = 60 * 1024 * 1024  # 60 MB

# File extensions / content-types Stage 1 knows how to open.
ALLOWED_PDF_EXTENSIONS = {".pdf"}
ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
ALLOWED_EXTENSIONS = ALLOWED_PDF_EXTENSIONS | ALLOWED_IMAGE_EXTENSIONS

# DPI used when rendering a PDF page to an image for display in the UI.
# 150 is a reasonable balance of legibility vs. payload size for a book page.
PAGE_RENDER_DPI = 150

# --- OCR (Milestone 2) ---
# Tesseract language pack to use. "eng" ships with a default `brew
# install tesseract`; other languages need their own trained data file
# (see README, "Known OCR limitations").
OCR_LANGUAGE = "eng"

# If a PDF page's embedded text (stripped) is shorter than this many
# characters, it's treated as "clearly insufficient" and OCR is run on
# the rendered page image too, alongside (not instead of) the embedded
# text. This catches pages that are mostly a scanned diagram with just
# a stray page number or caption as real PDF text. Raw image uploads
# always run OCR regardless of this threshold, since they never have an
# embedded text layer at all.
MIN_SUFFICIENT_EMBEDDED_TEXT_CHARS = 20

# Maximum number of PDF pages /parse/pages will process in one request.
# Raised to 100 to support full chapters and books.
MAX_PAGE_RANGE = 100

# CORS origins allowed to call this API. The Vite dev server defaults to
# port 5173; 3000 is included in case someone changes the Vite config.
CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
