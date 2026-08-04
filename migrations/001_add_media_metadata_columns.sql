-- 001_add_media_metadata_columns.sql
--
-- Adds TMDB metadata columns to the watchlist table so the watchlist-engine MCP
-- server can store runtime, genres and poster URLs, which get_watchlist_stats
-- needs to aggregate total watch time and top-rated genres.
--
-- Every column is nullable: existing rows and the existing FastAPI routes are
-- unaffected. Base.metadata.create_all() in app/main.py only creates missing
-- tables and never alters an existing one, so this must be run by hand:
--
--   psql "$DATABASE_URL" -f migrations/001_add_media_metadata_columns.sql

ALTER TABLE watchlist
  ADD COLUMN IF NOT EXISTS tmdb_id         INTEGER,
  ADD COLUMN IF NOT EXISTS media_type      VARCHAR(10),
  ADD COLUMN IF NOT EXISTS year            INTEGER,
  ADD COLUMN IF NOT EXISTS runtime_minutes INTEGER,
  ADD COLUMN IF NOT EXISTS genres          TEXT[],
  ADD COLUMN IF NOT EXISTS poster_url      TEXT,
  ADD COLUMN IF NOT EXISTS synopsis        TEXT;

-- Guard against nonsense values arriving from a bad TMDB response.
-- NULL passes a CHECK constraint, so unpopulated rows are unaffected.
ALTER TABLE watchlist
  DROP CONSTRAINT IF EXISTS media_type_valid;
ALTER TABLE watchlist
  ADD CONSTRAINT media_type_valid CHECK (media_type IS NULL OR media_type IN ('movie', 'tv'));

ALTER TABLE watchlist
  DROP CONSTRAINT IF EXISTS runtime_positive;
ALTER TABLE watchlist
  ADD CONSTRAINT runtime_positive CHECK (runtime_minutes IS NULL OR runtime_minutes > 0);

-- get_watchlist_stats always filters by user_id; this keeps that cheap as the
-- seeder grows the table.
CREATE INDEX IF NOT EXISTS ix_watchlist_user_id ON watchlist (user_id);
