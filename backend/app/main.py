from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine, Base
from app.routers import assistant, auth, watchlist, dashboard, media

# Newest source file at the moment this process imported the app. Uvicorn keeps
# serving whatever it loaded at boot, so an edited file and a running server can
# disagree indefinitely — and the symptom is stale ANSWERS, not an error, which
# is impossible to tell apart from a bug in the new code. Comparing this against
# the files on disk settles that question in one request.
_SOURCE_LOADED_AT = datetime.fromtimestamp(
    max(p.stat().st_mtime for p in Path(__file__).parent.rglob("*.py")),
    tz=timezone.utc,
)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Media Watchlist API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(watchlist.router)
app.include_router(dashboard.router)
app.include_router(media.router)
app.include_router(assistant.router)


@app.get("/")
def root():
    return {
        "message": "Media Watchlist API is running",
        # If this is older than your last edit, the server is serving stale code
        # and needs restarting — see "Am I running the code I just edited?" in
        # the README.
        "code_loaded_at": _SOURCE_LOADED_AT.isoformat(),
    }
