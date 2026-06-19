"""workspace_access_decision: no membership denies; viewers/auditors are read-only."""

from __future__ import annotations

import pytest

from metis_core.policy import workspace_access_decision
from metis_protocol import Role


def test_no_membership_denies_read() -> None:
    assert not workspace_access_decision(None).allowed


def test_no_membership_denies_write() -> None:
    assert not workspace_access_decision(None, require_write=True).allowed


@pytest.mark.parametrize("role", list(Role))
def test_any_member_may_read(role: Role) -> None:
    assert workspace_access_decision(role).allowed


@pytest.mark.parametrize(
    ("role", "allowed"),
    [
        (Role.AUDITOR, False),
        (Role.VIEWER, False),
        (Role.MEMBER, True),
        (Role.ADMIN, True),
        (Role.OWNER, True),
    ],
)
def test_write_requires_writer_role(role: Role, allowed: bool) -> None:
    assert workspace_access_decision(role, require_write=True).allowed is allowed


@pytest.mark.parametrize(
    ("role", "allowed"),
    [
        (Role.AUDITOR, False),
        (Role.VIEWER, False),
        (Role.MEMBER, False),
        (Role.ADMIN, True),
        (Role.OWNER, True),
    ],
)
def test_admin_requires_admin_role(role: Role, allowed: bool) -> None:
    assert workspace_access_decision(role, require_admin=True).allowed is allowed
