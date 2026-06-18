"""Routing policy: restricted data never selects a cloud provider; tiers select correctly.

Pure tests — the allowlist is enforced from task class + sensitivity, before any prompt.
"""

import pytest

from metis_core.llm import (
    AnthropicProvider,
    MetisModelRouter,
    NoEligibleProviderError,
    StubProvider,
    task_tier,
)
from metis_protocol import ModelRequest, ModelTaskClass, ModelTier, Sensitivity


def _request(task: ModelTaskClass, sensitivity: Sensitivity) -> ModelRequest:
    return ModelRequest(task_class=task, messages=(), sensitivity=sensitivity)


def _router() -> MetisModelRouter:
    # Cloud preferred, local fallback.
    return MetisModelRouter([AnthropicProvider(client=None, name="anthropic"), StubProvider()])


@pytest.mark.parametrize(
    ("sensitivity", "expected"),
    [
        (Sensitivity.PUBLIC, "anthropic"),
        (Sensitivity.INTERNAL, "anthropic"),
        (Sensitivity.CONFIDENTIAL, "anthropic"),
        (Sensitivity.RESTRICTED, "stub-local"),
    ],
)
def test_restricted_data_routes_to_local(sensitivity: Sensitivity, expected: str) -> None:
    chosen = _router().route(_request(ModelTaskClass.EXTRACT_CLAIMS, sensitivity))
    assert chosen.name == expected


def test_local_tier_task_uses_local_provider() -> None:
    # PARSE_ASSIST is a LOCAL-tier task; the cloud provider doesn't serve LOCAL.
    chosen = _router().route(_request(ModelTaskClass.PARSE_ASSIST, Sensitivity.PUBLIC))
    assert chosen.name == "stub-local"


def test_no_eligible_provider_raises() -> None:
    router = MetisModelRouter([AnthropicProvider(client=None)])
    with pytest.raises(NoEligibleProviderError):
        router.route(_request(ModelTaskClass.EXTRACT_CLAIMS, Sensitivity.RESTRICTED))


def test_task_tier_mapping() -> None:
    assert task_tier(ModelTaskClass.SEGMENT) == ModelTier.LOCAL
    assert task_tier(ModelTaskClass.EXTRACT_CLAIMS) == ModelTier.STANDARD
    assert task_tier(ModelTaskClass.QUERY_ANSWER) == ModelTier.FRONTIER
