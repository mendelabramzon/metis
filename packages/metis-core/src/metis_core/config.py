"""Core configuration, plus the shared service settings base promoted from Stage 0.

Precedence: field defaults < ``.env`` < process environment (ADR 0006).
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseServiceSettings(BaseSettings):
    """Shared base for every Metis service's settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    log_level: str = "INFO"


class CoreSettings(BaseServiceSettings):
    """Durable-substrate configuration: the database and the object store.

    Object-store credentials are plaintext here for local/dev use; encrypted
    secret storage is Stage 14.
    """

    model_config = SettingsConfigDict(
        env_prefix="METIS_CORE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+asyncpg://metis:metis@localhost:5432/metis"
    object_store_endpoint_url: str | None = None  # set for MinIO; leave None for AWS S3
    object_store_bucket: str = "metis-artifacts"
    object_store_region: str = "us-east-1"
    object_store_access_key: str = "minioadmin"
    object_store_secret_key: str = "minioadmin"
