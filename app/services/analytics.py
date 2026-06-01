"""Lightweight, self-hosted visit + time-on-page tracking.

Visits are deduplicated to one row per visitor per day (enforced by a unique
constraint and short-circuited by an in-process cache so repeat page loads cost
nothing). Time-on-page is rolled up into a single row per day.
"""
import threading
from datetime import datetime

from sqlalchemy.exc import IntegrityError

from ..database import SessionLocal
from ..models import DailyVisit, DailyDwell

# Page routes worth counting as a "visit". Excludes /static, /api, /auth.
TRACKED_PATHS = {"/tree", "/columbarium", "/about", "/my-wishes", "/settings"}

# Upper bound on a single time-on-page sample (seconds). Caps garbage from tabs
# left open for hours so they don't skew the average.
MAX_DWELL_SECONDS = 1800

_lock = threading.Lock()
_seen_day = None          # the day _seen_keys is valid for
_seen_keys: set[str] = set()  # visitor_keys already recorded today


def _today():
    return datetime.utcnow().date()


def record_visit(visitor_key: str, registered: bool, source: str | None = None) -> None:
    """Record at most one visit per visitor per day. The in-process cache skips
    the DB write for repeat loads; the unique constraint is the source of truth
    across restarts and concurrent workers. ``source`` (from the landing ?src=)
    is captured on the day's first visit only — first-touch attribution."""
    today = _today()
    global _seen_day, _seen_keys
    with _lock:
        if _seen_day != today:
            _seen_day, _seen_keys = today, set()
        if visitor_key in _seen_keys:
            return
        _seen_keys.add(visitor_key)

    db = SessionLocal()
    try:
        db.add(DailyVisit(
            day=today, visitor_key=visitor_key, registered=registered, source=source,
        ))
        db.commit()
    except IntegrityError:
        db.rollback()  # already recorded (race or stale cache after restart)
    finally:
        db.close()


def record_dwell(seconds: int) -> None:
    """Add one time-on-page sample to today's rollup row."""
    seconds = max(0, min(int(seconds), MAX_DWELL_SECONDS))
    today = _today()
    db = SessionLocal()
    try:
        row = db.get(DailyDwell, today)
        if row is None:
            row = DailyDwell(day=today, total_seconds=0, sample_count=0)
            db.add(row)
        row.total_seconds += seconds
        row.sample_count += 1
        db.commit()
    except IntegrityError:
        # Another worker created today's row first; retry the increment once.
        db.rollback()
        row = db.get(DailyDwell, today)
        if row is not None:
            row.total_seconds += seconds
            row.sample_count += 1
            db.commit()
    finally:
        db.close()
