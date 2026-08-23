from datetime import datetime, timezone
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

# Which source wins when a title has several posters. Must stay identical to the
# CASE in the media_primary_poster view (migrations/002); test_poster_precedence
# asserts they agree.
POSTER_SOURCE_PRIORITY = {"manual": 0, "tmdb": 1, "scraped": 2}


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

    # Best-effort link into the shared catalogue. Nullable because `title` is
    # free text typed by users and cannot always be resolved to a media row;
    # NOT NULL would either block those inserts or force fabricated entries.
    media_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("media.id", ondelete="SET NULL"), nullable=True, index=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    owner: Mapped["User"] = relationship("User", back_populates="watchlist")
    media: Mapped["Media | None"] = relationship("Media")

    @property
    def primary_poster(self) -> "MediaPoster | None":
        """The winning poster for this title, or None."""
        if self.media is None:
            return None
        valid = [p for p in self.media.posters if p.is_valid]
        if not valid:
            return None
        return min(
            valid,
            key=lambda p: (POSTER_SOURCE_PRIORITY.get(p.source, 9), -p.fetched_at.timestamp()),
        )

    def _poster_of_size(self, size: str) -> str | None:
        if self.media is None:
            return None
        matches = [p for p in self.media.posters if p.is_valid and p.size_label == size]
        if not matches:
            return None
        return min(
            matches,
            key=lambda p: (POSTER_SOURCE_PRIORITY.get(p.source, 9), -p.fetched_at.timestamp()),
        ).url

    @property
    def display_poster_url(self) -> str | None:
        """Card-sized poster: the user's own override first, else the catalogue."""
        if self.poster_url:
            return self.poster_url
        return self._poster_of_size("w500") or (
            self.primary_poster.url if self.primary_poster else None
        )

    @property
    def display_poster_url_large(self) -> str | None:
        """Full-size poster for the detail view."""
        if self.poster_url:
            return self.poster_url
        return self._poster_of_size("original") or self.display_poster_url

    @property
    def vote_average(self) -> float | None:
        """TMDB's public score, which lives on the shared catalogue row.

        None for items that never resolved to a catalogue entry, and for rows
        catalogued before migration 003 added the column.
        """
        return self.media.vote_average if self.media else None


class Media(Base):
    """One row per real-world title, shared by every user tracking it."""

    __tablename__ = "media"

    __table_args__ = (
        CheckConstraint("media_type IN ('movie','tv')", name="ck_media_media_type"),
        CheckConstraint("runtime_minutes IS NULL OR runtime_minutes > 0", name="ck_media_runtime"),
        CheckConstraint("year IS NULL OR year BETWEEN 1888 AND 2100", name="ck_media_year"),
        CheckConstraint("tmdb_id IS NULL OR tmdb_id > 0", name="ck_media_tmdb_id"),
        CheckConstraint("vote_average IS NULL OR vote_average BETWEEN 0 AND 10",
                        name="ck_media_vote_average"),
        # A vector with no model recorded cannot be compared against anything,
        # because nothing establishes what it is comparable with.
        CheckConstraint("embedding IS NULL OR embedding_model IS NOT NULL",
                        name="ck_media_embedding_provenance"),
        Index("uq_media_tmdb", "tmdb_id", "media_type", unique=True,
              postgresql_where=text("tmdb_id IS NOT NULL")),
        Index("uq_media_title_key", "title_key", "media_type", text("COALESCE(year, -1)"),
              unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tmdb_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    media_type: Mapped[str] = mapped_column(String(10), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)

    # Computed by Postgres so it can never drift from title; never assigned
    # from Python.
    title_key: Mapped[str] = mapped_column(
        Text, Computed("lower(btrim(title))", persisted=True), nullable=False
    )

    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    runtime_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    genres: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    synopsis: Mapped[str | None] = mapped_column(Text, nullable=True)

    # TMDB's 0-10 community score. Distinct from WatchlistItem.rating, which is
    # one user's 1-5 opinion: a title has one vote_average and as many ratings
    # as it has viewers.
    vote_average: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Semantic fingerprint of this title — see migrations/003 and
    # app/embeddings.py. Only comparable against vectors sharing
    # embedding_model, which is why the model name is stored beside it.
    embedding: Mapped[list[float] | None] = mapped_column(ARRAY(Float), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    posters: Mapped[list["MediaPoster"]] = relationship(
        "MediaPoster", back_populates="media", cascade="all, delete-orphan")


class MediaPoster(Base):
    """One row per (title, source, size).

    Several rows per title is the point: a TMDB poster and a scraped poster
    coexist and the read path picks a winner, so a low-confidence scrape can
    never destroy the API value.
    """

    __tablename__ = "media_posters"

    __table_args__ = (
        CheckConstraint("source IN ('tmdb','scraped','manual')", name="ck_media_posters_source"),
        CheckConstraint(r"url ~ '^https://[^ ]+$' AND length(url) BETWEEN 12 AND 2048",
                        name="ck_media_posters_url"),
        CheckConstraint("(width IS NULL OR width > 0) AND (height IS NULL OR height > 0)",
                        name="ck_media_posters_dims"),
        CheckConstraint("source <> 'scraped' OR source_page_url IS NOT NULL",
                        name="ck_media_posters_scrape_provenance"),
        CheckConstraint("last_verified_at IS NULL OR last_verified_at >= fetched_at",
                        name="ck_media_posters_verified_after_fetch"),
        Index("uq_media_posters_slot", "media_id", "source", "size_label", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    media_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("media.id", ondelete="CASCADE"), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    size_label: Mapped[str] = mapped_column(String(16), nullable=False, default="original")
    url: Mapped[str] = mapped_column(Text, nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_page_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_valid: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    media: Mapped["Media"] = relationship("Media", back_populates="posters")
