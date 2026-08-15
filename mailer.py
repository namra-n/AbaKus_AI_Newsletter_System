"""
mailer.py
Sends the rendered HTML newsletter via SMTP (works with Gmail, Outlook,
or any transactional provider like Brevo/Resend using their SMTP creds —
no code change needed, just different env vars). If SMTP credentials
aren't configured, falls back to writing the email to disk so the system
is fully testable without setting up a mail account.
"""

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, FROM_NAME, NEWSLETTER_TITLE

SEND_ENABLED = bool(SMTP_USER and SMTP_PASSWORD)


def send_email(to_email: str, html_body: str, subject: str = None) -> bool:
    subject = subject or f"{NEWSLETTER_TITLE} — this week's picks"

    if not SEND_ENABLED:
        os.makedirs("outputs/dry_run", exist_ok=True)
        safe_name = to_email.replace("@", "_at_")
        path = f"outputs/dry_run/{safe_name}.html"
        with open(path, "w") as f:
            f.write(html_body)
        print(f"[mailer] SMTP not configured — wrote preview to {path}")
        return True

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{FROM_NAME} <{SMTP_USER}>"
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, to_email, msg.as_string())
        print(f"[mailer] Sent to {to_email}")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"[mailer] ERROR sending to {to_email}: {exc}")
        return False
