"""Tiny SMTP helper shared by the API (reports, notifications) and the
reminder cron script. No-ops quietly when SMTP isn't configured."""
import smtplib
from email.message import EmailMessage

from ..config import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, REPORT_EMAIL


def send_email(to_email: str, subject: str, body: str) -> None:
    """Send a plain-text email to a single recipient. Raises on SMTP failure;
    returns silently if SMTP isn't configured or no recipient is given."""
    if not SMTP_HOST or not to_email:
        return
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = SMTP_USER or REPORT_EMAIL
    msg["To"] = to_email
    msg.set_content(body)
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
        smtp.ehlo()
        smtp.starttls()
        if SMTP_USER and SMTP_PASS:
            smtp.login(SMTP_USER, SMTP_PASS)
        smtp.send_message(msg)
