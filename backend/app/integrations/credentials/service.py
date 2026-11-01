"""Persistence helpers for ciphertext scoped to one tenant connection.

Encryption and decryption belong to the provider that owns a credential format;
this service only persists already-encrypted material and rotation metadata.
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import IntegrationCredential


async def store_encrypted_credential(
    db: AsyncSession,
    *,
    organization_id: UUID,
    connection_id: UUID,
    credential_type: str,
    encrypted_value: str,
    key_version: str,
    expires_at: datetime | None,
) -> IntegrationCredential:
    credential = await db.scalar(
        select(IntegrationCredential)
        .where(
            IntegrationCredential.organization_id == organization_id,
            IntegrationCredential.connection_id == connection_id,
            IntegrationCredential.credential_type == credential_type,
        )
        .with_for_update()
    )
    now = datetime.now(UTC)
    if credential is None:
        credential = IntegrationCredential(
            organization_id=organization_id,
            connection_id=connection_id,
            credential_type=credential_type,
            encrypted_value=encrypted_value,
            key_version=key_version,
            expires_at=expires_at,
            rotated_at=now,
        )
        db.add(credential)
    else:
        credential.encrypted_value = encrypted_value
        credential.key_version = key_version
        credential.expires_at = expires_at
        credential.rotated_at = now
    await db.flush()
    return credential


async def delete_connection_credentials(
    db: AsyncSession,
    *,
    organization_id: UUID,
    connection_id: UUID,
    credential_type: str | None = None,
) -> None:
    query = select(IntegrationCredential).where(
        IntegrationCredential.organization_id == organization_id,
        IntegrationCredential.connection_id == connection_id,
    )
    if credential_type is not None:
        query = query.where(IntegrationCredential.credential_type == credential_type)
    rows = await db.scalars(query.with_for_update())
    for credential in rows.all():
        await db.delete(credential)
    await db.flush()
