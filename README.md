# Parsing Agent (ShortCastle / ChessMethod — Part 2)

Turns a chess book (PDF, or a single scanned page image) into a
structured, book-order-preserving curriculum for ChessMethod:
`Book → Level → Chapter → Lesson → Activity`.

This is a **separate project** from the existing `annotation agent`
(Part 1). It does not modify or depend on that project — see
[`docs/PGN_PARSER_ADAPTER.md`](docs/PGN_PARSER_ADAPTER.md) for the PGN
parser reuse adapter.

> **Note on this document:** an earlier README in this repo understated
> what had actually been built — it still listed diagrams, chess, and
> curriculum assembly as "not implemented" after they had, in fact,
> been written and wired up. This version reflects the codebase as it
> actually stands, verified by reading the source, not by trusting
> whatever a prior README claimed.

## Pipeline

```text
PDF / PNG / JPG / JPEG / WEBP upload
        │
        ▼
   page selection (PDFs only) / page RANGE for /parse/pages (up to 100)
        │
        ▼
 PDF/image extraction (PyMuPDF) ──▶ diagram detector (OpenCV + ONNX CNN) ──▶ FEN
        │                                │
        ▼                                ▼
 embedded text / local Tesseract OCR    crop → recognize → infer side-to-move
        │                                → validate (python-chess) → FEN
        ▼                                │
 heuristic structure classification      │
 per block (heading, moves,              │
 explainer, diagram hint, unclassified)  │
        │                                │
        ▼                                │
 move extraction & SAN normalization     │
 (figurines, castling, annotations)      │
        │                                │
        ▼                                │
 python-chess legal replay engine ◀──────┘
 (bidirectional diagram matching)
        │
        ▼
 PGN reconstruction + Seven Tag Roster + resolved/unresolved validation
        │
        ▼
 curriculum builder: pages → Chapters/Lessons (heading regex) →
 Activities (games, puzzles, explainer text), unresolved items
 flagged needs_review
        │
        ▼
 ChessMethod JSON export  ◀──▶  React UI (Workbench: parse, OCR,
                                 Structure, Games & Replay tabs)
        │
        ▼
 [planned] Puzzle Explainer: original tactical + history prose per
 puzzle, generated from position facts only — never from book text
```

## Architecture

```text
parsing agent/
├── src/
│   ├── api.py               FastAPI app: /health, /parse, /parse/pages,
│   │                        /pdf/page-count, /build-curriculum
│   ├── main.py               `python -m src.main` entry point
│   ├── config.py             upload limits, CORS, render DPI, OCR settings,
│   │                        MAX_PAGE_RANGE=100 — no DB config, there is none
│   │
│   ├── pdf/                  Stage 1 — implemented
│   │   ├── models.py         BoundingBox / TextBlock / PageExtraction
│   │   ├── extractor.py      PDF page + single-image extraction (pymupdf,
│   │   │                    Pillow) + OCR wiring
│   │   └── renderer.py       page → PNG rendering
│   │
│   ├── ocr/                  Milestone 2 — implemented
│   │   └── tesseract.py      run_ocr(image) -> OcrResult (local Tesseract)
│   │
│   ├── structure/            Milestone 3 — implemented
│   │   ├── models.py         StructureElement / Section / ContinuationPoint
│   │   └── detector.py       classify_page(page) -> elements;
│   │                        detect_sections(...) -> cross-page Sections
│   │
│   ├── diagrams/              Milestone 4 — implemented
│   │   ├── models.py         DiagramCandidate / DiagramRecognitionResult /
│   │   │                    SideToMoveEvidence / ValidationResult
│   │   ├── detector.py       board detection on the rendered page
│   │   ├── cropper.py        crop_diagram, image_to_base64_png
│   │   ├── recognizer.py     ONNX tile classifier → piece placement
│   │   ├── context.py        infer_side_to_move from surrounding text
│   │   ├── validators.py     python-chess FEN legality validation
│   │   └── pipeline.py       process_page_diagrams: detect → crop →
│   │                        recognize → infer side → validate → FEN
│   │
│   ├── chess/                 Milestone 5 — implemented
│   │   ├── models.py         GameOrPuzzle / ReplayResult / HalfMove /
│   │   │                    GameMetadata
│   │   ├── san.py            SAN normalization, game-result detection
│   │   ├── extractor.py      extract_games_from_page
│   │   ├── replay.py         python-chess legal replay engine
│   │   ├── pgn.py /
│   │   │   pgn_adapter.py    PGN build + adapter to Part 1's PGN parser
│   │   └── pipeline.py       process_page_chess coordinator
│   │
│   ├── curriculum/            Final phase (M6–M8 scope) — implemented
│   │   ├── models.py         Activity / Lesson / Chapter / Level /
│   │   │                    BookCurriculum, with resolved/needs_review flags
│   │   ├── builder.py        assemble_curriculum_from_pages,
│   │   │                    build_curriculum_from_pdf — chapter/lesson
│   │   │                    heading detection via regex, ties in chess +
│   │   │                    diagram pipelines per page
│   │   └── exporter.py       export_chessmethod_curriculum,
│   │                        save_chessmethod_json
│   │
│   └── puzzles/               NOT implemented — spec only, see below
│       └── __init__.py       (empty)
│
├── frontend/                  React + Vite workbench UI
│   └── src/
│       ├── App.jsx            upload, page selector, results tabs (OCR,
│       │                     Structure, Games & Replay), Cross-page
│       │                     Continuity panel
│       ├── api.js             fetch wrapper around the backend
│       └── index.css
│
├── tests/
│   ├── test_pdf_extractor.py
│   ├── test_api.py            incl. /parse/pages and /build-curriculum
│   ├── test_ocr.py / run_ocr_smoke.py
│   ├── test_structure.py / run_structure_smoke.py
│   ├── test_diagrams.py
│   ├── test_chess.py
│   └── test_curriculum.py
│
├── docs/
│   └── PGN_PARSER_ADAPTER.md
│
├── data/                      empty; see "No database" below
├── requirements.txt
└── .gitignore
```

## API

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Liveness + which stage/milestone is implemented |
| POST | `/parse` | `file` (PDF/image) + `page_number` (PDFs only) → `PageExtraction` JSON, including `structure_elements` |
| POST | `/parse/pages` | `file` (PDF only) + `start_page` + `end_page` (max `MAX_PAGE_RANGE` = 100) → each page's extraction plus cross-page `sections` |
| POST | `/pdf/page-count` | `file` (PDF) → `{filename, page_count}` |
| POST | `/build-curriculum` | `file` (PDF) + `start_page`/`end_page`/`book_title` → full `BookCurriculum` + ChessMethod export JSON |

`diagrams` and `chess` processing run inside `/build-curriculum` (via
`src/curriculum/builder.py`), not as separate endpoints — there was no
need identified yet for calling them standalone outside the curriculum
build.

## No database, no persistent storage

There is no PostgreSQL, MongoDB, Firebase, Supabase, cloud storage, or
vector DB anywhere in this project. Uploaded files are read into
memory, processed, and discarded when the request finishes. `data/input/`
and `data/output/` exist only for your own manual local debugging; the
app itself never writes there.

## Milestone status

| Stage | Scope | Status |
|-------|-------|--------|
| M1 | 1 page: PDF/image → text + image + layout metadata | **Done** |
| M2 | 1 page: OCR → text + bounding boxes | **Done** |
| M3 | Cross-page continuity (structure detection) | **Done** |
| M4 | Chess diagram detection + FEN | **Done** |
| M5 | Move OCR, SAN normalization, PGN & python-chess replay | **Done** |
| M6–M8 | Curriculum assembly, human-review flags, ChessMethod JSON export | **Done** (`src/curriculum/`, `/build-curriculum`) |
| — | Puzzle Explainer (tactical + history prose per puzzle) | **Not started — design spec below** |

## Known limitations (carried forward, still real)

- **Heuristics, not an LLM.** Structure classification (`src/structure/detector.py`)
  and chapter/lesson detection (`src/curriculum/builder.py`) are regex/word-shape
  rules, tuned on synthetic and one real book (`TacticsCourse (1).pdf`) — not
  validated broadly across real chess-book layouts (footnotes, running headers,
  descriptive notation, multi-column text).
- **No layout/position awareness.** Classification looks only at block text,
  never font size, boldness, or position on the page.
- **Diagram recognition confidence-gated, not perfect.** `process_page_diagrams`
  marks a result `unresolved` on low recognition confidence or invalid FEN
  rather than guessing — by design — but the underlying ONNX recognizer's
  real-world accuracy on scanned book diagrams is unverified beyond test fixtures.
- **Puzzle solution matching across the whole book** (a puzzle's solution
  appearing hundreds of pages later) is out of scope — continuity detection
  only looks at adjacent pages within one request.
- **Test execution in this environment.** The project's own `.venv` was built
  on macOS and its interpreter path isn't portable; running the full suite
  requires your Mac (`pytest -v`) or a freshly built venv with `requirements.txt`
  installed — see Setup below.

## Setup (run this on your Mac)

### 1. Install Tesseract (system binary — required for OCR)

```bash
brew install tesseract
tesseract --version
```

### 2. Backend

```bash
cd ~/"parsing agent"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest -v
uvicorn src.api:app --reload --port 8000
# GET http://127.0.0.1:8000/health should return {"status": "ok", ...}
```

### 3. Frontend

```bash
cd ~/"parsing agent"/frontend
npm install
npm run dev
# open the URL Vite prints (default http://localhost:5173)
```

---

## Planned: Puzzle Explainer module (`src/puzzles/`)

**Status: design spec only, not yet built.** Currently `src/puzzles/`
is an empty package.

### Goal

For every puzzle `Activity` the curriculum builder already extracts
(FEN, solution moves, page number, PGN tags), generate two pieces of
original prose:

1. **Tactical explainer** — what's happening in the position and why
   the solution works.
2. **History explainer** — how the game reached this position (move
   history) plus any player/event/date context, combined into one
   explainer, per project decision.

### Copyright-safety approach

The generator **never sees the book's own explainer prose**. Its only
inputs are the FEN, the move list/PGN tags, and motif labels computed
locally by code (fork, pin, back-rank, etc. — derived from the board
itself via `python-chess`, not from anyone's description of the board).
Positions, moves, and game metadata are facts, not copyrightable
expression; the actual prose is generated from scratch using our own
template banks. This is stronger than paraphrasing the book's text,
which can still be judged a derivative work — here there is nothing to
paraphrase because the source text is never an input.

As a guardrail, a similarity check (`similarity.py`) computes n-gram
overlap between generated text and that page's actual book `explainer`
block; high overlap flags `needs_review` instead of shipping silently,
consistent with the project's existing unresolved-first philosophy.

### Planned module layout

```
src/puzzles/
├── models.py       PuzzleFacts, PuzzleExplainer dataclasses
├── motifs.py        detect_motifs(board, solution_moves) -> list[str]
│                     starting set: fork, pin, back-rank mate, skewer
├── facts.py         build_puzzle_facts(activity, game_metadata)
│                     material count, checks, mate-in-N, side to move,
│                     opening name, PGN tags if present
├── explain.py        generate_tactical_explainer(facts) -> str
│                     generate_history_explainer(facts) -> str
├── similarity.py      overlap_score(generated_text, book_text) -> float
└── render.py          render_puzzle_html(activity, explainer) -> str
```

### Data flow

```
curriculum.builder.assemble_curriculum_from_pages
        │ (Activity objects with fen/pgn/moves/solution)
        ▼
puzzles.facts.build_puzzle_facts
        ▼
puzzles.motifs.detect_motifs
        ▼
puzzles.explain.generate_tactical_explainer / generate_history_explainer
        ▼
Activity gains: explainer_tactical, explainer_history, motifs,
                explainer_needs_review
        ▼
puzzles.render.render_puzzle_html  →  HTML per puzzle
```

`Activity.to_chessmethod_json()` will include the four new fields.
`/build-curriculum` will run this step automatically for every
`activity_type == "puzzle"`; a standalone `POST /explain-puzzle`
(single FEN/PGN in, HTML out) is a candidate addition for previewing
one puzzle from the frontend.

### Testing plan

- `test_puzzles.py`: motif detection against known FEN fixtures, and
  the similarity guardrail correctly flagging a deliberately
  near-verbatim test case.
- Invariant test: `facts.py` never reads `structure_elements` of type
  `explainer` — asserts the book's own prose can't leak into the
  generator's inputs even by accident.

### Open decision

Starting motif taxonomy: small fixed set (fork, pin, back-rank,
skewer) vs. a larger tactical vocabulary from the start. Affects how
much `motifs.py` needs on day one — to be settled before implementation.
