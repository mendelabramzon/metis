"""Build Foresight objects: an expected future state, a validity window, and its evidence.

The caller owns the validity window (``valid_from``/``valid_to``) — those are policy/temporal
decisions, and tying expiry to the maintainer's refresh cadence is a Stage 6 concern. This
builder interprets *what* is expected from the supporting claims (task class
``build_foresight``), with a deterministic, evidence-only fallback when no model is wired.
Every Foresight carries the claim refs it rests on, so a prediction always traces to evidence.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from metis_core import propagate_policy
from metis_core.llm import ModelCaller
from metis_maintainer.memory._build import maintainer_provenance, now_utc, stable_id
from metis_maintainer.memory.prompts import ForesightDraft
from metis_protocol import (
    Claim,
    ClaimRef,
    Foresight,
    ForesightId,
    ForesightStatus,
    ModelTaskClass,
    Sensitivity,
    WorkspaceId,
)


class ForesightBuilder:
    def __init__(self, *, caller: ModelCaller | None = None) -> None:
        self._caller = caller

    async def build(
        self,
        *,
        claims: Sequence[Claim],
        valid_from: datetime,
        valid_to: datetime,
    ) -> Foresight:
        if not claims:
            raise ValueError("cannot build a Foresight without supporting claims")
        workspace_id = claims[0].provenance.workspace_id
        policy = propagate_policy([claim.policy for claim in claims])
        draft = await self._draft(workspace_id, claims, policy.sensitivity)
        return Foresight(
            id=stable_id(
                ForesightId,
                f"{workspace_id}:{valid_from.isoformat()}:"
                + "|".join(sorted(str(claim.id) for claim in claims)),
            ),
            provenance=maintainer_provenance(
                workspace_id,
                agent="foresight-builder",
                operation="build_foresight",
                inputs=[str(claim.id) for claim in claims],
            ),
            policy=policy,
            created_at=now_utc(),
            statement=draft.statement,
            predicted_state=draft.predicted_state,
            valid_from=valid_from,
            valid_to=valid_to,
            status=ForesightStatus.ACTIVE,
            claims=tuple(ClaimRef(claim_id=claim.id) for claim in claims),
            confidence=draft.confidence,
        )

    async def _draft(
        self, workspace_id: WorkspaceId, claims: Sequence[Claim], sensitivity: Sensitivity
    ) -> ForesightDraft:
        if self._caller is None:
            return _deterministic_foresight(claims)
        return await self._caller.call_structured(
            task_class=ModelTaskClass.BUILD_FORESIGHT,
            workspace_id=workspace_id,
            user_content="Evidence:\n" + "\n".join(f"- {claim.text}" for claim in claims),
            output_type=ForesightDraft,
            sensitivity=sensitivity,
        )


def _deterministic_foresight(claims: Sequence[Claim]) -> ForesightDraft:
    lead = claims[0].text
    state = "_".join(lead.lower().split()[:3]) or "expected_state"
    confidence = sum(claim.confidence for claim in claims) / len(claims)
    return ForesightDraft(
        statement=f"Expected, based on current evidence: {lead}",
        predicted_state=state,
        confidence=confidence,
    )
