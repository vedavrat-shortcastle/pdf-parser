import React, { useState, useEffect, useCallback, useMemo } from "react";
import { fetchPdfPageCount, parsePage, buildCurriculum } from "./api.js";

const PDF_EXTENSION = ".pdf";
const IMAGE_EXTENSIONS = [".png", ".jpg", ".jpeg", ".webp"];

function isPdf(filename) {
  return filename.toLowerCase().endsWith(PDF_EXTENSION);
}

function isImage(filename) {
  const lower = filename.toLowerCase();
  return IMAGE_EXTENSIONS.some((ext) => lower.endsWith(ext));
}

export default function App() {
  const [file, setFile] = useState(null);
  const [pageNumber, setPageNumber] = useState(1);
  const [pageCount, setPageCount] = useState(null);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [curriculumData, setCurriculumData] = useState(null);
  const [curriculumLoading, setCurriculumLoading] = useState(false);
  const [curriculumError, setCurriculumError] = useState(null);

  const fileKind = useMemo(() => {
    if (!file) return null;
    if (isPdf(file.name)) return "pdf";
    if (isImage(file.name)) return "image";
    return "unsupported";
  }, [file]);

  const handleFileChange = useCallback(async (event) => {
    const selected = event.target.files?.[0];
    if (!selected) return;

    setFile(selected);
    setResult(null);
    setError(null);
    setCurriculumData(null);
    setCurriculumError(null);
    setPageNumber(1);
    setPageCount(null);

    if (isPdf(selected.name)) {
      try {
        const info = await fetchPdfPageCount(selected);
        setPageCount(info.page_count);
      } catch (err) {
        setError(err.message);
      }
    }
  }, []);

  const handleParse = useCallback(async () => {
    if (!file) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const data = await parsePage(file, pageNumber);
      setResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [file, pageNumber]);

  const handleBuildCurriculum = useCallback(async () => {
    if (!file) return;
    setCurriculumLoading(true);
    setCurriculumError(null);
    try {
      const data = await buildCurriculum(file, 1, pageCount);
      setCurriculumData(data);
    } catch (err) {
      setCurriculumError(err.message);
    } finally {
      setCurriculumLoading(false);
    }
  }, [file, pageCount]);

  return (
    <div className="workbench">
      <header className="header">
        <div className="header-brand">SHORTCASTLE</div>
        <div className="header-subtitle">
          Chess Book Parsing Agent — PDF to Curriculum Pipeline
        </div>
      </header>

      <main className="main">
        <section className="panel panel-controls">
          <h2>Source</h2>

          <label className="field">
            <span>Upload PDF or image</span>
            <input
              type="file"
              accept=".pdf,.png,.jpg,.jpeg,.webp"
              onChange={handleFileChange}
            />
          </label>

          {file && (
            <div className="file-meta">
              <div>
                <strong>File:</strong> {file.name}
              </div>
              <div>
                <strong>Type:</strong>{" "}
                {fileKind === "unsupported" ? (
                  <span className="badge badge-warn">unsupported</span>
                ) : (
                  <span className="badge badge-ok">{fileKind}</span>
                )}
              </div>
            </div>
          )}

          {fileKind === "pdf" && (
            <label className="field">
              <span>
                Page number{pageCount ? ` (1–${pageCount})` : ""}
              </span>
              <input
                type="number"
                min={1}
                max={pageCount ?? undefined}
                value={pageNumber}
                onChange={(e) => setPageNumber(Number(e.target.value) || 1)}
              />
            </label>
          )}

          <div className="btn-group-primary">
            <button
              className="btn-primary"
              onClick={handleParse}
              disabled={!file || fileKind === "unsupported" || loading}
            >
              {loading ? "Parsing…" : "Parse Page"}
            </button>
            {fileKind === "pdf" && (
              <button
                className="btn-secondary"
                onClick={handleBuildCurriculum}
                disabled={!file || curriculumLoading}
                title="Assemble full-book curriculum hierarchy and export ChessMethod JSON"
              >
                {curriculumLoading ? "Building Curriculum…" : "Build Curriculum"}
              </button>
            )}
          </div>

          {error && <div className="error-box">{error}</div>}
          {curriculumError && <div className="error-box">{curriculumError}</div>}

          <DetectionStatus result={result} />
        </section>

        <section className="panel panel-results">
          <h2>Results</h2>
          {!result && !loading && (
            <p className="placeholder">
              Upload a file and click "Parse Page" to see the extracted
              text, layout, and rendered page image here, or click "Build Curriculum"
              to compile the entire book into ChessMethod JSON.
            </p>
          )}
          {result && <ResultsView result={result} />}
        </section>
      </main>

      {curriculumData && (
        <CurriculumWorkbench data={curriculumData} />
      )}

      <footer className="footer">
        SHORTCASTLE — PDF extraction, OCR, structure detection, diagram recognition, move replay &amp; curriculum export.
      </footer>
    </div>
  );
}

function DetectionStatus({ result }) {
  const diagrams = result?.diagrams;
  const resolvedDiagrams = diagrams ? diagrams.filter((d) => d.status === "resolved").length : 0;
  const diagramNote = diagrams
    ? `${diagrams.length} detected (${resolvedDiagrams} resolved)`
    : null;

  const games = result?.games;
  const resolvedGames = games ? games.filter((g) => g.replay?.resolved).length : 0;
  const gamesNote = games
    ? `${games.length} detected (${resolvedGames} resolved)`
    : null;

  const rows = [
    { label: "Text extraction", done: true },
    {
      label: "OCR",
      done: true,
      note: result
        ? result.ocr_used
          ? "ran on this page"
          : "not needed (embedded text was sufficient)"
        : null,
    },
    { label: "Structure detection", done: true },
    {
      label: "Diagram detection + FEN (M4)",
      done: true,
      note: diagramNote,
    },
    {
      label: "Move parsing & game replay (M5)",
      done: true,
      note: gamesNote,
    },
    { label: "Curriculum export", done: true },
  ];

  return (
    <div className="detection-status">
      <h3>Pipeline status</h3>
      <ul>
        {rows.map((row) => (
          <li key={row.label} className={row.done ? "status-done" : "status-pending"}>
            <span className="status-dot" />
            {row.label}
            {row.note && <span className="status-note"> — {row.note}</span>}
          </li>
        ))}
      </ul>
      {result && (
        <div className="source-summary">
          <div>
            <strong>Source kind:</strong> {result.source_kind}
          </div>
          <div>
            <strong>Embedded text:</strong>{" "}
            {result.has_embedded_text ? "yes" : "no"}
          </div>
          <div>
            <strong>OCR used:</strong> {result.ocr_used ? "yes" : "no"}
          </div>
          {result.diagrams && (
            <div>
              <strong>Diagrams:</strong> {result.diagrams.length} ({resolvedDiagrams} resolved)
            </div>
          )}
          {result.games && (
            <div>
              <strong>Games / Puzzles:</strong> {result.games.length} ({resolvedGames} resolved)
            </div>
          )}
          {result.ocr_used && result.ocr?.mean_confidence != null && (
            <div>
              <strong>OCR mean confidence:</strong>{" "}
              {result.ocr.mean_confidence.toFixed(1)}%
            </div>
          )}
          <div>
            <strong>Page:</strong> {result.page_number} / {result.page_count}
          </div>
        </div>
      )}
    </div>
  );
}

function ResultsView({ result }) {
  const games = result.games ?? [];
  const diagrams = result.diagrams ?? [];
  const [tab, setTab] = useState(
    games.length > 0 ? "games" : diagrams.length > 0 ? "diagrams" : "image"
  );
  const ocr = result.ocr;

  return (
    <div>
      {result.warnings?.length > 0 && (
        <div className="warning-box">
          {result.warnings.map((w, i) => (
            <div key={i}>⚠ {w}</div>
          ))}
        </div>
      )}

      <div className="tabs">
        <button
          className={tab === "games" ? "tab active" : "tab"}
          onClick={() => setTab("games")}
        >
          Games &amp; Replay ({games.length})
        </button>
        <button
          className={tab === "diagrams" ? "tab active" : "tab"}
          onClick={() => setTab("diagrams")}
        >
          Diagrams ({diagrams.length})
        </button>
        <button
          className={tab === "image" ? "tab active" : "tab"}
          onClick={() => setTab("image")}
        >
          Page Image
        </button>
        <button
          className={tab === "text" ? "tab active" : "tab"}
          onClick={() => setTab("text")}
        >
          Embedded Text
        </button>
        <button
          className={tab === "blocks" ? "tab active" : "tab"}
          onClick={() => setTab("blocks")}
        >
          Embedded Blocks ({result.blocks?.length ?? 0})
        </button>
        <button
          className={tab === "ocr" ? "tab active" : "tab"}
          onClick={() => setTab("ocr")}
          disabled={!result.ocr_used}
          title={result.ocr_used ? undefined : "OCR did not run for this page"}
        >
          OCR {result.ocr_used ? `(${ocr?.blocks?.length ?? 0} lines)` : "(not run)"}
        </button>
        <button
          className={tab === "structure" ? "tab active" : "tab"}
          onClick={() => setTab("structure")}
        >
          Structure ({result.structure_elements?.length ?? 0})
        </button>
        <button
          className={tab === "raw" ? "tab active" : "tab"}
          onClick={() => setTab("raw")}
        >
          Raw JSON
        </button>
      </div>

      <div className="tab-content">
        {tab === "games" && <GamesView games={games} diagrams={diagrams} />}
        {tab === "diagrams" && <DiagramsView diagrams={diagrams} />}
        {tab === "image" && result.image_base64_png && (
          <img
            className="page-image"
            alt={`Page ${result.page_number} of ${result.filename}`}
            src={`data:image/png;base64,${result.image_base64_png}`}
          />
        )}

        {tab === "text" && (
          <pre className="extracted-text">
            {result.text || "(no embedded text on this page)"}
          </pre>
        )}

        {tab === "blocks" && (
          <table className="blocks-table">
            <thead>
              <tr>
                <th>#</th>
                <th>bbox [x0, y0, x1, y1]</th>
                <th>Text</th>
              </tr>
            </thead>
            <tbody>
              {(result.blocks ?? []).map((block) => (
                <tr key={block.block_index}>
                  <td>{block.block_index}</td>
                  <td className="mono">
                    [{block.bbox.map((n) => n.toFixed(1)).join(", ")}]
                  </td>
                  <td>{block.text}</td>
                </tr>
              ))}
              {(result.blocks ?? []).length === 0 && (
                <tr>
                  <td colSpan={3} className="placeholder">
                    No text blocks on this page.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}

        {tab === "ocr" && (
          <OcrView ocr={ocr} />
        )}

        {tab === "structure" && (
          <StructureElementsTable elements={result.structure_elements ?? []} />
        )}

        {tab === "raw" && (
          <pre className="raw-json">
            {JSON.stringify(
              {
                ...result,
                image_base64_png: result.image_base64_png
                  ? `<${result.image_base64_png.length} base64 chars, omitted here>`
                  : "",
              },
              null,
              2
            )}
          </pre>
        )}
      </div>
    </div>
  );
}

const CHESS_SYMBOLS = {
  K: "♔", Q: "♕", R: "♖", B: "♗", N: "♘", P: "♙",
  k: "♚", q: "♛", r: "♜", b: "♝", n: "♞", p: "♟",
};

function MiniChessBoard({ placement }) {
  if (!placement) return null;
  const ranks = placement.split("/");
  if (ranks.length !== 8) return null;

  return (
    <div className="mini-chessboard-container">
      <div className="mini-chessboard">
        {ranks.map((rankStr, rowIdx) => {
          const expanded = rankStr.replace(/\d/g, (d) => " ".repeat(Number(d)));
          return (
            <div key={rowIdx} className="mini-row">
              <span className="rank-label">{8 - rowIdx}</span>
              {expanded.split("").map((ch, colIdx) => {
                const isLight = (rowIdx + colIdx) % 2 === 0;
                return (
                  <div
                    key={colIdx}
                    className={`mini-square ${isLight ? "sq-light" : "sq-dark"}`}
                  >
                    {ch !== " " && (
                      <span className={`piece ${ch === ch.toUpperCase() ? "white-piece" : "black-piece"}`}>
                        {CHESS_SYMBOLS[ch] || ch}
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
          );
        })}
        <div className="file-labels">
          <span className="file-label-pad" />
          {"abcdefgh".split("").map((f) => (
            <span key={f} className="file-label">
              {f}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

function DiagramCard({ diagram }) {
  const [showDebug, setShowDebug] = useState(false);
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    if (diagram.fen || diagram.piece_placement) {
      navigator.clipboard.writeText(diagram.fen || diagram.piece_placement);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const isResolved = diagram.status === "resolved";
  const isValid = diagram.validation?.is_valid;

  return (
    <div className={`diagram-card ${isResolved ? "diagram-resolved" : "diagram-unresolved"}`}>
      <div className="diagram-card-header">
        <div className="diagram-card-title">
          <span className="diagram-id-badge">{diagram.diagram_id}</span>
          <span className={`badge ${isResolved ? "badge-ok" : "badge-warn"}`}>
            {diagram.status}
          </span>
          <span className={`badge ${isValid ? "badge-ok" : "badge-err"}`}>
            {isValid ? "Validation: PASS" : "Validation: FAIL"}
          </span>
          {diagram.mean_confidence != null && (
            <span className="badge badge-neutral">
              Confidence: {(diagram.mean_confidence * 100).toFixed(1)}%
            </span>
          )}
        </div>
      </div>

      <div className="diagram-card-body">
        {/* Left: Cropped Board Image */}
        <div className="diagram-crop-pane">
          {diagram.crop_base64_png || diagram.crop ? (
            <img
              src={diagram.crop_base64_png || diagram.crop}
              alt={`Crop of ${diagram.diagram_id}`}
              className="diagram-crop-img"
            />
          ) : (
            <div className="diagram-crop-placeholder">No crop preview</div>
          )}
        </div>

        {/* Center: Recognition Details */}
        <div className="diagram-info-pane">
          {!isResolved && diagram.reason && (
            <div className="unresolved-alert">
              <strong>Unresolved reason:</strong> {diagram.reason}
            </div>
          )}

          <div className="diagram-meta-row">
            <span className="meta-label">Candidate FEN:</span>
            <div className="fen-box">
              <code className="mono">{diagram.fen || "(none — metadata unconfirmed)"}</code>
              {diagram.fen && (
                <button className="btn-copy" onClick={handleCopy}>
                  {copied ? "Copied!" : "Copy"}
                </button>
              )}
            </div>
          </div>

          <div className="diagram-meta-row">
            <span className="meta-label">Piece placement:</span>
            <code className="mono">{diagram.piece_placement || "n/a"}</code>
          </div>

          <div className="diagram-meta-row">
            <span className="meta-label">Side to move:</span>
            <span>
              {diagram.side_to_move ? (
                <strong className={diagram.side_to_move === "white" ? "side-white" : "side-black"}>
                  {diagram.side_to_move.toUpperCase()}
                </strong>
              ) : (
                <span className="text-dim">Undetermined from context</span>
              )}
            </span>
          </div>

          {diagram.side_to_move_source && (
            <div className="diagram-meta-row source-quote-row">
              <span className="meta-label">Evidence:</span>
              <span className="source-quote">
                "{diagram.side_to_move_source.text}" (page {diagram.side_to_move_source.page})
              </span>
            </div>
          )}

          <div className="diagram-meta-row">
            <span className="meta-label">Validation check:</span>
            <span className={isValid ? "val-pass" : "val-fail"}>
              {diagram.validation?.details || (isValid ? "Legal position" : "Validation failed")}
            </span>
          </div>

          {diagram.min_confidence != null && (
            <div className="diagram-meta-row">
              <span className="meta-label">Worst tile:</span>
              <span>{(diagram.min_confidence * 100).toFixed(1)}%</span>
            </div>
          )}

          <div className="debug-toggle-row">
            <button
              className="btn-link"
              onClick={() => setShowDebug((prev) => !prev)}
            >
              {showDebug ? "▲ Hide debug details" : "▼ Show debug details"}
            </button>
          </div>
        </div>

        {/* Right: Visual 8x8 Mini-Board */}
        <div className="diagram-board-pane">
          <MiniChessBoard placement={diagram.piece_placement} />
        </div>
      </div>

      {/* Collapsible Debug View */}
      {showDebug && (
        <div className="diagram-debug-pane">
          <h4>Developer Debug Information</h4>
          <div className="debug-grid">
            <div>
              <strong>Bounding box [x0, y0, x1, y1]:</strong>
              <div className="mono">[{diagram.bbox.map((n) => n.toFixed(1)).join(", ")}]</div>
            </div>
            <div>
              <strong>FEN Metadata status:</strong>
              <div>{diagram.fen_metadata_status}</div>
            </div>
            <div>
              <strong>python-chess result:</strong>
              <pre className="mono-pre">{JSON.stringify(diagram.validation, null, 2)}</pre>
            </div>
            <div>
              <strong>Side-to-move evidence:</strong>
              <pre className="mono-pre">
                {JSON.stringify(diagram.side_to_move_source || null, null, 2)}
              </pre>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function DiagramsView({ diagrams }) {
  if (!diagrams || diagrams.length === 0) {
    return (
      <div className="placeholder-box">
        <p className="placeholder">No chess diagrams detected on this page.</p>
      </div>
    );
  }

  const resolved = diagrams.filter((d) => d.status === "resolved").length;
  const unresolved = diagrams.filter((d) => d.status === "unresolved").length;

  return (
    <div className="diagrams-view">
      <div className="diagrams-summary-bar">
        <div>
          <strong>Total Detected:</strong> {diagrams.length}
        </div>
        <div>
          <span className="badge badge-ok">{resolved} resolved</span>
        </div>
        {unresolved > 0 && (
          <div>
            <span className="badge badge-warn">{unresolved} unresolved</span>
          </div>
        )}
      </div>

      <div className="diagrams-list">
        {diagrams.map((diag) => (
          <DiagramCard key={diag.diagram_id} diagram={diag} />
        ))}
      </div>
    </div>
  );
}

function GamesView({ games, diagrams }) {
  if (!games || games.length === 0) {
    return (
      <div className="placeholder-box">
        <p className="placeholder">No chess games or tactical puzzles detected on this page.</p>
      </div>
    );
  }

  const resolved = games.filter((g) => g.replay?.resolved).length;
  const unresolved = games.filter((g) => !g.replay?.resolved).length;

  return (
    <div className="games-view">
      <div className="diagrams-summary-bar">
        <div>
          <strong>Total Games / Puzzles:</strong> {games.length}
        </div>
        <div>
          <span className="badge badge-ok">{resolved} resolved</span>
        </div>
        {unresolved > 0 && (
          <div>
            <span className="badge badge-warn">{unresolved} unresolved</span>
          </div>
        )}
      </div>

      <div className="games-list">
        {games.map((game) => (
          <GameCard key={game.game_id} game={game} diagrams={diagrams} />
        ))}
      </div>
    </div>
  );
}

function GameCard({ game, diagrams }) {
  const [currentPly, setCurrentPly] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [showDebug, setShowDebug] = useState(false);
  const [copiedPgn, setCopiedPgn] = useState(false);
  const [copiedFen, setCopiedFen] = useState(false);

  const halfMoves = game.replay?.half_moves ?? [];
  const maxPly = halfMoves.length;
  const isResolved = game.replay?.resolved;

  useEffect(() => {
    let timer = null;
    if (isPlaying) {
      if (currentPly >= maxPly) {
        setIsPlaying(false);
      } else {
        timer = setTimeout(() => {
          setCurrentPly((prev) => (prev < maxPly ? prev + 1 : prev));
        }, 750);
      }
    }
    return () => {
      if (timer) clearTimeout(timer);
    };
  }, [isPlaying, currentPly, maxPly]);

  const currentFen =
    currentPly === 0
      ? (game.replay?.initial_fen || "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1")
      : (halfMoves[currentPly - 1]?.fen_after || "");

  const currentPlacement = currentFen ? currentFen.split(" ")[0] : "";

  const activeDiagramMatch = game.replay?.diagram_matches?.find(
    (m) => m.ply === currentPly
  );

  const handleCopyPgn = () => {
    if (game.pgn) {
      navigator.clipboard.writeText(game.pgn);
      setCopiedPgn(true);
      setTimeout(() => setCopiedPgn(false), 2000);
    }
  };

  const handleCopyFen = () => {
    if (currentFen) {
      navigator.clipboard.writeText(currentFen);
      setCopiedFen(true);
      setTimeout(() => setCopiedFen(false), 2000);
    }
  };

  // Group half-moves into full move rows
  const moveRows = [];
  for (let i = 0; i < halfMoves.length; i += 2) {
    moveRows.push({
      moveNumber: halfMoves[i].move_number,
      white: halfMoves[i],
      black: halfMoves[i + 1] || null,
    });
  }

  return (
    <div className={`game-card ${isResolved ? "game-resolved" : "game-unresolved"}`}>
      <div className="game-card-header">
        <div className="game-header-main">
          <span className="game-kind-badge">{game.kind.toUpperCase()}</span>
          <span className="game-id-badge">{game.game_id}</span>
          <h4 className="game-title">{game.metadata.title || "Game Sequence"}</h4>
          {game.metadata.white && game.metadata.black && (
            <span className="game-players">
              {game.metadata.white} vs {game.metadata.black}
            </span>
          )}
          {game.metadata.eco && (
            <span className="badge badge-neutral">[{game.metadata.eco}]</span>
          )}
          <span className="badge badge-result">{game.metadata.result || "*"}</span>
          <span className={`badge ${isResolved ? "badge-ok" : "badge-warn"}`}>
            {isResolved ? "Legal Replay: PASS" : "Unresolved Moves"}
          </span>
        </div>
        <div className="game-header-sub">
          {game.metadata.site && <span>{game.metadata.site}</span>}
          {game.metadata.date && <span> • {game.metadata.date}</span>}
        </div>
      </div>

      <div className="game-card-body">
        {/* Left: Interactive Board & Controls */}
        <div className="game-board-pane">
          <MiniChessBoard placement={currentPlacement} />

          <div className="replay-controls">
            <button
              className="ctrl-btn"
              onClick={() => { setIsPlaying(false); setCurrentPly(0); }}
              title="Start position"
              disabled={currentPly === 0}
            >
              |◀
            </button>
            <button
              className="ctrl-btn"
              onClick={() => { setIsPlaying(false); setCurrentPly((p) => Math.max(0, p - 1)); }}
              title="Previous move"
              disabled={currentPly === 0}
            >
              ◀
            </button>
            <button
              className={`ctrl-btn play-btn ${isPlaying ? "playing" : ""}`}
              onClick={() => setIsPlaying((p) => !p)}
              title={isPlaying ? "Pause replay" : "Play replay"}
              disabled={maxPly === 0}
            >
              {isPlaying ? "❚❚" : "▶"}
            </button>
            <button
              className="ctrl-btn"
              onClick={() => { setIsPlaying(false); setCurrentPly((p) => Math.min(maxPly, p + 1)); }}
              title="Next move"
              disabled={currentPly >= maxPly}
            >
              ▶
            </button>
            <button
              className="ctrl-btn"
              onClick={() => { setIsPlaying(false); setCurrentPly(maxPly); }}
              title="Final position"
              disabled={currentPly >= maxPly}
            >
              ▶|
            </button>
            <span className="ply-indicator">
              Ply {currentPly} / {maxPly}
            </span>
          </div>

          {activeDiagramMatch && (
            <div className="diagram-match-banner">
              🎯 Position matches Diagram {activeDiagramMatch.diagram_id || `#${activeDiagramMatch.diagram_index}`} on this page
            </div>
          )}

          <div className="fen-strip">
            <span className="fen-label">FEN:</span>
            <code className="fen-text">{currentFen}</code>
            <button className="copy-btn" onClick={handleCopyFen}>
              {copiedFen ? "Copied!" : "Copy"}
            </button>
          </div>
        </div>

        {/* Right: Moves Grid & PGN */}
        <div className="game-moves-pane">
          <div className="moves-list-header">
            <span>Moves ({halfMoves.length} plies)</span>
            <button className="copy-btn" onClick={handleCopyPgn}>
              {copiedPgn ? "PGN Copied!" : "Copy PGN"}
            </button>
          </div>

          <div className="moves-grid">
            <button
              className={`move-btn move-start-btn ${currentPly === 0 ? "active-ply" : ""}`}
              onClick={() => { setIsPlaying(false); setCurrentPly(0); }}
            >
              Start
            </button>
            {moveRows.map((row) => (
              <div key={row.moveNumber} className="move-row">
                <span className="move-num">{row.moveNumber}.</span>
                <button
                  className={`move-btn ${currentPly === row.white.ply ? "active-ply" : ""} ${row.white.diagram_anchor ? "anchor-ply" : ""}`}
                  onClick={() => { setIsPlaying(false); setCurrentPly(row.white.ply); }}
                  title={row.white.diagram_anchor ? "Diagram anchor" : undefined}
                >
                  {row.white.san}
                  {row.white.annotation && <span className="move-annot">{row.white.annotation}</span>}
                  {row.white.diagram_anchor && <span className="anchor-dot">📍</span>}
                </button>
                {row.black && (
                  <button
                    className={`move-btn ${currentPly === row.black.ply ? "active-ply" : ""} ${row.black.diagram_anchor ? "anchor-ply" : ""}`}
                    onClick={() => { setIsPlaying(false); setCurrentPly(row.black.ply); }}
                    title={row.black.diagram_anchor ? "Diagram anchor" : undefined}
                  >
                    {row.black.san}
                    {row.black.annotation && <span className="move-annot">{row.black.annotation}</span>}
                    {row.black.diagram_anchor && <span className="anchor-dot">📍</span>}
                  </button>
                )}
              </div>
            ))}
          </div>

          {/* Collapsible Debug View */}
          <div className="game-debug-toggle">
            <button
              className="btn-link"
              onClick={() => setShowDebug((prev) => !prev)}
            >
              {showDebug ? "▲ Hide debug details" : "▼ Show debug details"}
            </button>
          </div>

          {showDebug && (
            <div className="diagram-debug-pane">
              <h4>Game Diagnostics &amp; Replay Details</h4>
              <div className="debug-grid">
                <div>
                  <strong>Resolved status:</strong>
                  <div>{isResolved ? "Fully resolved (all plies legal)" : "Unresolved"}</div>
                </div>
                {game.replay?.unresolved_reason && (
                  <div>
                    <strong>Unresolved reason:</strong>
                    <div className="val-fail">{game.replay.unresolved_reason}</div>
                  </div>
                )}
                {game.replay?.failing_move && (
                  <div>
                    <strong>Failing move:</strong>
                    <div>{game.replay.failing_move} at ply {game.replay.failing_ply}</div>
                  </div>
                )}
                <div>
                  <strong>Starting FEN:</strong>
                  <div className="mono">{game.replay?.initial_fen}</div>
                </div>
                <div>
                  <strong>Final FEN:</strong>
                  <div className="mono">{game.replay?.final_fen}</div>
                </div>
                <div>
                  <strong>Reconstructed PGN:</strong>
                  <pre className="mono-pre">{game.pgn}</pre>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function OcrView({ ocr }) {
  if (!ocr) {
    return <p className="placeholder">OCR did not run for this page.</p>;
  }

  return (
    <div>
      <div className="ocr-summary">
        <div>
          <strong>Engine:</strong> {ocr.engine} ({ocr.language})
        </div>
        <div>
          <strong>Words:</strong> {ocr.word_count} &nbsp; <strong>Lines:</strong>{" "}
          {ocr.line_count}
        </div>
        <div>
          <strong>Mean confidence:</strong>{" "}
          {ocr.mean_confidence != null ? `${ocr.mean_confidence.toFixed(1)}%` : "n/a"}
        </div>
      </div>

      {ocr.warnings?.length > 0 && (
        <div className="warning-box">
          {ocr.warnings.map((w, i) => (
            <div key={i}>⚠ {w}</div>
          ))}
        </div>
      )}

      <h4>OCR text</h4>
      <pre className="extracted-text">{ocr.text || "(no text recognized)"}</pre>

      <h4>OCR lines / bounding boxes</h4>
      <table className="blocks-table">
        <thead>
          <tr>
            <th>#</th>
            <th>bbox [x0, y0, x1, y1]</th>
            <th>Text</th>
            <th>Confidence</th>
          </tr>
        </thead>
        <tbody>
          {(ocr.blocks ?? []).map((block) => (
            <tr key={block.line_index}>
              <td>{block.line_index}</td>
              <td className="mono">
                [{block.bbox.map((n) => n.toFixed(1)).join(", ")}]
              </td>
              <td>{block.text}</td>
              <td>
                {block.confidence != null ? (
                  <ConfidenceBadge value={block.confidence} />
                ) : (
                  "n/a"
                )}
              </td>
            </tr>
          ))}
          {(ocr.blocks ?? []).length === 0 && (
            <tr>
              <td colSpan={4} className="placeholder">
                No text recognized on this page.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function ConfidenceBadge({ value }) {
  const className =
    value >= 80 ? "badge badge-ok" : value >= 50 ? "badge badge-warn" : "badge badge-error";
  return <span className={className}>{value.toFixed(0)}%</span>;
}

const ELEMENT_TYPE_LABELS = {
  heading: "heading",
  moves: "moves",
  explainer: "explainer",
  diagram_candidate_hint: "diagram hint",
  unclassified: "unclassified",
};

function ElementTypeBadge({ type }) {
  const className =
    type === "heading"
      ? "badge badge-ok"
      : type === "moves"
      ? "badge badge-ok"
      : type === "diagram_candidate_hint"
      ? "badge badge-warn"
      : type === "unclassified"
      ? "badge badge-warn"
      : "badge";
  return <span className={className}>{ELEMENT_TYPE_LABELS[type] ?? type}</span>;
}

function StructureElementsTable({ elements }) {
  if (!elements.length) {
    return <p className="placeholder">No text on this page to classify.</p>;
  }
  return (
    <div>
      <p className="placeholder">
        Milestone 3 heuristic classification of this page's text in
        isolation — no cross-page context. Diagram detection is a
        textual cue only ("White to play..."), not a located board.
      </p>
      <table className="blocks-table">
        <thead>
          <tr>
            <th>#</th>
            <th>Type</th>
            <th>Source</th>
            <th>Text</th>
          </tr>
        </thead>
        <tbody>
          {elements.map((el) => (
            <tr key={`${el.source}-${el.index_on_page}`}>
              <td>{el.index_on_page}</td>
              <td>
                <ElementTypeBadge type={el.element_type} />
              </td>
              <td className="mono">{el.source}</td>
              <td>{el.text}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}


function CurriculumWorkbench({ data }) {
  const [copied, setCopied] = useState(false);
  const [filterNeedsReview, setFilterNeedsReview] = useState(false);
  const [expandedChapters, setExpandedChapters] = useState({});

  const curriculum = data.curriculum;
  const cmJson = data.chessmethod_json;
  const stats = cmJson.curriculum_stats;

  const toggleChapter = (chapId) => {
    setExpandedChapters((prev) => ({
      ...prev,
      [chapId]: !(prev[chapId] ?? true),
    }));
  };

  const handleDownload = () => {
    const jsonStr = JSON.stringify(cmJson, null, 2);
    const blob = new Blob([jsonStr], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${(curriculum.book_title || "curriculum").replace(/\s+/g, "_")}_chessmethod.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const handleCopy = () => {
    navigator.clipboard.writeText(JSON.stringify(cmJson, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <section className="panel panel-curriculum">
      <div className="curriculum-header">
        <div>
          <h2>ChessMethod Curriculum Export</h2>
          <div className="curriculum-subtitle">
            <strong>{curriculum.book_title}</strong> ({curriculum.total_pages} pages parsed)
          </div>
        </div>
        <div className="curriculum-actions">
          <button className="btn-primary" onClick={handleDownload}>
            ⬇ Download ChessMethod JSON
          </button>
          <button className="btn-secondary" onClick={handleCopy}>
            {copied ? "JSON Copied!" : "Copy JSON"}
          </button>
        </div>
      </div>

      <div className="curriculum-stats-bar">
        <div className="stat-card">
          <div className="stat-val">{stats.total_chapters}</div>
          <div className="stat-lbl">Chapters</div>
        </div>
        <div className="stat-card">
          <div className="stat-val">{stats.total_lessons}</div>
          <div className="stat-lbl">Lessons</div>
        </div>
        <div className="stat-card">
          <div className="stat-val">{stats.total_activities}</div>
          <div className="stat-lbl">Activities</div>
        </div>
        <div className="stat-card">
          <div className="stat-val stat-ok">{stats.resolved_activities}</div>
          <div className="stat-lbl">Resolved (Pass)</div>
        </div>
        <div className="stat-card">
          <div className="stat-val stat-warn">{stats.needs_review_count}</div>
          <div className="stat-lbl">Needs Review</div>
        </div>
        <div className="stat-card">
          <div className="stat-val">{stats.resolution_rate_percent}%</div>
          <div className="stat-lbl">Resolution Rate</div>
        </div>
      </div>

      <div className="curriculum-filter-bar">
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={filterNeedsReview}
            onChange={(e) => setFilterNeedsReview(e.target.checked)}
          />
          <span>Show only activities needing human review ({stats.needs_review_count})</span>
        </label>
      </div>

      <div className="curriculum-tree">
        {curriculum.levels.map((lvl) => (
          <div key={lvl.id} className="level-block">
            <h3 className="level-title">Level: {lvl.title}</h3>
            {lvl.chapters.map((chap) => {
              const isExpanded = expandedChapters[chap.id] ?? true;
              return (
                <div key={chap.id} className="chapter-card">
                  <div className="chapter-header" onClick={() => toggleChapter(chap.id)}>
                    <div className="chapter-title-row">
                      <span className="chapter-toggle">{isExpanded ? "▼" : "▶"}</span>
                      <span className="chapter-name">
                        Chapter {chap.number}: {chap.title}
                      </span>
                      <span className="chapter-pages">
                        (Pages {chap.page_start}–{chap.page_end})
                      </span>
                    </div>
                    <span className="badge badge-neutral">
                      {chap.lessons.length} lessons
                    </span>
                  </div>

                  {isExpanded && (
                    <div className="lessons-container">
                      {chap.lessons.map((les) => {
                        const filteredActivities = filterNeedsReview
                          ? les.activities.filter((a) => a.needs_review)
                          : les.activities;

                        if (filterNeedsReview && filteredActivities.length === 0) {
                          return null;
                        }

                        return (
                          <div key={les.id} className="lesson-block">
                            <div className="lesson-header">
                              <span className="lesson-badge">{les.number}</span>
                              <span className="lesson-title">{les.title}</span>
                              <span className="lesson-meta">
                                (Pages {les.page_start}–{les.page_end}) • {les.activities.length} activities
                              </span>
                            </div>

                            <div className="activities-grid">
                              {filteredActivities.map((act) => (
                                <div
                                  key={act.id}
                                  className={`activity-item ${act.resolved ? "act-resolved" : "act-unresolved"}`}
                                >
                                  <div className="act-header">
                                    <span className="act-type">{act.activity_type.toUpperCase()}</span>
                                    <span className="act-title">{act.title}</span>
                                    <span className="act-page">P.{act.page_number}</span>
                                    <span className={`badge ${act.resolved ? "badge-ok" : "badge-warn"}`}>
                                      {act.resolved ? "PASS" : "REVIEW"}
                                    </span>
                                  </div>

                                  {act.fen && (
                                    <div className="act-fen">
                                      <code>{act.fen}</code>
                                    </div>
                                  )}

                                  {act.moves?.length > 0 && (
                                    <div className="act-moves">
                                      <strong>Moves:</strong> {act.moves.slice(0, 10).join(" ")}
                                      {act.moves.length > 10 ? "…" : ""}
                                    </div>
                                  )}

                                  {act.needs_review && (
                                    <div className="act-review-alert">
                                      ⚠ {act.review_reason || "Flagged for human audit"}
                                    </div>
                                  )}
                                </div>
                              ))}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </section>
  );
}
