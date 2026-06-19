"""Human-approval queue for outbound/destructive skill runs (approval-by-default).

A run that needs approval (manifest ``requires_approval`` or an ``outbound_action`` permission)
is held: the runner submits a request and returns ``NEEDS_APPROVAL`` instead of executing. A
human approves the request key, then the same run proceeds. The request key is a stable hash of
the skill + arguments, so re-submitting the same unit of work is idempotent.

The queue is an async ``ApprovalQueue`` so it may be durable: ``InMemoryApprovalQueue`` is the
in-process default (the dev backend, and the runner when none is injected); the gateway injects a
Postgres-backed queue on the server so held approvals survive a restart.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Protocol, runtime_checkable

from metis_protocol import SkillInput


class SkillApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(frozen=True)
class ApprovalRequest:
    key: str
    skill_name: str
    skill_version: str
    status: SkillApprovalStatus = SkillApprovalStatus.PENDING


def approval_key(skill_input: SkillInput) -> str:
    """A stable key for one unit of work (skill + version + canonical arguments)."""
    canonical = json.dumps(skill_input.arguments, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(
        f"{skill_input.skill_name}\0{skill_input.skill_version}\0{canonical}".encode()
    ).hexdigest()[:32]
    return digest


@runtime_checkable
class ApprovalQueue(Protocol):
    """The approval gate the runner and agent consult — in-memory or durable, hence async."""

    async def submit(self, skill_input: SkillInput) -> ApprovalRequest: ...

    async def is_approved(self, skill_input: SkillInput) -> bool: ...

    async def approve(self, key: str) -> None: ...

    async def reject(self, key: str) -> None: ...

    async def pending(self) -> Sequence[ApprovalRequest]: ...


class InMemoryApprovalQueue:
    """In-process approval queue (the default; the durable sibling persists to Postgres)."""

    def __init__(self) -> None:
        self._requests: dict[str, ApprovalRequest] = {}

    async def submit(self, skill_input: SkillInput) -> ApprovalRequest:
        key = approval_key(skill_input)
        return self._requests.setdefault(
            key,
            ApprovalRequest(
                key=key,
                skill_name=skill_input.skill_name,
                skill_version=skill_input.skill_version,
            ),
        )

    async def is_approved(self, skill_input: SkillInput) -> bool:
        request = self._requests.get(approval_key(skill_input))
        return request is not None and request.status is SkillApprovalStatus.APPROVED

    async def approve(self, key: str) -> None:
        self._set(key, SkillApprovalStatus.APPROVED)

    async def reject(self, key: str) -> None:
        self._set(key, SkillApprovalStatus.REJECTED)

    async def pending(self) -> Sequence[ApprovalRequest]:
        return [r for r in self._requests.values() if r.status is SkillApprovalStatus.PENDING]

    def _set(self, key: str, status: SkillApprovalStatus) -> None:
        existing = self._requests.get(key)
        if existing is not None:
            self._requests[key] = replace(existing, status=status)
