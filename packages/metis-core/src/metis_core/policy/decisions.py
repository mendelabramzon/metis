"""Deterministic policy decisions — pure functions, no LLM and no I/O.

Policy is enforced outside prompts (guiding principle 6). These functions answer:
may this data use this provider, may this skill run on this data, is egress allowed,
and how does sensitivity propagate to a derived artifact.
"""

from __future__ import annotations

from collections.abc import Sequence

from metis_protocol import (
    ModelTier,
    PermissionScope,
    PolicyDecision,
    PolicyState,
    Role,
    Sensitivity,
    SkillManifest,
    max_sensitivity,
    role_can_admin,
    role_can_write,
    sensitivity_rank,
)


def route_decision(
    policy: PolicyState, *, tier: ModelTier, provider_is_external: bool
) -> PolicyDecision:
    """Whether data under ``policy`` may be sent to a provider of this tier/externality."""
    if provider_is_external and not policy.allow_external_models:
        return PolicyDecision.deny("external models are not allowed for this data")
    if provider_is_external and sensitivity_rank(policy.sensitivity) >= sensitivity_rank(
        Sensitivity.RESTRICTED
    ):
        return PolicyDecision.deny("restricted data must use a local provider")
    return PolicyDecision.allow(f"permitted for tier {tier.value}")


def skill_access_decision(manifest: SkillManifest, policy: PolicyState) -> PolicyDecision:
    """Whether a skill may run against data under ``policy`` (sensitivity ceiling)."""
    if sensitivity_rank(policy.sensitivity) > sensitivity_rank(manifest.sensitivity_ceiling):
        return PolicyDecision.deny("data sensitivity exceeds the skill's ceiling")
    return PolicyDecision(
        allowed=True,
        reason="within the skill's sensitivity ceiling",
        required_scopes=tuple(manifest.permissions),
    )


def egress_decision(manifest: SkillManifest) -> PolicyDecision:
    """Whether a skill is permitted outbound network egress."""
    if manifest.network or PermissionScope.NETWORK in manifest.permissions:
        return PolicyDecision(
            allowed=True,
            reason="network egress permitted by manifest",
            required_scopes=(PermissionScope.NETWORK,),
        )
    return PolicyDecision.deny("no network egress permission in manifest")


def propagate_policy(parents: Sequence[PolicyState]) -> PolicyState:
    """Policy a derived artifact inherits: most-restrictive sensitivity, AND of
    external-model allowance, OR of legal hold, union of tags."""
    if not parents:
        return PolicyState()
    return PolicyState(
        sensitivity=max_sensitivity(*(p.sensitivity for p in parents)),
        allow_external_models=all(p.allow_external_models for p in parents),
        legal_hold=any(p.legal_hold for p in parents),
        tags=tuple(sorted({tag for parent in parents for tag in parent.tags})),
    )


def workspace_access_decision(
    role: Role | None, *, require_write: bool = False, require_admin: bool = False
) -> PolicyDecision:
    """Whether a caller holding ``role`` may access a workspace.

    ``role is None`` means no membership — the isolation gate, and a hard deny: this is what
    keeps one user's personal workspace invisible to another. Any membership grants read; writes
    require a writer role (member/admin/owner), and administering membership/settings requires
    admin/owner. The caller resolves ``role`` from ``IdentityStore.resolve_role`` before access.
    """
    if role is None:
        return PolicyDecision.deny("no membership in this workspace")
    if require_admin and not role_can_admin(role):
        return PolicyDecision.deny(f"role {role.value} cannot administer this workspace")
    if require_write and not role_can_write(role):
        return PolicyDecision.deny(f"role {role.value} is read-only in this workspace")
    return PolicyDecision.allow(f"role {role.value} permits this access")
