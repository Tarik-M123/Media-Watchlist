"""Fill in the catalogue columns that migration 003 added.

003 adds media.vote_average and media.embedding as nullable columns, so existing
rows arrive with both empty. Enrichment only runs when an item is created, and
_upsert_media deliberately does not rewrite catalogue rows it already knows, so
nothing in the normal request path will ever fill them in. This closes that gap.

Two independent passes, either skippable:

  scores      re-fetches vote_average from TMDB. Needs TMDB_API_KEY and network.
  embeddings  computes semantic fingerprints. Runs locally; downloads the model
              (~67 MB) on first use, then needs no network at all.

Safe to re-run: each pass selects only rows still missing its column, so a
second run reports nothing to do.

    cd backend && ./.venv/Scripts/python.exe backfill_media.py [--dry-run]
                                                              [--skip-scores]
                                                              [--skip-embeddings]
"""

import sys
import time

from sqlalchemy import or_

from app import media_catalogue, tmdb
from app.database import SessionLocal
from app.embeddings import MODEL_NAME
from app.models import Media

# Same spacing as backfill_posters.py: a backfill is the one place we make a
# burst of TMDB calls.
DELAY_SECONDS = 0.3


def backfill_scores(db, dry_run: bool) -> int:
    """Fetch vote_average for catalogue rows that have none."""
    pending = (
        db.query(Media)
        .filter(Media.vote_average.is_(None))
        .filter(Media.tmdb_id.isnot(None))
        .order_by(Media.id)
        .all()
    )

    print(f"scores: {len(pending)} row(s) without a TMDB score")
    if not pending:
        return 0
    if dry_run:
        for media in pending:
            print(f"  would fetch: {media.title!r} (tmdb {media.tmdb_id})")
        return 0

    updated, failed = 0, []
    for media in pending:
        try:
            data = tmdb.details(media.tmdb_id, media.media_type)
        except tmdb.TMDBError as exc:
            failed.append(media.title)
            print(f"  MISS  {media.title!r} — {str(exc).splitlines()[0]}")
            time.sleep(DELAY_SECONDS)
            continue

        score = data.get("vote_average")
        if score is None:
            failed.append(media.title)
            print(f"  MISS  {media.title!r} — TMDB has no score for it")
        else:
            media.vote_average = score
            updated += 1
            print(f"  OK    {media.title!r} -> {score}/10")
        time.sleep(DELAY_SECONDS)

    db.commit()
    print(f"scores: updated {updated}, unresolved {len(failed)}\n")
    return updated


def backfill_embeddings(db, dry_run: bool) -> int:
    """Compute embeddings for rows with none, or with one from another model."""
    pending = (
        db.query(Media)
        .filter(
            or_(
                Media.embedding.is_(None),
                # IS DISTINCT FROM rather than !=, because a NULL model would
                # make an ordinary inequality return NULL and filter the row out
                # — exactly the row that most needs re-embedding.
                Media.embedding_model.is_distinct_from(MODEL_NAME),
            )
        )
        .order_by(Media.id)
        .all()
    )

    print(f"embeddings: {len(pending)} row(s) without a current vector")
    if not pending:
        return 0
    if dry_run:
        for media in pending:
            print(f"  would embed: {media.title!r}")
        return 0

    print(f"  (first run downloads {MODEL_NAME}, ~67 MB)")
    written, failed = 0, []
    for media in pending:
        if media_catalogue.record_embedding(db, media, force=True):
            written += 1
            print(f"  OK    {media.title!r}")
        else:
            failed.append(media.title)
            print(f"  MISS  {media.title!r} — see the log for why")

    db.commit()
    print(f"embeddings: wrote {written}, failed {len(failed)}\n")
    return written


def main(dry_run: bool = False, skip_scores: bool = False, skip_embeddings: bool = False) -> int:
    db = SessionLocal()
    try:
        if dry_run:
            print("dry run — nothing will be written\n")
        if not skip_scores:
            backfill_scores(db, dry_run)
        if not skip_embeddings:
            backfill_embeddings(db, dry_run)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(
        main(
            dry_run="--dry-run" in sys.argv,
            skip_scores="--skip-scores" in sys.argv,
            skip_embeddings="--skip-embeddings" in sys.argv,
        )
    )
