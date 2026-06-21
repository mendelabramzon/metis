"""`metis-setup` generates usable, paste-ready deployment secrets and never persists them.

The load-bearing properties: the secret-store key it prints is a real Fernet key (it must construct
the same Cryptobox the app uses), every run is fresh, and the output is a self-documenting .env
block carrying the keep-it-stable warning. External provider keys are deliberately *not* generated.
"""

from __future__ import annotations

from metis_core.security import Cryptobox
from metis_deploy.setup import CRED_KEY, generate_secrets, main, render


def test_generates_all_owned_secrets() -> None:
    values = generate_secrets()
    assert set(values) == {
        "POSTGRES_PASSWORD",
        "MINIO_ROOT_PASSWORD",
        "METIS_GATEWAY_OPERATOR_TOKEN",
        "METIS_GATEWAY_USER_TOKEN",
        CRED_KEY,
    }
    assert all(len(v) >= 32 for v in values.values())  # not a weak/placeholder value
    # External provider keys are issued by the provider, never generated here.
    assert "ANTHROPIC_API_KEY" not in values
    assert "GOOGLE_CLIENT_SECRET" not in values


def test_cred_key_only_prints_just_the_key() -> None:
    assert set(generate_secrets(cred_key_only=True)) == {CRED_KEY}


def test_cred_key_is_a_usable_fernet_key() -> None:
    key = generate_secrets(cred_key_only=True)[CRED_KEY]
    box = Cryptobox(key)  # raises if it's not a valid Fernet key
    assert box.decrypt(box.encrypt("provider-secret")) == "provider-secret"


def test_each_run_is_fresh() -> None:
    assert generate_secrets()[CRED_KEY] != generate_secrets()[CRED_KEY]


def test_render_is_a_documented_env_block() -> None:
    out = render({CRED_KEY: "abc123"}, generated_on="2026-06-22")
    assert "2026-06-22" in out
    assert "STABLE and IDENTICAL" in out  # the don't-rotate-or-lose-it warning
    assert "\nMETIS_CRED_STORE_KEY=abc123  #" in out  # a real .env assignment, with a purpose note


def test_main_prints_without_error(capsys) -> None:
    assert main(["--cred-key-only"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("#")  # the documented header
    assert "METIS_CRED_STORE_KEY=" in out
