"""Model profiles: local / cloud / GPU, all routing through the Stage 4 abstraction.

A profile only selects *which providers the router sees*; the routing logic — and crucially the
restricted-data block (restricted data never leaves the node) — is the same Stage 4 router in every
profile. ``local`` and ``gpu`` expose only a non-external provider (a CPU Ollama or a GPU vLLM
endpoint), so all data stays local; ``cloud`` adds an external provider in front of a local
fallback. Whatever the profile, restricted data still routes local — the invariant the profiles
must preserve.
"""

from __future__ import annotations

from enum import StrEnum

from metis_core.llm.provider import StubProvider
from metis_core.llm.router import MetisModelRouter, RoutableProvider
from metis_core.llm.routing_config import RoutingConfig


class ModelProfile(StrEnum):
    LOCAL = "local"  # CPU Ollama, non-external
    CLOUD = "cloud"  # hosted provider + local fallback
    GPU = "gpu"  # local vLLM, non-external


def is_external_capable(profile: ModelProfile) -> bool:
    """Only the cloud profile may reach an external provider (for non-restricted data)."""
    return profile is ModelProfile.CLOUD


def build_providers(
    profile: ModelProfile,
    *,
    local_provider: RoutableProvider | None = None,
    cloud_provider: RoutableProvider | None = None,
) -> tuple[RoutableProvider, ...]:
    """The ordered provider list for a profile (cloud preferred, local fallback for cloud)."""
    local = local_provider if local_provider is not None else StubProvider()
    if profile is ModelProfile.CLOUD:
        if cloud_provider is None:
            raise ValueError("the cloud profile requires a cloud provider")
        return (cloud_provider, local)  # external first, local fallback
    return (local,)  # local / gpu: no external provider exists in this profile


def build_router(
    profile: ModelProfile,
    *,
    local_provider: RoutableProvider | None = None,
    cloud_provider: RoutableProvider | None = None,
    config: RoutingConfig | None = None,
) -> MetisModelRouter:
    """A Stage 4 router wired for ``profile`` (restricted-data routing holds in every profile)."""
    providers = build_providers(
        profile, local_provider=local_provider, cloud_provider=cloud_provider
    )
    return MetisModelRouter(providers, config=config)
