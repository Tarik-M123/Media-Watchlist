"""Small runtime settings read from the environment."""

import os

# Streaming availability is country-specific — TMDB keys it by region, so a
# title on Netflix in one market may have no entry at all in another. Bosnia is
# the default because that is where this app is used; change WATCH_REGION in
# backend/.env rather than editing code.
DEFAULT_WATCH_REGION = "BA"


def watch_region() -> str:
    """ISO 3166-1 country code used for provider lookups."""
    return (os.getenv("WATCH_REGION") or DEFAULT_WATCH_REGION).strip().upper()
