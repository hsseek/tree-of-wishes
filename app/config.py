import os
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

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

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR}/wishes.db")

# Rate limits (likes / views per IP per hour, across all wishes)
LIKE_RATE_LIMIT_PER_HOUR  = int(os.getenv("LIKE_RATE_LIMIT_PER_HOUR",  "50"))
VIEW_RATE_LIMIT_PER_HOUR  = int(os.getenv("VIEW_RATE_LIMIT_PER_HOUR",  "200"))

# Session
SESSION_SECRET = os.getenv("SESSION_SECRET", "insecure-dev-secret-change-in-production")
BASE_URL        = os.getenv("BASE_URL", "http://localhost:8000").rstrip("/")

# OAuth — Google
GOOGLE_CLIENT_ID     = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")

# Report / contact email (SMTP)
REPORT_EMAIL = os.getenv("REPORT_EMAIL", "")
SMTP_HOST    = os.getenv("SMTP_HOST", "")
SMTP_PORT    = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER    = os.getenv("SMTP_USER", "")
SMTP_PASS    = os.getenv("SMTP_PASS", "")
