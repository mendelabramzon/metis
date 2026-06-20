"""Connector secrets table: encrypted-at-rest credentials, durable and shared across processes.

The deployment backend behind the connector secret store. A secret the gateway writes — an OAuth
refresh token, a Telegram TDLib database-encryption key — must be readable by the ingest worker and
survive a restart; both connect to the same Postgres, so this one table is the shared, durable home.
Only ciphertext is stored (encrypted with the deployment's ``Cryptobox``); the plaintext exists only
inside the box at use time. Operational state, no policy/provenance envelope.
"""

from __future__ import annotations

from sqlalchemy.orm import Mapped, mapped_column

from metis_core.db.base import Base
from metis_core.db.types import TZDateTime


class ConnectorSecretRow(Base):
    """One encrypted secret, keyed by name (e.g. ``gmail:refresh_token``,
    ``telegram_tdlib:db_key:<user>``). Mutable, so the store upserts."""

    __tablename__ = "connector_secrets"

    name: Mapped[str] = mapped_column(primary_key=True)
    ciphertext: Mapped[str] = mapped_column()
    updated_at: Mapped[TZDateTime] = mapped_column(index=True)
