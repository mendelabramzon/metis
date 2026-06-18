"""The model router: pick a provider by task class + sensitivity, enforcing the
provider allowlist **before any prompt is constructed**. Restricted data routes to a
local (non-external) provider regardless of the task's quality tier.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from metis_core.llm.errors import NoEligibleProviderError
from metis_core.llm.routing_config import RoutingConfig, task_tier
from metis_protocol import (
    ModelRequest,
    ModelResponse,
    ModelTier,
    Sensitivity,
    is_at_least,
)


@runtime_checkable
class RoutableProvider(Protocol):
    """A ``ModelProvider`` the router can reason about (adds externality)."""

    @property
    def name(self) -> str: ...

    @property
    def is_external(self) -> bool: ...

    def supports(self, tier: ModelTier, sensitivity: Sensitivity) -> bool: ...

    async def generate(self, request: ModelRequest) -> ModelResponse: ...


class MetisModelRouter:
    def __init__(
        self,
        providers: Sequence[RoutableProvider],
        *,
        config: RoutingConfig | None = None,
    ) -> None:
        # Ordered by preference (e.g. cloud first, local fallback).
        self._providers = list(providers)
        self._config = config if config is not None else RoutingConfig()

    def route(self, request: ModelRequest) -> RoutableProvider:
        tier = task_tier(request.task_class)
        external_blocked = is_at_least(request.sensitivity, self._config.external_block_floor)
        for provider in self._providers:
            if provider.is_external and external_blocked:
                continue  # allowlist enforced before any prompt construction
            if provider.supports(tier, request.sensitivity):
                return provider
        raise NoEligibleProviderError(
            f"no provider for task={request.task_class.value} "
            f"sensitivity={request.sensitivity.value}"
        )

    async def generate(self, request: ModelRequest) -> ModelResponse:
        return await self.route(request).generate(request)


if TYPE_CHECKING:
    from metis_protocol import ModelRouter

    def _conforms(router: MetisModelRouter) -> ModelRouter:
        return router  # static proof MetisModelRouter satisfies the protocol
