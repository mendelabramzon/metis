"""Ingestion security hardening (Stage 14): encrypted connector credentials + webhook verification.

Connector credentials are stored encrypted at rest (the Stage 11 ``SecretResolver``, now with
encryption), and inbound webhook payloads are signature-verified before they become ingest jobs.
"""

from __future__ import annotations

from metis_ingestion.security.cred_store import ConnectorSecretResolver, EncryptedCredentialStore
from metis_ingestion.security.webhook_verify import sign, verify_webhook

__all__ = [
    "ConnectorSecretResolver",
    "EncryptedCredentialStore",
    "sign",
    "verify_webhook",
]
