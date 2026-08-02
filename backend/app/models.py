from datetime import datetime, timezone
from sqlalchemy import Integer, String, ForeignKey, DateTime, CheckConstraint
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
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    platform: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="planning_to_watch")
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    owner: Mapped["User"] = relationship("User", back_populates="watchlist")
