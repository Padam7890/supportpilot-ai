"""Minimal SMTP delivery for transactional verification messages."""

import asyncio
import json
import logging
import smtplib
from email.message import EmailMessage

from app.core.config import settings

logger = logging.getLogger(__name__)


def _log_email_event(level: int, event: str, **fields: object) -> None:
    logger.log(
        level, "transactional_email %s", json.dumps({"event": event, **fields}, sort_keys=True)
    )


def smtp_is_configured() -> bool:
    return bool(settings.email_smtp_host and settings.email_from_address)


def _send_sync(message: EmailMessage, email_kind: str) -> None:
    host = settings.email_smtp_host
    if not host:
        raise RuntimeError("SMTP is not configured")
    stage = "connect"
    _log_email_event(
        logging.INFO,
        "smtp_connecting",
        email_kind=email_kind,
        smtp_host=host,
        smtp_port=settings.email_smtp_port,
        smtp_tls_mode="implicit_tls" if settings.email_use_ssl else "starttls",
    )
    try:
        smtp_class = smtplib.SMTP_SSL if settings.email_use_ssl else smtplib.SMTP
        with smtp_class(host, settings.email_smtp_port, timeout=15) as client:
            if not settings.email_use_ssl:
                stage = "starttls"
                client.starttls()
            if settings.email_smtp_username:
                stage = "authentication"
                client.login(
                    settings.email_smtp_username,
                    settings.email_smtp_password.get_secret_value()
                    if settings.email_smtp_password
                    else "",
                )
            stage = "send_message"
            client.send_message(message)
        _log_email_event(
            logging.INFO,
            "smtp_accepted",
            email_kind=email_kind,
            smtp_host=host,
            smtp_port=settings.email_smtp_port,
        )
    except Exception as exc:  # Do not log SMTP response text, addresses, or credentials.
        _log_email_event(
            logging.ERROR,
            "smtp_failed",
            email_kind=email_kind,
            smtp_host=host,
            smtp_port=settings.email_smtp_port,
            smtp_stage=stage,
            error_type=type(exc).__name__,
        )
        raise


async def send_order_verification_code(email: str, code: str) -> None:
    if not smtp_is_configured():
        _log_email_event(
            logging.ERROR,
            "smtp_not_configured",
            email_kind="shopify_order_verification",
            smtp_host_present=bool(settings.email_smtp_host),
            from_address_present=bool(settings.email_from_address),
            smtp_username_present=bool(settings.email_smtp_username),
            smtp_password_present=bool(settings.email_smtp_password),
            smtp_port=settings.email_smtp_port,
            smtp_ssl=settings.email_use_ssl,
        )
        raise RuntimeError("Transactional email is not configured")
    _log_email_event(logging.INFO, "send_requested", email_kind="shopify_order_verification")
    message = EmailMessage()
    message["Subject"] = "Your SupportPilot order verification code"
    message["From"] = settings.email_from_address
    message["To"] = email
    message.set_content(
        f"Your order verification code is {code}. It expires in 10 minutes. "
        "If you did not request this code, you can ignore this email."
    )
    await asyncio.to_thread(_send_sync, message, "shopify_order_verification")


async def send_auth_code(email: str, code: str, purpose: str) -> None:
    purpose_copy = {
        "login": ("Your SupportPilot sign-in code", "Use this code to finish signing in"),
        "registration": ("Verify your SupportPilot email", "Use this code to verify your email"),
        "password_reset": (
            "Reset your SupportPilot password",
            "Use this code to reset your password",
        ),
    }
    if purpose not in purpose_copy:
        raise ValueError("Unsupported authentication email purpose")
    if not smtp_is_configured():
        _log_email_event(
            logging.ERROR,
            "smtp_not_configured",
            email_kind=f"auth_{purpose}",
            smtp_host_present=bool(settings.email_smtp_host),
            from_address_present=bool(settings.email_from_address),
        )
        raise RuntimeError("Transactional email is not configured")
    subject, intro = purpose_copy[purpose]
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.email_from_address
    message["To"] = email
    message.set_content(
        f"{intro}: {code}. It expires in 10 minutes. If you did not request this, ignore this email."
    )
    _log_email_event(logging.INFO, "send_requested", email_kind=f"auth_{purpose}")
    await asyncio.to_thread(_send_sync, message, f"auth_{purpose}")


async def send_notification_email(email: str, title: str, body: str, action_path: str | None) -> None:
    """Deliver a small notification email without logging its recipient or content."""
    if not smtp_is_configured():
        raise RuntimeError("Transactional email is not configured")
    origin = (settings.cors_origins[0] if settings.cors_origins else "http://localhost:3000").rstrip("/")
    safe_path = action_path if action_path and action_path.startswith("/dashboard/") and not action_path.startswith("//") else "/dashboard"
    message = EmailMessage()
    message["Subject"] = f"SupportPilot: {title[:150]}"
    message["From"] = settings.email_from_address
    message["To"] = email
    message.set_content(f"{body or title}\n\nOpen SupportPilot: {origin}{safe_path}")
    await asyncio.to_thread(_send_sync, message, "workspace_notification")
