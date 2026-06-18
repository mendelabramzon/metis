"""Translate a skill manifest into an enforceable policy envelope — deny-by-default.

The manifest is the security contract: anything not declared is denied. This wraps it in
predicates the runner and sandbox consult, and reuses the Stage 2 deterministic policy helpers
(``skill_access_decision`` for the sensitivity ceiling, ``egress_decision`` for network). A
missing declaration fails closed; it never defaults open.
"""

from __future__ import annotations

from dataclasses import dataclass

from metis_core import egress_decision, skill_access_decision
from metis_protocol import (
    PermissionScope,
    PolicyDecision,
    PolicyState,
    Sensitivity,
    SkillManifest,
    sensitivity_rank,
)


@dataclass(frozen=True)
class SkillPolicy:
    """Predicates over a manifest's declared permissions (everything else is denied)."""

    manifest: SkillManifest

    def allows_connector(self, name: str) -> bool:
        return name in self.manifest.allowed_connectors

    def allows_network(self) -> bool:
        return egress_decision(self.manifest).allowed

    def allows_secrets(self) -> bool:
        return PermissionScope.SECRETS in self.manifest.permissions

    def within_sensitivity(self, sensitivity: Sensitivity) -> bool:
        return sensitivity_rank(sensitivity) <= sensitivity_rank(self.manifest.sensitivity_ceiling)

    def needs_approval(self) -> bool:
        # Outbound/destructive capability always needs approval, regardless of the flag.
        return (
            self.manifest.requires_approval
            or PermissionScope.OUTBOUND_ACTION in self.manifest.permissions
        )

    def can_run_on(self, sensitivity: Sensitivity) -> PolicyDecision:
        """Whether the skill may run against data of this sensitivity (Stage 2 helper)."""
        return skill_access_decision(self.manifest, PolicyState(sensitivity=sensitivity))
