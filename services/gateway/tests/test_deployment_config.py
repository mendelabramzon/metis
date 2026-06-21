"""The deployment config layer: overrides persist encrypted, overlay env, and drive status/masking.

Pure logic over a :class:`SecretStore` — no backend wiring — so the overlay, secret masking, and
status precedence are pinned independently of the HTTP/runtime-apply surface.
"""

from __future__ import annotations

import pytest

from metis_core.security import Cryptobox, EncryptedSecretStore, generate_key
from metis_gateway.config_store import (
    DeploymentConfigStore,
    effective_settings,
    status,
    status_fields,
)
from metis_gateway.settings import GatewaySettings


def _store() -> DeploymentConfigStore:
    return DeploymentConfigStore(EncryptedSecretStore(Cryptobox(generate_key())))


def test_overrides_round_trip_and_clear() -> None:
    store = _store()
    store.set_many({"anthropic_api_key": "sk-secret", "openai_base_url": "https://proxy/v1"})
    assert store.overrides() == {
        "anthropic_api_key": "sk-secret",
        "openai_base_url": "https://proxy/v1",
    }
    store.set("anthropic_api_key", "")  # empty clears the override
    assert "anthropic_api_key" not in store.overrides()


def test_unknown_key_and_bad_int_are_rejected() -> None:
    store = _store()
    with pytest.raises(KeyError):
        store.set("not_a_field", "x")
    with pytest.raises(ValueError, match="invalid literal"):
        store.set("telegram_api_id", "not-an-int")


def test_effective_settings_overlay_env_and_coerces_int() -> None:
    base = GatewaySettings(anthropic_api_key=None, telegram_api_id=0)
    eff = effective_settings(base, {"anthropic_api_key": "sk-x", "telegram_api_id": "424242"})
    assert eff.anthropic_api_key == "sk-x"
    assert eff.telegram_api_id == 424242  # coerced from the stored string
    assert base.anthropic_api_key is None  # the base is unchanged (a copy is overlaid)


def test_status_reflects_provider_precedence_and_auth() -> None:
    none = status(GatewaySettings())
    assert none.chat_provider is None  # nothing configured => extractive answers
    assert none.embeddings_source == "stub"
    assert none.google_oauth_configured is False
    assert none.telegram_tdlib_configured is False

    configured = status(
        GatewaySettings(
            anthropic_api_key="sk-x",
            model_endpoint="http://localhost:11434",
            google_client_id="cid",
            google_client_secret="csecret",
            telegram_api_id=42,
            telegram_api_hash="hash",
        )
    )
    assert configured.chat_provider == "anthropic"  # cloud wins over local in the router order
    assert configured.embeddings_source == "local"  # the local endpoint embeds
    assert configured.google_oauth_configured is True
    assert configured.telegram_tdlib_configured is True


def test_status_fields_mask_secrets_only() -> None:
    fields = {
        f.key: f
        for f in status_fields(
            GatewaySettings(anthropic_api_key="sk-abcd1234", openai_base_url="https://proxy/v1")
        )
    }
    secret = fields["anthropic_api_key"]
    assert secret.set is True
    assert secret.secret is True
    assert secret.value == "····1234"  # masked to the last 4
    assert "abcd" not in (secret.value or "")

    shown = fields["openai_base_url"]
    assert shown.set is True
    assert shown.secret is False
    assert shown.value == "https://proxy/v1"  # non-secret shown in clear

    assert fields["openai_api_key"].set is False
    assert fields["openai_api_key"].value is None
