"""Minimal TMDB client, shared by the API and the watchlist-engine MCP server.

Lives in the backend package rather than in mcp_server/ because both halves now
need it: the API enriches newly created items, and the MCP server seeds. A
second copy would drift.

Accepts either credential TMDB hands out:
  * a v3 API key  -> sent as an `api_key` query parameter
  * a v4 read access token (a long JWT starting `eyJ`) -> sent as a Bearer header
"""

import os
from typing import Any

import httpx

API_BASE = "https://api.themoviedb.org/3"
IMAGE_BASE = "https://image.tmdb.org/t/p"

# Two sizes are stored per title. `original` is routinely 2000x3000 and several
# megabytes — fine for the detail modal, ruinous for a grid of cards, so the
# card grid gets w500 instead.
POSTER_SIZE_CARD = "w500"
POSTER_SIZE_LARGE = "original"
# Small enough for a search-suggestion row, where a dozen load at once.
POSTER_SIZE_THUMB = "w185"

TIMEOUT = httpx.Timeout(15.0)

# Item creation must not hang on a slow third party, so the enrichment path
# uses a much tighter budget than the seeder.
ENRICH_TIMEOUT = httpx.Timeout(6.0)


class TMDBError(RuntimeError):
    """Raised for anything the caller can act on: missing key, bad key, no match."""


def _credentials() -> tuple[dict[str, str], dict[str, str]]:
    """Return (headers, params) carrying the configured credential."""
    key = (os.getenv("TMDB_API_KEY") or "").strip()
    if not key:
        raise TMDBError(
            "TMDB_API_KEY is not set, so live metadata is unavailable.\n"
            "  1. Get a free key at https://www.themoviedb.org/settings/api\n"
            "  2. Add `TMDB_API_KEY=your_key` to backend/.env\n"
            "  3. Restart the API (and reconnect the MCP server)\n"
            "Meanwhile, seed_watchlist_items(source='mock') works fully offline."
        )
    # v4 read access tokens are JWTs; v3 keys are 32-char hex strings.
    if key.startswith("eyJ"):
        return {"Authorization": f"Bearer {key}"}, {}
    return {}, {"api_key": key}


def _get(client: httpx.Client, path: str, params: dict[str, Any], timeout=TIMEOUT) -> dict:
    headers, auth_params = _credentials()
    try:
        resp = client.get(
            f"{API_BASE}{path}",
            params={**auth_params, **params},
            headers=headers,
            timeout=timeout,
        )
    except httpx.RequestError as exc:
        raise TMDBError(f"Could not reach TMDB: {exc}") from exc

    if resp.status_code == 401:
        raise TMDBError(
            "TMDB rejected the credential (401). Check TMDB_API_KEY in backend/.env "
            "— it should be either the v3 API key or the v4 read access token."
        )
    if resp.status_code == 429:
        raise TMDBError("TMDB rate limit hit (429). Wait a moment and retry.")
    resp.raise_for_status()
    return resp.json()


def poster_url(poster_path: str | None, size: str = POSTER_SIZE_LARGE) -> str | None:
    return f"{IMAGE_BASE}/{size}{poster_path}" if poster_path else None


def suggested_rating(vote_average: float | None) -> int | None:
    """Map TMDB's 0-10 vote average onto this app's 1-5 integer rating.

    The watchlist table has CHECK (rating >= 1 AND rating <= 5), so the raw
    vote_average can never be stored directly.
    """
    if not vote_average:
        return None
    return max(1, min(5, round(vote_average / 2)))


def search(title: str, media_type: str = "auto", year: int | None = None, timeout=TIMEOUT) -> dict:
    """Find the best match for `title` and return its full details.

    media_type: "movie", "tv", or "auto" (searches both and takes the most popular).
    """
    if media_type not in ("movie", "tv", "auto"):
        raise TMDBError(f"media_type must be 'movie', 'tv' or 'auto' (got {media_type!r})")

    with httpx.Client() as client:
        if media_type == "auto":
            params: dict[str, Any] = {"query": title}
            if year:
                params["year"] = year
            results = _get(client, "/search/multi", params, timeout).get("results", [])
            results = [r for r in results if r.get("media_type") in ("movie", "tv")]
        else:
            params = {"query": title}
            if year:
                params["year" if media_type == "movie" else "first_air_date_year"] = year
            results = _get(client, f"/search/{media_type}", params, timeout).get("results", [])
            for r in results:
                r["media_type"] = media_type

        if not results:
            hint = f" (year={year})" if year else ""
            raise TMDBError(f"No TMDB match for {title!r}{hint}. Try a different spelling or drop the year.")

        # TMDB orders by relevance, but popularity breaks ties far more reliably
        # for short/ambiguous titles.
        best = max(results, key=lambda r: r.get("popularity") or 0)
        resolved_type = best["media_type"]
        details = _get(client, f"/{resolved_type}/{best['id']}", {}, timeout)

    return _normalise(details, resolved_type)


def details(tmdb_id: int, media_type: str, timeout=TIMEOUT) -> dict:
    """Fetch one known title directly, skipping the search step.

    Used when the user picked from the suggestions, so the identity is already
    settled and guessing at a best match would only add a way to be wrong.
    """
    if media_type not in ("movie", "tv"):
        raise TMDBError(f"media_type must be 'movie' or 'tv' (got {media_type!r})")
    with httpx.Client() as client:
        payload = _get(client, f"/{media_type}/{tmdb_id}", {}, timeout)
    return _normalise(payload, media_type)


def search_candidates(query: str, limit: int = 8, timeout=TIMEOUT) -> list[dict]:
    """Titles matching `query`, best first, for the Add form's suggestion list.

    Deliberately lighter than search(): no per-title details call, so this stays
    cheap enough to run while somebody is typing.
    """
    query = (query or "").strip()
    if len(query) < 2:
        return []

    with httpx.Client() as client:
        results = _get(client, "/search/multi", {"query": query}, timeout).get("results", [])

    candidates = []
    for r in results:
        media_type = r.get("media_type")
        if media_type not in ("movie", "tv"):
            continue
        date = (r.get("release_date") if media_type == "movie" else r.get("first_air_date")) or ""
        title = (
            r.get("title") or r.get("original_title")
            if media_type == "movie"
            else r.get("name") or r.get("original_name")
        )
        if not title:
            continue
        candidates.append({
            "tmdb_id": r.get("id"),
            "media_type": media_type,
            "title": title,
            "year": int(date[:4]) if date[:4].isdigit() else None,
            "poster_thumb": poster_url(r.get("poster_path"), size=POSTER_SIZE_THUMB),
            "popularity": r.get("popularity") or 0,
        })

    # Same ordering rule as search(): popularity settles short or ambiguous
    # queries far more reliably than TMDB's relevance ranking.
    candidates.sort(key=lambda c: c["popularity"], reverse=True)
    for c in candidates:
        c.pop("popularity")
    return candidates[:limit]


def watch_providers(tmdb_id: int, media_type: str, region: str, timeout=TIMEOUT) -> dict:
    """Where a title can be watched in `region`.

    TMDB sources this from JustWatch and keys it by country, so a title can be
    widely available yet have nothing for a smaller market. That is an ordinary
    outcome, not an error: the caller gets empty lists.
    """
    if media_type not in ("movie", "tv"):
        raise TMDBError(f"media_type must be 'movie' or 'tv' (got {media_type!r})")

    with httpx.Client() as client:
        payload = _get(client, f"/{media_type}/{tmdb_id}/watch/providers", {}, timeout)

    block = (payload.get("results") or {}).get(region.upper()) or {}

    def names(key: str) -> list[str]:
        entries = block.get(key) or []
        entries.sort(key=lambda p: p.get("display_priority", 999))
        # dict.fromkeys keeps first-seen order while dropping duplicates.
        return list(dict.fromkeys(p["provider_name"] for p in entries if p.get("provider_name")))

    # Subscription and free tiers are what "where is it streaming" means; rent
    # and buy are a different question and are kept apart rather than merged in.
    streaming = names("flatrate") + [n for n in names("free") + names("ads") if n not in names("flatrate")]

    return {
        "region": region.upper(),
        "streaming": streaming,
        "rent": names("rent"),
        "buy": names("buy"),
        "link": block.get("link"),
    }


def _normalise(d: dict, media_type: str) -> dict:
    """Flatten a TMDB details payload into the shape the watchlist table stores."""
    estimated = False

    if media_type == "movie":
        title = d.get("title") or d.get("original_title") or ""
        date = d.get("release_date") or ""
        runtime = d.get("runtime") or None
        episodes = None
        creators = [c["name"] for c in (d.get("production_companies") or [])[:1]]
    else:
        title = d.get("name") or d.get("original_name") or ""
        date = d.get("first_air_date") or ""
        episodes = d.get("number_of_episodes") or None

        # TMDB has emptied episode_run_time for a lot of series, so fall back to
        # a concrete episode's runtime. That episode is often a finale, which
        # runs long, hence the estimated flag.
        per_episode = (d.get("episode_run_time") or [None])[0]
        if not per_episode:
            for key in ("last_episode_to_air", "next_episode_to_air"):
                per_episode = (d.get(key) or {}).get("runtime")
                if per_episode:
                    estimated = True
                    break

        # For a series, "watch time" is the whole run, not one episode.
        runtime = per_episode * episodes if (per_episode and episodes) else per_episode
        creators = [c["name"] for c in (d.get("created_by") or [])]

    path = d.get("poster_path")

    return {
        "tmdb_id": d.get("id"),
        "media_type": media_type,
        "title": title,
        "year": int(date[:4]) if date[:4].isdigit() else None,
        "runtime_minutes": runtime,
        "runtime_is_estimated": estimated,
        "episode_count": episodes,
        "genres": [g["name"] for g in (d.get("genres") or [])],
        # Kept at `original` so existing callers (the MCP seeder, and the
        # pre-002 watchlist.poster_url column) see exactly what they did before.
        "poster_url": poster_url(path),
        # The raw path, so callers can build any size without re-parsing a URL.
        "poster_path": path,
        "synopsis": d.get("overview") or None,
        "vote_average": round(d["vote_average"], 1) if d.get("vote_average") else None,
        "suggested_rating": suggested_rating(d.get("vote_average")),
        "creators": creators,
    }
