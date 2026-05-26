from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware

from .config import SESSION_SECRET
from .database import engine, Base, run_migrations
from .models import *  # ensure all models are registered before create_all
from .routes.api import router as api_router
from .routes.auth import router as auth_router
from .routes.pages import router as pages_router

Base.metadata.create_all(bind=engine)
run_migrations()

app = FastAPI(title="Tree of Wishes", version="0.1.0")

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
