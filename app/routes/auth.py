import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..config import BASE_URL, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
from ..database import get_db
from ..models import User

router = APIRouter(prefix="/auth")

_GOOGLE_AUTH  = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
_GOOGLE_USER  = "https://www.googleapis.com/oauth2/v2/userinfo"


def _cb(provider: str) -> str:
    return f"{BASE_URL}/auth/{provider}/callback"


def _find_or_create_user(db: Session, *, email: str, provider_field: str,
                          provider_id: str, display_name: str | None,
                          avatar_url: str | None) -> User:
    user = db.query(User).filter(
        getattr(User, provider_field) == provider_id
    ).first()
    if not user and email:
        user = db.query(User).filter(User.email == email).first()
    if not user:
        user = User(email=email or f"{provider_field}:{provider_id}")
        db.add(user)
    setattr(user, provider_field, provider_id)
    if display_name:
        user.display_name = display_name
    if avatar_url:
        user.avatar_url = avatar_url
    db.commit()
    db.refresh(user)
    return user


# ─── Google ───────────────────────────────────────────────────────────────────

@router.get("/google")
async def google_login(request: Request):
    state = secrets.token_urlsafe(16)
    request.session["oauth_state"] = state
    params = urlencode({
        "client_id":     GOOGLE_CLIENT_ID,
        "redirect_uri":  _cb("google"),
        "response_type": "code",
        "scope":         "openid email profile",
        "state":         state,
    })
    return RedirectResponse(f"{_GOOGLE_AUTH}?{params}")


@router.get("/google/callback")
async def google_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    db: Session = Depends(get_db),
):
    if not code or state != request.session.pop("oauth_state", None):
        return RedirectResponse("/my-wishes")

    async with httpx.AsyncClient() as client:
        tok = (await client.post(_GOOGLE_TOKEN, data={
            "code":          code,
            "client_id":     GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri":  _cb("google"),
            "grant_type":    "authorization_code",
        })).json()

        if "error" in tok:
            return RedirectResponse("/my-wishes")

        profile = (await client.get(
            _GOOGLE_USER,
            headers={"Authorization": f"Bearer {tok['access_token']}"},
        )).json()

    user = _find_or_create_user(
        db,
        email=profile.get("email", ""),
        provider_field="google_id",
        provider_id=profile.get("id", ""),
        display_name=profile.get("name"),
        avatar_url=profile.get("picture"),
    )
    request.session["user_id"] = user.id
    return RedirectResponse("/my-wishes")


# ─── Logout ───────────────────────────────────────────────────────────────────

@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=302)
