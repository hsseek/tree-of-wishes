import uuid
import mimetypes
from datetime import datetime, date
from pathlib import Path
from typing import Optional

from fastapi import (
    APIRouter, Depends, HTTPException, Request, UploadFile, File, Form,
    Query,
)
from fastapi.responses import FileResponse, JSONResponse
import bcrypt
from sqlalchemy.orm import Session
from sqlalchemy import or_, asc, desc

from ..database import get_db
from ..models import Wish, WishStatus, effective_age_expr
from ..services.capacity import ensure_tree_capacity
from ..services.rate_limit import (
    check_creation_rate, record_creation,
    can_like, record_like,
    can_record_view, record_view,
)
from ..config import MAX_FILE_SIZE_BYTES, ALLOWED_MIME_TYPES, UPLOAD_DIR

router = APIRouter(prefix="/api")


def _hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def _verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())

PAGE_SIZE = 50


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host or "unknown"


def _wish_to_dict(wish: Wish) -> dict:
    return {
        "id": wish.id,
        "text": wish.text,
        "name": wish.name,
        "due_date": wish.due_date.isoformat() if wish.due_date else None,
        "status": wish.status.value if wish.status else wish.status,
        "board": wish.board,
        "created_at": wish.created_at.isoformat(),
        "fulfilled_at": wish.fulfilled_at.isoformat() if wish.fulfilled_at else None,
        "likes": wish.likes,
        "views": wish.views,
        "has_attachment": wish.attachment_filename is not None,
        "attachment_filename": wish.attachment_filename,
        "attachment_mimetype": wish.attachment_mimetype,
        "has_password": wish.password_hash is not None,
    }


# ─── List wishes ──────────────────────────────────────────────────────────────

@router.get("/wishes")
def list_wishes(
    board: str = Query("tree", regex="^(tree|columbarium)$"),
    page: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    offset = page * PAGE_SIZE

    if board == "tree":
        q = (
            db.query(Wish)
            .filter(Wish.board == "tree")
            .order_by(asc(effective_age_expr()))
        )
    else:
        q = (
            db.query(Wish)
            .filter(Wish.board == "columbarium")
            .order_by(asc(Wish.created_at))
        )

    total = q.count()
    wishes = q.offset(offset).limit(PAGE_SIZE).all()
    return {
        "total": total,
        "page": page,
        "page_size": PAGE_SIZE,
        "has_more": offset + len(wishes) < total,
        "wishes": [_wish_to_dict(w) for w in wishes],
    }


# ─── Get single wish ──────────────────────────────────────────────────────────

@router.get("/wishes/{wish_id}")
def get_wish(wish_id: int, db: Session = Depends(get_db)):
    wish = db.query(Wish).filter(Wish.id == wish_id).first()
    if not wish:
        raise HTTPException(404, "Wish not found")
    return _wish_to_dict(wish)


# ─── Record view ──────────────────────────────────────────────────────────────

@router.post("/wishes/{wish_id}/view")
def record_wish_view(wish_id: int, request: Request, db: Session = Depends(get_db)):
    wish = db.query(Wish).filter(Wish.id == wish_id).first()
    if not wish:
        raise HTTPException(404, "Wish not found")
    ip = _client_ip(request)
    if can_record_view(db, ip, wish_id):
        record_view(db, ip, wish_id)
        wish.views += 1
        db.commit()
    return {"views": wish.views}


# ─── Like ─────────────────────────────────────────────────────────────────────

@router.post("/wishes/{wish_id}/like")
def like_wish(wish_id: int, request: Request, db: Session = Depends(get_db)):
    wish = db.query(Wish).filter(Wish.id == wish_id).first()
    if not wish:
        raise HTTPException(404, "Wish not found")
    ip = _client_ip(request)
    accepted = record_like(db, ip, wish_id)
    if accepted:
        wish.likes += 1
        db.commit()
    return {"likes": wish.likes, "accepted": accepted}


# ─── Create wish ──────────────────────────────────────────────────────────────

@router.post("/wishes")
async def create_wish(
    request: Request,
    text: str = Form(...),
    name: Optional[str] = Form(None),
    password: str = Form(...),
    due_date: str = Form(...),
    attachment: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
):
    ip = _client_ip(request)
    if not check_creation_rate(db, ip):
        raise HTTPException(429, "Too many wishes created recently. Please wait.")

    # Parse due_date
    try:
        parsed_due = date.fromisoformat(due_date)
    except ValueError:
        raise HTTPException(400, "Invalid due_date format. Use YYYY-MM-DD.")
    if parsed_due <= date.today():
        raise HTTPException(400, "due_date must be in the future.")

    # Attachments are not allowed at creation time (only on fulfilled wishes via edit)
    if attachment and attachment.filename:
        raise HTTPException(400, "Attachments can only be added after a wish is fulfilled.")

    attachment_path = None
    attachment_filename = None
    attachment_mimetype = None

    # Hash password
    pw_hash = _hash_password(password)

    # Enforce tree capacity (evicts oldest if full)
    ensure_tree_capacity(db)

    wish = Wish(
        text=text.strip(),
        name=name.strip() if name else None,
        password_hash=pw_hash,
        due_date=parsed_due,
        status=WishStatus.active,
        created_at=datetime.utcnow(),
        board="tree",
        attachment_path=attachment_path,
        attachment_filename=attachment_filename,
        attachment_mimetype=attachment_mimetype,
        owner_id=None,  # Extension point: set from auth session when registration is added
    )
    db.add(wish)
    record_creation(db, ip)
    db.commit()
    db.refresh(wish)
    return _wish_to_dict(wish)


# ─── Verify password ──────────────────────────────────────────────────────────

@router.post("/wishes/{wish_id}/verify")
def verify_password(
    wish_id: int,
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    wish = db.query(Wish).filter(Wish.id == wish_id, Wish.board == "tree").first()
    if not wish:
        raise HTTPException(404, "Wish not found")
    if not wish.password_hash or not _verify_password(password, wish.password_hash):
        raise HTTPException(403, "Wrong password")
    return {"ok": True}


# ─── Edit wish ────────────────────────────────────────────────────────────────

@router.patch("/wishes/{wish_id}")
async def edit_wish(
    wish_id: int,
    password: str = Form(...),
    text: Optional[str] = Form(None),
    remove_attachment: bool = Form(False),
    attachment: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
):
    wish = db.query(Wish).filter(Wish.id == wish_id, Wish.board == "tree").first()
    if not wish:
        raise HTTPException(404, "Wish not found")
    if not wish.password_hash or not _verify_password(password, wish.password_hash):
        raise HTTPException(403, "Wrong password")

    if text is not None:
        wish.text = text.strip()

    if remove_attachment and wish.attachment_path:
        path = UPLOAD_DIR / wish.attachment_path
        if path.exists():
            path.unlink()
        wish.attachment_path = None
        wish.attachment_filename = None
        wish.attachment_mimetype = None

    if attachment and attachment.filename:
        # Attachments allowed only on fulfilled wishes (or registered users, when auth is added)
        if wish.status != WishStatus.fulfilled and wish.owner_id is None:
            raise HTTPException(400, "Attachments can only be added to fulfilled wishes.")
        content = await attachment.read()
        if len(content) > MAX_FILE_SIZE_BYTES:
            raise HTTPException(413, "File too large.")
        guessed_type, _ = mimetypes.guess_type(attachment.filename)
        mime = guessed_type or attachment.content_type or "application/octet-stream"
        if mime not in ALLOWED_MIME_TYPES:
            raise HTTPException(415, "File type not allowed.")
        if wish.attachment_path:
            old = UPLOAD_DIR / wish.attachment_path
            if old.exists():
                old.unlink()
        ext = Path(attachment.filename).suffix
        stored_name = f"{uuid.uuid4().hex}{ext}"
        dest = UPLOAD_DIR / stored_name
        dest.write_bytes(content)
        wish.attachment_path = stored_name
        wish.attachment_filename = attachment.filename
        wish.attachment_mimetype = mime

    db.commit()
    db.refresh(wish)
    return _wish_to_dict(wish)


# ─── Fulfill wish ─────────────────────────────────────────────────────────────

@router.post("/wishes/{wish_id}/fulfill")
def fulfill_wish(
    wish_id: int,
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    wish = db.query(Wish).filter(Wish.id == wish_id, Wish.board == "tree").first()
    if not wish:
        raise HTTPException(404, "Wish not found")
    if not wish.password_hash or not _verify_password(password, wish.password_hash):
        raise HTTPException(403, "Wrong password")
    if wish.status == WishStatus.fulfilled:
        raise HTTPException(409, "Already fulfilled")
    wish.status = WishStatus.fulfilled
    wish.fulfilled_at = datetime.utcnow()
    db.commit()
    db.refresh(wish)
    return _wish_to_dict(wish)


# ─── Unfulfill wish ───────────────────────────────────────────────────────────

@router.post("/wishes/{wish_id}/unfulfill")
def unfulfill_wish(
    wish_id: int,
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    wish = db.query(Wish).filter(Wish.id == wish_id, Wish.board == "tree").first()
    if not wish:
        raise HTTPException(404, "Wish not found")
    if not wish.password_hash or not _verify_password(password, wish.password_hash):
        raise HTTPException(403, "Wrong password")
    if wish.status != WishStatus.fulfilled:
        raise HTTPException(409, "Wish is not fulfilled")
    wish.status = WishStatus.active
    wish.fulfilled_at = None
    db.commit()
    db.refresh(wish)
    return _wish_to_dict(wish)


# ─── Delete wish ──────────────────────────────────────────────────────────────

@router.delete("/wishes/{wish_id}")
def delete_wish(
    wish_id: int,
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    wish = db.query(Wish).filter(Wish.id == wish_id, Wish.board == "tree").first()
    if not wish:
        raise HTTPException(404, "Wish not found")
    if not wish.password_hash or not _verify_password(password, wish.password_hash):
        raise HTTPException(403, "Wrong password")
    if wish.attachment_path:
        path = UPLOAD_DIR / wish.attachment_path
        if path.exists():
            path.unlink()
    db.delete(wish)
    db.commit()
    return {"ok": True}


# ─── Serve attachment ─────────────────────────────────────────────────────────

@router.get("/attachment/{wish_id}")
def get_attachment(wish_id: int, db: Session = Depends(get_db)):
    wish = db.query(Wish).filter(Wish.id == wish_id).first()
    if not wish or not wish.attachment_path:
        raise HTTPException(404, "No attachment")
    path = UPLOAD_DIR / wish.attachment_path
    if not path.exists():
        raise HTTPException(404, "Attachment file missing")
    return FileResponse(
        path=str(path),
        filename=wish.attachment_filename,
        media_type=wish.attachment_mimetype or "application/octet-stream",
    )


# ─── Search ───────────────────────────────────────────────────────────────────

@router.get("/search")
def search_wishes(
    q: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
):
    pattern = f"%{q}%"
    results = (
        db.query(Wish)
        .filter(
            or_(
                Wish.text.ilike(pattern),
                Wish.name.ilike(pattern),
            )
        )
        .order_by(asc(Wish.created_at))
        .limit(100)
        .all()
    )
    return {"query": q, "results": [_wish_to_dict(w) for w in results]}
