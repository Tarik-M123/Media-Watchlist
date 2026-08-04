"""Database access for the watchlist-engine MCP server.

Deliberately reuses the FastAPI app's SQLAlchemy models instead of issuing raw
INSERTs. The allowed status values and the rating/media_type CHECK constraints
live in backend/app/models.py; duplicating them here would let the seeder drift
away from what the API accepts.
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
ENV_FILE = BACKEND_DIR / ".env"

# Load backend/.env *before* importing app.database, which reads DATABASE_URL at
# import time. Its own load_dotenv() call searches upward from the process cwd
# and would not find backend/.env when the server is launched from the repo root.
load_dotenv(ENV_FILE)

if not os.getenv("DATABASE_URL"):
    raise RuntimeError(
        f"DATABASE_URL is not set. Expected it in {ENV_FILE}. "
        "Copy backend/.env.example to backend/.env and fill it in."
    )

# Import the app's models by path so both halves of the project agree on schema.
sys.path.insert(0, str(BACKEND_DIR))

from app.database import SessionLocal  # noqa: E402
from app.models import User, WatchlistItem  # noqa: E402

__all__ = ["SessionLocal", "User", "WatchlistItem", "STATUSES", "session", "resolve_user_id"]

# Mirrors the status_valid CHECK constraint on the watchlist table.
STATUSES = ("planning_to_watch", "watching", "finished", "dropped")

DEMO_EMAIL = "demo@watchlist.local"


def session():
    """Context-managed Session. Callers use `with session() as db:`."""
    return SessionLocal()


def resolve_user_id(db, user_id: int | None) -> int:
    """Return a usable user_id, creating a demo user when none is given.

    watchlist.user_id is a NOT NULL FK to users.id, so seeding needs a real user
    to attach to. Passing None reuses the demo user across runs rather than
    piling up a new one each time.
    """
    if user_id is not None:
        user = db.query(User).filter(User.id == user_id).first()
        if user is None:
            existing = [uid for (uid,) in db.query(User.id).order_by(User.id).all()]
            raise ValueError(
                f"No user with id={user_id}. Existing user ids: {existing or 'none'}. "
                "Omit user_id to use the demo user instead."
            )
        return user.id

    demo = db.query(User).filter(User.email == DEMO_EMAIL).first()
    if demo is None:
        demo = User(email=DEMO_EMAIL)
        db.add(demo)
        db.flush()  # assigns demo.id without ending the caller's transaction
    return demo.id
