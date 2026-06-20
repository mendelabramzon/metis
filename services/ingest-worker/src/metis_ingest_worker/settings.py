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
    # "queue": lease durable ingest.poll jobs and run each source's sync (the server path); "poll":
    # continuously poll one configured connector directly (the local-folder dev path).
    mode: str = "queue"
    # The source to poll and the workspace it belongs to. Database and object-store
    # configuration come from metis-core's CoreSettings (METIS_CORE_* env).
    # When set, ``source_id`` names a registered SourceConfig: the worker resumes from that
    # source's durable cursor and records a ConnectorRun per cycle, and the source's workspace
    # (not ``workspace_id`` below) drives ingestion. Left empty, the worker polls with an
    # in-process cursor and no run history (the local-folder dev mode).
    source_id: str = ""
    connector: str = "local_folder"  # "local_folder" | "imap"
    workspace_id: str = ""
    ingest_root: str = "."  # for connector == "local_folder"
    # IMAP source (connector == "imap"); secrets are dev-plain here — Stage 14 hardens them.
    imap_host: str = ""
    imap_username: str = ""
    imap_password: str = ""
    imap_mailbox: str = "INBOX"
    # Google Drive source (connector == "gdrive"): the folder to sync, plus the OAuth token endpoint
    # and client id. The refresh token and client secret are resolved from the encrypted credential
    # store (keyed by cred_store_key); per-source folder selection is a later slice.
    gdrive_folder_id: str = ""
    # Gmail source (connector == "gmail"): the mailbox slice to sync (an optional Gmail search query
    # and comma-separated label ids), over the same Google OAuth as Drive.
    gmail_query: str = ""
    gmail_label_ids: str = ""  # comma-separated label ids, e.g. "INBOX,IMPORTANT"
    gmail_user_id: str = "me"
    google_token_url: str = "https://oauth2.googleapis.com/token"
    google_client_id: str = ""
    cred_store_key: str = ""  # Fernet key for the encrypted credential store (tokens at rest)
    # OCR for scanned PDFs (optional): a vision model for the parse-quality escalation. Either an
    # Anthropic key (cloud Claude vision) and/or a self-hosted OpenAI-compatible vision endpoint.
    # Absent both, ingestion stays deterministic + layout-only (no OCR).
    anthropic_api_key: str = ""
    vision_endpoint: str = ""  # OpenAI-compatible base URL of a vision model (e.g. a local VLM)
    vision_model: str = ""
    vision_external: bool = False  # whether vision_endpoint is an external provider (policy gating)
