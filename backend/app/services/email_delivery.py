"""Minimal SMTP delivery for transactional verification messages."""

import asyncio
import smtplib
from email.message import EmailMessage

from app.core.config import settings


def smtp_is_configured() -> bool:
    return bool(settings.email_smtp_host and settings.email_from_address)


def _send_sync(message: EmailMessage) -> None:
    host = settings.email_smtp_host
    if not host:
        raise RuntimeError("SMTP is not configured")
    if settings.email_use_ssl:
        with smtplib.SMTP_SSL(host, settings.email_smtp_port, timeout=15) as client:
            if settings.email_smtp_username:
                client.login(
                    settings.email_smtp_username,
                    settings.email_smtp_password.get_secret_value() if settings.email_smtp_password else "",
                )
            client.send_message(message)
    else:
        with smtplib.SMTP(host, settings.email_smtp_port, timeout=15) as client:
            client.starttls()
            if settings.email_smtp_username:
                client.login(
                    settings.email_smtp_username,
                    settings.email_smtp_password.get_secret_value() if settings.email_smtp_password else "",
                )
            client.send_message(message)


async def send_order_verification_code(email: str, code: str) -> None:
    if not smtp_is_configured():
        raise RuntimeError("Transactional email is not configured")
    message = EmailMessage()
    message["Subject"] = "Your SupportPilot order verification code"
    message["From"] = settings.email_from_address
    message["To"] = email
    message.set_content(
        f"Your order verification code is {code}. It expires in 10 minutes. "
        "If you did not request this code, you can ignore this email."
    )
    await asyncio.to_thread(_send_sync, message)
