from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


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

MediaType = Literal["movie", "tv"]


class MediaCandidate(BaseModel):
    """One suggestion in the Add form's title picker."""
    tmdb_id: int
    media_type: MediaType
    title: str
    year: Optional[int] = None
    poster_thumb: Optional[str] = None


class MediaSearchResponse(BaseModel):
    results: list[MediaCandidate] = []
    # Set when the lookup could not run (no API key, TMDB unreachable). The form
    # stays usable in that case, so this is a note rather than an error status.
    unavailable: Optional[str] = None


class WatchProvidersResponse(BaseModel):
    region: str
    streaming: list[str] = []
    rent: list[str] = []
    buy: list[str] = []
    link: Optional[str] = None
    unavailable: Optional[str] = None


class WatchlistItemCreate(BaseModel):
    title: str
    platform: str
    status: StatusType = "planning_to_watch"
    rating: Optional[int] = None

    # Present when the user picked a suggestion, so enrichment can fetch that
    # exact title instead of searching for the typed text again.
    tmdb_id: Optional[int] = None
    media_type: Optional[MediaType] = None

    @field_validator("rating")
    @classmethod
    def rating_range(cls, v):
        if v is not None and not (1 <= v <= 5):
            raise ValueError("Rating must be between 1 and 5")
        return v

    @model_validator(mode="after")
    def validate_rating(self):
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


class PosterRef(BaseModel):
    """Provenance for the poster actually being shown — attribution and debugging."""
    url: str
    source: str            # 'tmdb' | 'scraped' | 'manual'
    size_label: str
    width: Optional[int] = None
    height: Optional[int] = None
    fetched_at: datetime

    model_config = {"from_attributes": True}


class WatchlistItemResponse(BaseModel):
    id: int
    user_id: int
    title: str
    platform: str
    status: str
    rating: Optional[int]

    # TMDB metadata. These columns have existed since migration 001 but were
    # never exposed, so the frontend could not render anything from them.
    tmdb_id: Optional[int] = None
    media_type: Optional[str] = None
    year: Optional[int] = None
    runtime_minutes: Optional[int] = None
    genres: Optional[list[str]] = None
    synopsis: Optional[str] = None

    # Posters. Already resolved server-side (per-user override, then the
    # catalogue winner), so the frontend just renders the URL or falls back to a
    # placeholder when it is null.
    media_id: Optional[int] = None
    poster_url: Optional[str] = Field(default=None, validation_alias="display_poster_url")
    poster_url_large: Optional[str] = Field(default=None, validation_alias="display_poster_url_large")
    poster: Optional[PosterRef] = Field(default=None, validation_alias="primary_poster")

    created_at: datetime
    updated_at: datetime

    # populate_by_name lets the field names still work when a response is built
    # from a dict rather than an ORM object.
    model_config = {"from_attributes": True, "populate_by_name": True}


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
