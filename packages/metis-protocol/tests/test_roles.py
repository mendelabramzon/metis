"""Role capability predicates: any membership reads; member+ writes; admin+ administers."""

from __future__ import annotations

import pytest

from metis_protocol import Role, role_can_admin, role_can_read, role_can_write


@pytest.mark.parametrize("role", list(Role))
def test_every_role_can_read(role: Role) -> None:
    assert role_can_read(role)


@pytest.mark.parametrize(
    ("role", "can_write"),
    [
        (Role.AUDITOR, False),
        (Role.VIEWER, False),
        (Role.MEMBER, True),
        (Role.ADMIN, True),
        (Role.OWNER, True),
    ],
)
def test_write_roles(role: Role, can_write: bool) -> None:
    assert role_can_write(role) is can_write


@pytest.mark.parametrize(
    ("role", "can_admin"),
    [
        (Role.AUDITOR, False),
        (Role.VIEWER, False),
        (Role.MEMBER, False),
        (Role.ADMIN, True),
        (Role.OWNER, True),
    ],
)
def test_admin_roles(role: Role, can_admin: bool) -> None:
    assert role_can_admin(role) is can_admin
