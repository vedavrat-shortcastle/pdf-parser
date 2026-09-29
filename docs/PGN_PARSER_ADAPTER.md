# PGN Parser Adapter (planned, not implemented)

This project (`parsing agent` / Part 2) does not import anything from
your existing `annotation agent` project (Part 1). At the time Stage 1
was built, that project's files were not available in the environment
doing the work, so nothing here depends on it existing, on its file
layout, or on its exact function signatures.

When you're ready to wire in reuse of `annotation agent`'s
`src/pgn_parser.py` (specifically `parse_pgn_text(...)`), the intended
integration point is:

```text
src/chess/pgn_adapter.py   (not yet created)
```

Suggested approach, to keep this project independently runnable even if
`annotation agent` moves, is renamed, or isn't present on a given
machine:

1. Add `annotation agent`'s directory to `sys.path` (or install it as an
   editable local package) only inside `pgn_adapter.py` — a `try/except
   ImportError` at the top, not a hard dependency anywhere else in this
   project.
2. `pgn_adapter.py` exposes a small, stable function such as
   `parse_game_text(pgn_text: str) -> ParsedGame` that either:
   - delegates to `annotation agent`'s `parse_pgn_text(...)` if it's
     importable, or
   - falls back to this project's own minimal PGN handling (built on
     `python-chess`, once that stage exists) if it isn't.
3. Nothing else in `parsing agent` should import `annotation agent`
   directly — only `pgn_adapter.py` should know it exists. That keeps
   Part 2 usable stand-alone and keeps Part 1 untouched, per your
   instruction not to modify it.

To actually build this adapter, share (upload) the real
`src/pgn_parser.py` — and ideally its function signatures / a couple of
usage examples — so the adapter can be written against what
`parse_pgn_text(...)` actually returns, rather than a guess.
