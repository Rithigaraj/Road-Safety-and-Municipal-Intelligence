"""Notifications: in-app feed (always) + optional SMTP email when configured.

Set these environment variables to enable e-mail delivery:
    SMTP_HOST, SMTP_PORT (default 587), SMTP_USER, SMTP_PASSWORD, NOTIFY_EMAIL
"""
from __future__ import annotations

import os
import smtplib
import threading
from email.mime.text import MIMEText

from sqlalchemy.orm import Session

from ..models import Notification
from .ws import hub


def notify(db: Session, ntype: str, title: str, body: str = "",
           ref_type: str | None = None, ref_id: int | None = None,
           email: bool = False) -> Notification:
    n = Notification(type=ntype, title=title, body=body,
                     ref_type=ref_type, ref_id=ref_id)
    db.add(n)
    db.commit()

    hub.broadcast(ntype, {"title": title, "ref_type": ref_type, "ref_id": ref_id})

    if email and os.getenv("SMTP_HOST") and os.getenv("NOTIFY_EMAIL"):
        threading.Thread(target=_send_email, args=(title, body), daemon=True).start()
    return n


def _send_email(subject: str, body: str) -> None:
    try:
        host = os.environ["SMTP_HOST"]
        port = int(os.getenv("SMTP_PORT", "587"))
        user = os.getenv("SMTP_USER", "")
        password = os.getenv("SMTP_PASSWORD", "")
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = user or "municipal-platform"
        msg["To"] = os.environ["NOTIFY_EMAIL"]
        with smtplib.SMTP(host, port, timeout=10) as server:
            server.starttls()
            if user:
                server.login(user, password)
            server.send_message(msg)
    except Exception as exc:  # never break the request path on mail errors
        print(f"[notifier] email failed: {exc}")
