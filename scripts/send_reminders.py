"""Send the D-day reminder for wishes whose due date has arrived.

The wisher gets a single nudge on the wish's due_date: "your wish's day is here
— did it come true?" with a deep link back to it. This is the return mechanism
that turns a one-shot wish into a repeat visit.

Recipient:
  - registered owner → their account email, in their language preference;
  - anonymous wisher → the optional email they entered, in the page language
    the wish was created in (wish.lang; Korean if unknown).
A registered owner's account email wins if a wish somehow has both.

Run daily from the project root via the venv, e.g. crontab:

    15 0 * * * cd /home/sun/PythonProjects/tree-of-wishes && \
        .venv/bin/python -m scripts.send_reminders >> backups/reminders.log 2>&1

Idempotent: each wish is sent at most once (reminder_sent_at is stamped after a
successful send and committed per-wish). `due_date <= today` (not `== today`) so
a missed cron day still goes out the next run; the normal case fires on D-day,
while the wish is still on the tree (the expiry sweep only moves it the day
*after* due_date).
"""
from datetime import date, datetime

from sqlalchemy import or_

from app.config import BASE_URL
from app.database import SessionLocal
from app.models import Wish, WishStatus
from app.services.email import send_email


def _recipient(wish: Wish) -> tuple[str | None, str]:
    """(email, language) for the reminder. Registered owner's account email
    wins; otherwise the anonymous wisher's opted-in email (Korean)."""
    owner = wish.owner
    if owner and owner.email:
        return owner.email, (owner.language or "en")
    if wish.reminder_email:
        return wish.reminder_email, (wish.lang or "ko")
    return None, "ko"


def _email_for(wish: Wish, language: str) -> tuple[str, str]:
    snippet = wish.text.strip().replace("\r", " ").replace("\n", " ")
    if len(snippet) > 80:
        snippet = snippet[:80].rstrip() + "…"
    lang = "en" if language == "en" else "ko"
    link = f"{BASE_URL}/wish/{wish.id}?lang={lang}"
    if lang == "en":
        subject = "[Tree of Wishes] Your wish's day has arrived"
        body = (
            "The day you wished for is here. Did it come true?\n\n"
            f"Wish : {snippet}\n"
            f"Link : {link}\n\n"
            "Open your wish, and if it came true, mark it as fulfilled.\n"
            "Your fulfilled wish makes the tree shine brighter. 🌳✨"
        )
    else:
        subject = "[소원의 나무] 소원의 기한이 되었어요"
        body = (
            "소원을 빌었던 날이 왔어요. 그 소원, 이루어졌나요?\n\n"
            f"소원 : {snippet}\n"
            f"링크 : {link}\n\n"
            "아래 링크에서 소원을 열고, 이루어졌다면 '이루어졌어요'로 표시해 보세요.\n"
            "당신의 이루어진 소원이 나무를 더 빛나게 합니다. 🌳✨"
        )
    return subject, body


def main() -> int:
    today = date.today()
    db = SessionLocal()
    sent = 0
    try:
        due = (
            db.query(Wish)
            .filter(
                or_(Wish.reminder_email.isnot(None), Wish.owner_id.isnot(None)),
                Wish.reminder_sent_at.is_(None),
                Wish.status != WishStatus.fulfilled,
                Wish.due_date <= today,
            )
            .all()
        )
        for wish in due:
            to_email, language = _recipient(wish)
            if not to_email:
                continue
            subject, body = _email_for(wish, language)
            try:
                send_email(to_email, subject, body)
            except Exception as e:  # noqa: BLE001 — log and keep going
                print(f"[reminders] FAILED wish {wish.id}: {e}")
                continue
            wish.reminder_sent_at = datetime.utcnow()
            db.commit()  # per-wish so a later failure can't double-send earlier ones
            sent += 1
        print(f"[reminders] {today}: sent {sent} of {len(due)} due reminder(s)")
        return sent
    finally:
        db.close()


if __name__ == "__main__":
    main()
