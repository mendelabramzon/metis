"""Restricted data cannot reach a disallowed (external) model provider."""

from __future__ import annotations

import pytest

from metis_core.llm.errors import NoEligibleProviderError
from metis_core.llm.provider import AnthropicProvider, StubProvider
from metis_core.llm.router import MetisModelRouter
from metis_protocol import ModelRequest, ModelTaskClass, Sensitivity


def _request(sensitivity: Sensitivity) -> ModelRequest:
    return ModelRequest(
        task_class=ModelTaskClass.QUERY_ANSWER, messages=(), sensitivity=sensitivity
    )


def test_restricted_routes_to_local_not_cloud() -> None:
    # cloud preferred, local fallback
    router = MetisModelRouter([AnthropicProvider(client=object()), StubProvider()])

    # internal data may use the external provider...
    assert router.route(_request(Sensitivity.INTERNAL)).is_external is True

    # ...but restricted data is forced to the local provider, before any prompt is built.
    chosen = router.route(_request(Sensitivity.RESTRICTED))
    assert chosen.is_external is False
    assert chosen.name == "stub-local"


def test_restricted_with_only_cloud_is_refused() -> None:
    router = MetisModelRouter([AnthropicProvider(client=object())])
    with pytest.raises(NoEligibleProviderError):
        router.route(_request(Sensitivity.RESTRICTED))
