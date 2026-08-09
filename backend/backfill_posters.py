"""Fetch TMDB metadata and posters for watchlist rows that never got any.

Enrichment runs when an item is created, so anything added before that existed
has no catalogue link. Migration 002 only promoted posters that already existed,
which those rows did not have. This closes that gap.

Safe to re-run: rows already linked are skipped, and posters upsert in place.

    cd backend && ./.venv/Scripts/python.exe backfill_posters.py [--dry-run]
"""

import sys
import time

from app import media_catalogue
from app.database import SessionLocal
from app.models import WatchlistItem

# TMDB's documented limit is generous, but a backfill is the one place we make
# a burst of calls, so space them out.
DELAY_SECONDS = 0.3


def main(dry_run: bool = False) -> int:
    db = SessionLocal()
    try:
        pending = (
            db.query(WatchlistItem)
            .filter(WatchlistItem.media_id.is_(None))
            .filter(WatchlistItem.poster_url.is_(None))
            .order_by(WatchlistItem.user_id, WatchlistItem.id)
            .all()
        )

        print(f"{len(pending)} item(s) without a poster\n")
        if dry_run:
            for item in pending:
                print(f"  would look up: {item.title!r} (user {item.user_id})")
            return 0

        resolved, failed = 0, []
        for item in pending:
            media = media_catalogue.enrich_item(db, item)
            if media:
                resolved += 1
                print(f"  OK    {item.title!r} -> media {media.id} ({media.year})")
            else:
                failed.append(item.title)
                print(f"  MISS  {item.title!r} — no TMDB match")
            time.sleep(DELAY_SECONDS)

        print(f"\nresolved {resolved}, unresolved {len(failed)}")
        if failed:
            print("\nNo TMDB match for these — they need a manual poster or a")
            print("scraped one (see the poster-fetcher agent):")
            for title in failed:
                print(f"  - {title}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main(dry_run="--dry-run" in sys.argv))
