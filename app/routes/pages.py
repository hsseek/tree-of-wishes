import time

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..database import get_db
from ..services.expiry import sweep_expired_wishes

router = APIRouter()
templates = Jinja2Templates(directory="templates")
templates.env.globals["sv"] = str(int(time.time()))


@router.get("/", response_class=RedirectResponse)
def root():
    return RedirectResponse(url="/tree", status_code=302)


@router.get("/tree", response_class=HTMLResponse)
def tree_page(request: Request, db: Session = Depends(get_db)):
    sweep_expired_wishes(db)
    return templates.TemplateResponse("tree.html", {"request": request})


@router.get("/columbarium", response_class=HTMLResponse)
def columbarium_page(request: Request, db: Session = Depends(get_db)):
    sweep_expired_wishes(db)
    return templates.TemplateResponse("columbarium.html", {"request": request})


@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    return templates.TemplateResponse("settings.html", {"request": request})


@router.get("/about", response_class=HTMLResponse)
def about_page(request: Request):
    return templates.TemplateResponse("about.html", {"request": request})


@router.get("/my-wishes", response_class=HTMLResponse)
def my_wishes_page(request: Request):
    # Stub: auth not implemented yet
    return templates.TemplateResponse("my_wishes.html", {"request": request})
