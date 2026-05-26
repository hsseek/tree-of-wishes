import time
from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..config import GOOGLE_CLIENT_ID
from ..database import get_db
from ..models import User, Wish
from ..services.expiry import sweep_expired_wishes

router = APIRouter()
templates = Jinja2Templates(directory="templates")
templates.env.globals["sv"] = str(int(time.time()))


def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.get(User, user_id)


@router.get("/", response_class=RedirectResponse)
def root():
    return RedirectResponse(url="/tree", status_code=302)


@router.get("/tree", response_class=HTMLResponse)
def tree_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    sweep_expired_wishes(db)
    return templates.TemplateResponse(
        "tree.html", {"request": request, "current_user": current_user}
    )


@router.get("/columbarium", response_class=HTMLResponse)
def columbarium_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    sweep_expired_wishes(db)
    return templates.TemplateResponse(
        "columbarium.html", {"request": request, "current_user": current_user}
    )


@router.get("/settings", response_class=HTMLResponse)
def settings_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    return templates.TemplateResponse(
        "settings.html", {"request": request, "current_user": current_user}
    )


@router.get("/about", response_class=HTMLResponse)
def about_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    return templates.TemplateResponse(
        "about.html", {"request": request, "current_user": current_user}
    )


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
    return templates.TemplateResponse(
        "my_wishes.html",
        {
            "request": request,
            "current_user": current_user,
            "wishes": wishes,
            "google_enabled": bool(GOOGLE_CLIENT_ID),
        },
    )
