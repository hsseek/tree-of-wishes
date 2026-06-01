import enum
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, DateTime, Date, Boolean, Enum as SAEnum,
    ForeignKey, UniqueConstraint, Index, case
)
from sqlalchemy.orm import relationship
from .database import Base


class WishStatus(str, enum.Enum):
    active = "active"
    fulfilled = "fulfilled"
    dead = "dead"


class Wish(Base):
    __tablename__ = "wishes"

    id = Column(Integer, primary_key=True, index=True)
    text = Column(String, nullable=False)
    name = Column(String, nullable=True)
    attachment_path = Column(String, nullable=True)
    attachment_filename = Column(String, nullable=True)
    attachment_mimetype = Column(String, nullable=True)
    password_hash = Column(String, nullable=True)
    due_date = Column(Date, nullable=False)
    status = Column(SAEnum(WishStatus), nullable=False, default=WishStatus.active)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    fulfilled_at = Column(DateTime, nullable=True)
    likes = Column(Integer, nullable=False, default=0)
    views = Column(Integer, nullable=False, default=0)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    # "tree" or "columbarium" — which store this wish lives in
    board = Column(String, nullable=False, default="tree")

    owner = relationship("User", back_populates="wishes")
    like_records = relationship("LikeRecord", back_populates="wish", cascade="all, delete-orphan")
    view_records = relationship("ViewRecord", back_populates="wish", cascade="all, delete-orphan")

    __table_args__ = (
        # Serves the expiry sweep (board + status + due_date range) run on every page load,
        # and the board filter shared by both list queries and capacity counts.
        Index("ix_wishes_board_status_due", "board", "status", "due_date"),
        # Serves the columbarium listing: WHERE board='columbarium' ORDER BY due_date DESC.
        Index("ix_wishes_board_due", "board", "due_date"),
    )


def effective_age_expr():
    """SQLAlchemy expression for ordering: fulfilled_at if fulfilled, else created_at."""
    return case(
        (Wish.status == WishStatus.fulfilled, Wish.fulfilled_at),
        else_=Wish.created_at,
    )


class User(Base):
    __tablename__ = "users"

    id           = Column(Integer, primary_key=True, index=True)
    email        = Column(String, unique=True, nullable=False)
    google_id    = Column(String, nullable=True)
    display_name = Column(String, nullable=True)
    avatar_url   = Column(String, nullable=True)
    language     = Column(String, nullable=False, default='en')
    created_at   = Column(DateTime, nullable=False, default=datetime.utcnow)

    wishes = relationship("Wish", back_populates="owner")


class LikeRecord(Base):
    """Tracks per-IP likes for deduplication."""
    __tablename__ = "like_records"

    id = Column(Integer, primary_key=True, index=True)
    ip = Column(String, nullable=False)
    wish_id = Column(Integer, ForeignKey("wishes.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    wish = relationship("Wish", back_populates="like_records")

    __table_args__ = (
        UniqueConstraint("ip", "wish_id", name="uq_like_ip_wish"),
        Index("ix_like_records_wish_id", "wish_id"),
    )


class ViewRecord(Base):
    """Tracks per-IP views for deduplication (windowed)."""
    __tablename__ = "view_records"

    id = Column(Integer, primary_key=True, index=True)
    ip = Column(String, nullable=False)
    wish_id = Column(Integer, ForeignKey("wishes.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    wish = relationship("Wish", back_populates="view_records")

    __table_args__ = (
        Index("ix_view_records_wish_ip", "wish_id", "ip"),
        # Serves check_view_rate: WHERE ip=? AND created_at>=? on a table that grows per view.
        Index("ix_view_records_ip_created", "ip", "created_at"),
    )


class CreationRateRecord(Base):
    """Tracks wish creation attempts per IP for rate limiting."""
    __tablename__ = "creation_rate_records"

    id = Column(Integer, primary_key=True, index=True)
    ip = Column(String, nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class DailyVisit(Base):
    """One row per unique visitor per day. visitor_key is "u{user_id}" for a
    logged-in user, else the anonymous "tow_vid" cookie value. The unique
    constraint keeps this table to one row per visitor per day."""
    __tablename__ = "daily_visits"

    id = Column(Integer, primary_key=True, index=True)
    day = Column(Date, nullable=False)
    visitor_key = Column(String, nullable=False)
    registered = Column(Boolean, nullable=False, default=False)
    # Referral source from the landing URL's ?src= on the day's first visit
    # (first-touch attribution per visitor per day); NULL means direct/unknown.
    source = Column(String, nullable=True)

    __table_args__ = (
        UniqueConstraint("day", "visitor_key", name="uq_daily_visit"),
        # Serves the dashboard: GROUP BY day, registered over a date range.
        Index("ix_daily_visits_day", "day"),
    )


class DailyDwell(Base):
    """Daily rollup of time-on-page samples. Kept as a single row per day
    (running total + count) so the table never grows per page view."""
    __tablename__ = "daily_dwell"

    day = Column(Date, primary_key=True)
    total_seconds = Column(Integer, nullable=False, default=0)
    sample_count = Column(Integer, nullable=False, default=0)
