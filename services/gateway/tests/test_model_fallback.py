"""The local-model answer path falls back to extractive generation when the model call fails."""

from __future__ import annotations

from typing import Any

from metis_core.llm import ModelError
from metis_gateway.models import FallbackAnswerGenerator
from metis_protocol import (
    ClaimId,
    ClaimRef,
    ContextBundle,
    ContextBundleId,
    ContextSection,
    QueryId,
    QueryRequest,
    WorkspaceId,
    new_id,
)


class _RaisingCaller:
    """Stands in for a model runtime that is down/refusing."""

    async def call_structured(self, **_kwargs: Any) -> Any:
        raise ModelError("model runtime unavailable")


async def test_fallback_to_extractive_on_model_error() -> None:
    generator = FallbackAnswerGenerator(caller=_RaisingCaller())
    query = QueryRequest(
        id=new_id(QueryId), workspace_id=WorkspaceId("ws_" + "3" * 32), text="who is the cto?"
    )
    bundle = ContextBundle(
        id=new_id(ContextBundleId),
        query_id=query.id,
        sections=(
            ContextSection(text="Ada is the CTO.", claims=(ClaimRef(claim_id=new_id(ClaimId)),)),
        ),
    )

    answer = await generator.generate(query, bundle, claims=[], sufficient=True)

    # The model call raised, so the deterministic extractive answer (over the bundle) is returned.
    assert answer.sufficient is True
    assert "Ada is the CTO." in answer.text
    assert answer.claims  # citations still come from the bundle
