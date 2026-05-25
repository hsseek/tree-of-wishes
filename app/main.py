from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

from .database import engine, Base
from .models import *  # ensure all models are registered before create_all
from .routes.api import router as api_router
from .routes.pages import router as pages_router

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Tree of Wishes", version="0.1.0")

app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(pages_router)
app.include_router(api_router)


@app.exception_handler(404)
async def not_found(_request, _exc):
    return JSONResponse({"detail": "Not found"}, status_code=404)


@app.exception_handler(429)
async def rate_limited(_request, exc):
    return JSONResponse({"detail": str(exc.detail)}, status_code=429)
