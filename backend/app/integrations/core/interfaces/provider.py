from typing import Protocol, runtime_checkable

from app.integrations.core.contracts.provider import ProviderDescriptor
from app.integrations.core.types import IntegrationCapability


@runtime_checkable
class IntegrationProvider(Protocol):
    @property
    def descriptor(self) -> ProviderDescriptor: ...

    def get_capability(self, capability: IntegrationCapability) -> object | None: ...
