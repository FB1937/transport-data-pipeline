from __future__ import annotations

import json
import smtplib
from email.message import EmailMessage
from urllib.error import URLError
from urllib.request import Request, urlopen

from .config import (
    ALERT_EMAIL_TO,
    DISCORD_WEBHOOK_URL,
    SMTP_FROM,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USERNAME,
)


def notify_failure(subject: str, message: str) -> list[str]:
    sent: list[str] = []
    errors: list[str] = []
    if DISCORD_WEBHOOK_URL:
        try:
            request = Request(
                DISCORD_WEBHOOK_URL,
                data=json.dumps({"content": f"**{subject}**\n{message}"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(request, timeout=15):
                pass
            sent.append("Discord")
        except (OSError, URLError, ValueError) as error:
            errors.append(f"Discord 알림 실패: {error}")
    if ALERT_EMAIL_TO:
        if not SMTP_HOST or not SMTP_FROM:
            errors.append("이메일 알림 설정이 불완전합니다: SMTP_HOST와 SMTP_FROM이 필요합니다.")
        else:
            try:
                email = EmailMessage()
                email["Subject"] = subject
                email["From"] = SMTP_FROM
                email["To"] = ALERT_EMAIL_TO
                email.set_content(message)
                with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
                    server.starttls()
                    if SMTP_USERNAME:
                        server.login(SMTP_USERNAME, SMTP_PASSWORD)
                    server.send_message(email)
                sent.append("email")
            except (OSError, smtplib.SMTPException) as error:
                errors.append(f"이메일 알림 실패: {error}")
    if errors:
        raise RuntimeError("; ".join(errors))
    return sent
