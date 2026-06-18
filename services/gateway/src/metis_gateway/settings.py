"""Typed settings for the gateway service (ADR 0006).

Precedence, lowest to highest: field defaults < values in ``.env`` < process
environment. The shared ``BaseServiceSettings`` base moves into metis-core in
Stage 2; until then each service is self-contained.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class GatewaySettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="METIS_GATEWAY_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    service_name: str = "gateway"
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"
