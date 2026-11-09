"""Read-only staging deployment smoke checks.

Does not create tickets, mutate orders, or require privileged credentials.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from urllib.parse import urlparse


def validate_base_url(value: str, *, allow_http: bool = False) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in ({"https", "http"} if allow_http else {"https"}):
        raise ValueError("Staging URL must use HTTPS")
    if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Staging URL must have a host and no credentials/query/fragment")
    if parsed.path not in {"", "/"}:
        raise ValueError("Staging URL must be an origin, without a path")
    return value.rstrip("/")


def probe_health(base_url: str, *, timeout: float = 5.0) -> tuple[bool, str]:
    request = urllib.request.Request(
        base_url + "/health/ready",
        headers={"Accept": "application/json", "User-Agent": "SupportPilot-Staging-Preflight/1"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = response.status
            content_type = response.headers.get("Content-Type", "")
            body = response.read(4096)
        if status != 200:
            return False, f"unexpected_status:{status}"
        if "application/json" not in content_type:
            return False, "unexpected_content_type"
        payload = json.loads(body)
        if not isinstance(payload, dict):
            return False, "unexpected_payload"
        return True, "ready"
    except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError):
        return False, "readiness_probe_failed"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only staging API readiness preflight")
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--allow-http-local", action="store_true")
    args = parser.parse_args(argv)
    try:
        url = validate_base_url(args.api_url, allow_http=args.allow_http_local)
        if args.allow_http_local and urlparse(url).scheme == "http" and urlparse(url).hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("HTTP is permitted for loopback hosts only")
    except ValueError as exc:
        print(f"staging_preflight=FAIL reason={exc}", file=sys.stderr)
        return 2
    passed, reason = probe_health(url)
    print(f"staging_preflight={'PASS' if passed else 'FAIL'} reason={reason}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
