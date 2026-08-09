"""Shim: the TMDB client now lives in the backend package.

It moved there because the API enriches newly created items and this server
seeds them; two copies of the same client would drift. `server.py` still does
`import tmdb`, so this module keeps that import working and re-exports the real
implementation from app.tmdb.

The sys.path and dotenv setup is duplicated from db.py rather than imported from
it because server.py imports this module first, so db.py has not necessarily run
its own setup yet.
"""

import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"

load_dotenv(BACKEND_DIR / ".env")

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.tmdb import (  # noqa: E402,F401
    API_BASE,
    IMAGE_BASE,
    POSTER_SIZE_CARD,
    POSTER_SIZE_LARGE,
    TIMEOUT,
    TMDBError,
    poster_url,
    search,
    suggested_rating,
)

__all__ = [
    "API_BASE",
    "IMAGE_BASE",
    "POSTER_SIZE_CARD",
    "POSTER_SIZE_LARGE",
    "TIMEOUT",
    "TMDBError",
    "poster_url",
    "search",
    "suggested_rating",
]
