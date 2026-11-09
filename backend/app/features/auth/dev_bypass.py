from app.core.config import settings
from app.features.auth.challenges import normalize_email


def auth_dev_otp_bypass_allowed(email: str) -> bool:
    """Allow skipping email OTP after password verification in local development only."""
    if settings.app_env != "development":
        return False
    allowed = {normalize_email(entry) for entry in settings.auth_dev_otp_bypass_emails if entry.strip()}
    return normalize_email(email) in allowed
