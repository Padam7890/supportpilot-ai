import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_token
from app.db.session import set_auth_challenge_context
from app.models import AuthChallenge, AuthIdentity
from app.services.email_delivery import send_auth_code

CHALLENGE_TTL = timedelta(minutes=10)
OTP_MAX_ATTEMPTS = 5
OTP_MAX_SENDS = 3
OTP_RESEND_INTERVAL = timedelta(seconds=30)


def normalize_email(email: str) -> str:
    return email.strip().casefold()


def mask_email(email: str) -> str:
    local, separator, domain = email.partition("@")
    if not separator:
        return "your email address"
    visible = local[:1] if local else "*"
    return f"{visible}{'*' * min(max(len(local) - 1, 3), 8)}@{domain}"


def _code_digest(challenge_id: UUID, code: str) -> str:
    payload = f"auth-otp:{challenge_id}:{code}".encode()
    return hmac.new(settings.jwt_secret.encode(), payload, hashlib.sha256).hexdigest()


def _new_otp() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


async def create_challenge(
    db: AsyncSession,
    *,
    identity: AuthIdentity | None,
    email: str,
    purpose: str,
    organization_id: UUID | None = None,
    user_id: UUID | None = None,
    send_code: bool = True,
) -> tuple[AuthChallenge, str, str]:
    now = datetime.now(UTC)
    challenge_id = uuid4()
    token = secrets.token_urlsafe(32)
    challenge = AuthChallenge(
        id=challenge_id,
        identity_id=identity.id if identity else None,
        token_hash=hash_token(token),
        purpose=purpose,
        organization_id=organization_id,
        user_id=user_id,
        code_digest=None,
        expires_at=now + CHALLENGE_TTL,
        attempt_count=0,
        send_count=0,
        last_sent_at=None,
        consumed_at=None,
        created_at=now,
    )
    await set_auth_challenge_context(db, challenge.token_hash)
    db.add(challenge)
    await db.flush()
    if send_code:
        await send_challenge_code(challenge, email, purpose)
    return challenge, token, email


async def send_challenge_code(challenge: AuthChallenge, email: str, purpose: str) -> None:
    code = _new_otp()
    challenge.code_digest = _code_digest(challenge.id, code)
    challenge.send_count += 1
    challenge.last_sent_at = datetime.now(UTC)
    try:
        await send_auth_code(email, code, purpose)
    except Exception as exc:
        challenge.code_digest = None
        challenge.send_count -= 1
        raise HTTPException(
            status_code=503,
            detail="Email verification is temporarily unavailable. Contact your workspace administrator.",
        ) from exc


async def get_challenge(
    db: AsyncSession,
    token: str,
    *,
    purpose: str,
    lock: bool = True,
) -> AuthChallenge:
    await set_auth_challenge_context(db, hash_token(token))
    statement = select(AuthChallenge).where(
        AuthChallenge.token_hash == hash_token(token),
        AuthChallenge.purpose == purpose,
    )
    if lock:
        statement = statement.with_for_update()
    challenge = await db.scalar(statement)
    now = datetime.now(UTC)
    if (
        challenge is None
        or challenge.consumed_at is not None
        or challenge.expires_at <= now
        or challenge.attempt_count >= OTP_MAX_ATTEMPTS
    ):
        raise HTTPException(
            status_code=400, detail="Verification is invalid or expired. Start again."
        )
    return challenge


def code_is_valid(challenge: AuthChallenge, code: str) -> bool:
    if challenge.code_digest is None:
        return False
    return hmac.compare_digest(challenge.code_digest, _code_digest(challenge.id, code))


def email_hint(email: str) -> str:
    return mask_email(email)
