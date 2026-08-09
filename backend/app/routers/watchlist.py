from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, selectinload
from app.database import get_db
from app import media_catalogue, models, schemas
from app.dependencies import get_current_user

router = APIRouter(prefix="/watchlist", tags=["watchlist"])

# Without this, WatchlistItemResponse's poster fields walk item.media.posters
# per row and turn one query into 2N.
WITH_POSTERS = selectinload(models.WatchlistItem.media).selectinload(models.Media.posters)


@router.get("/", response_model=list[schemas.WatchlistItemResponse])
def get_watchlist(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return (
        db.query(models.WatchlistItem)
        .options(WITH_POSTERS)
        .filter(models.WatchlistItem.user_id == current_user.id)
        .all()
    )


@router.post("/", response_model=schemas.WatchlistItemResponse, status_code=status.HTTP_201_CREATED)
def create_item(
    payload: schemas.WatchlistItemCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    item = models.WatchlistItem(**payload.model_dump(), user_id=current_user.id)
    db.add(item)
    db.commit()
    db.refresh(item)

    # Best-effort: the item is already committed above, so a TMDB outage, a
    # missing key, or an unrecognised title costs the poster, not the 201.
    media_catalogue.enrich_item(db, item)

    return item


@router.patch("/{item_id}", response_model=schemas.WatchlistItemResponse)
def update_item(
    item_id: int,
    payload: schemas.WatchlistItemUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    item = db.query(models.WatchlistItem).filter(
        models.WatchlistItem.id == item_id,
        models.WatchlistItem.user_id == current_user.id,
    ).first()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")

    update_data = payload.model_dump(exclude_unset=True)

    new_status = update_data.get("status", item.status)
    new_rating = update_data.get("rating", item.rating)

    if new_status == "finished" and new_rating is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Rating is required when status is 'finished'",
        )
    if new_status != "finished":
        update_data["rating"] = None

    for field, value in update_data.items():
        setattr(item, field, value)

    db.commit()
    db.refresh(item)
    return item


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    item = db.query(models.WatchlistItem).filter(
        models.WatchlistItem.id == item_id,
        models.WatchlistItem.user_id == current_user.id,
    ).first()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    db.delete(item)
    db.commit()
