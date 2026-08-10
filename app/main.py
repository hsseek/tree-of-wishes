from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

from .config import SESSION_SECRET
from .database import engine, Base, run_migrations
from .models import *  # ensure all models are registered before create_all
from .routes.api import router as api_router
from .routes.auth import router as auth_router
from .routes.pages import router as pages_router
from .services.analytics import TRACKED_PATHS

Base.metadata.create_all(bind=engine)
run_migrations()

# One year — keeps an anonymous visitor stable for daily-unique counting.
_VID_MAX_AGE = 365 * 24 * 60 * 60


async def track_visit(request: Request, call_next):
    """Issue the anonymous visitor cookie on tracked page loads. The visit
    itself is *not* recorded here — /api/track/visit records it once the page's
    JavaScript confirms a real browser. Counting on the bare request instead
    minted a fresh UUID for every cookie-less client, which let crawlers inflate
    unique-visitor counts several times over."""
    response = await call_next(request)
    try:
        if (
            request.method == "GET"
            and request.url.path in TRACKED_PATHS
            and not request.session.get("user_id")
            and not request.cookies.get("tow_vid")
        ):
            response.set_cookie(
                "tow_vid", uuid4().hex, max_age=_VID_MAX_AGE,
                httponly=True, samesite="lax",
            )
    except Exception:
        pass  # tracking must never break a page load
    return response


app = FastAPI(title="Tree of Wishes", version="0.1.0")

# Order matters: middleware added later is outermost. SessionMiddleware is added
# last so it runs first and populates request.session before track_visit reads it.
app.add_middleware(BaseHTTPMiddleware, dispatch=track_visit)
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)
app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(pages_router)
app.include_router(auth_router)
app.include_router(api_router)


@app.exception_handler(404)
async def not_found(_request, _exc):
    return JSONResponse({"detail": "Not found"}, status_code=404)


@app.exception_handler(429)
async def rate_limited(_request, exc):
    return JSONResponse({"detail": str(exc.detail)}, status_code=429)
