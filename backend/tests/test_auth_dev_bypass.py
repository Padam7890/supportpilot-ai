import pytest

from app.core.config import settings
from app.features.auth.dev_bypass import auth_dev_otp_bypass_allowed


@pytest.mark.parametrize(
    ("app_env", "emails", "candidate", "expected"),
    [
        ("production", ["padamthapamaho@gmail.com"], "padamthapamaho@gmail.com", False),
        ("development", [], "padamthapamaho@gmail.com", False),
        ("development", ["padamthapamaho@gmail.com"], "PadamThapamaho@Gmail.com", True),
        ("development", ["other@example.com"], "padamthapamaho@gmail.com", False),
    ],
)
def test_auth_dev_otp_bypass_allowed(
    monkeypatch: pytest.MonkeyPatch,
    app_env: str,
    emails: list[str],
    candidate: str,
    expected: bool,
) -> None:
    monkeypatch.setattr(settings, "app_env", app_env)
    monkeypatch.setattr(settings, "auth_dev_otp_bypass_emails", emails)
    assert auth_dev_otp_bypass_allowed(candidate) is expected
