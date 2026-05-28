from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker
from .config import DATABASE_URL

_is_sqlite = DATABASE_URL.startswith("sqlite")

engine = create_engine(
    DATABASE_URL,
    **({"connect_args": {"check_same_thread": False}} if _is_sqlite else {}),
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def run_migrations():
    """Add columns introduced after the initial schema without dropping data."""
    migrations = [
        ("users", "avatar_url", "ALTER TABLE users ADD COLUMN avatar_url VARCHAR"),
        ("users", "language",   "ALTER TABLE users ADD COLUMN language VARCHAR DEFAULT 'en'"),
    ]
    with engine.connect() as conn:
        for table, column, ddl in migrations:
            if _is_sqlite:
                rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
                existing = {r[1] for r in rows}
            else:
                rows = conn.execute(
                    text("SELECT column_name FROM information_schema.columns WHERE table_name = :t"),
                    {"t": table},
                ).fetchall()
                existing = {r[0] for r in rows}
            if column not in existing:
                conn.execute(text(ddl))
        conn.commit()
