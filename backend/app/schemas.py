from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, EmailStr, field_validator, model_validator


StatusType = Literal["planning_to_watch", "watching", "finished", "dropped"]


# --- Auth ---

class EmailRequest(BaseModel):
    email: EmailStr


class UserResponse(BaseModel):
    id: int
    email: str
    created_at: datetime

    model_config = {"from_attributes": True}


class AuthResponse(BaseModel):
    user: UserResponse
    token: str


# --- Watchlist ---

class WatchlistItemCreate(BaseModel):
    title: str
    platform: str
    status: StatusType = "planning_to_watch"
    rating: Optional[int] = None

    @field_validator("rating")
    @classmethod
    def rating_range(cls, v):
        if v is not None and not (1 <= v <= 5):
            raise ValueError("Rating must be between 1 and 5")
        return v

    @model_validator(mode="after")
    def rating_required_when_finished(self):
        if self.status == "finished" and self.rating is None:
            raise ValueError("Rating is required when status is 'finished'")
        if self.status != "finished" and self.rating is not None:
            self.rating = None
        return self


class WatchlistItemUpdate(BaseModel):
    title: Optional[str] = None
    platform: Optional[str] = None
    status: Optional[StatusType] = None
    rating: Optional[int] = None

    @field_validator("rating")
    @classmethod
    def rating_range(cls, v):
        if v is not None and not (1 <= v <= 5):
            raise ValueError("Rating must be between 1 and 5")
        return v

    @model_validator(mode="after")
    def rating_required_when_finished(self):
        if self.status == "finished" and self.rating is None:
            raise ValueError("Rating is required when status is 'finished'")
        if self.status is not None and self.status != "finished":
            self.rating = None
        return self


class WatchlistItemResponse(BaseModel):
    id: int
    user_id: int
    title: str
    platform: str
    status: str
    rating: Optional[int]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# --- Dashboard ---

class DashboardStats(BaseModel):
    planning_to_watch: int
    watching: int
    finished: int
    dropped: int
    total: int


class DashboardResponse(BaseModel):
    stats: DashboardStats
    items: dict[str, list[WatchlistItemResponse]]
