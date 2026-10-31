from typing import Generic, TypeVar
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

ModelT = TypeVar("ModelT")


class TenantRepository(Generic[ModelT]):
    def __init__(self, model: type[ModelT], session: AsyncSession):
        self.model = model
        self.session = session

    async def get(self, organization_id: UUID, record_id: UUID) -> ModelT | None:
        result = await self.session.execute(
            select(self.model).where(
                self.model.id == record_id,
                self.model.organization_id == organization_id,
            )
        )
        return result.scalar_one_or_none()

    async def list(
        self, organization_id: UUID, *, limit: int = 50, offset: int = 0
    ) -> list[ModelT]:
        result = await self.session.execute(
            select(self.model)
            .where(self.model.organization_id == organization_id)
            .order_by(self.model.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def count(self, statement) -> int:
        result = await self.session.execute(statement)
        return int(result.scalar_one())

    async def add(self, instance: ModelT) -> ModelT:
        self.session.add(instance)
        await self.session.flush()
        return instance

    async def delete(self, instance: ModelT) -> None:
        await self.session.delete(instance)
        await self.session.flush()
