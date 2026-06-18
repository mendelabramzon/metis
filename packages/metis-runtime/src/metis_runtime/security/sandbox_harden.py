"""Sandbox hardening: an isolation profile per skill trust tier (the Stage 9 subprocess is tier 0).

The Stage 9 ``SubprocessSandbox`` isolates env/secrets/cwd/limits but not raw syscalls, so it is
only safe for *first-party* skills. This selects a stronger profile by trust tier: a third-party
gets a container with capabilities dropped; an untrusted skill gets an OS-isolating runtime
(gVisor/Firecracker) with network and filesystem-write denied *regardless* of what its manifest
requests — an untrusted skill does not get to grant itself egress. The profile is configuration the
runner/ops enact (the runtimes themselves are Stage 15); the selection policy is enforced here.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from metis_protocol import PermissionScope, SkillManifest


class SkillTrust(StrEnum):
    FIRST_PARTY = "first_party"
    THIRD_PARTY = "third_party"
    UNTRUSTED = "untrusted"


class IsolationTier(StrEnum):
    SUBPROCESS = "subprocess"  # Stage 9 baseline: env/cwd/limits, not syscalls
    CONTAINER = "container"  # Docker with dropped caps
    GVISOR = "gvisor"  # OS-level isolation for untrusted code


@dataclass(frozen=True)
class IsolationProfile:
    tier: IsolationTier
    network: bool
    filesystem_write: bool
    drop_capabilities: bool


def select_profile(manifest: SkillManifest, *, trust: SkillTrust) -> IsolationProfile:
    """Pick the isolation profile for a skill by its trust tier (deny-by-default as trust drops)."""
    wants_network = manifest.network or PermissionScope.NETWORK in manifest.permissions
    wants_fs_write = PermissionScope.FILESYSTEM_WRITE in manifest.permissions

    if trust is SkillTrust.FIRST_PARTY:
        return IsolationProfile(
            tier=IsolationTier.SUBPROCESS,
            network=wants_network,
            filesystem_write=wants_fs_write,
            drop_capabilities=False,
        )
    if trust is SkillTrust.THIRD_PARTY:
        return IsolationProfile(
            tier=IsolationTier.CONTAINER,
            network=wants_network,
            filesystem_write=wants_fs_write,
            drop_capabilities=True,
        )
    # UNTRUSTED: strongest isolation; deny egress and writes no matter what the manifest asks for.
    return IsolationProfile(
        tier=IsolationTier.GVISOR,
        network=False,
        filesystem_write=False,
        drop_capabilities=True,
    )
