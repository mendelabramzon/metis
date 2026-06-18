"""Policy vocabulary: the attributes carried by artifacts and the shape of a
policy decision. Enforcement lives outside prompts (in core/runtime); this module
defines the *vocabulary* and the pure helpers for reasoning about sensitivity.
"""

from __future__ import annotations

from typing import Self

from metis_protocol.base import ProtocolModel
from metis_protocol.enums import SENSITIVITY_ORDER, PermissionScope, Sensitivity


def sensitivity_rank(value: Sensitivity) -> int:
    """Ordinal rank (0 = least restrictive)."""
    return SENSITIVITY_ORDER.index(value)


def max_sensitivity(*values: Sensitivity) -> Sensitivity:
    """The most restrictive of the given sensitivities (``PUBLIC`` if none)."""
    return max(values, key=sensitivity_rank, default=Sensitivity.PUBLIC)


def is_at_least(value: Sensitivity, floor: Sensitivity) -> bool:
    """True if ``value`` is at least as restrictive as ``floor``."""
    return sensitivity_rank(value) >= sensitivity_rank(floor)


class PolicyState(ProtocolModel):
    """Policy attributes carried by every artifact and propagated to derivations."""

    sensitivity: Sensitivity = Sensitivity.INTERNAL
    tags: tuple[str, ...] = ()
    allow_external_models: bool = True  # restricted data sets this False
    legal_hold: bool = False


class PolicyDecision(ProtocolModel):
    """The pure result of a policy check (computed outside prompts)."""

    allowed: bool
    reason: str = ""
    obligations: tuple[str, ...] = ()
    required_scopes: tuple[PermissionScope, ...] = ()

    @classmethod
    def allow(cls, reason: str = "") -> Self:
        return cls(allowed=True, reason=reason)

    @classmethod
    def deny(cls, reason: str) -> Self:
        return cls(allowed=False, reason=reason)
