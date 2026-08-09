"""Read-only TMDB lookups for the Add form: title suggestions and streaming platforms.

Both routes require authentication. Without it these would be an open proxy to a
third-party API being called with our credential.

Neither route fails hard. A missing key or an unreachable TMDB returns an empty
result with a reason attached, because the Add form has to keep working — the
picker is an accelerator, not a gate.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app import config, models, schemas, tmdb
from app.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/media", tags=["media"])

# Below this, a query matches half of TMDB and is being fired mid-keystroke.
MIN_QUERY_LENGTH = 2


@router.get("/search", response_model=schemas.MediaSearchResponse)
def search_media(
    q: str = Query(..., description="Partial title to search for"),
    current_user: models.User = Depends(get_current_user),
):
    if len(q.strip()) < MIN_QUERY_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Type at least {MIN_QUERY_LENGTH} characters to search.",
        )

    try:
        return {"results": tmdb.search_candidates(q)}
    except tmdb.TMDBError as exc:
        # First line only: the not-configured message is a multi-line set of
        # setup instructions meant for a developer, not a form field.
        return {"results": [], "unavailable": str(exc).splitlines()[0]}
    except Exception:
        logger.exception("Title search failed for %r", q)
        return {"results": [], "unavailable": "Title search is unavailable right now."}


@router.get("/providers/{media_type}/{tmdb_id}", response_model=schemas.WatchProvidersResponse)
def get_watch_providers(
    media_type: schemas.MediaType,
    tmdb_id: int,
    current_user: models.User = Depends(get_current_user),
):
    region = config.watch_region()
    try:
        return tmdb.watch_providers(tmdb_id, media_type, region)
    except tmdb.TMDBError as exc:
        return {"region": region, "unavailable": str(exc).splitlines()[0]}
    except Exception:
        logger.exception("Provider lookup failed for %s/%s", media_type, tmdb_id)
        return {"region": region, "unavailable": "Streaming info is unavailable right now."}
