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
    # Indexes added after the initial schema. create_all() only builds indexes when it
    # creates a table, so existing databases need these applied explicitly. CREATE INDEX
    # IF NOT EXISTS is supported by both SQLite and PostgreSQL and is idempotent.
    index_ddls = [
        "CREATE INDEX IF NOT EXISTS ix_wishes_board_status_due ON wishes (board, status, due_date)",
        "CREATE INDEX IF NOT EXISTS ix_wishes_board_due ON wishes (board, due_date)",
        "CREATE INDEX IF NOT EXISTS ix_view_records_ip_created ON view_records (ip, created_at)",
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
        for ddl in index_ddls:
            conn.execute(text(ddl))
        conn.commit()
