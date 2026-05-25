"""
Seed script: generates sample wishes (active, fulfilled, dead) for local dev.
Run: python seed.py
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

ACTIVE = [
    ("I wish to travel to Jeju Island this winter.", "Minho", date.today() + timedelta(days=120)),
    ("I wish my grandmother recovers quickly.", None, date.today() + timedelta(days=60)),
    ("I want to finish writing my novel.", "Yuna", date.today() + timedelta(days=200)),
    ("Please let me pass my driving test.", "Jake", date.today() + timedelta(days=30)),
    ("I wish for world peace. Really.", None, date.today() + timedelta(days=365)),
    ("May my cat come home safely.", "Sora", date.today() + timedelta(days=14)),
    ("I want to learn how to bake sourdough bread.", "Chris", date.today() + timedelta(days=90)),
    ("I wish to find a job I actually enjoy.", None, date.today() + timedelta(days=180)),
    ("Let this project succeed.", "Eunji", date.today() + timedelta(days=45)),
    ("I wish to run a half marathon.", "Taeho", date.today() + timedelta(days=270)),
    ("May my family stay healthy this year.", None, date.today() + timedelta(days=365)),
    ("I want to visit Paris before I turn 30.", "Rina", date.today() + timedelta(days=150)),
]

FULFILLED = [
    ("I wished to adopt a dog. Done — meet Bori!", "Jisoo", date.today() + timedelta(days=80),
     datetime.utcnow() - timedelta(days=10)),
    ("I got into grad school!", None, date.today() + timedelta(days=90),
     datetime.utcnow() - timedelta(days=5)),
    ("I finally called my old friend and we made up.", "Yoongi", date.today() + timedelta(days=60),
     datetime.utcnow() - timedelta(days=2)),
    ("I moved to a new apartment with morning sunlight.", "Ara", date.today() + timedelta(days=120),
     datetime.utcnow() - timedelta(days=20)),
]

DEAD = [
    ("I hoped the concert wouldn't be cancelled.", "Minseok",
     date.today() - timedelta(days=30)),
    ("I wanted to apply to that scholarship.", None,
     date.today() - timedelta(days=45)),
    ("Wish I had studied harder for that exam.", "Hana",
     date.today() - timedelta(days=60)),
    ("I hoped my garden would survive the drought.", "Sam",
     date.today() - timedelta(days=20)),
    ("I wanted to finish this before the year ended.", None,
     date.today() - timedelta(days=10)),
    ("I hoped my boss would appreciate the project.", "Jiyeon",
     date.today() - timedelta(days=55)),
]


def seed():
    db = SessionLocal()
    existing = db.query(Wish).count()
    if existing > 0:
        print(f"Database already has {existing} wishes. Skipping seed.")
        db.close()
        return

    now = datetime.utcnow()
    created = []

    for text, name, due in ACTIVE:
        w = Wish(
            text=text, name=name, password_hash=pw, due_date=due,
            status=WishStatus.active,
            created_at=now - timedelta(days=len(created) * 3 + 1),
            board="tree", likes=len(created) % 5, views=len(created) * 2 + 1,
        )
        db.add(w)
        created.append(w)

    for text, name, due, fulfilled_at in FULFILLED:
        w = Wish(
            text=text, name=name, password_hash=pw, due_date=due,
            status=WishStatus.fulfilled, fulfilled_at=fulfilled_at,
            created_at=fulfilled_at - timedelta(days=30),
            board="tree", likes=len(created) % 8 + 1, views=len(created) * 3,
        )
        db.add(w)
        created.append(w)

    for text, name, due in DEAD:
        created_at = datetime.utcnow() - timedelta(days=90 + len(created))
        w = Wish(
            text=text, name=name, password_hash=pw, due_date=due,
            status=WishStatus.dead,
            created_at=created_at,
            board="columbarium", likes=len(created) % 6, views=len(created) * 2,
        )
        db.add(w)
        created.append(w)

    db.commit()
    print(f"Seeded {len(created)} wishes ({len(ACTIVE)} active, {len(FULFILLED)} fulfilled, {len(DEAD)} dead).")
    print("Test password for all wishes: test1234")
    db.close()


if __name__ == "__main__":
    seed()
