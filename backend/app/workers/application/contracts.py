"""Typed job envelopes shared by the worker dispatcher and handlers."""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ClaimedJob:
    kind: str
    organization_id: UUID
    job_id: UUID | None = None
    related_id: UUID | None = None
    event_name: str | None = None
    correlation_id: str | None = None
    claim_token: UUID | None = None


class JobHandler:
    """Minimal handler contract; claim methods persist leases before returning."""

    kind: str

    async def claim(self, organization_id: UUID) -> ClaimedJob | None:
        raise NotImplementedError

    async def process(self, job: ClaimedJob) -> None:
        raise NotImplementedError
