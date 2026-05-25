# Tree of Wishes

An anonymous public wish bulletin board with a retro aesthetic. Leave a wish on the tree, watch it float among others as a glowing firefly, and see it move to the Columbarium when its time has passed.

---

## Features

- **Two boards**: Tree of Wishes (active wishes, light theme) and Columbarium (expired wishes, dark theme)
- **Firefly animation**: each wish drifts along a unique Lissajous path and flickers slowly
- **Keyword labels**: a meaningful word is extracted from each wish and floated beneath it
- **Hover preview**: hover any wish for an instant preview without clicking
- **Wish lifecycle**: wishes expire on their due date and move to the Columbarium automatically on next page visit
- **Fulfilled wishes**: mark a wish fulfilled with a password — it stays on the tree, brighter
- **Likes & views**: tracked per IP with deduplication; no registration required
- **Search**: full-text search across both boards; clicking a result opens the wish modal directly
- **Bilingual**: English and Korean (en / ko), switchable in the header
- **Anonymous & password-protected**: bcrypt-hashed passwords, deliberately unrecoverable

---

## Stack

| Layer | Choice | Why |
|---|---|---|
| Backend | **Python / FastAPI** | Lightweight async framework; minimal boilerplate; good SQLAlchemy integration |
| Database | **SQLite + SQLAlchemy** | Zero-config local dev; easy to swap for Postgres (`DATABASE_URL`) |
| Templates | **Jinja2** | Server-rendered HTML; no build step |
| Frontend | **Vanilla JS** | No framework overhead; single `WishGrid` class shared across both boards |
| Password hashing | **bcrypt (direct)** | `passlib` is incompatible with Python 3.13; `bcrypt` is used directly |
| File uploads | **python-multipart + aiofiles** | Built-in FastAPI support |

---

## Getting started

```bash
# 1. Create a virtual environment and install dependencies
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. (Optional) Seed the database with sample wishes
python seed.py

# 3. Start the server
uvicorn app.main:app --reload

# 4. Open http://localhost:8000
```

The SQLite database (`wishes.db`) and uploaded files (`uploads/`) are created automatically on first run.

To make the server accessible on your local network:

```bash
uvicorn app.main:app --reload --host 0.0.0.0
```

---

## Pages

| Route | Description |
|---|---|
| `/` | Redirects to `/tree` |
| `/tree` | Tree of Wishes — light theme, active + fulfilled wishes |
| `/columbarium` | Columbarium — dark theme, expired wishes |
| `/settings` | Language switcher |
| `/about` | About page |
| `/my-wishes` | Stub — gated behind future auth |

---

## Configuration

All limits live in `app/config.py`:

| Setting | Default | Notes |
|---|---|---|
| `MAX_FILE_SIZE_BYTES` | 5 MB | Enforced server-side |
| `ALLOWED_MIME_TYPES` | JPEG, PNG, GIF, WEBP, PDF, TXT | |
| `TREE_CAPACITY` | 10,000 | Independent of Columbarium |
| `COLUMBARIUM_CAPACITY` | 10,000 | Independent of Tree |
| `CREATION_LIMIT_PER_HOUR` | 5 | Wish creations per IP per hour |
| `VIEW_DEDUP_WINDOW_SECONDS` | 86,400 | One view credit per IP per wish per day |
| Like dedup | Permanent | One like per IP per wish, forever |

To use Postgres, set `DATABASE_URL` before starting:

```bash
DATABASE_URL=postgresql+psycopg2://user:pass@host/dbname uvicorn app.main:app
```

---

## Design rules

1. **Two independent 10,000 caps** — Tree and Columbarium never share quota.
2. **Effective age on the Tree** = `fulfilled_at` if fulfilled, else `created_at`. Used for both ordering and deletion candidate selection.
3. **Tree-full eviction is permanent** — the oldest wish by effective age is deleted forever, not moved to Columbarium.
4. **Only expiry-while-unfulfilled** moves wishes to the Columbarium, triggered lazily on the next page visit.
5. **Columbarium-full eviction** = fewest likes, ties broken by oldest `created_at`.
6. **Fulfilled wishes never enter the Columbarium** — they stay on the Tree as larger, brighter white glyphs.
7. **Attachments** can only be added at fulfillment time, not at creation.
8. **Passwords are bcrypt-hashed and unrecoverable** by design.

---

## Future: registration & Google OAuth

The architecture is ready for it without a schema migration:

- `app/models.py`: `User` model with `google_id` column already exists.
- `app/models.py`: `Wish.owner_id` is a nullable FK to `User` (currently `NULL` for all wishes).
- `app/services/capacity.py`: `ensure_tree_capacity()` has a comment marking where to add `filter(Wish.owner_id.is_(None))` to protect registered users from age-based deletion.
- `app/routes/api.py` (`create_wish`): a comment marks where to set `owner_id` from the session.

To add Google OAuth: install `authlib`, add `/auth/google` callback routes, populate `owner_id` on wish creation.

---

## Seed data

```bash
python seed.py
```

Adds 12 active + 4 fulfilled wishes on the Tree, and 6 dead wishes in the Columbarium. All use the test password **`test1234`**.
