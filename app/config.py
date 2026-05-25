from pathlib import Path

BASE_DIR = Path(__file__).parent.parent

UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB

ALLOWED_MIME_TYPES = {
    "image/jpeg", "image/png", "image/gif", "image/webp",
    "application/pdf", "text/plain",
}

TREE_CAPACITY = 10_000
COLUMBARIUM_CAPACITY = 10_000

# Rate limits
CREATION_LIMIT_PER_HOUR = 5          # max wish creations per IP per hour
LIKE_DEDUP_PERMANENT = True          # one like per IP per wish, forever
VIEW_DEDUP_WINDOW_SECONDS = 86_400   # 24 hours — one view credit per IP per wish per day

DATABASE_URL = f"sqlite:///{BASE_DIR}/wishes.db"
