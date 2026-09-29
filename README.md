# Parsing Agent (ShortCastle / ChessMethod — Part 2)

Turns a chess book (PDF, or a single scanned page image) into a
structured, book-order-preserving curriculum for ChessMethod:
`Book → Level → Chapter → Lesson → Activity`.

This is a **separate project** from the existing `annotation agent`
(Part 1). It does not modify or depend on that project — see
[`docs/PGN_PARSER_ADAPTER.md`](docs/PGN_PARSER_ADAPTER.md) for how
reuse of its PGN parser is planned once you provide that file.

## Current stage: Stage 1 (extraction) + Milestone 2 (OCR) + Milestone 3 (structure & continuity) + Milestone 4 (chess diagrams) + Milestone 5 (moves, SAN, PGN & replay) — implemented

```text
PDF / PNG / JPG / JPEG / WEBP upload
        │
        ▼
   page selection (PDFs only) / page RANGE for /parse/pages (up to 5)
        │
        ▼
 PDF/image extraction (PyMuPDF) ──▶ diagram detector (OpenCV + ONNX CNN) ──▶ FEN
        │                                                                     │
        ▼                                                                     │
 embedded text / local Tesseract OCR                                          │
        │                                                                     │
        ▼                                                                     │
 heuristic structure classification per block (heading, moves, explainer...)  │
        │                                                                     │
        ▼                                                                     │
 move extraction & SAN normalization (figurines, castling, annotations)       │
        │                                                                     │
        ▼                                                                     │
 python-chess legal replay engine (bidirectional diagram matching) ◀──────────┘
        │
        ▼
 PGN reconstruction + Seven Tag Roster + resolved/unresolved validation
        │
        ▼
 structured intermediate JSON  ──▶  React UI (Workbench with Games & Replay)
```

Everything past this — curriculum assembly and ChessMethod export (M6–M8) — is
planned. See "Roadmap" below.

### ⚠️ Important: what has and hasn't actually been run

Stage 1 (PyMuPDF-based PDF/image extraction, FastAPI, the frontend) was
written in a sandbox with no network access and none of those packages
installed — it was syntax-checked and reviewed, not executed, until you
confirmed it worked on your Mac.

**Milestone 2 (OCR)**: the environment that built it *does* have
`tesseract` and `pytesseract` installed, so the OCR module was actually
run against synthetic images — see "Testing" below.

**Milestone 3 (structure detection & continuity) is fully
executable in that same sandbox** — unlike PDF extraction, this layer
only needs plain Python dataclasses (`PageExtraction`, `TextBlock`),
not PyMuPDF, so every classification rule and every continuity case
(a game split across a page break, an explainer paragraph that just
happens to continue, a heading correctly breaking a run) was actually
run and passed — see "Testing" below for the exact list. What's still
unverified:

- The new `/parse/pages` FastAPI endpoint itself — blocked on
  FastAPI/PyMuPDF not being installed here. Written and reviewed, not
  executed end-to-end (same caveat as `/parse` from Stage 1).
- The React UI's new "Structure" tab and "Cross-page continuity" panel
  — reviewed and class-name/brace-balance checked, not rendered in a
  browser.
- **Real chess-book text.** The heuristics were tuned against synthetic
  examples I wrote (clean SAN move sequences, clean chapter headings,
  clean prose). Real books have footnotes, running headers that look
  like headings, figurine notation, descriptive notation (P-K4),
  multi-column layouts, and OCR noise — all of which will stress these
  heuristics in ways synthetic tests can't catch. Treat this as a
  first pass, not a validated classifier — see "Known limitations"
  under Milestone 3 below.

**Run the test suite on your Mac before trusting this further** —
Section "Setup" has the exact commands.

## Architecture

```text
parsing agent/
├── src/
│   ├── api.py              FastAPI app: /health, /parse, /parse/pages, /pdf/page-count
│   ├── main.py              `python -m src.main` entry point
│   ├── config.py            upload limits, CORS, render DPI, OCR settings, MAX_PAGE_RANGE — no DB config, there is none
│   │
│   ├── pdf/                 STAGE 1 — implemented
│   │   ├── models.py        BoundingBox / TextBlock / PageExtraction dataclasses (carries ocr_used / ocr)
│   │   ├── extractor.py     PDF page + single-image extraction (pymupdf, Pillow) + OCR wiring
│   │   └── renderer.py      page → PNG rendering, shared by extraction and OCR
│   │
│   ├── ocr/                 MILESTONE 2 — implemented
│   │   └── tesseract.py     run_ocr(image) -> OcrResult (local Tesseract via pytesseract)
│   │
│   ├── structure/           MILESTONE 3 — implemented
│   │   ├── models.py        StructureElement / Section / ContinuationPoint dataclasses
│   │   └── detector.py      classify_page(page) -> elements; detect_sections(...) -> cross-page Sections
│   │
│   ├── diagrams/            Stage — NOT implemented
│   ├── chess/               Stage — NOT implemented (adapter to Part 1 goes here)
│   ├── puzzles/             Stage — NOT implemented
│   └── curriculum/          Stage — NOT implemented
│
├── frontend/                 React + Vite workbench UI
│   └── src/
│       ├── App.jsx           upload, page selector, results tabs (incl. OCR + Structure tabs),
│       │                     pipeline status, and a separate Cross-page Continuity panel (M3)
│       ├── api.js            fetch wrapper around the backend
│       └── index.css
│
├── tests/
│   ├── test_pdf_extractor.py
│   ├── test_api.py                including /parse/pages tests (M3)
│   ├── test_ocr.py                pytest suite for src/ocr/tesseract.py
│   ├── run_ocr_smoke.py           plain-Python mirror of test_ocr.py, actually run in the authoring sandbox
│   ├── test_structure.py          pytest suite for src/structure/
│   └── run_structure_smoke.py     plain-Python mirror of test_structure.py, actually run (needs no PyMuPDF)
│
├── docs/
│   └── PGN_PARSER_ADAPTER.md
│
├── data/                     empty; see "No database, no persistent storage" below
├── requirements.txt
└── .gitignore
```

## Setup (run this on your Mac)

### 1. Install Tesseract (system binary — required for OCR)

```bash
brew install tesseract
tesseract --version   # should print something like "tesseract 5.x.x"
```

`pytesseract` (the Python package in `requirements.txt`) is just a thin
wrapper that shells out to this binary — installing the pip package
alone is **not** enough. If `tesseract` isn't on your `PATH`,
`src/ocr/tesseract.py` raises a clear `OcrError` explaining that,
rather than crashing unhelpfully or silently returning no text.

### 2. Backend

```bash
cd ~/"parsing agent"

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run the tests FIRST.
pytest -v

# Start the API
uvicorn src.api:app --reload --port 8000
# now GET http://127.0.0.1:8000/health should return {"status": "ok", ...}
```

### 3. Frontend

In a second terminal:

```bash
cd ~/"parsing agent"/frontend
npm install
npm run dev
# open the URL Vite prints (default http://localhost:5173)
```

Upload a PDF or a PNG/JPG/JPEG/WEBP, pick a page number (for PDFs), and
click **Parse Page**. If OCR ran for that page, an "OCR" tab appears
next to the embedded-text tabs with the recognized text, confidence,
and per-line bounding boxes.

## Troubleshooting: `pymupdf` fails to install / `pytest`, `uvicorn` "command not found"

If you saw something like this:

```text
error: metadata-generation-failed
...
note: This is an issue with the package mentioned above, not pip.
(base) ... % pytest -v
zsh: command not found: pytest
(base) ... % uvicorn src.api:app --reload --port 8000
...
ModuleNotFoundError: No module named 'pymupdf'
```

That's two separate problems stacked together:

**1. The `pymupdf` version in `requirements.txt` was too old for your
Python.** The original pin (`pymupdf==1.24.10`, from mid-2024) has no
prebuilt wheel for Python 3.14, so pip tried to compile it from source
and failed. This has been fixed — `requirements.txt` now uses
`pymupdf>=1.26.6` (the first release with Python 3.14 wheels) and
`Pillow>=11.0.0` (same story: 10.x has no 3.13/3.14 wheels). Make sure
you're using the updated `requirements.txt`, then reinstall.

**2. The install didn't happen inside this project's virtual
environment.** The `(base)` prompt and the `uvicorn` error trace
pointing at `/Library/Frameworks/Python.framework/Versions/3.14/...`
mean the commands ran against a global/conda Python, not
`~/"parsing agent"/.venv`. That's why `uvicorn` was found (it's
installed globally from something unrelated) but `pytest` and
`pymupdf` weren't. Every command below needs to run **after**
`source .venv/bin/activate`, with `(.venv)` visible in your prompt, not
`(base)`.

Full fix, from scratch:

```bash
cd ~/"parsing agent"          # or wherever you unzipped it

# Remove any partial venv from the failed attempt
rm -rf .venv

python3 -m venv .venv
source .venv/bin/activate     # prompt should now show (.venv), not (base)

which python3                 # should print a path INSIDE .venv
python3 --version             # note this

python3 -m pip install --upgrade pip
pip install -r requirements.txt

pytest -v                     # should now be found and run
uvicorn src.api:app --reload --port 8000
```

If `pip install -r requirements.txt` still fails to build something
from source even with the updated floors, your Python version may be
newer than this project's dependencies currently support anywhere. In
that case, use a slightly older, universally-supported Python instead
of whatever `python3` resolves to by default:

```bash
brew install python@3.12
rm -rf .venv
python3.12 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
pip install -r requirements.txt
```

## API

| Method | Path              | Purpose                                                        |
|--------|-------------------|-----------------------------------------------------------------|
| GET    | `/health`         | Liveness + which stage/milestone is implemented                |
| POST   | `/parse`          | `file` (PDF/image) + `page_number` (form field, PDFs only) → `PageExtraction` JSON, including this page's own `structure_elements` |
| POST   | `/parse/pages`    | `file` (PDF only) + `start_page` + `end_page` (max `MAX_PAGE_RANGE` = 5 pages) → each page's extraction plus cross-page `sections` |
| POST   | `/pdf/page-count` | `file` (PDF) → `{filename, page_count}`, so the UI can size the page selector |

Planned for later stages (not built yet, per the instruction not to add
endpoints before they're needed): `POST /validate`, `POST /build-curriculum`.

### `PageExtraction` JSON shape

```json
{
  "filename": "book.pdf",
  "source_kind": "pdf",
  "page_number": 12,
  "page_count": 212,
  "width": 595.0,
  "height": 842.0,
  "text": "The Pin\n\nA pin occurs when...",
  "blocks": [
    { "block_index": 0, "text": "The Pin", "bbox": [50.0, 40.0, 220.0, 62.0] }
  ],
  "has_embedded_text": true,
  "image_base64_png": "iVBORw0KG...",
  "warnings": [],
  "ocr_used": false,
  "ocr": null,
  "structure_elements": [
    { "element_type": "heading", "text": "The Pin", "page_number": 12, "source": "embedded", "index_on_page": 0, "bbox": [50.0, 40.0, 220.0, 62.0] }
  ],
  "diagrams": null
}
```

When OCR does run (embedded text missing or shorter than
`config.MIN_SUFFICIENT_EMBEDDED_TEXT_CHARS`, or any raw image upload),
`ocr_used` is `true` and `ocr` looks like:

```json
{
  "ocr_used": true,
  "ocr": {
    "text": "Puzzle 47\nWhite to play and win",
    "blocks": [
      { "line_index": 0, "text": "Puzzle 47", "bbox": [40.0, 30.0, 160.0, 58.0], "confidence": 91.2 },
      { "line_index": 1, "text": "White to play and win", "bbox": [40.0, 64.0, 310.0, 92.0], "confidence": 87.5 }
    ],
    "mean_confidence": 89.35,
    "word_count": 6,
    "line_count": 2,
    "engine": "tesseract",
    "language": "eng",
    "warnings": []
  }
}
```

Key design point: `text`/`blocks` (embedded, from PyMuPDF) and
`ocr.text`/`ocr.blocks` (from Tesseract) are **never merged**. A later
stage — or you, reading this JSON — always knows exactly which engine
produced which piece of text. `diagrams` remains a reserved placeholder
(`null`) for a stage that doesn't exist yet.

### `/parse/pages` JSON shape (Milestone 3)

```json
{
  "filename": "book.pdf",
  "start_page": 12,
  "end_page": 13,
  "pages": [ /* one PageExtraction dict per page, same shape as above */ ],
  "sections": [
    {
      "family": "moves",
      "page_start": 12,
      "page_end": 13,
      "element_count": 2,
      "spans_pages": true,
      "continuation_points": [
        { "from_page": 12, "to_page": 13, "confidence": "confirmed" }
      ],
      "preview_text": "1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 4. c3 Nf6 5. d3 d6 6. O-O O-O 7. Re1 a6 1-0"
    }
  ]
}
```

`confidence: "confirmed"` means the element right before the page break
didn't look finished (no game-result token, no terminal punctuation) —
strong evidence it really does continue. `"same_type_adjacent"` means
two same-family elements just happened to sit next to each other across
a page break with no heading between them, which is weaker evidence (it
could be two unrelated same-type paragraphs back to back) — this
distinction exists so a later stage (or you) can tell those apart
instead of treating every adjacency as equally certain.

## OCR (Milestone 2)

- **Engine**: local Tesseract only, via `pytesseract`. Nothing is
  uploaded to an external OCR service, and no models are downloaded at
  runtime — Tesseract's trained-data files are installed once, locally,
  by `brew install tesseract`.
- **When it runs**: for a PDF page, when the embedded text (stripped)
  is empty or shorter than `MIN_SUFFICIENT_EMBEDDED_TEXT_CHARS` (20
  chars by default, in `src/config.py`) — e.g. a scanned page whose
  only real PDF text is a running header or page number. For any raw
  image upload (PNG/JPG/JPEG/WEBP), OCR always runs, since there's
  never an embedded text layer to check first.
- **Grouping**: line-level, not word-level or whole-block. Tesseract's
  word-level output is grouped by `(block_num, par_num, line_num)` into
  one box + one averaged confidence per line — individual word boxes
  are too noisy to browse in a UI, and a Tesseract "block" can span
  unrelated paragraphs on a dense book page.
- **Failure handling**: if Tesseract can't run at all (binary missing,
  engine error), that's recorded as a warning on the page and
  `ocr_used` stays `false` — the rest of the page's extraction (image,
  embedded text if any) is still returned. This is different from OCR
  running successfully and finding *no* text (e.g. a truly blank page),
  which returns `ocr_used: true` with an empty `ocr.text` and a
  "no recognizable text" warning inside `ocr.warnings`, not an error.

### Known OCR limitations

- **Reading order** is Tesseract's own block/paragraph/line ordering,
  sorted deterministically. This works for a normal single-column book
  page but is **not guaranteed correct for multi-column layouts**,
  side-by-side diagrams with captions, or text wrapped around a diagram
  — those may come out in an unexpected order.
- **English only by default** (`language="eng"` in `src/config.py`).
  Other languages need their own Tesseract trained-data file (e.g.
  `brew install tesseract-lang` for additional languages on macOS) and
  passing that language code through.
- **Chess notation is not treated specially.** OCR reads figurine
  notation (♘, ♗, etc.), unusual old-notation glyphs, and diagram
  coordinate labels as generic text/noise — nothing here yet
  distinguishes "this OCR'd text is a chess move" from any other text.
  That's future work (`src/chess/` + `src/structure/`), not something
  Milestone 2 attempts.
- **Confidence is per-line, not per-character.** A line's confidence is
  the mean of its word confidences: a single garbled word can pull an
  otherwise-clean line's score down, and there's no per-character
  granularity to say which part of the line is suspect.
- **Never tried on a real scanned book page** in this environment —
  only on synthetic images (plain text rendered with PIL). Accuracy on
  actual scan artifacts (skew, shadows, low contrast, halftone dot
  patterns from old book printing) is unverified. Try it on a real page
  early and look at the confidence numbers before trusting a whole
  book's worth of OCR.
- **No image preprocessing** (deskew, binarization, contrast
  normalization, denoising) is done before handing the image to
  Tesseract. This is often what most improves OCR accuracy on real
  scans and is a natural next addition if accuracy on real pages is
  poor.

## Structure detection & cross-page continuity (Milestone 3)

- **Classification is heuristic, not LLM-based.** `src/structure/detector.py`
  uses regex/word-shape rules only — no API call, no model. The
  original spec allows an LLM for this (section 32) but doesn't
  require one; this project has no API key or network wiring for that
  yet, so a documented, inspectable heuristic is the honest choice for
  this milestone. Swapping in an LLM-assisted classifier later is a
  reasonable next step, not a requirement.
- **Element types**: `heading`, `moves`, `explainer`,
  `diagram_candidate_hint`, `unclassified`. `diagram_candidate_hint` is
  a **textual cue only** ("White to play and win") that a diagram
  likely exists nearby — it is not a bounding box or a recognized
  board; actual diagram pixel detection is still entirely unbuilt
  (`src/diagrams/`). `unclassified` is a real, deliberate outcome for
  text that doesn't confidently match anything (a stray page number, a
  running header) — it is not forced into the closest-looking category,
  per the project's unresolved-first philosophy.
- **Continuity detection** (`detect_sections`) groups consecutive
  elements of the same family (`moves` or `explainer` — headings and
  diagram hints are never merged into a run) across a page range into
  one `Section`. Every time such a run crosses a page boundary, a
  `ContinuationPoint` records it with a confidence level:
  - `"confirmed"` — the element right before the break didn't look
    finished (no game-result token like `1-0`/`0-1`/`1/2-1/2` or `#`
    for moves; no sentence-ending punctuation for explainer text).
  - `"same_type_adjacent"` — the prior element *did* look finished, but
    the same-family text resumed anyway with no heading in between.
    Weaker signal — could genuinely be one continuous passage, or could
    be two unrelated paragraphs of the same kind sitting back to back.
- **Scope for this milestone**: `/parse/pages` processes at most
  `MAX_PAGE_RANGE` (5) pages per request, matching the spec's own M3
  scope ("5 pages: cross-page continuity"). A larger range is M4's job.

### Known limitations

- **Tuned on synthetic examples, not a real book.** The regex
  heuristics (SAN-token matching, heading word-shape, sentence-ending
  punctuation) were written and tested against clean examples I
  constructed. Real book text will have footnotes, running
  headers/footers that superficially look like headings, figurine
  notation (♘, ♗), descriptive notation (P-K4), diagram captions, and
  OCR noise — all likely to cause misclassification in ways the
  synthetic tests can't catch. Try this on a real page early and look
  at the actual `structure_elements` output before trusting it broadly.
- **No layout/position awareness.** Classification looks only at each
  block's *text*, never its position, font size, or boldness on the
  page — real headings are usually visually distinct (larger, bold,
  centered) in ways this heuristic can't see, since it never looks at
  the rendered image or PDF font metadata.
- **`moves` detection is SAN-only.** It won't recognize descriptive
  notation (P-K4, N-KB3), figurine notation, or non-English move
  notation — all called out as needing a "normalization layer" in the
  original spec (`src/chess/`, not built yet). A page in one of these
  notations will likely come back `explainer` or `unclassified` instead
  of `moves`.
- **Continuity is a text-adjacency heuristic, not validated
  understanding.** Two unrelated `explainer` paragraphs with no heading
  between them will be merged into one Section (at
  `"same_type_adjacent"` confidence) even if they're about completely
  different topics — the detector has no semantic understanding of
  *what* the text says, only its shape.
- **Multi-column layouts, diagrams interrupting text mid-paragraph, and
  sidebars** are not specifically handled — PyMuPDF's own block reading
  order is trusted as-is (same limitation Stage 1's text-block
  extraction already has).

## Diagram recognition and chess validation — not built yet

Per the project's design:

- **Diagram recognition** requires evaluating existing open-source
  board/piece recognizers (e.g. Chesscog) against real chess-book pages
  before building anything custom. Not started.
- **Move/FEN validation** will use `python-chess` and follow an
  "unresolved-first" philosophy: uncertain extractions get flagged, not
  silently guessed. Not implemented — no chess validation exists yet
  in this codebase.
- **Curriculum export** to the ChessMethod JSON shape needs a real
  export sample before the exact schema can be committed to. Not
  implemented.

## Testing

```bash
pytest -v
```

Covers:

1. PDF opening (valid + invalid bytes)
2. Page range validation (in range, zero, out of range)
3. Embedded text extraction (present, correct page selected, blank page)
4. Image rendering (present, decodable PNG)
5. Text blocks + bounding boxes
6. Image upload path (PNG) + rejection of garbage bytes
7. Extension → source-kind guessing
8. API-level: `/health`, `/parse` (PDF + image + error cases), `/pdf/page-count`
9. **OCR module import** (`test_ocr.py::test_module_imports_and_reports_availability`)
10. **OCR output structure** — `OcrResult`/`OcrBlock` shape, `to_dict()` keys, bbox sanity (`test_ocr.py::test_run_ocr_returns_expected_structure`)
11. **OCR on image input** — grayscale conversion, line grouping vs. word-by-word (`test_ocr.py::test_run_ocr_accepts_grayscale_image`, `test_run_ocr_groups_by_line_not_just_words`)
12. **OCR on empty/invalid input** — blank image succeeds with empty result, `None` raises `OcrError` (`test_ocr.py::test_run_ocr_on_blank_image_succeeds_with_no_text`, `test_run_ocr_raises_on_none_image`)
13. **API response when embedded text is absent** — a blank PDF page triggers OCR and populates `ocr` (`test_api.py::test_parse_pdf_page_with_no_embedded_text_runs_ocr`); an image upload always does too (`test_api.py::test_parse_image_upload`)
14. **Structure classification** — heading/moves/explainer/diagram-hint/unclassified text (`test_structure.py::test_classify_text`), embedded-text and OCR-fallback classification (`test_structure.py::test_classify_page_embedded_text`, `test_classify_page_falls_back_to_ocr`), empty page (`test_classify_page_empty_when_no_text_at_all`)
15. **Cross-page continuity** — an unfinished game merging across a page break with `"confirmed"` confidence, a finished-looking explainer paragraph merging with `"same_type_adjacent"` confidence, a heading correctly breaking continuity, and empty input (`test_structure.py::test_unfinished_game_merges_across_page_break_with_confirmed_confidence`, `test_finished_explainer_merging_gets_weaker_confidence`, `test_heading_breaks_section_continuity`, `test_detect_sections_on_empty_input`)
16. **`/parse/pages` API** — a game correctly detected spanning two pages, non-PDF uploads rejected, a range over `MAX_PAGE_RANGE` rejected, an invalid range (end before start) rejected (`test_api.py::test_parse_pages_*`)

### What was actually executed, vs. written-and-reviewed

| Test file | Executed in the authoring sandbox? |
|---|---|
| `tests/test_pdf_extractor.py` | No — PyMuPDF not installed there. Written + `py_compile`'d only. Confirmed working since you ran Stage 1. |
| `tests/test_api.py` | No — FastAPI/httpx not installed there. Written + `py_compile`'d only (including the new `/parse/pages` tests). |
| `tests/test_ocr.py` | No — needs `pytest`, which isn't installed there. See `run_ocr_smoke.py` below. |
| `tests/run_ocr_smoke.py` | **Yes.** Plain-Python mirror of `test_ocr.py`'s exact assertions (`tesseract` 5.3.4 + `pytesseract` were available). **6/6 passed.** |
| `tests/test_structure.py` | No — needs `pytest`. See `run_structure_smoke.py` below. |
| `tests/run_structure_smoke.py` | **Yes.** This module needs no PyMuPDF at all (`PageExtraction`/`TextBlock` are plain dataclasses), so it ran cleanly despite neither `pymupdf` nor `pytest` being available. **8/8 passed**, including both the "confirmed" and "same_type_adjacent" continuity cases and the heading-breaks-a-run case. |

Run `pytest tests/test_ocr.py tests/test_structure.py -v` on your Mac
too — both should pass the same way their smoke-test mirrors did, since
they check the same things, but neither has been run through the
actual `pytest` runner yet.

Not yet covered because the stages don't exist: FEN validation, move
parsing, legal replay, puzzle solution replay, curriculum JSON schema
validation, exact source-order preservation across a full book. These
will get their own tests when those stages are built.

## No database, no persistent storage

There is no PostgreSQL, MongoDB, Firebase, Supabase, cloud storage, or
vector DB anywhere in this project, and none is planned for the
research-prototype phase. Uploaded files are read into memory, processed,
and discarded when the request finishes — nothing is written to disk by
the API. `data/input/` and `data/output/` exist only as a convenience
for your own manual local debugging; the app itself never writes there.

## Roadmap (from the original spec)

| Stage | Scope                                              | Status |
|-------|-----------------------------------------------------|--------|
| M1    | 1 page: PDF/image → text + image + layout metadata  | **Done** |
| M2    | 1 page: OCR → text + bounding boxes                 | **Done** |
| M3    | 5 pages: cross-page continuity                       | **Done** |
| M4    | 10–20 pages: chess diagram detection + FEN          | **Done** |
| M5    | Move OCR, SAN normalization, PGN & python-chess replay | **Done (this milestone)** |
| M6    | 1 complete puzzle book                               | Not started |
| M7    | 1 complete instructional book                        | Not started |
| M8    | ChessMethod JSON validation / import readiness       | Not started |

### Next milestone (M6 — 1 complete puzzle book)

- Raise `MAX_PAGE_RANGE` (currently 5, in `src/config.py`) to handle a
  10–20 page run, and check the heuristics in `src/structure/detector.py`
  still hold up at that scale — a longer run means more chances for a
  running header to get misclassified as a heading, more chances for a
  multi-page game to get incorrectly split, etc.
- "Mixed content detection" per the original spec: pages that combine
  a diagram, prose, and moves together (a typical instructional-book
  page) rather than being cleanly one type. This likely means moving
  beyond whole-block classification toward finer-grained detection
  within a block, or toward actually locating diagram regions
  (`src/diagrams/`, still not started — needs the open-source-tool
  evaluation the spec calls for, e.g. Chesscog, benchmarked against
  real book pages before building anything custom).
- Consider whether `_looks_like_moves`/`_looks_like_heading` need
  tuning against a real book page — this is the first milestone where
  trying that is strongly recommended before going further (see "Known
  limitations" above).
- Puzzle-number matching across widely separated pages (spec section
  17: a puzzle's solution can be "hundreds of pages later") is still
  out of scope until `src/puzzles/` — M3's continuity detection only
  looks at *adjacent* pages within one short request, not the whole book.
