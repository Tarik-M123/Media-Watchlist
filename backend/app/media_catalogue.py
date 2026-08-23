"""Resolve a watchlist item to a shared catalogue entry and cache its posters.

Every function here is best-effort. Enrichment is a nice-to-have layered on top
of item creation: if TMDB is unreachable, unconfigured, or has no match, the
item must still be created. Callers get None rather than an exception.
"""

import logging

from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app import embeddings, tmdb
from app.models import Media, MediaPoster

logger = logging.getLogger(__name__)

# TMDB serves the same file at many widths. w500 backs the card grid; original
# backs the detail modal.
POSTER_SIZES = (
    ("w500", tmdb.POSTER_SIZE_CARD),
    ("original", tmdb.POSTER_SIZE_LARGE),
)


def _upsert_media(db: Session, data: dict) -> Media | None:
    """Find or create the catalogue row for a TMDB payload."""
    if not data.get("media_type") or not data.get("title"):
        return None

    values = {
        "tmdb_id": data.get("tmdb_id"),
        "media_type": data["media_type"],
        "title": data["title"],
        "year": data.get("year"),
        "runtime_minutes": data.get("runtime_minutes"),
        "genres": data.get("genres") or None,
        "synopsis": data.get("synopsis"),
        # Fetched by tmdb._normalise since 001 and discarded until migration 003
        # gave it somewhere to live.
        "vote_average": data.get("vote_average"),
    }

    # DO NOTHING rather than DO UPDATE: a later lookup of the same title should
    # not silently rewrite a catalogue row other users are already seeing.
    # index_elements cannot be used here because both unique indexes are
    # expression-based (partial on tmdb_id, COALESCE(year,-1) on the other), so
    # the conflict target is left to Postgres.
    db.execute(pg_insert(Media).values(**values).on_conflict_do_nothing())
    db.flush()

    q = db.query(Media).filter(Media.media_type == values["media_type"])
    if values["tmdb_id"] is not None:
        return q.filter(Media.tmdb_id == values["tmdb_id"]).first()
    return (
        q.filter(Media.title_key == values["title"].strip().lower())
        .filter(Media.year.is_(values["year"]) if values["year"] is None else Media.year == values["year"])
        .first()
    )


def _record_posters(db: Session, media: Media, poster_path: str | None) -> None:
    """Store the card and full-size URLs for one TMDB poster path."""
    if not poster_path:
        return

    for size_label, tmdb_size in POSTER_SIZES:
        url = tmdb.poster_url(poster_path, size=tmdb_size)
        if not url:
            continue
        db.execute(
            pg_insert(MediaPoster)
            .values(media_id=media.id, source="tmdb", size_label=size_label, url=url)
            # Re-fetching a size updates the URL in place instead of piling up
            # rows; uq_media_posters_slot is the conflict target.
            .on_conflict_do_update(
                index_elements=["media_id", "source", "size_label"],
                set_={"url": url, "is_valid": True},
            )
        )


def record_embedding(db: Session, media: Media, *, force: bool = False) -> bool:
    """Compute and store the semantic fingerprint for one catalogue entry.

    Returns True if a vector was written. Never raises: semantic search is an
    accelerator, and a missing model must not cost the caller its catalogue row.
    The vector is assigned only after the model returns, so a failure leaves the
    surrounding transaction untouched rather than half-written.

    Skips rows that already carry a current vector unless `force` is set.
    _upsert_media never rewrites an existing row's text, so for anything reached
    through enrich_item a present vector is by definition still accurate.
    """
    if not force and media.embedding and media.embedding_model == embeddings.MODEL_NAME:
        return False

    try:
        vectors = embeddings.embed_documents([embeddings.document_for(media)])
    except embeddings.EmbeddingsUnavailable as exc:
        # First line only: the not-installed message is multi-line setup
        # instructions meant for a developer, not a log.
        logger.info("Embedding skipped for %r: %s", media.title, str(exc).splitlines()[0])
        return False
    except Exception:
        logger.exception("Unexpected embedding failure for %r", media.title)
        return False

    if not vectors:
        return False

    media.embedding = vectors[0]
    media.embedding_model = embeddings.MODEL_NAME
    media.embedding_updated_at = datetime.now(timezone.utc)
    return True


def enrich_item(db: Session, item, *, timeout=tmdb.ENRICH_TIMEOUT) -> Media | None:
    """Look the item's title up on TMDB and attach it to the catalogue.

    Returns the linked Media, or None if anything went wrong. Never raises:
    creating a watchlist item must not depend on a third party being reachable.
    """
    try:
        if item.tmdb_id and item.media_type:
            # The user picked this title from the suggestions, so the identity is
            # settled — searching the typed text again could land on a different show.
            data = tmdb.details(item.tmdb_id, item.media_type, timeout=timeout)
        else:
            data = tmdb.search(item.title, media_type=item.media_type or "auto", timeout=timeout)
    except tmdb.TMDBError as exc:
        # First line only — the not-configured message is a multi-line set of
        # setup instructions that would swamp the log.
        logger.info("TMDB enrichment skipped for %r: %s", item.title, str(exc).splitlines()[0])
        return None
    except Exception:
        logger.exception("Unexpected TMDB enrichment failure for %r", item.title)
        return None

    try:
        media = _upsert_media(db, data)
        if media is None:
            return None

        _record_posters(db, media, data.get("poster_path"))
        # Swallows its own failures, so a missing embedding model costs the
        # semantic search and nothing else.
        record_embedding(db, media)

        item.media_id = media.id
        # Mirror the metadata onto the item too, so existing consumers that read
        # these columns directly (get_watchlist_stats) see enriched rows.
        for field in ("tmdb_id", "media_type", "year", "runtime_minutes", "genres", "synopsis"):
            if getattr(item, field, None) is None and data.get(field) is not None:
                setattr(item, field, data[field])

        db.commit()
        db.refresh(item)
        return media
    except Exception:
        logger.exception("Failed to record catalogue entry for %r", item.title)
        db.rollback()
        return None
