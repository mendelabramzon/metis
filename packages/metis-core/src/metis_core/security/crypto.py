"""At-rest encryption for secrets/credentials: authenticated symmetric encryption (Fernet).

A :class:`Cryptobox` wraps a Fernet key (AES-128-CBC + HMAC-SHA256 with a timestamp). The key is
either a raw Fernet key or derived from a passphrase via scrypt. Encryption is authenticated, so a
tampered ciphertext fails to decrypt (``DecryptionError``) rather than returning garbage. The key
never leaves the box; plaintext is only produced on an explicit :meth:`Cryptobox.decrypt`.
"""

from __future__ import annotations

import base64

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt


class DecryptionError(RuntimeError):
    """Ciphertext failed authentication (wrong key or tampering)."""


def generate_key() -> str:
    """A fresh random Fernet key (urlsafe-base64 text)."""
    return Fernet.generate_key().decode("ascii")


def derive_key(passphrase: str, *, salt: bytes) -> str:
    """Derive a Fernet key from a passphrase with scrypt (store the salt alongside the data)."""
    kdf = Scrypt(salt=salt, length=32, n=2**14, r=8, p=1)
    raw = kdf.derive(passphrase.encode("utf-8"))
    return base64.urlsafe_b64encode(raw).decode("ascii")


class Cryptobox:
    """Authenticated encrypt/decrypt of short secrets; the key stays inside the box."""

    def __init__(self, key: str) -> None:
        self._fernet = Fernet(key.encode("ascii"))

    @classmethod
    def from_passphrase(cls, passphrase: str, *, salt: bytes) -> Cryptobox:
        return cls(derive_key(passphrase, salt=salt))

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")

    def decrypt(self, token: str) -> str:
        try:
            return self._fernet.decrypt(token.encode("ascii")).decode("utf-8")
        except InvalidToken as exc:
            raise DecryptionError("ciphertext failed authentication") from exc
