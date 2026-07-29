from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app import models, schemas
from app.dependencies import create_token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=schemas.AuthResponse)
def login(payload: schemas.EmailRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == payload.email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User does not exist, please register",
        )
    token = create_token(user.id)
    return {"user": user, "token": token}


@router.post("/register", response_model=schemas.AuthResponse, status_code=status.HTTP_201_CREATED)
def register(payload: schemas.EmailRequest, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(models.User.email == payload.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )
    user = models.User(email=payload.email)
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_token(user.id)
    return {"user": user, "token": token}
