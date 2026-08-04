"""watchlist-engine — local MCP server for the Media Watchlist app.

Three tools:
  fetch_tmdb_media     - look up real metadata + poster URLs on TMDB (read-only)
  seed_watchlist_items - populate PostgreSQL with realistic rows across statuses
  get_watchlist_stats  - aggregate watch time, genres and status distribution

Run standalone:  mcp_server/.venv/Scripts/python.exe mcp_server/server.py
"""

import random
from collections import Counter, defaultdict

from fastmcp import FastMCP
from pydantic import BaseModel, Field

import tmdb
from db import STATUSES, WatchlistItem, resolve_user_id, session
from seed_data import CATALOG

mcp = FastMCP("Watchlist Engine")

# Rows only ever carry a rating when status == 'finished' (rating_range CHECK
# plus the API's own validation in schemas.py). Seeded ratings skew high because
# people rarely finish things they hate.
FINISHED_RATING_WEIGHTS = {2: 1, 3: 3, 4: 5, 5: 3}


# --------------------------------------------------------------------------- #
# Return models — give FastMCP a schema so tools emit structured output
# --------------------------------------------------------------------------- #

class MediaMetadata(BaseModel):
    tmdb_id: int | None = None
    media_type: str | None = None
    title: str
    year: int | None = None
    runtime_minutes: int | None = Field(None, description="Total runtime; for a series, whole run")
    runtime_is_estimated: bool = Field(
        False, description="True when a series runtime was derived from one episode because TMDB had no episode_run_time"
    )
    episode_count: int | None = None
    genres: list[str] = []
    poster_url: str | None = None
    synopsis: str | None = None
    vote_average: float | None = Field(None, description="TMDB score, 0-10")
    suggested_rating: int | None = Field(None, description="vote_average mapped onto this app's 1-5 scale")
    creators: list[str] = []


class SeedResult(BaseModel):
    user_id: int
    inserted: int
    by_status: dict[str, int]
    titles: list[str]
    deleted_existing: int = 0
    source: str
    notes: list[str] = []


class GenreRating(BaseModel):
    genre: str
    average_rating: float
    items_rated: int


class WatchTime(BaseModel):
    finished_minutes: int
    finished_hours: float
    backlog_minutes: int = Field(..., description="planning_to_watch + watching")
    backlog_hours: float
    dropped_minutes: int


class WatchlistStats(BaseModel):
    user_id: int
    total_items: int
    status_distribution: dict[str, int]
    watch_time: WatchTime
    top_genres_by_rating: list[GenreRating]
    genre_counts: dict[str, int]
    platform_counts: dict[str, int]
    rating_distribution: dict[int, int]
    average_rating: float | None
    items_missing_runtime: int
    items_missing_genres: int


# --------------------------------------------------------------------------- #
# Tools
# --------------------------------------------------------------------------- #

@mcp.tool
def fetch_tmdb_media(title: str, media_type: str = "auto", year: int | None = None) -> MediaMetadata:
    """Look up a movie or TV show on TMDB and return its metadata and poster URL.

    Read-only — nothing is written to the database. Use this to grab a real
    high-resolution poster URL instead of copy-pasting one by hand.

    Args:
        title: Title to search for, e.g. "Peaky Blinders".
        media_type: "movie", "tv", or "auto" to search both (default).
        year: Optional release / first-air year to disambiguate remakes.
    """
    return MediaMetadata(**tmdb.search(title, media_type=media_type, year=year))


@mcp.tool
def seed_watchlist_items(
    user_id: int | None = None,
    count: int = 12,
    source: str = "mock",
    reset: bool = False,
) -> SeedResult:
    """Populate the watchlist table with realistic entries spread across all four statuses.

    Respects the app's own rules: `platform` is always set, and `rating` is only
    populated on 'finished' rows (1-5) and left NULL everywhere else.

    Args:
        user_id: Which user to seed. Omit to reuse/create demo@watchlist.local.
        count: How many items to insert (capped at the catalogue size).
        source: "mock" for the built-in offline catalogue, or "tmdb" to enrich
            each title with live TMDB data (requires TMDB_API_KEY).
        reset: If True, DELETE this user's existing watchlist rows first.
            Off by default — destructive.
    """
    if source not in ("mock", "tmdb"):
        raise ValueError(f"source must be 'mock' or 'tmdb' (got {source!r})")
    if count < 1:
        raise ValueError("count must be at least 1")

    notes: list[str] = []
    if count > len(CATALOG):
        notes.append(f"count={count} exceeds the {len(CATALOG)}-title catalogue; inserting {len(CATALOG)}.")
        count = len(CATALOG)

    picks = random.sample(CATALOG, count)

    with session() as db:
        try:
            uid = resolve_user_id(db, user_id)

            deleted = 0
            if reset:
                deleted = db.query(WatchlistItem).filter(WatchlistItem.user_id == uid).delete()

            by_status: Counter[str] = Counter()
            titles: list[str] = []

            for i, entry in enumerate(picks):
                data = dict(entry)

                if source == "tmdb":
                    try:
                        live = tmdb.search(data["title"], media_type=data["media_type"], year=data.get("year"))
                        data.update({k: v for k, v in live.items() if v is not None and k != "platform"})
                    except tmdb.TMDBError as exc:
                        notes.append(f"TMDB lookup failed for {data['title']!r}, used mock data ({exc.args[0].splitlines()[0]})")

                # Round-robin so every status is represented even at small counts.
                status = STATUSES[i % len(STATUSES)]

                rating = None
                if status == "finished":
                    rating = data.get("suggested_rating") or random.choices(
                        list(FINISHED_RATING_WEIGHTS), weights=list(FINISHED_RATING_WEIGHTS.values())
                    )[0]

                db.add(WatchlistItem(
                    user_id=uid,
                    title=data["title"],
                    platform=data.get("platform") or random.choice(["Netflix", "HBO Max", "Prime Video"]),
                    status=status,
                    rating=rating,
                    tmdb_id=data.get("tmdb_id"),
                    media_type=data.get("media_type"),
                    year=data.get("year"),
                    runtime_minutes=data.get("runtime_minutes"),
                    genres=data.get("genres") or None,
                    poster_url=data.get("poster_url"),
                    synopsis=data.get("synopsis"),
                ))
                by_status[status] += 1
                titles.append(data["title"])

            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    return SeedResult(
        user_id=uid,
        inserted=len(titles),
        by_status=dict(by_status),
        titles=titles,
        deleted_existing=deleted,
        source=source,
        notes=notes,
    )


@mcp.tool
def get_watchlist_stats(user_id: int | None = None) -> WatchlistStats:
    """Aggregate live stats for a user: watch time, top-rated genres, status split.

    Watch time and genre rankings come from the TMDB metadata columns. Rows added
    through the frontend leave those NULL; such rows are skipped in those two
    sections and counted in items_missing_runtime / items_missing_genres.

    Args:
        user_id: Which user to report on. Omit to use demo@watchlist.local.
    """
    with session() as db:
        try:
            uid = resolve_user_id(db, user_id)
            items = db.query(WatchlistItem).filter(WatchlistItem.user_id == uid).all()

            status_counts = {s: 0 for s in STATUSES}
            genre_counts: Counter[str] = Counter()
            platform_counts: Counter[str] = Counter()
            rating_counts = {r: 0 for r in range(1, 6)}
            genre_ratings: defaultdict[str, list[int]] = defaultdict(list)

            finished_min = backlog_min = dropped_min = 0
            missing_runtime = missing_genres = 0

            for item in items:
                status_counts[item.status] = status_counts.get(item.status, 0) + 1
                platform_counts[item.platform] += 1

                minutes = item.runtime_minutes or 0
                if not item.runtime_minutes:
                    missing_runtime += 1
                if item.status == "finished":
                    finished_min += minutes
                elif item.status == "dropped":
                    dropped_min += minutes
                else:
                    backlog_min += minutes

                if item.genres:
                    for g in item.genres:
                        genre_counts[g] += 1
                        if item.status == "finished" and item.rating is not None:
                            genre_ratings[g].append(item.rating)
                else:
                    missing_genres += 1

                if item.rating is not None:
                    rating_counts[item.rating] = rating_counts.get(item.rating, 0) + 1
        finally:
            db.close()

    all_ratings = [r for r, n in rating_counts.items() for _ in range(n)]

    top_genres = sorted(
        (
            GenreRating(genre=g, average_rating=round(sum(rs) / len(rs), 2), items_rated=len(rs))
            for g, rs in genre_ratings.items()
        ),
        key=lambda gr: (-gr.average_rating, -gr.items_rated, gr.genre),
    )

    return WatchlistStats(
        user_id=uid,
        total_items=len(items),
        status_distribution=status_counts,
        watch_time=WatchTime(
            finished_minutes=finished_min,
            finished_hours=round(finished_min / 60, 1),
            backlog_minutes=backlog_min,
            backlog_hours=round(backlog_min / 60, 1),
            dropped_minutes=dropped_min,
        ),
        top_genres_by_rating=top_genres,
        genre_counts=dict(genre_counts.most_common()),
        platform_counts=dict(platform_counts.most_common()),
        rating_distribution=rating_counts,
        average_rating=round(sum(all_ratings) / len(all_ratings), 2) if all_ratings else None,
        items_missing_runtime=missing_runtime,
        items_missing_genres=missing_genres,
    )


if __name__ == "__main__":
    mcp.run()
