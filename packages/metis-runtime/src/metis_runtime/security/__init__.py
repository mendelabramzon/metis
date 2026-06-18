"""Runtime security hardening (Stage 14): injection defense, taint enforcement, sandbox profiles.

The runtime half of the hardening: untrusted retrieved content is fenced as data (injection
defense), the Stage 10 taint boundary is enforced through one chokepoint, and skills are assigned an
isolation profile by trust tier. The durable-substrate half (secrets, audit integrity, deletion,
backup) lives in ``metis-core``.
"""

from __future__ import annotations

from metis_runtime.security.injection_defense import (
    InjectionFindings,
    fence_untrusted,
    render_untrusted,
    scan,
)
from metis_runtime.security.sandbox_harden import (
    IsolationProfile,
    IsolationTier,
    SkillTrust,
    select_profile,
)
from metis_runtime.security.taint import TaintBoundary

__all__ = [
    "InjectionFindings",
    "IsolationProfile",
    "IsolationTier",
    "SkillTrust",
    "TaintBoundary",
    "fence_untrusted",
    "render_untrusted",
    "scan",
    "select_profile",
]
