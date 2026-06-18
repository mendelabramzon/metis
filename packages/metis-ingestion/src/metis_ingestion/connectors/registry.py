"""Connector registry: register each connector with its auth + default sensitivity, resolve by name.

A source is configured by *name* ("slack", "gdrive", ...), so the registry maps a name to how that
connector authenticates and how sensitive its data is by default, plus a factory that builds it. The
default sensitivity is applied when the caller doesn't override — a floor, never a ceiling — so a
misconfigured source errs on the side of *more* restrictive, not less.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from metis_ingestion.connectors.auth import ConnectorAuth, basic_auth, no_auth, oauth2, token_auth
from metis_ingestion.connectors.base import FetchingConnector, RateLimiter, Transport
from metis_ingestion.connectors.calendar import CalendarConnector
from metis_ingestion.connectors.gdrive import GoogleDriveConnector
from metis_ingestion.connectors.imap import ImapConnector
from metis_ingestion.connectors.slack import SlackConnector
from metis_ingestion.connectors.web_clip import WebClipConnector
from metis_protocol import Sensitivity, WorkspaceId

ConnectorFactory = Callable[..., FetchingConnector]


@dataclass(frozen=True)
class ConnectorSpec:
    """How a named connector authenticates, how sensitive its data is, and how to build it."""

    name: str
    factory: ConnectorFactory
    auth: ConnectorAuth
    default_sensitivity: Sensitivity


class UnknownConnectorError(KeyError):
    """No connector is registered under the requested name."""


class ConnectorRegistry:
    def __init__(self) -> None:
        self._specs: dict[str, ConnectorSpec] = {}

    def register(self, spec: ConnectorSpec) -> None:
        self._specs[spec.name] = spec

    def get(self, name: str) -> ConnectorSpec | None:
        return self._specs.get(name)

    def names(self) -> list[str]:
        return sorted(self._specs)

    def create(
        self,
        name: str,
        *,
        workspace_id: WorkspaceId,
        transport: Transport,
        sensitivity: Sensitivity | None = None,
        tags: Sequence[str] = (),
        rate_limiter: RateLimiter | None = None,
    ) -> FetchingConnector:
        """Build a connector by name, defaulting sensitivity to the spec's floor."""
        spec = self._specs.get(name)
        if spec is None:
            raise UnknownConnectorError(name)
        return spec.factory(
            workspace_id=workspace_id,
            transport=transport,
            sensitivity=sensitivity if sensitivity is not None else spec.default_sensitivity,
            tags=tags,
            rate_limiter=rate_limiter,
        )

    @classmethod
    def with_defaults(cls) -> ConnectorRegistry:
        """The built-in connectors, in the plan's delivery order, with sensible auth/sensitivity."""
        registry = cls()
        registry.register(
            ConnectorSpec("imap", ImapConnector, basic_auth(), Sensitivity.CONFIDENTIAL)
        )
        registry.register(
            ConnectorSpec("slack", SlackConnector, token_auth(), Sensitivity.INTERNAL)
        )
        registry.register(
            ConnectorSpec("web_clip", WebClipConnector, no_auth(), Sensitivity.PUBLIC)
        )
        registry.register(
            ConnectorSpec("gdrive", GoogleDriveConnector, oauth2(), Sensitivity.INTERNAL)
        )
        registry.register(
            ConnectorSpec("calendar", CalendarConnector, oauth2(), Sensitivity.INTERNAL)
        )
        return registry
