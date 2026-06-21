"""Operator-set deployment config (model provider keys, Google OAuth, Telegram app credentials).

Providers and connector auth are normally env config (:class:`GatewaySettings`). This lets an
operator set them at runtime instead: overrides persist in the encrypted secret store (durable +
shared across processes on Postgres) and are overlaid on the env settings to form the *effective*
settings the backend wires its model plane + OAuth/Telegram flows from. Secrets are never returned
in clear — :func:`status_fields` masks them to a set/unset flag + last-4.

Embeddings are intentionally **not** runtime-configurable: changing an embedding model is a
re-index under the version-gating invariant (ADR 0014), so it stays env-only.
"""

from __future__ import annotations

from dataclasses import dataclass

from metis_core.security import SecretNotFoundError, SecretStore
from metis_gateway.settings import GatewaySettings

# The operator-configurable settings fields -> whether the value is a secret (masked in the status
# view). Stored as strings under a "cfg:" namespace in the shared secret store; int fields are
# coerced when overlaid. Keep this in sync with the GatewaySettings field names it mirrors.
CONFIG_KEYS: dict[str, bool] = {
    "anthropic_api_key": True,
    "openai_api_key": True,
    "openai_base_url": False,
    "openai_chat_model": False,
    "model_endpoint": False,
    "chat_model": False,
    "google_client_id": False,
    "google_client_secret": True,
    "google_redirect_uri": False,
    "google_scopes": False,
    "telegram_api_id": False,  # an int, but not a secret
    "telegram_api_hash": True,
}
_INT_KEYS = frozenset({"telegram_api_id"})
_PREFIX = "cfg:"


class DeploymentConfigStore:
    """Reads/writes the operator's config overrides in an encrypted :class:`SecretStore`."""

    def __init__(self, store: SecretStore) -> None:
        self._store = store

    def overrides(self) -> dict[str, str]:
        """The currently-stored overrides (raw strings), keyed by settings-field name."""
        out: dict[str, str] = {}
        for key in CONFIG_KEYS:
            try:
                out[key] = self._store.resolve(_PREFIX + key)
            except SecretNotFoundError:
                continue
        return out

    def set(self, key: str, value: str | None) -> None:
        """Persist (or, for an empty value, clear) one override. Validates int fields up front."""
        if key not in CONFIG_KEYS:
            raise KeyError(key)
        if value is None or value == "":
            self._store.delete(_PREFIX + key)
            return
        if key in _INT_KEYS:
            int(value)  # raises ValueError on a non-integer before we persist it
        self._store.set(_PREFIX + key, value)

    def set_many(self, values: dict[str, str | None]) -> None:
        for key, value in values.items():
            self.set(key, value)


def effective_settings(base: GatewaySettings, overrides: dict[str, str]) -> GatewaySettings:
    """``base`` (env) overlaid with the stored overrides — the settings the backend wires from."""
    update: dict[str, object] = {
        key: (int(value) if key in _INT_KEYS else value) for key, value in overrides.items()
    }
    return base.model_copy(update=update) if update else base


def chat_provider(settings: GatewaySettings) -> str | None:
    """Which provider answers, in the router's cloud-first order — or None (extractive answers)."""
    if settings.anthropic_api_key:
        return "anthropic"
    if settings.openai_api_key:
        return "openai"
    if any(cap.kind.value == "chat" for cap in settings.model_manifests):
        return "self-hosted"
    if settings.model_endpoint:
        return "local"
    return None


def embeddings_source(settings: GatewaySettings) -> str:
    """Where retrieval embeddings come from: a self-hosted manifest, a local endpoint, or stubs."""
    if any(cap.kind.value == "embed" for cap in settings.model_manifests):
        return "self-hosted"
    if settings.model_endpoint:
        return "local"
    return "stub"


@dataclass(frozen=True)
class ConfigStatus:
    """The deployment's model + connector-auth readiness, for the operator status surface."""

    chat_provider: str | None  # None => answers are extractive (no model)
    embeddings_source: str
    google_oauth_configured: bool
    telegram_tdlib_configured: bool


def status(settings: GatewaySettings) -> ConfigStatus:
    return ConfigStatus(
        chat_provider=chat_provider(settings),
        embeddings_source=embeddings_source(settings),
        google_oauth_configured=bool(settings.google_client_id and settings.google_client_secret),
        telegram_tdlib_configured=bool(settings.telegram_api_id and settings.telegram_api_hash),
    )


@dataclass(frozen=True)
class ConfigField:
    """One config field's masked state for the status view (no clear secret ever leaves here)."""

    key: str
    secret: bool
    set: bool
    # Masked (last-4) for secrets; the effective value for non-secrets; None when unset.
    value: str | None


def _mask(value: str) -> str:
    return f"····{value[-4:]}" if len(value) >= 4 else "····"


def status_fields(settings: GatewaySettings) -> list[ConfigField]:
    """Each configurable field's effective state, secrets masked — backs `GET /admin/config`."""
    fields: list[ConfigField] = []
    for key, secret in CONFIG_KEYS.items():
        raw = getattr(settings, key)
        text = "" if raw in (None, 0) else str(raw)
        is_set = text != ""
        if not is_set:
            value: str | None = None
        elif secret:
            value = _mask(text)
        else:
            value = text
        fields.append(ConfigField(key=key, secret=secret, set=is_set, value=value))
    return fields
