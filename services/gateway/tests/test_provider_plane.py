"""The configurable provider plane: cloud-first routing with a policy-bound local fallback.

``assemble_chat_providers`` builds the ordered provider list the ``MetisModelRouter`` routes over.
The clients are never called here — only routing decisions (which provider, external or not) are
checked — so no API keys or network are needed; dummy client objects suffice.
"""

from __future__ import annotations

from typing import Any

from metis_core.llm import MetisModelRouter, RoutableProvider
from metis_gateway.models import assemble_chat_providers
from metis_gateway.settings import GatewaySettings
from metis_protocol import ModelRequest, ModelTaskClass, Sensitivity

_LOCAL = "http://localhost:11434"


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
