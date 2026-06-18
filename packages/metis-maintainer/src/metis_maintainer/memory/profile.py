"""Build Profile objects (stable workspace/user/company/person facts) with conflict tracking.

Profiles are derived deterministically, not by an LLM judge: facts are keyed by claim
predicate, and when one key carries two or more *distinct* values the builder keeps every
value as its own fact flagged ``conflicting=True`` and emits an explicit
:class:`~metis_protocol.Contradiction`. Conflicting evidence is therefore surfaced, never
silently merged into one "winning" value. Deciding which value is correct (or whether two
phrasings are really the same fact) is deferred to the Stage 6 contradiction detector — here
we keep the conflict visible. Claims without a predicate each become their own fact, so
unrelated statements never look like a conflict.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from metis_core import propagate_policy
from metis_maintainer.memory._build import maintainer_provenance, now_utc, stable_id
from metis_protocol import (
    Claim,
    ClaimRef,
    Contradiction,
    ContradictionId,
    ContradictionStatus,
    EntityRef,
    Profile,
    ProfileFact,
    ProfileId,
    ProfileScope,
    WorkspaceId,
)


@dataclass(frozen=True)
class ProfileResult:
    """A profile plus any conflicts found while building it (both surfaced, never merged)."""

    profile: Profile
    contradictions: tuple[Contradiction, ...]


class ProfileBuilder:
    def build(
        self,
        *,
        scope: ProfileScope,
        label: str,
        claims: Sequence[Claim],
        subject: EntityRef | None = None,
    ) -> ProfileResult:
        if not claims:
            raise ValueError("cannot build a Profile from no claims")
        workspace_id = claims[0].provenance.workspace_id

        grouped: dict[str, list[Claim]] = {}
        for claim in claims:
            key = claim.predicate if claim.predicate else f"_claim:{claim.id}"
            grouped.setdefault(key, []).append(claim)

        facts: list[ProfileFact] = []
        contradictions: list[Contradiction] = []
        for key, group in grouped.items():
            display = key if not key.startswith("_claim:") else "fact"
            by_value: dict[str, list[Claim]] = {}
            for claim in group:
                by_value.setdefault(claim.text, []).append(claim)
            conflicting = len(by_value) > 1
            for value, supporters in by_value.items():
                facts.append(
                    ProfileFact(
                        key=display,
                        value=value,
                        claims=tuple(ClaimRef(claim_id=claim.id) for claim in supporters),
                        confidence=sum(claim.confidence for claim in supporters) / len(supporters),
                        conflicting=conflicting,
                    )
                )
            if conflicting:
                contradictions.append(_contradiction(workspace_id, display, group))

        policy = propagate_policy([claim.policy for claim in claims])
        profile = Profile(
            id=stable_id(ProfileId, f"{workspace_id}:{scope.value}:{label}"),
            provenance=maintainer_provenance(
                workspace_id,
                agent="profile-builder",
                operation="consolidate_memory",
                inputs=[str(claim.id) for claim in claims],
            ),
            policy=policy,
            created_at=now_utc(),
            scope=scope,
            label=label,
            subject=subject,
            facts=tuple(facts),
        )
        return ProfileResult(profile=profile, contradictions=tuple(contradictions))


def _contradiction(workspace_id: WorkspaceId, key: str, claims: Sequence[Claim]) -> Contradiction:
    values = sorted({claim.text for claim in claims})
    return Contradiction(
        id=stable_id(
            ContradictionId,
            f"{workspace_id}:{key}:" + "|".join(sorted(str(claim.id) for claim in claims)),
        ),
        provenance=maintainer_provenance(
            workspace_id,
            agent="profile-builder",
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
