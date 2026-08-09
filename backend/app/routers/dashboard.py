from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, selectinload
from app.database import get_db
from app import models, schemas
from app.dependencies import get_current_user

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

STATUSES = ["planning_to_watch", "watching", "finished", "dropped"]


@router.get("/", response_model=schemas.DashboardResponse)
def get_dashboard(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    all_items = (
        db.query(models.WatchlistItem)
        # Eager-load the catalogue and its posters: the response model resolves
        # a poster per item, which would otherwise be 2N queries.
        .options(selectinload(models.WatchlistItem.media).selectinload(models.Media.posters))
        .filter(models.WatchlistItem.user_id == current_user.id)
        .all()
    )

    grouped: dict[str, list] = {s: [] for s in STATUSES}
    counts = {s: 0 for s in STATUSES}

    for item in all_items:
        grouped.setdefault(item.status, []).append(item)
        counts[item.status] = counts.get(item.status, 0) + 1

    stats = schemas.DashboardStats(
        planning_to_watch=counts["planning_to_watch"],
        watching=counts["watching"],
        finished=counts["finished"],
        dropped=counts["dropped"],
        total=len(all_items),
    )

    return {"stats": stats, "items": grouped}
