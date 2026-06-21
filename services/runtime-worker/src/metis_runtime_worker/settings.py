"""Typed settings for the runtime worker (ADR 0006).

Precedence, lowest to highest: field defaults < values in ``.env`` < process
environment.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class RuntimeWorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="METIS_RUNTIME_WORKER_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    service_name: str = "runtime-worker"
    poll_interval_seconds: float = 2.0
    log_level: str = "INFO"
    database_url: str = "postgresql+asyncpg://metis:metis@localhost:5432/metis"
