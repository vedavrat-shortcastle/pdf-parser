"""
Entry point for running the API directly with `python -m src.main`.

In practice you'll usually run it via uvicorn instead (see README):

    uvicorn src.api:app --reload --port 8000

This file exists mainly so `python -m src.main` also works, and as an
obvious place to add startup/shutdown hooks later if a future stage
ever needs one (e.g. loading a diagram-recognition model once at
startup instead of per-request).
"""

from __future__ import annotations

import uvicorn

if __name__ == "__main__":
    uvicorn.run("src.api:app", host="127.0.0.1", port=8000, reload=True)
