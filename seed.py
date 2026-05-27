"""
Seed script: generates sample wishes for local dev.
Run: python seed.py           (skips if data exists)
     python seed.py --reset   (clears all wishes first)
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from datetime import datetime, date, timedelta
import bcrypt
from app.database import SessionLocal, engine
from app.models import Base, Wish, WishStatus

Base.metadata.create_all(bind=engine)
pw = bcrypt.hashpw(b"test1234", bcrypt.gensalt()).decode()

# ---------------------------------------------------------------------------
# Tree of Wishes (active)
# ---------------------------------------------------------------------------

TREE_HISTORICAL = [
    (
        "In spite of everything I still believe that people are really good at heart.",
        "Anne Frank",
        datetime(1944, 7, 15),
        date(2099, 12, 31),
    ),
    (
        "The best time to plant a tree was 20 years ago. The second best time is now.",
        "Ancient Proverb",
        datetime(1271, 1, 1),
        date(2099, 12, 31),
    ),
]

TREE_GENERAL = [
    # English
    ("Let me find work that actually means something to me", "James", date(2026, 12, 31)),
    ("Let me fall in love this year", None, date(2026, 12, 31)),
    ("Please help me get into graduate school", "Emily", date(2027, 3, 31)),
    # Korean
    ("혼자 내일로 기차여행", "민준", date(2026, 12, 31)),
    ("아영이랑 한강 데이트", None, date(2026, 8, 15)),
    ("동기들이랑 바다 여행 가기", "서연", date(2026, 8, 31)),
]

# ---------------------------------------------------------------------------
# Columbarium (dead — once-active hopes that were never fulfilled)
# ---------------------------------------------------------------------------

BALLOU_TEXT = (
    "Sarah, my love for you is deathless — it seems to bind me with mighty cables "
    "that nothing but Omnipotence could break; and yet my love of Country comes over "
    "me like a strong wind and bears me unresistibly on with all these chains to the "
    "battle field. The memories of the blissful moments I have spent with you come "
    "creeping over me, and I feel most gratified to God and to you that I have enjoyed "
    "them for so long. And hard it is for me to give them up and burn to ashes the "
    "hopes of future years, when, God willing, we might still have lived and loved "
    "together, and seen our sons grown up to honorable manhood around us.\n"
    "If I do not return, my dear Sarah, never forget how much I love you, and when "
    "my last breath escapes me on the battle field, it will whisper your name."
)

COLUMBARIUM_HISTORICAL = [
    (
        BALLOU_TEXT,
        "Sullivan Ballou",
        datetime(1861, 7, 14),
        date(1861, 7, 21),
    ),
]

COLUMBARIUM_GENERAL = [
    # English — present-tense hopes that expired unfulfilled
    ("I just want us to be okay again", "Tom", date.today() - timedelta(days=30)),
    ("I want to finish the manuscript before the deadline", None, date.today() - timedelta(days=60)),
    ("Please let my mom be okay after the surgery", "Grace", date.today() - timedelta(days=14)),
    # Korean
    ("지영이랑 낚시 가기", "지훈", date(2026, 5, 15)),
    ("엄마한테 미안하다고 말하고 싶어요", None, date(2026, 5, 8)),
    ("이번 봄에 제주도 가기", "소윤", date(2026, 5, 31)),
]


def seed(reset: bool = False):
    db = SessionLocal()

    if reset:
        deleted = db.query(Wish).delete()
        db.commit()
        print(f"Deleted {deleted} existing wishes.")
    else:
        existing = db.query(Wish).count()
        if existing > 0:
            print(f"Database already has {existing} wishes. Run with --reset to overwrite.")
            db.close()
            return

    now = datetime.utcnow()
    created = []

    for text, name, created_at, due_date in TREE_HISTORICAL:
        w = Wish(
            text=text, name=name, password_hash=None,
            status=WishStatus.active, created_at=created_at, due_date=due_date,
            board="tree", likes=0, views=0,
        )
        db.add(w)
        created.append(w)

    for i, (text, name, due_date) in enumerate(TREE_GENERAL):
        w = Wish(
            text=text, name=name, password_hash=pw,
            status=WishStatus.active,
            created_at=now - timedelta(days=i * 5 + 1),
            due_date=due_date,
            board="tree", likes=i % 5, views=i * 2 + 1,
        )
        db.add(w)
        created.append(w)

    for text, name, created_at, due_date in COLUMBARIUM_HISTORICAL:
        w = Wish(
            text=text, name=name, password_hash=None,
            status=WishStatus.dead, created_at=created_at, due_date=due_date,
            board="columbarium", likes=0, views=0,
        )
        db.add(w)
        created.append(w)

    for i, (text, name, due_date) in enumerate(COLUMBARIUM_GENERAL):
        w = Wish(
            text=text, name=name, password_hash=pw,
            status=WishStatus.dead,
            created_at=now - timedelta(days=90 + i * 5),
            due_date=due_date,
            board="columbarium", likes=i % 4, views=i * 2,
        )
        db.add(w)
        created.append(w)

    db.commit()
    tree_count = len(TREE_HISTORICAL) + len(TREE_GENERAL)
    col_count = len(COLUMBARIUM_HISTORICAL) + len(COLUMBARIUM_GENERAL)
    print(f"Seeded {len(created)} wishes ({tree_count} tree, {col_count} columbarium).")
    print("Test password for general wishes: test1234")
    db.close()


if __name__ == "__main__":
    seed(reset="--reset" in sys.argv)
