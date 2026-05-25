from datetime import date
from sqlalchemy.orm import Session
from ..models import Wish, WishStatus
from .capacity import ensure_columbarium_capacity


def sweep_expired_wishes(db: Session) -> int:
    """
    Lazy expiry: move unfulfilled wishes past their due_date from tree → columbarium.
    Called on every Tree/Columbarium page visit. Returns count migrated.
    """
    today = date.today()
    expired = (
        db.query(Wish)
        .filter(
            Wish.board == "tree",
            Wish.status == WishStatus.active,
            Wish.due_date < today,
        )
        .all()
    )

    migrated = 0
    for wish in expired:
        # Make room in columbarium before migrating
        ensure_columbarium_capacity(db)
        wish.status = WishStatus.dead
        wish.board = "columbarium"
        migrated += 1

    if migrated:
        db.commit()

    return migrated
