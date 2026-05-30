import json
import time
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import GOOGLE_CLIENT_ID, ADMIN_EMAIL
from ..database import get_db
from ..models import User, Wish, DailyVisit, DailyDwell
from ..services.expiry import sweep_expired_wishes

router = APIRouter()
templates = Jinja2Templates(directory="templates")
templates.env.globals["sv"] = str(int(time.time()))

_SUPPORTED_LANGS = {"en", "ko"}


def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.get(User, user_id)


def _is_admin(user: Optional[User]) -> bool:
    return bool(ADMIN_EMAIL and user and user.email == ADMIN_EMAIL)


def _get_season() -> str:
    month = datetime.utcnow().month
    if month in (3, 4, 5):
        return "spring"
    elif month in (6, 7, 8):
        return "summer"
    elif month in (9, 10, 11):
        return "autumn"
    else:
        return "winter"


@lru_cache(maxsize=None)
def _load_locale(lang: str) -> str:
    path = Path("static/locales") / f"{lang}.json"
    return path.read_text(encoding="utf-8")


def _detect_lang(request: Request, user: Optional[User]) -> str:
    if user and user.language in _SUPPORTED_LANGS:
        return user.language
    cookie = request.cookies.get("tow_lang", "")
    if cookie in _SUPPORTED_LANGS:
        return cookie
    accept = request.headers.get("accept-language", "")
    return "ko" if "ko" in accept.lower() else "en"


def _base_ctx(request: Request, current_user: Optional[User]) -> dict:
    lang = _detect_lang(request, current_user)
    return {
        "request": request,
        "current_user": current_user,
        "season": _get_season(),
        "is_admin": _is_admin(current_user),
        "lang": lang,
        "translations_json": _load_locale(lang),
    }


@router.get("/", response_class=RedirectResponse)
def root():
    return RedirectResponse(url="/tree", status_code=302)


@router.get("/wish/{wish_id}", response_class=RedirectResponse)
def wish_deep_link(wish_id: int, db: Session = Depends(get_db)):
    wish = db.query(Wish).filter(Wish.id == wish_id).first()
    if not wish:
        raise HTTPException(404, "Wish not found")
    return RedirectResponse(url=f"/{wish.board}?open={wish_id}", status_code=302)


@router.get("/tree", response_class=HTMLResponse)
def tree_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    sweep_expired_wishes(db)
    return templates.TemplateResponse("tree.html", _base_ctx(request, current_user))


@router.get("/columbarium", response_class=HTMLResponse)
def columbarium_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    sweep_expired_wishes(db)
    return templates.TemplateResponse("columbarium.html", _base_ctx(request, current_user))


@router.get("/settings", response_class=HTMLResponse)
def settings_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    return templates.TemplateResponse("settings.html", _base_ctx(request, current_user))


@router.get("/about", response_class=HTMLResponse)
def about_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    return templates.TemplateResponse("about.html", _base_ctx(request, current_user))


@router.get("/admin/analytics", response_class=HTMLResponse)
def admin_analytics_page(
    request: Request,
    days: int = 30,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    # Hide existence from non-admins.
    if not _is_admin(current_user):
        raise HTTPException(404, "Not found")

    days = max(1, min(days, 365))
    today = datetime.utcnow().date()
    start_day = today - timedelta(days=days - 1)
    start_dt = datetime.combine(start_day, datetime.min.time())

    # Unique visitors per day, split by registered flag.
    visit_rows = (
        db.query(DailyVisit.day, DailyVisit.registered, func.count().label("n"))
        .filter(DailyVisit.day >= start_day)
        .group_by(DailyVisit.day, DailyVisit.registered)
        .all()
    )
    anon = {}
    reg = {}
    for day, registered, n in visit_rows:
        (reg if registered else anon)[day.isoformat()] = n

    # Registrations per day, derived from users.created_at.
    reg_rows = (
        db.query(func.date(User.created_at).label("d"), func.count().label("n"))
        .filter(User.created_at >= start_dt)
        .group_by("d")
        .all()
    )
    registrations = {str(d): n for d, n in reg_rows}

    # Average time-on-page per day from the daily rollup.
    dwell_rows = (
        db.query(DailyDwell).filter(DailyDwell.day >= start_day).all()
    )
    avg_dwell = {
        r.day.isoformat(): (r.total_seconds / r.sample_count if r.sample_count else 0)
        for r in dwell_rows
    }

    rows = []
    totals = {"anon": 0, "reg": 0, "visits": 0, "registrations": 0}
    for i in range(days):
        d = today - timedelta(days=i)
        key = d.isoformat()
        a = anon.get(key, 0)
        r = reg.get(key, 0)
        reg_count = registrations.get(key, 0)
        secs = avg_dwell.get(key, 0)
        totals["anon"] += a
        totals["reg"] += r
        totals["visits"] += a + r
        totals["registrations"] += reg_count
        rows.append({
            "date": key,
            "anon": a,
            "registered": r,
            "total": a + r,
            "registrations": reg_count,
            "avg_dwell": _fmt_duration(secs),
        })

    ctx = _base_ctx(request, current_user)
    ctx.update({"active_page": "admin", "rows": rows, "totals": totals, "days": days})
    return templates.TemplateResponse("admin_analytics.html", ctx)


def _fmt_duration(seconds: float) -> str:
    seconds = int(round(seconds))
    if seconds <= 0:
        return "—"
    if seconds < 60:
        return f"{seconds}s"
    return f"{seconds // 60}m {seconds % 60:02d}s"


@router.get("/my-wishes", response_class=HTMLResponse)
def my_wishes_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    wishes = []
    if current_user:
        wishes = (
            db.query(Wish)
            .filter(Wish.owner_id == current_user.id)
            .order_by(Wish.created_at.desc())
            .all()
        )
    ctx = _base_ctx(request, current_user)
    ctx.update({"wishes": wishes, "google_enabled": bool(GOOGLE_CLIENT_ID)})
    return templates.TemplateResponse("my_wishes.html", ctx)
