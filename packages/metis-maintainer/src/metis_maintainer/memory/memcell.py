"""Build a MemCell (episode-like memory) from a cluster of claims and events.

Every MemCell is bound to the exact claim refs and source-span refs it was interpreted
from, so it always traces back to evidence (the Stage 5 traceability invariant) — a cell
with no source spans is a programming error and is refused. The cell's id is derived from
its input claim/event ids, so re-consolidating the same evidence is idempotent.

Summarization goes through the Stage 4 router (task class ``summarize_episode``); when no
caller is supplied a deterministic, evidence-only fallback is used, which keeps unit tests
reproducible without a model (the same seam ``BaselineExtractor`` uses for extraction).
"""

from __future__ import annotations

from collections.abc import Sequence

from metis_core import propagate_policy
from metis_core.llm import ModelCaller
from metis_maintainer.memory._build import maintainer_provenance, now_utc, stable_id
from metis_maintainer.memory.prompts import EpisodeSummary
from metis_protocol import (
    Claim,
    ClaimRef,
    Event,
    MemCell,
    MemCellId,
    MemSceneRef,
    ModelTaskClass,
    Sensitivity,
    SourceSpanRef,
    WorkspaceId,
)


class MemCellBuilder:
    def __init__(self, *, caller: ModelCaller | None = None) -> None:
        self._caller = caller  # Stage 4 seam; None -> deterministic, evidence-only summary

    async def build(
        self,
        *,
        workspace_id: WorkspaceId,
        claims: Sequence[Claim],
        events: Sequence[Event] = (),
        scene: MemSceneRef | None = None,
    ) -> MemCell:
        source_spans = _dedup_spans(claims, events)
        if not source_spans:
            raise ValueError("cannot build a MemCell without any source spans")

        policy = propagate_policy(
            [*(claim.policy for claim in claims), *(event.policy for event in events)]
        )
        summary = await self._summarize(workspace_id, claims, events, policy.sensitivity)
        occurred = [event.occurred_at for event in events if event.occurred_at is not None]

        key = "|".join(
            sorted(str(claim.id) for claim in claims) + sorted(str(event.id) for event in events)
        )
        provenance = maintainer_provenance(
            workspace_id,
            agent="memcell-builder",
            operation="summarize_episode",
            inputs=[str(claim.id) for claim in claims] + [str(event.id) for event in events],
        )
        return MemCell(
            id=stable_id(MemCellId, f"{workspace_id}:{key}"),
            provenance=provenance,
            policy=policy,
            created_at=now_utc(),
            summary=summary.summary,
            content=summary.content,
            claims=tuple(ClaimRef(claim_id=claim.id) for claim in claims),
            source_spans=source_spans,
            scene=scene,
            occurred_at=min(occurred) if occurred else None,
            salience=summary.salience,
        )

    async def _summarize(
        self,
        workspace_id: WorkspaceId,
        claims: Sequence[Claim],
        events: Sequence[Event],
        sensitivity: Sensitivity,
    ) -> EpisodeSummary:
        if self._caller is None:
            return _deterministic_summary(claims, events)
        return await self._caller.call_structured(
            task_class=ModelTaskClass.SUMMARIZE_EPISODE,
            workspace_id=workspace_id,
            user_content=_render(claims, events),
            output_type=EpisodeSummary,
            sensitivity=sensitivity,
        )


def _dedup_spans(claims: Sequence[Claim], events: Sequence[Event]) -> tuple[SourceSpanRef, ...]:
    seen: set[str] = set()
    spans: list[SourceSpanRef] = []
    span_groups = [claim.source_spans for claim in claims] + [
        event.source_spans for event in events
    ]
    for refs in span_groups:
        for ref in refs:
            if ref.source_span_id not in seen:
                seen.add(ref.source_span_id)
                spans.append(ref)
    return tuple(spans)


def _render(claims: Sequence[Claim], events: Sequence[Event]) -> str:
    lines = ["Claims:", *(f"- {claim.text}" for claim in claims)]
    if events:
        lines += ["Events:", *(f"- {event.summary}" for event in events)]
    return "\n".join(lines)


def _deterministic_summary(claims: Sequence[Claim], events: Sequence[Event]) -> EpisodeSummary:
    """Evidence-only fallback: no interpretation beyond the claim/event text itself."""
    texts = [claim.text for claim in claims] + [event.summary for event in events]
    return EpisodeSummary(summary=texts[0] if texts else "", content=" ".join(texts))
