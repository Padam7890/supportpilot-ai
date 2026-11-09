"""Read-only staging readiness preflight regression tests."""
import io
import json
from unittest.mock import patch
from urllib.error import URLError

import pytest

from scripts.staging_preflight import probe_health, validate_base_url


@pytest.mark.parametrize("url", [
    "http://staging.example.com", "https://user:pass@staging.example.com",
    "https://staging.example.com/path", "https://staging.example.com?token=secret",
    "file:///etc/passwd",
])
def test_reject_unsafe_origins(url: str) -> None:
    with pytest.raises(ValueError):
        validate_base_url(url)


def test_accept_https_origin() -> None:
    assert validate_base_url("https://staging.example.com/") == "https://staging.example.com"


class FakeResponse:
    status = 200
    headers = {"Content-Type": "application/json"}

    def __init__(self, payload: dict) -> None:
        self.body = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit: int) -> bytes:
        return self.body


def test_ready_when_db_and_redis_connected() -> None:
    response = FakeResponse({"status": "ready", "checks": {"database": "connected", "redis": "connected"}})
    with patch("scripts.staging_preflight.urllib.request.urlopen", return_value=response):
        assert probe_health("https://staging.example.com") == (True, "ready")


def test_unready_dependencies_fail() -> None:
    response = FakeResponse({"status": "ready", "checks": {"database": "disconnected", "redis": "connected"}})
    with patch("scripts.staging_preflight.urllib.request.urlopen", return_value=response):
        assert probe_health("https://staging.example.com") == (False, "dependencies_not_ready")


def test_network_failure_fails_closed() -> None:
    with patch("scripts.staging_preflight.urllib.request.urlopen", side_effect=URLError("offline")):
        assert probe_health("https://staging.example.com") == (False, "readiness_probe_failed")
