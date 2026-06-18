"""Secret storage: values encrypted at rest, resolved by name — the connector ``SecretResolver``.

A value is encrypted with a :class:`~metis_core.security.crypto.Cryptobox` before storage, so a
leaked store dump exposes only ciphertext. :class:`EncryptedSecretStore` satisfies the Stage 11
``SecretResolver`` (``resolve(name) -> str``), so a connector can pull a credential without the
gateway or a model ever seeing it. A keyring/KMS backend slots behind the same :class:`SecretStore`
protocol; the deployment profile (Stage 15) picks one.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from metis_core.security.crypto import Cryptobox


class SecretNotFoundError(KeyError):
    """No secret is stored under the requested name."""


@runtime_checkable
class SecretStore(Protocol):
    def set(self, name: str, value: str) -> None: ...

    def resolve(self, name: str) -> str: ...

    def delete(self, name: str) -> None: ...

    def names(self) -> list[str]: ...


class EncryptedSecretStore:
    """Secrets held as ciphertext; plaintext is produced only on :meth:`resolve`."""

    def __init__(self, crypto: Cryptobox) -> None:
        self._crypto = crypto
        self._ciphertext: dict[str, str] = {}

    def set(self, name: str, value: str) -> None:
        self._ciphertext[name] = self._crypto.encrypt(value)

    def resolve(self, name: str) -> str:
        token = self._ciphertext.get(name)
        if token is None:
            raise SecretNotFoundError(name)
        return self._crypto.decrypt(token)

    def delete(self, name: str) -> None:
        self._ciphertext.pop(name, None)

    def names(self) -> list[str]:
        return sorted(self._ciphertext)

    def ciphertext(self, name: str) -> str | None:
        """The stored ciphertext (no decryption) — lets callers prove at-rest data is encrypted."""
        return self._ciphertext.get(name)
