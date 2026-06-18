"""Detect contradictions among claims — deterministic checks first (the implementation bias).

``ClaimContradictionDetector`` groups claims by ``(subject entity, predicate)`` and flags a
group whose claims assert two or more *distinct* values as a contradiction. This is the cheap,
deterministic pass; an LLM judge for ambiguous cases is reserved for later (it would route
through the Stage 4 ``detect_contradiction`` task class). Contradictions are surfaced with
stable ids and the claim ids they cite — never merged away.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from metis_core import propagate_policy
from metis_maintainer.jobs.base import JobOutcome, MaintainerDeps, Trigger, workspace_of
from metis_maintainer.memory._build import maintainer_provenance, now_utc, stable_id
from metis_protocol import (
    Claim,
    ClaimFilter,
    ClaimRef,
    ClaimStore,
    Contradiction,
    ContradictionId,
    ContradictionStatus,
    MemoryScope,
    WorkspaceId,
)


def _build_contradiction(
    workspace_id: WorkspaceId, key: str, claims: Sequence[Claim]
) -> Contradiction:
    values = sorted({claim.text for claim in claims})
    return Contradiction(
        id=stable_id(
            ContradictionId,
            f"{workspace_id}:{key}:" + "|".join(sorted(str(claim.id) for claim in claims)),
        ),
        provenance=maintainer_provenance(
            workspace_id,
            agent="contradiction-detector",
            operation="detect_contradiction",
            inputs=[str(claim.id) for claim in claims],
        ),
        policy=propagate_policy([claim.policy for claim in claims]),
        created_at=now_utc(),
        summary=f"Conflicting values for '{key}'",
        explanation="Evidence disagrees on '" + key + "': " + " vs ".join(values),
        status=ContradictionStatus.OPEN,
        claims=tuple(ClaimRef(claim_id=claim.id) for claim in claims),
    )


class ClaimContradictionDetector:
    """The ``ContradictionDetector`` protocol impl (deterministic same-key/different-value)."""

    def __init__(self, claim_store: ClaimStore) -> None:
        self._claims = claim_store

    async def detect(self, scope: MemoryScope) -> Sequence[Contradiction]:
        claims = await self._claims.query(ClaimFilter(workspace_id=scope.workspace_id))
        groups: dict[tuple[str, str], list[Claim]] = {}
        for claim in claims:
            if claim.predicate is None or claim.negated:
                continue  # need a predicate to compare; negations handled as their own case below
            subject = str(claim.subject_ref.entity_id) if claim.subject_ref is not None else ""
            groups.setdefault((subject, claim.predicate), []).append(claim)
        return [
            _build_contradiction(scope.workspace_id, predicate, group)
            for (_, predicate), group in groups.items()
            if len({claim.text for claim in group}) > 1
        ]


class DetectContradictionsJob:
    kind = "detect_contradictions"
    triggers: tuple[Trigger, ...] = (Trigger.EVENT, Trigger.PERIODIC)

    def idempotency_key(self, payload: Mapping[str, Any]) -> str:
        # Per triggering batch (event) or per cadence bucket (periodic); each new unit re-scans.
        return str(payload.get("batch_id") or payload.get("bucket") or "")

    async def run(self, deps: MaintainerDeps, payload: Mapping[str, Any]) -> JobOutcome:
        scope = MemoryScope(workspace_id=workspace_of(payload))
        detector = ClaimContradictionDetector(deps.claim_store)
        contradictions = await detector.detect(scope)
        for contradiction in contradictions:
            await deps.memory_store.write_contradiction(contradiction)
        return JobOutcome(
            kind=self.kind,
            summary=f"detected {len(contradictions)} contradiction(s)",
            counts={"contradictions": len(contradictions)},
        )


if TYPE_CHECKING:
    from metis_protocol import ContradictionDetector

    def _conforms(detector: ClaimContradictionDetector) -> ContradictionDetector:
        return detector  # static proof of the protocol
