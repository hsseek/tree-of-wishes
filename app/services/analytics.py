"""Lightweight, self-hosted visit + time-on-page tracking.

Visits are deduplicated to one row per visitor per day (enforced by a unique
constraint and short-circuited by an in-process cache so repeat page loads cost
nothing). Time-on-page is rolled up into a single row per day.
"""
import threading
from datetime import datetime
from urllib.parse import urlsplit

from sqlalchemy.exc import IntegrityError

from ..database import SessionLocal
from ..models import DailyVisit, DailyDwell

# Page routes worth counting as a "visit". Excludes /static, /api, /auth.
TRACKED_PATHS = {"/tree", "/columbarium", "/about", "/my-wishes", "/settings"}

# Upper bound on a single time-on-page sample (seconds). Caps garbage from tabs
# left open for hours so they don't skew the average.
MAX_DWELL_SECONDS = 1800

# Referrer hosts worth collapsing into one stable tag. Matched against the host
# with any leading "www."/"m."/"l."/"lm." stripped, either exactly or as a
# suffix (so "search.naver.com" and "co.search.naver.com" both hit "naver.com").
# Hosts not listed here are kept verbatim, which surfaces the long tail.
_REFERRER_TAGS = {
    "instagram.com": "instagram",
    "threads.com": "threads",
    "threads.net": "threads",
    "facebook.com": "facebook",
    "fb.com": "facebook",
    "google.com": "google",
    "naver.com": "naver",
    "daum.net": "daum",
    "kakao.com": "kakao",
    "kakaocorp.com": "kakao",
    "t.co": "x",
    "x.com": "x",
    "twitter.com": "x",
    "youtube.com": "youtube",
    "youtu.be": "youtube",
    "reddit.com": "reddit",
    "bing.com": "bing",
    "duckduckgo.com": "duckduckgo",
    "chatgpt.com": "chatgpt",
    "chat.openai.com": "chatgpt",
    "claude.ai": "claude",
    "perplexity.ai": "perplexity",
    "linkedin.com": "linkedin",
    "pinterest.com": "pinterest",
    "tiktok.com": "tiktok",
    "discord.com": "discord",
    "t.me": "telegram",
}

# Sub-domain prefixes that carry no attribution meaning. "l."/"lm." are the
# Meta link shims (l.instagram.com, lm.facebook.com).
_STRIP_PREFIXES = ("www.", "m.", "l.", "lm.")


def clean_source(raw: str | None) -> str | None:
    """Normalise a source value to a short, safe tag; None if absent or empty.
    Permits dots so a bare referrer host ("someblog.tistory.com") survives."""
    if not raw:
        return None
    tag = "".join(c for c in raw.lower() if c.isalnum() or c in "-_.")[:40]
    return tag.strip(".") or None


def classify_referrer(referrer: str | None, self_host: str | None) -> str | None:
    """Map a referring URL to a source tag. Returns None for absent, malformed,
    or same-site referrers — a visitor arriving from our own pages tells us
    nothing about where they originally came from, so it counts as direct."""
    if not referrer:
        return None
    try:
        host = (urlsplit(referrer).hostname or "").lower()
    except ValueError:
        return None
    if not host:
        return None

    for prefix in _STRIP_PREFIXES:
        if host.startswith(prefix):
            host = host[len(prefix):]
            break

    if self_host and (host == self_host or host.endswith(f".{self_host}")):
        return None

    # Google's country domains (google.co.kr, google.de, ...) all mean "google".
    if host == "google" or host.startswith("google."):
        return "google"

    for known, tag in _REFERRER_TAGS.items():
        if host == known or host.endswith(f".{known}"):
            return tag
    return clean_source(host)

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
