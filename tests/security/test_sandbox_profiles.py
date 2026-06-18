"""Isolation hardens by trust tier; an untrusted skill is denied egress regardless of manifest."""

from __future__ import annotations

from metis_protocol import PermissionScope, SkillManifest
from metis_runtime.security import IsolationTier, SkillTrust, select_profile


def _manifest(**kwargs: object) -> SkillManifest:
    return SkillManifest(name="x", version="1", **kwargs)  # type: ignore[arg-type]


def test_first_party_uses_subprocess_and_honors_manifest() -> None:
    profile = select_profile(_manifest(network=True), trust=SkillTrust.FIRST_PARTY)
    assert profile.tier is IsolationTier.SUBPROCESS
    assert profile.network is True
    assert profile.drop_capabilities is False


def test_third_party_is_containerized_with_dropped_caps() -> None:
    profile = select_profile(_manifest(network=True), trust=SkillTrust.THIRD_PARTY)
    assert profile.tier is IsolationTier.CONTAINER
    assert profile.drop_capabilities is True


def test_untrusted_denies_network_regardless_of_manifest() -> None:
    profile = select_profile(
        _manifest(network=True, permissions=(PermissionScope.NETWORK,)),
        trust=SkillTrust.UNTRUSTED,
    )
    assert profile.tier is IsolationTier.GVISOR
    assert profile.network is False  # the skill cannot grant itself egress
    assert profile.filesystem_write is False
    assert profile.drop_capabilities is True
