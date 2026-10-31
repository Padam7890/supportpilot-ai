import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash

from app.core.config import settings

password_hash = PasswordHash.recommended()
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return password_hash.verify(password, hashed)


def create_access_token(user_id: str, organization_id: str) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "org": organization_id,
        "typ": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def create_refresh_token(user_id: str, organization_id: str) -> tuple[str, datetime]:
    now = datetime.now(UTC)
    expires_at = now + timedelta(days=settings.refresh_token_expire_days)
    payload = {
        "sub": user_id,
        "org": organization_id,
        "jti": str(uuid.uuid4()),
        "typ": "refresh",
        "iat": now,
        "exp": expires_at,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM), expires_at


def create_platform_access_token(platform_owner_id: str) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": platform_owner_id,
            "typ": "platform_access",
            "iat": now,
            "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
        },
        settings.jwt_secret,
        algorithm=ALGORITHM,
    )


def create_platform_refresh_token(platform_owner_id: str) -> tuple[str, datetime]:
    now = datetime.now(UTC)
    expires_at = now + timedelta(days=settings.refresh_token_expire_days)
    token = jwt.encode(
        {
            "sub": platform_owner_id,
            "jti": str(uuid.uuid4()),
            "typ": "platform_refresh",
            "iat": now,
            "exp": expires_at,
        },
        settings.jwt_secret,
        algorithm=ALGORITHM,
    )
    return token, expires_at


def create_invitation_token(invitation_id: str, organization_id: str) -> tuple[str, datetime]:
    now = datetime.now(UTC)
    expires_at = now + timedelta(hours=settings.invitation_expire_hours)
    payload = {
        "sub": invitation_id,
        "org": organization_id,
        "typ": "invitation",
        "iat": now,
        "exp": expires_at,
        "nonce": secrets.token_urlsafe(12),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM), expires_at


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def decode_access_token(token: str) -> dict:
    claims = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    if claims.get("typ") != "access":
        raise jwt.InvalidTokenError("Expected access token")
    return claims


def decode_refresh_token(token: str) -> dict:
    claims = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    if claims.get("typ") != "refresh":
        raise jwt.InvalidTokenError("Expected refresh token")
    return claims


def decode_platform_access_token(token: str) -> dict:
    claims = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    if claims.get("typ") != "platform_access":
        raise jwt.InvalidTokenError("Expected platform access token")
    return claims


def decode_platform_refresh_token(token: str) -> dict:
    claims = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    if claims.get("typ") != "platform_refresh":
        raise jwt.InvalidTokenError("Expected platform refresh token")
    return claims


def decode_invitation_token(token: str) -> dict:
    claims = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    if claims.get("typ") != "invitation":
        raise jwt.InvalidTokenError("Expected invitation token")
    return claims


def create_widget_visitor_token(
    *, organization_id: str, widget_public_id: str, conversation_id: str, expires_at: datetime
) -> str:
    """Create a narrowly scoped storefront visitor token, never a workspace token."""
    issued_at = datetime.now(UTC)
    # Retries reuse the original expiry and cannot extend a visitor session.
    return jwt.encode(
        {
            "sub": conversation_id,
            "org": organization_id,
            "wid": widget_public_id,
            "typ": "widget_visitor",
            "iat": issued_at,
            "exp": expires_at,
        },
        settings.jwt_secret,
        algorithm=ALGORITHM,
    )


def decode_widget_visitor_token(token: str) -> dict:
    claims = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    if claims.get("typ") != "widget_visitor":
        raise jwt.InvalidTokenError("Expected widget visitor token")
    return claims
