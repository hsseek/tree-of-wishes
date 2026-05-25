import os
from sqlalchemy.orm import Session
from sqlalchemy import asc
from ..models import Wish, WishStatus, effective_age_expr
from ..config import TREE_CAPACITY, COLUMBARIUM_CAPACITY, UPLOAD_DIR


def _delete_wish_files(wish: Wish):
    """Remove uploaded attachment from disk when a wish is permanently deleted."""
    if wish.attachment_path:
        path = UPLOAD_DIR / wish.attachment_path
        if path.exists():
            os.remove(path)


def ensure_tree_capacity(db: Session):
    """
    If the tree has reached TREE_CAPACITY, permanently delete the single oldest
    wish by effective-age (fulfilled_at if fulfilled, else created_at).
    The evicted wish is gone forever — it does NOT go to the columbarium.

    Extension point: once owner_id support is added, skip wishes where
    owner_id IS NOT NULL to protect registered users from age-based deletion.
    """
    count = db.query(Wish).filter(Wish.board == "tree").count()
    if count < TREE_CAPACITY:
        return

    oldest = (
        db.query(Wish)
        .filter(Wish.board == "tree")
        # Extension point: .filter(Wish.owner_id.is_(None)) when protecting registered users
        .order_by(asc(effective_age_expr()))
        .first()
    )
    if oldest:
        _delete_wish_files(oldest)
        db.delete(oldest)
        db.flush()


def ensure_columbarium_capacity(db: Session):
    """
    If the columbarium has reached COLUMBARIUM_CAPACITY, permanently delete the
    least popular wish (fewest likes; ties broken by oldest created_at).
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
