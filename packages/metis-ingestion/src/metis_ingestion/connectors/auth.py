"""Per-connector auth configuration — it names the secrets a connector needs, never their values.

A connector declares *which* credentials it requires (an API token, a username/password pair, an
OAuth client + refresh token) as secret *names*; the values are fetched at use time through a
:class:`SecretResolver`. Keeping values out of the config means an :class:`ConnectorAuth` can be
logged, persisted, and passed around without leaking a credential. For Stage 11 the resolver is
in-process; the encrypted credential store and the OAuth refresh/expiry/revocation lifecycle are
Stage 14 — this module is the seam they slot into.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

from metis_ingestion.connectors.base import AuthError


class AuthMethod(StrEnum):
    NONE = "none"
    TOKEN = "token"
    BASIC = "basic"
    OAUTH2 = "oauth2"


@runtime_checkable
class SecretResolver(Protocol):
    """Resolves a secret *name* to its value at use time (Stage 14 owns the encrypted store)."""

    def resolve(self, name: str) -> str: ...


class InMemorySecretResolver:
    """An in-process resolver for tests/dev; a missing secret fails closed with ``AuthError``."""

    def __init__(self, secrets: Mapping[str, str]) -> None:
        self._secrets = dict(secrets)

    def resolve(self, name: str) -> str:
        try:
            return self._secrets[name]
        except KeyError as exc:
            raise AuthError(f"missing secret {name!r}") from exc


@dataclass(frozen=True)
class ConnectorAuth:
    """How a connector authenticates, by secret *name* — the values live in the resolver."""

    method: AuthMethod
    secret_names: tuple[str, ...] = ()

    def resolve(self, resolver: SecretResolver) -> dict[str, str]:
        """Resolve every declared secret (raising ``AuthError`` on the first missing one)."""
        return {name: resolver.resolve(name) for name in self.secret_names}

    def is_satisfied_by(self, resolver: SecretResolver) -> bool:
        try:
            self.resolve(resolver)
        except AuthError:
            return False
        return True


def no_auth() -> ConnectorAuth:
    return ConnectorAuth(method=AuthMethod.NONE)


def token_auth(name: str = "api_token") -> ConnectorAuth:
    return ConnectorAuth(method=AuthMethod.TOKEN, secret_names=(name,))


def basic_auth(*, username: str = "username", password: str = "password") -> ConnectorAuth:
    return ConnectorAuth(method=AuthMethod.BASIC, secret_names=(username, password))


def oauth2(
    *, client_secret: str = "client_secret", refresh_token: str = "refresh_token"
) -> ConnectorAuth:
    return ConnectorAuth(method=AuthMethod.OAUTH2, secret_names=(client_secret, refresh_token))
