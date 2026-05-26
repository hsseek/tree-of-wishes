import os
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import asc
from ..models import Wish, WishStatus, effective_age_expr
from ..config import TREE_CAPACITY, COLUMBARIUM_CAPACITY, UPLOAD_DIR


def _delete_wish_files(wish: Wish):
    if wish.attachment_path:
        path = UPLOAD_DIR / wish.attachment_path
        if path.exists():
            os.remove(path)


def _wish_info(wish: Wish) -> dict:
    return {
        "id":         wish.id,
        "owner_id":   wish.owner_id,
        "text":       wish.text,
        "name":       wish.name,
        "status":     wish.status.value,
        "created_at": wish.created_at.isoformat(),
        "due_date":   wish.due_date.isoformat() if wish.due_date else None,
        "likes":      wish.likes,
        "views":      wish.views,
    }


def ensure_tree_capacity(db: Session) -> Optional[dict]:
    """
    If the tree is full, evict one wish and return its info if it was owned
    by a registered user (so the caller can send a notification), else None.

    Eviction order:
      Tier 1 — oldest anonymous wish (owner_id IS NULL) by effective age.
      Tier 2 — oldest registered user's wish, if no anonymous wish exists.
    """
    count = db.query(Wish).filter(Wish.board == "tree").count()
    if count < TREE_CAPACITY:
        return None

    base_q = (
        db.query(Wish)
        .filter(Wish.board == "tree")
        .order_by(asc(effective_age_expr()))
    )

    # Tier 1: prefer evicting an anonymous wish
    evicted = base_q.filter(Wish.owner_id.is_(None)).first()
    # Tier 2: fall back to the oldest registered user's wish
    if evicted is None:
        evicted = base_q.first()

    if not evicted:
        return None

    info = _wish_info(evicted) if evicted.owner_id is not None else None
    _delete_wish_files(evicted)
    db.delete(evicted)
    db.flush()
    return info


def ensure_columbarium_capacity(db: Session):
    """
    If the columbarium is full, permanently delete the least popular wish
    (fewest likes; ties broken by oldest created_at).
    """
    count = db.query(Wish).filter(Wish.board == "columbarium").count()
    if count < COLUMBARIUM_CAPACITY:
        return

    least_popular = (
        db.query(Wish)
        .filter(Wish.board == "columbarium")
        .order_by(asc(Wish.likes), asc(Wish.created_at))
        .first()
    )
    if least_popular:
        _delete_wish_files(least_popular)
        db.delete(least_popular)
        db.flush()
