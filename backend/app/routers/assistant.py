"""Natural-language questions about the signed-in user's watchlist.

Requires authentication, like every other route that reads user data — the
assistant reads one user's rows and answers about them, so an unauthenticated
call would be asking whose watchlist.

Never fails hard. A missing API key or an unreachable model returns an empty
answer with a reason attached, because the dashboard has to keep working: the
assistant is an accelerator, not a gate.
"""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import assistant, models, schemas
from app.database import get_db
from app.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.post("/ask", response_model=schemas.AssistantResponse)
def ask(
    payload: schemas.AssistantAskRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    try:
        answer, sources = assistant.ask(
            db,
            current_user,
            payload.question,
            history=[turn.model_dump() for turn in payload.history],
        )
        return {"answer": answer, "sources": sources}
    except assistant.AssistantUnavailable as exc:
        # First line only: the not-configured message is a multi-line set of
        # setup instructions meant for a developer, not a chat panel.
        return {"unavailable": str(exc).splitlines()[0]}
    except Exception:
        logger.exception("Assistant failed for user %s", current_user.id)
        return {"unavailable": "The assistant is unavailable right now."}
