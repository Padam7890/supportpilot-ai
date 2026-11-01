"""Central registry for real provider adapters and their capabilities."""

from typing import TypeVar

from app.integrations.core.contracts.provider import ProviderDescriptor
from app.integrations.core.errors.integration import IntegrationError, IntegrationErrorCode
from app.integrations.core.interfaces.provider import IntegrationProvider
from app.integrations.core.types import IntegrationCapability

CapabilityT = TypeVar("CapabilityT")


class IntegrationRegistry:
    """Registry populated at application startup with concrete adapters."""

    def __init__(self) -> None:
        self._providers: dict[str, IntegrationProvider] = {}

    def register(self, provider: IntegrationProvider) -> None:
        descriptor = provider.descriptor
        provider_id = descriptor.provider_id
        if provider_id in self._providers:
            raise ValueError(f"Integration provider is already registered: {provider_id}")
        missing = [
            capability.value
            for capability in descriptor.capabilities
            if provider.get_capability(capability) is None
        ]
        if missing:
            raise ValueError(
                f"Provider {provider_id} declares missing capabilities: {', '.join(missing)}"
            )
        self._providers[provider_id] = provider

    def list_providers(self) -> tuple[ProviderDescriptor, ...]:
        return tuple(self._providers[key].descriptor for key in sorted(self._providers))

    def get_provider(self, provider_id: str) -> IntegrationProvider:
        provider = self._providers.get(provider_id)
        if provider is None:
            raise IntegrationError(IntegrationErrorCode.PROVIDER_NOT_FOUND, retryable=False)
        return provider

    def get_capability(
        self,
        provider_id: str,
        capability: IntegrationCapability,
        capability_type: type[CapabilityT],
    ) -> CapabilityT:
        provider = self.get_provider(provider_id)
        implementation = provider.get_capability(capability)
        if implementation is None or not isinstance(implementation, capability_type):
            raise IntegrationError(IntegrationErrorCode.UNSUPPORTED_CAPABILITY, retryable=False)
        return implementation
