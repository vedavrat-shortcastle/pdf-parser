"""
FastAPI application for the Parsing Agent — Stage 1 + Milestone 2 (OCR)
+ Milestone 3 (structure detection & cross-page continuity).

Endpoints (see README for the planned /validate, /build-curriculum
endpoints that come with later stages):

    GET  /health       -> liveness check + which stage/milestone is implemented
    POST /parse        -> upload a PDF (with a page number) or a single
                           image, get back the PageExtraction JSON, which
                           now includes `has_embedded_text`, `ocr_used`,
                           `ocr`, and `structure_elements`
    POST /parse/pages  -> upload a PDF + a small page range (Milestone
                           3, capped at MAX_PAGE_RANGE pages), get back
                           each page's extraction plus cross-page
                           `sections` showing where a game/explanation
                           continues across a page break

Nothing here writes the uploaded file to disk. Bytes are read into
memory, processed, and discarded when the request finishes. There is no
database (see src/config.py and README, "No Database").
"""

from __future__ import annotations

import base64
import io
import os

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image

from src.config import (
    ALLOWED_EXTENSIONS,
    ALLOWED_PDF_EXTENSIONS,
    CORS_ORIGINS,
    MAX_PAGE_RANGE,
    MAX_UPLOAD_BYTES,
)
from src.chess.pipeline import process_page_chess
from src.curriculum.builder import build_curriculum_from_pdf
from src.diagrams.pipeline import process_page_diagrams
from src.pdf.extractor import (
    ExtractionError,
    extract_image_page,
    extract_pdf_page,
    get_pdf_page_count,
    guess_source_kind,
)
from src.structure.detector import classify_page, detect_sections

app = FastAPI(
    title="ShortCastle Parsing Agent API",
    description="Stage 1: PDF/image page extraction for the chess book parsing pipeline.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "stage": (
            "1 - PDF/image extraction, 2 - local OCR (Tesseract), "
            "3 - structure detection & cross-page continuity, "
            "4 - chess diagram detection + diagram-to-FEN, "
            "5 - move extraction, SAN normalization, PGN reconstruction & python-chess replay, "
            "6 - curriculum hierarchy assembly & ChessMethod JSON export"
        ),
        "implemented_endpoints": ["/health", "/parse", "/parse/pages", "/pdf/page-count", "/build-curriculum"],
        "planned_endpoints": ["/validate"],
    }


@app.post("/parse")
async def parse(
    file: UploadFile = File(...),
    page_number: int = Form(1),
) -> dict:
    """
    Parse one page.

    - For a PDF: `page_number` (1-indexed) selects which page to extract.
    - For an image (PNG/JPG/JPEG/WEBP): `page_number` is ignored — the
      whole image is treated as a single page.

    The response's `structure_elements` classifies that page's text in
    isolation (no cross-page context) — for actual continuity across
    several pages, use /parse/pages instead.
    """
    filename = file.filename or "upload"
    ext = os.path.splitext(filename)[1].lower()

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {sorted(ALLOWED_EXTENSIONS)}",
        )

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit for this prototype.",
        )

    try:
        source_kind = guess_source_kind(filename)
        if source_kind == "pdf":
            if page_number < 1:
                raise HTTPException(status_code=400, detail="page_number must be >= 1.")
            extraction = extract_pdf_page(file_bytes, filename, page_number)
        else:
            extraction = extract_image_page(file_bytes, filename)
    except ExtractionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    body = extraction.to_dict()
    elements = classify_page(extraction)
    body["structure_elements"] = [e.to_dict() for e in elements]

    # Milestone 4: diagram detection + diagram-to-FEN
    if extraction.image_base64_png:
        img_bytes = base64.b64decode(extraction.image_base64_png)
        page_img = Image.open(io.BytesIO(img_bytes))
        diagrams = process_page_diagrams(
            image=page_img,
            page_number=extraction.page_number,
            page_text=extraction.text,
            page_extraction=extraction,
            structure_elements=elements,
        )
        diagram_dicts = [d.to_dict() for d in diagrams]
        body["diagrams"] = diagram_dicts
    else:
        body["diagrams"] = []

    # Milestone 5: chess moves, replay, and game/puzzle reconstruction
    games = process_page_chess(
        page_extraction=extraction,
        structure_elements=elements,
        diagrams=body.get("diagrams", []),
    )
    body["games"] = [g.to_dict() for g in games]

    return body


@app.post("/parse/pages")
async def parse_pages(
    file: UploadFile = File(...),
    start_page: int = Form(1),
    end_page: int = Form(...),
) -> dict:
    """
    Milestone 3: parse a short run of consecutive PDF pages and detect
    where a game or an explanation continues across a page break,
    instead of treating each page as an independent document.

    Capped at MAX_PAGE_RANGE pages per request (5, matching this
    milestone's own scope — see README roadmap for M4's larger range).
    PDFs only: a single image upload is already exactly one page, so
    there is nothing to detect continuity between — use /parse for that.
    """
    filename = file.filename or "upload"
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_PDF_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                "This endpoint only accepts PDFs — a single image upload is "
                "already one page, with nothing to detect continuity between. "
                "Use /parse for a single image."
            ),
        )

    if start_page < 1 or end_page < start_page:
        raise HTTPException(status_code=400, detail="Invalid page range.")
    if (end_page - start_page + 1) > MAX_PAGE_RANGE:
        raise HTTPException(
            status_code=400,
            detail=f"This milestone supports at most {MAX_PAGE_RANGE} pages per request.",
        )

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit for this prototype.",
        )

    pages_json: list[dict] = []
    elements_by_page = {}
    try:
        for page_number in range(start_page, end_page + 1):
            extraction = extract_pdf_page(file_bytes, filename, page_number)
            elements = classify_page(extraction)
            elements_by_page[page_number] = elements

            page_json = extraction.to_dict()
            page_json["structure_elements"] = [e.to_dict() for e in elements]
            if extraction.image_base64_png:
                img_bytes = base64.b64decode(extraction.image_base64_png)
                page_img = Image.open(io.BytesIO(img_bytes))
                diagrams = process_page_diagrams(
                    image=page_img,
                    page_number=page_number,
                    page_text=extraction.text,
                    page_extraction=extraction,
                    structure_elements=elements,
                )
                diagram_dicts = [d.to_dict() for d in diagrams]
                page_json["diagrams"] = diagram_dicts
            else:
                page_json["diagrams"] = []

            # Milestone 5: chess games per page
            page_games = process_page_chess(
                page_extraction=extraction,
                structure_elements=elements,
                diagrams=page_json.get("diagrams", []),
            )
            page_json["games"] = [g.to_dict() for g in page_games]
            pages_json.append(page_json)
    except ExtractionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    sections = detect_sections(elements_by_page)

    return {
        "filename": filename,
        "start_page": start_page,
        "end_page": end_page,
        "pages": pages_json,
        "sections": [s.to_dict() for s in sections],
    }


@app.post("/pdf/page-count")
async def pdf_page_count(file: UploadFile = File(...)) -> dict:
    """
    Small convenience endpoint so the frontend can populate a page
    selector's max value right after upload, without extracting a page.
    """
    filename = file.filename or "upload"
    ext = os.path.splitext(filename)[1].lower()
    if ext != ".pdf":
        raise HTTPException(status_code=400, detail="This endpoint only accepts PDFs.")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    try:
        count = get_pdf_page_count(file_bytes, filename)
    except ExtractionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"filename": filename, "page_count": count}


@app.post("/build-curriculum")
async def build_curriculum_endpoint(
    file: UploadFile = File(...),
    start_page: int = Form(1),
    end_page: int | None = Form(None),
    book_title: str | None = Form(None),
) -> dict:
    """
    Final Phase: build a full-book hierarchical curriculum (Book -> Level -> Chapter -> Lesson -> Activity)
    with human-review flags and ChessMethod JSON export schema.
    """
    filename = file.filename or "upload"
    ext = os.path.splitext(filename)[1].lower()
    if ext != ".pdf":
        raise HTTPException(status_code=400, detail="Curriculum export requires a PDF book.")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit.",
        )

    try:
        total_count = get_pdf_page_count(file_bytes, filename)
    except ExtractionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if start_page < 1:
        raise HTTPException(status_code=400, detail="start_page must be >= 1.")
    effective_end = end_page if end_page is not None else total_count
    if effective_end < start_page:
        raise HTTPException(status_code=400, detail="end_page must be >= start_page.")

    try:
        curriculum = build_curriculum_from_pdf(
            file_bytes=file_bytes,
            filename=filename,
            start_page=start_page,
            end_page=effective_end,
        )
        if book_title:
            curriculum.book_title = book_title
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to build curriculum: {exc}") from exc

    return {
        "curriculum": curriculum.to_dict(),
        "chessmethod_json": curriculum.to_chessmethod_json(),
    }


