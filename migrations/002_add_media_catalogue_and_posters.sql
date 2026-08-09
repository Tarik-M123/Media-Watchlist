-- 002_add_media_catalogue_and_posters.sql
--
-- Introduces a shared media catalogue and a poster table with per-source
-- provenance, so a poster fetched once is reused by every user tracking that
-- title instead of being copied onto each per-user watchlist row.
--
-- The motivation is not deduplication at this scale — it is that posters can
-- arrive from sources of differing trust (the TMDB API, a scraped page, a
-- manual override). A single watchlist.poster_url column cannot record which
-- source won, so a scrape overwriting a TMDB URL destroys it irrecoverably.
--
-- Nothing here is destructive. watchlist.poster_url is KEPT and redefined as a
-- per-user override; existing values are COPIED into media_posters, not moved.
--
-- Like 001, Base.metadata.create_all() will not apply this, so run it by hand:
--
--   psql "$DATABASE_URL" -f migrations/002_add_media_catalogue_and_posters.sql
--
-- Run the PRE-FLIGHT block first and confirm each query returns zero rows.


-- ===========================================================================
-- PRE-FLIGHT — confirm existing data satisfies the new CHECKs
-- ===========================================================================
-- Expect 0 rows from each of these. If any returns rows, fix the data first.
--
--   SELECT id, year FROM watchlist
--    WHERE year IS NOT NULL AND (year < 1888 OR year > 2100);
--
--   SELECT id, poster_url FROM watchlist
--    WHERE poster_url IS NOT NULL AND poster_url !~ '^https://';
--
-- Rows with a poster but no media_type cannot be backfilled, because
-- media.media_type is NOT NULL. Expect 0: the only writer of poster_url is
-- seed_watchlist_items(source='tmdb'), which always sets media_type.
--
--   SELECT count(*) FROM watchlist
--    WHERE poster_url IS NOT NULL AND media_type IS NULL;


BEGIN;

-- ---------------------------------------------------------------------------
-- media — one row per real-world title, shared across all users.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS media (
    id              SERIAL       PRIMARY KEY,

    -- Nullable: titles found by scraping have no TMDB id. Uniqueness is
    -- enforced by a PARTIAL index below so those NULLs do not collide.
    tmdb_id         INTEGER,

    -- NOT NULL even though watchlist.media_type is nullable: a catalogue entry
    -- of unknown type cannot be deduplicated or displayed sensibly.
    media_type      VARCHAR(10)  NOT NULL,

    title           VARCHAR(255) NOT NULL,

    -- Dedupe key for titles with no tmdb_id. GENERATED so it can never drift
    -- from title. Deliberately naive (case + surrounding whitespace only);
    -- anything cleverer belongs in application code where it can be tested.
    title_key       TEXT GENERATED ALWAYS AS (lower(btrim(title))) STORED,

    year            INTEGER,
    runtime_minutes INTEGER,
    genres          TEXT[],
    synopsis        TEXT,

    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),

    CONSTRAINT ck_media_media_type CHECK (media_type IN ('movie', 'tv')),
    CONSTRAINT ck_media_runtime    CHECK (runtime_minutes IS NULL OR runtime_minutes > 0),
    CONSTRAINT ck_media_year       CHECK (year IS NULL OR year BETWEEN 1888 AND 2100),
    CONSTRAINT ck_media_tmdb_id    CHECK (tmdb_id IS NULL OR tmdb_id > 0)
);

-- The upsert target for TMDB-sourced writes, and the guard against two
-- catalogue rows sharing one TMDB identity. PARTIAL because most rows have no
-- tmdb_id; the partial form keeps the index small and states the intent.
CREATE UNIQUE INDEX IF NOT EXISTS uq_media_tmdb
    ON media (tmdb_id, media_type)
    WHERE tmdb_id IS NOT NULL;

-- The upsert target for scraped/manual writes, which arrive with a title and
-- maybe a year but no id. COALESCE(year, -1) rather than NULLS NOT DISTINCT so
-- this works on Postgres < 15; -1 is unreachable because ck_media_year floors
-- real years at 1888.
CREATE UNIQUE INDEX IF NOT EXISTS uq_media_title_key
    ON media (title_key, media_type, COALESCE(year, -1));


-- ---------------------------------------------------------------------------
-- media_posters — one row per (title, source, size). Several rows per title is
-- the whole point: a TMDB poster and a scraped poster coexist, and the read
-- path picks a winner, so a low-trust scrape never destroys the API value.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS media_posters (
    id               SERIAL      PRIMARY KEY,
    media_id         INTEGER     NOT NULL REFERENCES media(id) ON DELETE CASCADE,

    -- CHECK rather than an ENUM type so adding a source later is an
    -- ALTER ... DROP/ADD CONSTRAINT, consistent with status_valid on watchlist.
    source           VARCHAR(16) NOT NULL,

    -- TMDB serves w92..w780 and original. Part of the unique key, so
    -- re-fetching a given size updates in place rather than accumulating.
    size_label       VARCHAR(16) NOT NULL DEFAULT 'original',

    url              TEXT        NOT NULL,
    width            INTEGER,
    height           INTEGER,

    -- Where a scraped URL was found. Without it a bad poster is untraceable.
    source_page_url  TEXT,

    -- Set false when a URL stops resolving. Invalid rows drop out of the view
    -- and the next-best source takes over, without losing the history.
    is_valid         BOOLEAN     NOT NULL DEFAULT TRUE,

    fetched_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_verified_at TIMESTAMPTZ,

    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ck_media_posters_source
        CHECK (source IN ('tmdb', 'scraped', 'manual')),

    -- Structural guard against an agent writing junk: https only (no data:,
    -- javascript:, http:) and a length ceiling. Host allowlisting lives in the
    -- application, where it can change without a migration.
    CONSTRAINT ck_media_posters_url
        CHECK (url ~ '^https://[^ ]+$' AND length(url) BETWEEN 12 AND 2048),

    CONSTRAINT ck_media_posters_dims
        CHECK ((width IS NULL OR width > 0) AND (height IS NULL OR height > 0)),

    -- A scrape with no provenance URL is not auditable, so refuse it outright.
    CONSTRAINT ck_media_posters_scrape_provenance
        CHECK (source <> 'scraped' OR source_page_url IS NOT NULL),

    CONSTRAINT ck_media_posters_verified_after_fetch
        CHECK (last_verified_at IS NULL OR last_verified_at >= fetched_at)
);

-- Does three jobs: enforces one slot per (title, source, size); is the
-- ON CONFLICT target for every poster write; and its leading media_id serves
-- the view lookup and keeps ON DELETE CASCADE off a sequential scan.
CREATE UNIQUE INDEX IF NOT EXISTS uq_media_posters_slot
    ON media_posters (media_id, source, size_label);


-- ---------------------------------------------------------------------------
-- media_primary_poster — the precedence rule, written down exactly once.
--
--   manual  : a human chose it, so it wins.
--   tmdb    : structured API data, high confidence.
--   scraped : Playwright against markup that changes without notice.
--
-- A scraped poster therefore surfaces only when a title has no manual and no
-- valid TMDB poster.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW media_primary_poster AS
SELECT DISTINCT ON (media_id)
       media_id,
       id AS poster_id,
       url,
       source,
       size_label,
       width,
       height,
       fetched_at
FROM media_posters
WHERE is_valid
ORDER BY media_id,
         CASE source
             WHEN 'manual'  THEN 0
             WHEN 'tmdb'    THEN 1
             WHEN 'scraped' THEN 2
             ELSE 9
         END,
         fetched_at DESC,
         id DESC;


-- ---------------------------------------------------------------------------
-- watchlist.media_id — nullable on purpose. Rows typed into the frontend are
-- free text with no tmdb_id and cannot always be resolved to a catalogue entry;
-- NOT NULL would either block those inserts or force fabricated media rows.
--
-- ON DELETE SET NULL: RESTRICT would make catalogue cleanup impossible, and
-- CASCADE would delete a user's watchlist entry because a shared metadata row
-- was tidied up.
-- ---------------------------------------------------------------------------
ALTER TABLE watchlist
    ADD COLUMN IF NOT EXISTS media_id INTEGER;

ALTER TABLE watchlist DROP CONSTRAINT IF EXISTS fk_watchlist_media;
ALTER TABLE watchlist
    ADD CONSTRAINT fk_watchlist_media
    FOREIGN KEY (media_id) REFERENCES media(id) ON DELETE SET NULL;

-- Postgres does not index FK columns automatically. Needed for the dashboard
-- join, and so ON DELETE SET NULL does not sequential-scan watchlist.
CREATE INDEX IF NOT EXISTS ix_watchlist_media_id ON watchlist (media_id);

COMMENT ON COLUMN watchlist.poster_url IS
    'Per-user poster override. Shared posters live in media_posters; the API '
    'serves COALESCE(watchlist.poster_url, media_primary_poster.url). Pre-002 '
    'rows still hold a TMDB URL, copied into media_posters by 002.';


-- ===========================================================================
-- BACKFILL — copy, never move.
-- ===========================================================================

-- 1. A catalogue row per distinct title that already has a poster. DISTINCT ON
--    collapses the N per-user copies into one, preferring a copy with a tmdb_id.
INSERT INTO media (tmdb_id, media_type, title, year, runtime_minutes, genres, synopsis)
SELECT DISTINCT ON (lower(btrim(w.title)), w.media_type, COALESCE(w.year, -1))
       w.tmdb_id, w.media_type, w.title, w.year, w.runtime_minutes, w.genres, w.synopsis
FROM watchlist w
WHERE w.poster_url IS NOT NULL
  AND w.media_type IS NOT NULL
  AND w.poster_url ~ '^https://'
ORDER BY lower(btrim(w.title)), w.media_type, COALESCE(w.year, -1),
         (w.tmdb_id IS NULL), w.id
ON CONFLICT DO NOTHING;

-- 2. Link watchlist rows to the catalogue: by tmdb_id where present, else by
--    the normalised title key. Unmatched rows keep media_id NULL, a valid state.
UPDATE watchlist w
SET    media_id = m.id
FROM   media m
WHERE  w.media_id IS NULL
  AND (
        (w.tmdb_id IS NOT NULL AND m.tmdb_id = w.tmdb_id AND m.media_type = w.media_type)
     OR (w.tmdb_id IS NULL
         AND m.title_key = lower(btrim(w.title))
         AND m.media_type = w.media_type
         AND COALESCE(m.year, -1) = COALESCE(w.year, -1))
      );

-- 3. Promote existing URLs into media_posters as source='tmdb'. Justified
--    because the only writer of watchlist.poster_url is the TMDB path in
--    mcp_server; the offline CATALOG carries no poster_url at all.
--    fetched_at borrows updated_at so staleness is not reset to now().
INSERT INTO media_posters (media_id, source, size_label, url, fetched_at)
SELECT DISTINCT ON (w.media_id)
       w.media_id, 'tmdb', 'original', w.poster_url, w.updated_at
FROM watchlist w
WHERE w.media_id IS NOT NULL
  AND w.poster_url IS NOT NULL
  AND w.poster_url ~ '^https://'
ORDER BY w.media_id, w.updated_at DESC
ON CONFLICT (media_id, source, size_label) DO NOTHING;

-- Post-check (expect 0): a poster-bearing row that failed to link.
--   SELECT count(*) FROM watchlist
--    WHERE poster_url IS NOT NULL AND media_type IS NOT NULL AND media_id IS NULL;

COMMIT;


-- ===========================================================================
-- DOWN — destructive: drops every scraped/manual poster gathered since 002.
-- Dump first:
--   pg_dump "$DATABASE_URL" -t media -t media_posters > posters_backup.sql
-- watchlist.poster_url is untouched by 002, so pre-002 posters survive this.
-- ===========================================================================
--
-- BEGIN;
-- DROP VIEW  IF EXISTS media_primary_poster;
-- ALTER TABLE watchlist DROP CONSTRAINT IF EXISTS fk_watchlist_media;
-- DROP INDEX IF EXISTS ix_watchlist_media_id;
-- ALTER TABLE watchlist DROP COLUMN IF EXISTS media_id;
-- DROP TABLE IF EXISTS media_posters;
-- DROP TABLE IF EXISTS media;
-- COMMIT;
