"""Deterministic policy decisions — table-driven, no LLM and no database."""

import pytest

from metis_core.policy import (
    egress_decision,
    propagate_policy,
    route_decision,
    skill_access_decision,
)
from metis_protocol import (
    ModelTier,
    PermissionScope,
    PolicyState,
    Sensitivity,
    SkillManifest,
)


@pytest.mark.parametrize(
    ("sensitivity", "external", "allowed"),
    [
        (Sensitivity.PUBLIC, True, True),
        (Sensitivity.INTERNAL, True, True),
        (Sensitivity.CONFIDENTIAL, True, True),
        (Sensitivity.RESTRICTED, True, False),
        (Sensitivity.RESTRICTED, False, True),
    ],
)
def test_route_decision_by_sensitivity(
    sensitivity: Sensitivity, external: bool, allowed: bool
) -> None:
    policy = PolicyState(sensitivity=sensitivity)
    decision = route_decision(policy, tier=ModelTier.STANDARD, provider_is_external=external)
    assert decision.allowed is allowed


def test_route_blocks_external_when_data_disallows_it() -> None:
    policy = PolicyState(sensitivity=Sensitivity.PUBLIC, allow_external_models=False)
    assert not route_decision(policy, tier=ModelTier.FRONTIER, provider_is_external=True).allowed


def test_skill_access_respects_sensitivity_ceiling() -> None:
    manifest = SkillManifest(name="s", version="1", sensitivity_ceiling=Sensitivity.INTERNAL)
    assert skill_access_decision(manifest, PolicyState(sensitivity=Sensitivity.INTERNAL)).allowed
    assert not skill_access_decision(
        manifest, PolicyState(sensitivity=Sensitivity.RESTRICTED)
    ).allowed


def test_egress_decision() -> None:
    networked = SkillManifest(name="s", version="1", network=True)
    allowed = egress_decision(networked)
    assert allowed.allowed
    assert PermissionScope.NETWORK in allowed.required_scopes
    assert not egress_decision(SkillManifest(name="s", version="1", network=False)).allowed


def test_propagate_policy_takes_most_restrictive() -> None:
    derived = propagate_policy(
        [
            PolicyState(sensitivity=Sensitivity.PUBLIC, tags=("a",)),
            PolicyState(
                sensitivity=Sensitivity.RESTRICTED,
                allow_external_models=False,
                legal_hold=True,
                tags=("b",),
            ),
        ]
    )
    assert derived.sensitivity == Sensitivity.RESTRICTED
    assert derived.allow_external_models is False
    assert derived.legal_hold is True
    assert derived.tags == ("a", "b")
