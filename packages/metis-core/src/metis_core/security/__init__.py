"""Security and privacy hardening (Stage 14): secrets at rest, audit integrity, deletion, backup.

Cross-cutting controls that make the substrate trustworthy for private workspaces: secret encryption
at rest (the connector ``SecretResolver``), audit hash-chain verification, right-to-erasure across
the truth hierarchy, and backup/restore of the non-DB tiers. Policy stays outside prompts; these are
the durable-substrate half of the hardening (injection/taint/sandbox live in ``metis-runtime``).
"""

from __future__ import annotations

from metis_core.security.audit_integrity import AuditTamperError, assert_intact
from metis_core.security.backup import BackupManifest, back_up, restore
from metis_core.security.crypto import Cryptobox, DecryptionError, derive_key, generate_key
from metis_core.security.deletion import ErasureResult, erase_artifact
from metis_core.security.secrets import (
    EncryptedSecretStore,
    PostgresSecretStore,
    SecretNotFoundError,
    SecretStore,
)

__all__ = [
    "AuditTamperError",
    "BackupManifest",
    "Cryptobox",
    "DecryptionError",
    "EncryptedSecretStore",
    "ErasureResult",
    "PostgresSecretStore",
    "SecretNotFoundError",
    "SecretStore",
    "assert_intact",
    "back_up",
    "derive_key",
    "erase_artifact",
    "generate_key",
    "restore",
]
