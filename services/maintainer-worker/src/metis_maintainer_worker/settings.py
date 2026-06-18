"""Typed settings for the maintainer worker (ADR 0006).

Precedence, lowest to highest: field defaults < values in ``.env`` < process
environment.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class MaintainerWorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="METIS_MAINTAINER_WORKER_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    service_name: str = "maintainer-worker"
    poll_interval_seconds: float = 30.0
    log_level: str = "INFO"
