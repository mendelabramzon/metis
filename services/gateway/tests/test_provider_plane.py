"""The configurable provider plane: cloud-first routing with a policy-bound local fallback.

``assemble_chat_providers`` builds the ordered provider list the ``MetisModelRouter`` routes over.
The clients are never called here — only routing decisions (which provider, external or not) are
checked — so no API keys or network are needed; dummy client objects suffice.
"""

from __future__ import annotations

from typing import Any

from metis_core.llm import MetisModelRouter, RoutableProvider
from metis_gateway.models import ModelPlane, SpendTracker, assemble_chat_providers
from metis_gateway.settings import GatewaySettings
from metis_protocol import AuditEvent, ModelRequest, ModelTaskClass, Sensitivity

_LOCAL = "http://localhost:11434"


class _Sink:
    async def emit(self, event: AuditEvent) -> None:  # pragma: no cover - not exercised
        return None


def _plane(providers: tuple[RoutableProvider, ...]) -> ModelPlane:
    return ModelPlane(
        providers=providers, spend=SpendTracker(_Sink()), local_client=None, closers=()
    )


def _router(
    settings: GatewaySettings, *, anthropic: bool, openai: bool, local: bool
) -> MetisModelRouter:
    dummy: Any = object()  # the router inspects tier/externality only, never calls the client
    providers = assemble_chat_providers(
        settings,
        anthropic_client=dummy if anthropic else None,
        openai_client=dummy if openai else None,
        local_client=dummy if local else None,
    )
    return MetisModelRouter(providers)


def _route(
    router: MetisModelRouter, task: ModelTaskClass, sensitivity: Sensitivity
) -> RoutableProvider:
    return router.route(ModelRequest(task_class=task, messages=(), sensitivity=sensitivity))


def test_nonrestricted_upper_tier_prefers_cloud() -> None:
    settings = GatewaySettings(anthropic_api_key="k", model_endpoint=_LOCAL)
    router = _router(settings, anthropic=True, openai=False, local=True)
    # QUERY_ANSWER is a FRONTIER task; internal data -> the cloud provider (first), not local.
    provider = _route(router, ModelTaskClass.QUERY_ANSWER, Sensitivity.INTERNAL)
    assert provider.is_external is True
    assert provider.name == "anthropic"


def test_restricted_data_routes_local() -> None:
    settings = GatewaySettings(anthropic_api_key="k", model_endpoint=_LOCAL)
    router = _router(settings, anthropic=True, openai=False, local=True)
    provider = _route(router, ModelTaskClass.QUERY_ANSWER, Sensitivity.RESTRICTED)
    assert provider.is_external is False
    assert provider.name == "ollama"


def test_local_tier_routes_local_even_with_cloud() -> None:
    settings = GatewaySettings(anthropic_api_key="k", model_endpoint=_LOCAL)
    router = _router(settings, anthropic=True, openai=False, local=True)
    # QUERY_REWRITE is a LOCAL task; the cloud provider doesn't serve LOCAL -> local.
    provider = _route(router, ModelTaskClass.QUERY_REWRITE, Sensitivity.INTERNAL)
    assert provider.is_external is False
    assert provider.name == "ollama"


def test_openai_compatible_cloud_assembles() -> None:
    settings = GatewaySettings(openai_api_key="k")
    router = _router(settings, anthropic=False, openai=True, local=False)
    provider = _route(router, ModelTaskClass.QUERY_ANSWER, Sensitivity.INTERNAL)
    assert provider.is_external is True
    assert provider.name == "openai"


def test_no_providers_without_config() -> None:
    providers = assemble_chat_providers(
        GatewaySettings(), anthropic_client=None, openai_client=None, local_client=None
    )
    assert providers == []


def test_local_only_policy_drops_external_providers() -> None:
    settings = GatewaySettings(openai_api_key="k", model_endpoint=_LOCAL)
    dummy: Any = object()
    providers = assemble_chat_providers(
        settings, anthropic_client=None, openai_client=dummy, local_client=dummy
    )
    # providers[0] is the external OpenAI provider, providers[1] the local Ollama one.
    assert providers[0].is_external is True
    assert providers[1].is_external is False

    plane = _plane(tuple(providers))
    assert plane.make_caller(allow_external=True) is not None  # both providers
    assert plane.make_caller(allow_external=False) is not None  # local survives

    # A workspace forbidding external models, with only an external provider available, gets no
    # caller at all — it can never reach the cloud.
    external_only = _plane((providers[0],))
    assert external_only.make_caller(allow_external=False) is None
