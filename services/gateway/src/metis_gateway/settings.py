"""Typed settings for the gateway service (ADR 0006).

Precedence, lowest to highest: field defaults < values in ``.env`` < process environment. Tokens are
plaintext dev defaults here; real secret storage and SSO are Stage 14. The gateway serves a single
workspace for now (multi-tenant routing is a later concern).
"""

from pydantic_settings import SettingsConfigDict

from metis_core import BaseServiceSettings

_DEV_WORKSPACE = "ws_" + "0" * 32


class GatewaySettings(BaseServiceSettings):
    model_config = SettingsConfigDict(
        env_prefix="METIS_GATEWAY_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    service_name: str = "gateway"
    host: str = "127.0.0.1"
    port: int = 8000

    workspace_id: str = _DEV_WORKSPACE
    operator_token: str = "operator-dev-token"  # full scope (approvals, jobs, audit)
    user_token: str = "user-dev-token"  # query/read scope
    skills_root: str | None = None  # directory of skill packages to register, if any

    # "memory" (in-process) or "postgres" (durable: Postgres + object store + memory index).
    # The Postgres backend reads DB/object-store config from the core settings (METIS_CORE_*).
    backend: str = "memory"

    # Local model runtime (Ollama). Set the endpoint to answer with a local LLM and (on the Postgres
    # backend) retrieve with local embeddings; unset = extractive answers + stub vectors.
    model_endpoint: str | None = None  # e.g. http://localhost:11434
    chat_model: str = "gemma4:e4b"
    embedding_model: str = "bge-m3"
