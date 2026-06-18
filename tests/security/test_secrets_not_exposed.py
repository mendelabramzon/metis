"""Secrets are encrypted at rest and hidden from skill code unless the skill declares the need."""

from __future__ import annotations

import pytest

from metis_core.security import Cryptobox, DecryptionError, EncryptedSecretStore, generate_key
from metis_ingestion.security import EncryptedCredentialStore
from metis_protocol import SkillInput, SkillOutcome


def test_secret_store_is_ciphertext_at_rest() -> None:
    store = EncryptedSecretStore(Cryptobox(generate_key()))
    store.set("api_token", "xoxb-top-secret")
    assert store.resolve("api_token") == "xoxb-top-secret"  # plaintext only on resolve
    assert "xoxb-top-secret" not in (store.ciphertext("api_token") or "")  # not at rest


def test_wrong_key_cannot_decrypt() -> None:
    token = Cryptobox(generate_key()).encrypt("secret")
    with pytest.raises(DecryptionError):
        Cryptobox(generate_key()).decrypt(token)


def test_connector_credentials_are_encrypted_and_namespaced() -> None:
    creds = EncryptedCredentialStore(Cryptobox(generate_key()))
    creds.set_credential(connector="slack", name="bot_token", value="xoxb-1")
    creds.set_credential(connector="gdrive", name="bot_token", value="ya29-2")

    assert creds.for_connector("slack").resolve("bot_token") == "xoxb-1"
    assert creds.for_connector("gdrive").resolve("bot_token") == "ya29-2"
    assert "xoxb-1" not in (creds.ciphertext(connector="slack", name="bot_token") or "")


async def test_skill_sees_secret_only_with_the_secrets_permission(make_runner, bundle) -> None:
    registry, runner = make_runner(secrets={"METIS_SECRET": "do-not-leak"})

    # a skill WITHOUT the secrets permission gets a scrubbed env — no secret
    loaded = registry.get("probe", "1.0.0")
    assert loaded is not None
    result = await runner.run(
        loaded.manifest, SkillInput(skill_name="probe", skill_version="1.0.0"), bundle
    )
    assert result.outcome is SkillOutcome.SUCCESS
    assert result.output == {"saw_secret": False}

    # a skill WITH the secrets permission may see the declared secret
    loaded_secret = registry.get("probe_secret", "1.0.0")
    assert loaded_secret is not None
    granted = await runner.run(
        loaded_secret.manifest,
        SkillInput(skill_name="probe_secret", skill_version="1.0.0"),
        bundle,
    )
    assert granted.output == {"saw_secret": True}
