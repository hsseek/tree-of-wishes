import uuid
import mimetypes
import secrets
import smtplib
from email.message import EmailMessage
from datetime import datetime, date
from pathlib import Path
from typing import Optional

from fastapi import (
    APIRouter, BackgroundTasks, Depends, HTTPException, Request,
    UploadFile, File, Form, Query,
)
from fastapi.responses import FileResponse, JSONResponse
import bcrypt
from sqlalchemy.orm import Session
from sqlalchemy import or_, asc, desc

from sqlalchemy import text as sa_text
from ..database import get_db
from ..models import Wish, WishStatus, effective_age_expr
from ..services.analytics import record_dwell
from ..services.capacity import ensure_tree_capacity
from ..services.rate_limit import (
    check_creation_rate, record_creation,
    can_like, record_like, revoke_like,
    can_record_view, record_view,
    check_like_rate, check_view_rate,
)
from ..config import (
    MAX_FILE_SIZE_BYTES, ALLOWED_MIME_TYPES, UPLOAD_DIR,
    REPORT_EMAIL, SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS,
    BASE_URL, ADMIN_EMAIL, REEL_API_TOKEN,
)
from ..models import User

router = APIRouter(prefix="/api")


def _hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def _verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def _check_auth(wish: "Wish", password: Optional[str], request: Request, db: Session) -> None:
    """Pass if the session user owns the wish, is admin, or provides a valid password."""
    user_id = request.session.get("user_id")
    if user_id and wish.owner_id is not None and wish.owner_id == user_id:
        return
    if user_id and ADMIN_EMAIL:
        user = db.query(User).filter(User.id == user_id).first()
        if user and user.email == ADMIN_EMAIL:
            return
    if not wish.password_hash or not _verify_password(password or "", wish.password_hash):
        raise HTTPException(403, "Wrong password")


def _send_smtp_email(subject: str, body: str) -> None:
    """Send an email via SMTP. Raises on failure."""
    if not REPORT_EMAIL or not SMTP_HOST:
        return
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = SMTP_USER or REPORT_EMAIL
    msg["To"] = REPORT_EMAIL
    msg.set_content(body)
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
        smtp.ehlo()
        smtp.starttls()
        if SMTP_USER and SMTP_PASS:
            smtp.login(SMTP_USER, SMTP_PASS)
        smtp.send_message(msg)


def _notify_first_like(to_email: str, wish_text: str, wish_id: int, language: str = 'en') -> None:
    snippet = wish_text[:80] + ('…' if len(wish_text) > 80 else '')
    link = f"{BASE_URL}/wish/{wish_id}"
    if language == 'ko':
        subject = "[소원의 나무] 소원에 첫 번째 좋아요가 달렸습니다"
        body = (
            "누군가 회원님의 소원에 좋아요를 눌렀습니다!\n\n"
            f"소원   : {snippet}\n"
            f"링크   : {link}"
        )
    else:
        subject = "[Tree of Wishes] Your wish received its first like"
        body = (
            "Someone liked your wish on Tree of Wishes!\n\n"
            f"Wish   : {snippet}\n"
            f"Link   : {link}"
        )
    try:
        _send_smtp_email(subject, body)
    except Exception:
        pass


def _notify_eviction(info: dict) -> None:
    body = (
        "A wish owned by a registered user was evicted to make room on the tree.\n\n"
        f"Wish ID  : {info['id']}\n"
        f"Owner ID : {info['owner_id']}\n"
        f"Name     : {info['name'] or '—'}\n"
        f"Text     : {info['text']}\n"
        f"Status   : {info['status']}\n"
        f"Created  : {info['created_at']}\n"
        f"Due      : {info['due_date'] or '—'}\n"
        f"Likes    : {info['likes']}\n"
        f"Views    : {info['views']}\n"
        f"Evicted  : {datetime.utcnow().isoformat()} UTC"
    )
    try:
        _send_smtp_email("[Tree of Wishes] Registered user's wish evicted", body)
    except Exception:
        pass  # don't block wish creation if email fails


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
        "owner_id": wish.owner_id,
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
            .order_by(desc(Wish.due_date))
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


# ─── Private reel endpoint ──────────────────────────────────────────────────────
# Token-gated wish lookup for the Instagram reel generator. Only callers that send
# the shared secret (X-Reel-Token) can use it; disabled (404) when no token is set.
# The wish text itself is public on the site — this just keeps the tool's bulk
# lookup private to the owner.

@router.get("/reel/wishes")
def reel_wishes(
    request: Request,
    ids: str = Query("", description="comma-separated wish ids, in order"),
    board: str = Query("", regex="^(tree|columbarium|)$"),
    limit: int = Query(3, ge=1, le=20),
    db: Session = Depends(get_db),
):
    token = request.headers.get("X-Reel-Token", "")
    if not REEL_API_TOKEN or not secrets.compare_digest(token, REEL_API_TOKEN):
        raise HTTPException(404, "Not found")   # hide existence from others

    if ids:
        id_list = [int(x) for x in ids.split(",") if x.strip().isdigit()]
        rows = db.query(Wish).filter(Wish.id.in_(id_list)).all()
        order = {wid: i for i, wid in enumerate(id_list)}
        rows.sort(key=lambda w: order.get(w.id, 1 << 30))
    else:
        q = db.query(Wish)
        if board:
            q = q.filter(Wish.board == board)
        rows = q.limit(limit).all()
    return {"wishes": [
        {"id": w.id, "text": w.text, "board": w.board,
         "status": w.status.value if w.status else None, "name": w.name}
        for w in rows
    ]}


# ─── Record view ──────────────────────────────────────────────────────────────

@router.post("/wishes/{wish_id}/view")
def record_wish_view(wish_id: int, request: Request, db: Session = Depends(get_db)):
    wish = db.query(Wish).filter(Wish.id == wish_id).first()
    if not wish:
        raise HTTPException(404, "Wish not found")
    ip = _client_ip(request)
    if not check_view_rate(db, ip):
        raise HTTPException(429, "Too many view requests — please wait.")
    if can_record_view(db, ip, wish_id):
        record_view(db, ip, wish_id)
        wish.views += 1
        db.commit()
    return {"views": wish.views}


# ─── Like ─────────────────────────────────────────────────────────────────────

@router.get("/wishes/{wish_id}/liked")
def get_liked_status(wish_id: int, request: Request, db: Session = Depends(get_db)):
    ip = _client_ip(request)
    liked = not can_like(db, ip, wish_id)
    return {"liked": liked}


@router.post("/wishes/{wish_id}/like")
def like_wish(
    wish_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    wish = db.query(Wish).filter(Wish.id == wish_id).first()
    if not wish:
        raise HTTPException(404, "Wish not found")
    ip = _client_ip(request)
    already_liked = not can_like(db, ip, wish_id)
    if already_liked:
        revoke_like(db, ip, wish_id)
        wish.likes = max(0, wish.likes - 1)
        db.commit()
        return {"likes": wish.likes, "liked": False}
    if not check_like_rate(db, ip):
        raise HTTPException(429, "Too many likes — please wait.")
    record_like(db, ip, wish_id)
    wish.likes += 1
    db.commit()
    if wish.likes == 1 and wish.owner_id is not None:
        owner = db.query(User).filter(User.id == wish.owner_id).first()
        if owner and owner.email:
            background_tasks.add_task(
                _notify_first_like, owner.email, wish.text, wish.id, owner.language or 'en'
            )
    return {"likes": wish.likes, "liked": True}


# ─── Create wish ──────────────────────────────────────────────────────────────

@router.post("/wishes")
async def create_wish(
    request: Request,
    background_tasks: BackgroundTasks,
    text: str = Form(...),
    name: Optional[str] = Form(None),
    password: Optional[str] = Form(None),
    due_date: str = Form(...),
    attachment: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
):
    user_id = request.session.get("user_id")
    if not user_id and not password:
        raise HTTPException(400, "Password is required.")

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

    pw_hash = _hash_password(password) if password else None

    evicted = ensure_tree_capacity(db)

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
        owner_id=request.session.get("user_id"),
    )
    db.add(wish)
    record_creation(db, ip)
    db.commit()
    db.refresh(wish)
    if evicted:
        background_tasks.add_task(_notify_eviction, evicted)
    return _wish_to_dict(wish)


# ─── Verify password ──────────────────────────────────────────────────────────

@router.post("/wishes/{wish_id}/verify")
def verify_password(
    wish_id: int,
    request: Request,
    password: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    wish = db.query(Wish).filter(Wish.id == wish_id).first()
    if not wish:
        raise HTTPException(404, "Wish not found")
    _check_auth(wish, password, request, db)
    return {"ok": True}


# ─── Edit wish ────────────────────────────────────────────────────────────────

@router.patch("/wishes/{wish_id}")
async def edit_wish(
    wish_id: int,
    request: Request,
    password: Optional[str] = Form(None),
    text: Optional[str] = Form(None),
    remove_attachment: bool = Form(False),
    attachment: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
):
    wish = db.query(Wish).filter(Wish.id == wish_id).first()
    if not wish:
        raise HTTPException(404, "Wish not found")
    _check_auth(wish, password, request, db)

    is_owner = request.session.get("user_id") == wish.owner_id and wish.owner_id is not None

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
        if not is_owner:
            raise HTTPException(403, "Only registered users can attach files.")
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
    request: Request,
    password: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    wish = db.query(Wish).filter(Wish.id == wish_id, Wish.board == "tree").first()
    if not wish:
        raise HTTPException(404, "Wish not found")
    _check_auth(wish, password, request, db)
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
    request: Request,
    password: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    wish = db.query(Wish).filter(Wish.id == wish_id, Wish.board == "tree").first()
    if not wish:
        raise HTTPException(404, "Wish not found")
    _check_auth(wish, password, request, db)
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
    request: Request,
    password: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    wish = db.query(Wish).filter(Wish.id == wish_id).first()
    if not wish:
        raise HTTPException(404, "Wish not found")
    _check_auth(wish, password, request, db)
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


# ─── Report ───────────────────────────────────────────────────────────────────

@router.post("/report")
def submit_report(
    request: Request,
    type: str = Form(...),
    message: str = Form(...),
):
    if not REPORT_EMAIL or not SMTP_HOST:
        raise HTTPException(503, "Reporting is not configured on this server.")
    message = message.strip()
    if len(message) < 5:
        raise HTTPException(400, "Message too short.")
    if len(message) > 2000:
        raise HTTPException(400, "Message too long.")

    subject = "[Tree of Wishes] " + ("Abuse report" if type == "abuse" else "Suggestion")
    body = (
        f"Type: {type}\n"
        f"Message:\n{message}\n\n"
        f"IP: {_client_ip(request)}\n"
        f"Time: {datetime.utcnow().isoformat()} UTC"
    )
    try:
        _send_smtp_email(subject, body)
    except Exception:
        raise HTTPException(500, "Failed to send report.")

    return {"ok": True}


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


# ─── User language preference ─────────────────────────────────────────────────

_SUPPORTED_LANGUAGES = {"en", "ko"}

@router.patch("/me/language")
def set_language(
    request: Request,
    language: str = Form(...),
    db: Session = Depends(get_db),
):
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(401, "Not signed in")
    if language not in _SUPPORTED_LANGUAGES:
        raise HTTPException(400, f"Unsupported language: {language}")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    user.language = language
    db.commit()
    return {"language": language}


# ─── Analytics ──────────────────────────────────────────────────────────────

@router.post("/track/dwell")
def track_dwell(s: int = Query(0, ge=0)):
    """Record one time-on-page sample (seconds). Called via navigator.sendBeacon,
    so it returns 204 and never blocks the client."""
    record_dwell(s)
    return JSONResponse(status_code=204, content=None)


# ─── Health ───────────────────────────────────────────────────────────────────

@router.get("/health")
def health_check(db: Session = Depends(get_db)):
    try:
        db.execute(sa_text("SELECT 1"))
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(503, f"Database unavailable: {e}")
