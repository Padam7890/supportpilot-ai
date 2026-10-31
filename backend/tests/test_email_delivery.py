import asyncio
import logging

import pytest

from app.core.config import settings
from app.services.email_delivery import send_order_verification_code


def test_unconfigured_email_logs_safe_configuration_diagnostics(monkeypatch, caplog):
    monkeypatch.setattr(settings, "email_smtp_host", None)
    monkeypatch.setattr(settings, "email_from_address", None)
    monkeypatch.setattr(settings, "email_smtp_username", None)
    monkeypatch.setattr(settings, "email_smtp_password", None)

    caplog.set_level(logging.ERROR, logger="app.services.email_delivery")
    recipient = "private-shopper@example.com"
    code = "928174"

    with pytest.raises(RuntimeError, match="not configured"):
        asyncio.run(send_order_verification_code(recipient, code))

    assert "smtp_not_configured" in caplog.text
    assert '"smtp_host_present": false' in caplog.text
    assert '"from_address_present": false' in caplog.text
    assert recipient not in caplog.text
    assert code not in caplog.text
