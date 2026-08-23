-- 003_add_media_scores_and_embeddings.sql
--
-- Adds the two things the "ask your watchlist" assistant needs from the shared
-- catalogue: a public score, and a semantic fingerprint of each title.
--
-- vote_average has been fetched from TMDB since 001 and discarded — tmdb.py
-- normalises it into the payload and _upsert_media never stored it, because no
-- column existed. Storing it turns "what is this rated?" into a column read
-- rather than a live API call, and — more usefully — makes the score something
-- you can FILTER on ("highly rated things I have not started").
--
-- embedding is a fixed-length list of numbers describing what a title is ABOUT,
-- so "something slow and melancholy" can match Arrival without either text
-- sharing a word. It is FLOAT8[] rather than pgvector's `vector` type on
-- purpose: pgvector is not available on this installation (absent from
-- pg_available_extensions), and at this catalogue size a numpy dot product in
-- the API process is indistinguishable from an indexed vector search. All
-- similarity maths lives behind embeddings.find_similar(), so moving to
-- pgvector later is a change to one function, not to every caller.
--
-- Like 001 and 002, Base.metadata.create_all() will not apply this. Run it by
-- hand:
--
--   psql "$DATABASE_URL" -f migrations/003_add_media_scores_and_embeddings.sql
--
-- Nothing here is destructive: four nullable columns, no data is rewritten.
-- Existing rows keep working with every new column NULL — that is the ordinary
-- "not enriched yet" state, and backfill_media.py fills it in.


BEGIN;

-- ---------------------------------------------------------------------------
-- media.vote_average — TMDB's 0-10 community score.
--
-- REAL, not NUMERIC: TMDB reports one decimal place and tmdb.py already rounds
-- to it, so the exactness NUMERIC buys is not worth its cost here. Distinct
-- from watchlist.rating, which is this user's own 1-5 opinion; a title has one
-- vote_average and as many ratings as it has viewers.
-- ---------------------------------------------------------------------------
ALTER TABLE media ADD COLUMN IF NOT EXISTS vote_average REAL;

ALTER TABLE media DROP CONSTRAINT IF EXISTS ck_media_vote_average;
ALTER TABLE media
    ADD CONSTRAINT ck_media_vote_average
    CHECK (vote_average IS NULL OR vote_average BETWEEN 0 AND 10);


-- ---------------------------------------------------------------------------
-- media.embedding — the semantic fingerprint, and its provenance.
--
-- No index. A FLOAT8[] cannot take a useful similarity index (that is precisely
-- what pgvector's HNSW/IVFFlat exist to provide), so every search is a full
-- scan. At a catalogue of this size that is free. The day the scan stops being
-- free is the day to install pgvector.
-- ---------------------------------------------------------------------------
ALTER TABLE media ADD COLUMN IF NOT EXISTS embedding FLOAT8[];

-- Which model produced the vector. This is load-bearing, not bookkeeping:
-- different models emit different dimensions, and comparing vectors across
-- models either raises (length mismatch) or — far worse — silently returns
-- plausible nonsense at the same length. Recording the name lets the search
-- skip rows it cannot legitimately compare, so swapping models degrades to
-- "fewer results until the backfill re-runs" instead of "wrong results".
ALTER TABLE media ADD COLUMN IF NOT EXISTS embedding_model TEXT;

-- When the vector was computed. A synopsis edited after this timestamp means
-- the fingerprint describes text that no longer exists; without it, a stale
-- vector is indistinguishable from a current one.
ALTER TABLE media ADD COLUMN IF NOT EXISTS embedding_updated_at TIMESTAMPTZ;

-- A vector whose model is unknown is unusable — it cannot be compared against
-- anything, because nothing can establish what it is comparable WITH. Refuse
-- the combination outright rather than storing a row that can only mislead.
ALTER TABLE media DROP CONSTRAINT IF EXISTS ck_media_embedding_provenance;
ALTER TABLE media
    ADD CONSTRAINT ck_media_embedding_provenance
    CHECK (embedding IS NULL OR embedding_model IS NOT NULL);

COMMENT ON COLUMN media.embedding IS
    'Semantic fingerprint of title+year+genres+synopsis. Only comparable against '
    'vectors sharing embedding_model. Written by app/embeddings.py; searched by '
    'embeddings.find_similar(), which is the single seam to swap for pgvector.';


-- Post-check (expect 0): a vector with no model recorded. The CHECK above makes
-- this unreachable, so a non-zero count means the constraint failed to apply.
--
--   SELECT count(*) FROM media WHERE embedding IS NOT NULL AND embedding_model IS NULL;

COMMIT;


-- ===========================================================================
-- DOWN — drops the scores and every computed vector. The vectors are
-- reproducible offline via backfill_media.py; the scores need TMDB_API_KEY.
-- ===========================================================================
--
-- BEGIN;
-- ALTER TABLE media DROP CONSTRAINT IF EXISTS ck_media_embedding_provenance;
-- ALTER TABLE media DROP CONSTRAINT IF EXISTS ck_media_vote_average;
-- ALTER TABLE media DROP COLUMN IF EXISTS embedding_updated_at;
-- ALTER TABLE media DROP COLUMN IF EXISTS embedding_model;
-- ALTER TABLE media DROP COLUMN IF EXISTS embedding;
-- ALTER TABLE media DROP COLUMN IF EXISTS vote_average;
-- COMMIT;
