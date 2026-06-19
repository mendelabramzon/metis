"""Typed settings for the ingest worker (ADR 0006).

Precedence, lowest to highest: field defaults < values in ``.env`` < process
environment.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class IngestWorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="METIS_INGEST_WORKER_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    service_name: str = "ingest-worker"
    poll_interval_seconds: float = 5.0
    log_level: str = "INFO"
    # The source to poll and the workspace it belongs to. Database and object-store
    # configuration come from metis-core's CoreSettings (METIS_CORE_* env).
    connector: str = "local_folder"  # "local_folder" | "imap"
    workspace_id: str = ""
    ingest_root: str = "."  # for connector == "local_folder"
    # IMAP source (connector == "imap"); secrets are dev-plain here — Stage 14 hardens them.
    imap_host: str = ""
    imap_username: str = ""
    imap_password: str = ""
    imap_mailbox: str = "INBOX"
