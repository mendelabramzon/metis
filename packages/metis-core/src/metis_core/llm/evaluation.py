"""Extraction-evaluation seed: compare providers/models on a document fixture.

Stage 13 promotes this to the ``eval/`` workspace member. It reports schema-validity,
claim count, cost, and latency per provider so model/provider choices are comparable;
CI runs it with deterministic stub providers (no live calls).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from metis_core.llm.errors import ModelError, StructuredOutputError
from metis_core.llm.router import RoutableProvider
from metis_core.llm.structured import parse_structured, schema_for
from metis_protocol import ExtractionBatch, ModelMessage, ModelRequest, ModelTaskClass, Sensitivity


@dataclass(frozen=True)
class ExtractionEvalResult:
    provider: str
    schema_valid: bool
    claim_count: int
    cost_usd: float | None
    latency_ms: float | None
    error: str | None = None


async def evaluate_extraction(
    provider: RoutableProvider,
    *,
    document_text: str,
    sensitivity: Sensitivity = Sensitivity.INTERNAL,
) -> ExtractionEvalResult:
    request = ModelRequest(
        task_class=ModelTaskClass.EXTRACT_CLAIMS,
        messages=(ModelMessage(role="user", content=document_text),),
        sensitivity=sensitivity,
        response_schema=schema_for(ExtractionBatch),
        max_tokens=4096,
    )
    try:
        response = await provider.generate(request)
    except ModelError as exc:
        return ExtractionEvalResult(provider.name, False, 0, None, None, str(exc))

    run = response.model_run
    try:
        batch = parse_structured(response, ExtractionBatch)
    except StructuredOutputError as exc:
        return ExtractionEvalResult(provider.name, False, 0, run.cost_usd, run.latency_ms, str(exc))
    return ExtractionEvalResult(
        provider=provider.name,
        schema_valid=True,
        claim_count=len(batch.claims),
        cost_usd=run.cost_usd,
        latency_ms=run.latency_ms,
    )


async def compare_providers(
    providers: Sequence[RoutableProvider],
    *,
    document_text: str,
) -> list[ExtractionEvalResult]:
    return [await evaluate_extraction(p, document_text=document_text) for p in providers]
