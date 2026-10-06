"""Send the digest by email (SMTP) and/or Telegram, using credentials from the environment."""

from __future__ import annotations

import os
import smtplib
import sqlite3
from email.message import EmailMessage

import requests


def email(subject: str, markdown: str, html_body: str) -> bool:
    host, user, password, to = (os.environ.get(k) for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "DIGEST_TO"))
    if not (host and user and password and to):
        return False
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, user, to
    msg.set_content(markdown)
    msg.add_alternative(html_body, subtype="html")
    with smtplib.SMTP(host, int(os.environ.get("SMTP_PORT", "587")), timeout=30) as smtp:
        smtp.starttls()
        smtp.login(user, password)
        smtp.send_message(msg)
    return True


def telegram(rows: list[sqlite3.Row], header: str) -> bool:
    token, chat_id = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat_id):
        return False
    lines = [header]
    for row in rows[:10]:
        score = row["fit_score"] if row["fit_score"] is not None else f"~{row['rule_score']}"
        lines.append(f"{score} · {row['title']} — {row['company']} ({row['location']})\n{row['url']}")
    resp = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": "\n\n".join(lines)[:4000], "disable_web_page_preview": True},
        timeout=20,
    )
    resp.raise_for_status()
    return True
