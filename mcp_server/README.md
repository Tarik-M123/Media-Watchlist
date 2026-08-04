# watchlist-engine MCP server

A local [FastMCP](https://gofastmcp.com) server that fetches real TMDB metadata and
talks directly to the app's PostgreSQL database, so testing doesn't need
hand-copied poster URLs or hand-written mock rows.

## Why its own venv

`fastmcp` requires a newer pydantic than the API's pinned `2.9.2`. Installing it
into `backend/.venv` upgrades pydantic underneath FastAPI. This is a dev tool, not
a production dependency, so it lives in `mcp_server/.venv` and stays out of
`backend/requirements.txt`.

It still imports `backend/app/models.py` for the ORM classes, so the allowed status
values and CHECK constraints are defined in exactly one place.

## Setup

```bash
# from the repo root
py -3.11 -m venv mcp_server/.venv
mcp_server/.venv/Scripts/python.exe -m pip install -r mcp_server/requirements.txt

# one-time schema migration (adds nullable TMDB metadata columns)
psql "$DATABASE_URL" -f migrations/001_add_media_metadata_columns.sql
```

Reads `DATABASE_URL` and the optional `TMDB_API_KEY` from `backend/.env`.

Claude Code picks the server up from `.mcp.json` at the repo root — approve it when
prompted, or run `/mcp` to reconnect after changing the code.

## Tools

### `fetch_tmdb_media(title, media_type="auto", year=None)`
Read-only TMDB lookup. Returns tmdb_id, title, year, runtime, genres, an
`original`-size poster URL, synopsis, `vote_average` (0–10) and `suggested_rating`
— the vote average mapped onto this app's 1–5 integer scale, since the `rating`
column is `CHECK (rating BETWEEN 1 AND 5)` and cannot hold a TMDB score directly.

For a series, `runtime_minutes` is the **whole run** (episode length × episode
count), which is what watch time means for a watchlist.

Requires `TMDB_API_KEY`. Without one it fails with instructions rather than a stack
trace; everything else still works offline.

### `seed_watchlist_items(user_id=None, count=12, source="mock", reset=False)`
Inserts realistic rows spread round-robin across all four statuses. Honours the
app's invariants: `platform` is always set, and `rating` is populated only on
`finished` rows.

- `user_id=None` reuses (or creates) `demo@watchlist.local` rather than piling up a
  new user per run.
- `source="tmdb"` enriches each catalogue title with live data; individual lookup
  failures fall back to mock data and are reported in `notes`.
- `reset=True` deletes that user's existing rows first — **destructive**, off by default.

### `get_watchlist_stats(user_id=None)`
Status distribution, watch time (finished / backlog / dropped), top genres by
average rating, genre and platform counts, rating histogram and mean.

Rows added through the frontend have NULL metadata; they're skipped in the watch
time and genre sections and counted in `items_missing_runtime` /
`items_missing_genres` rather than causing an error.

## Run standalone

```bash
mcp_server/.venv/Scripts/python.exe mcp_server/server.py
```
