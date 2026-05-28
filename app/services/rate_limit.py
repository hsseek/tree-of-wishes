from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from ..models import LikeRecord, ViewRecord, CreationRateRecord
from ..config import (
    CREATION_LIMIT_PER_HOUR, VIEW_DEDUP_WINDOW_SECONDS,
    LIKE_RATE_LIMIT_PER_HOUR, VIEW_RATE_LIMIT_PER_HOUR,
)


def check_creation_rate(db: Session, ip: str) -> bool:
    """Return True if this IP is allowed to create a wish right now."""
    window_start = datetime.utcnow() - timedelta(hours=1)
    count = (
        db.query(CreationRateRecord)
        .filter(
            CreationRateRecord.ip == ip,
            CreationRateRecord.created_at >= window_start,
        )
        .count()
    )
    return count < CREATION_LIMIT_PER_HOUR


def record_creation(db: Session, ip: str):
    db.add(CreationRateRecord(ip=ip, created_at=datetime.utcnow()))
    db.flush()


def can_like(db: Session, ip: str, wish_id: int) -> bool:
    """Return True if this IP has not already liked this wish."""
    exists = (
        db.query(LikeRecord)
        .filter(LikeRecord.ip == ip, LikeRecord.wish_id == wish_id)
        .first()
    )
    return exists is None


def record_like(db: Session, ip: str, wish_id: int) -> bool:
    """
    Attempt to record a like. Returns True if the like was accepted,
    False if this IP already liked this wish (duplicate).
    """
    record = LikeRecord(ip=ip, wish_id=wish_id, created_at=datetime.utcnow())
    db.add(record)
    try:
        db.flush()
        return True
    except IntegrityError:
        db.rollback()
        return False


def can_record_view(db: Session, ip: str, wish_id: int) -> bool:
    """Return True if this IP hasn't viewed this wish within the dedup window."""
    window_start = datetime.utcnow() - timedelta(seconds=VIEW_DEDUP_WINDOW_SECONDS)
    exists = (
        db.query(ViewRecord)
        .filter(
            ViewRecord.ip == ip,
            ViewRecord.wish_id == wish_id,
            ViewRecord.created_at >= window_start,
        )
        .first()
    )
    return exists is None


def record_view(db: Session, ip: str, wish_id: int):
    db.add(ViewRecord(ip=ip, wish_id=wish_id, created_at=datetime.utcnow()))
    db.flush()


def check_like_rate(db: Session, ip: str) -> bool:
    """Return True if this IP is under the hourly like rate limit."""
    window_start = datetime.utcnow() - timedelta(hours=1)
    count = (
        db.query(LikeRecord)
        .filter(LikeRecord.ip == ip, LikeRecord.created_at >= window_start)
        .count()
    )
    return count < LIKE_RATE_LIMIT_PER_HOUR


def check_view_rate(db: Session, ip: str) -> bool:
    """Return True if this IP is under the hourly view rate limit."""
    window_start = datetime.utcnow() - timedelta(hours=1)
    count = (
        db.query(ViewRecord)
        .filter(ViewRecord.ip == ip, ViewRecord.created_at >= window_start)
        .count()
    )
    return count < VIEW_RATE_LIMIT_PER_HOUR
