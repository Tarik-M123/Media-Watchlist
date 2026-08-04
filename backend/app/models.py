from datetime import datetime, timezone
from sqlalchemy import Integer, String, Text, ForeignKey, DateTime, CheckConstraint
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    watchlist: Mapped[list["WatchlistItem"]] = relationship("WatchlistItem", back_populates="owner", cascade="all, delete-orphan")


class WatchlistItem(Base):
    __tablename__ = "watchlist"

    __table_args__ = (
        CheckConstraint("rating >= 1 AND rating <= 5", name="rating_range"),
        CheckConstraint("status IN ('planning_to_watch','watching','finished','dropped')", name="status_valid"),
        CheckConstraint("media_type IS NULL OR media_type IN ('movie','tv')", name="media_type_valid"),
        CheckConstraint("runtime_minutes IS NULL OR runtime_minutes > 0", name="runtime_positive"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    platform: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="planning_to_watch")
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # TMDB metadata — all nullable, populated by the watchlist-engine MCP server.
    # Items added through the API/frontend simply leave these NULL.
    tmdb_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    media_type: Mapped[str | None] = mapped_column(String(10), nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    runtime_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    genres: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    poster_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    synopsis: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    owner: Mapped["User"] = relationship("User", back_populates="watchlist")
