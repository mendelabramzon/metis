"""Typed settings for the gateway service (ADR 0006).

Precedence, lowest to highest: field defaults < values in ``.env`` < process environment. Tokens are
plaintext dev defaults here; real secret storage and SSO are Stage 14. The gateway serves a single
workspace for now (multi-tenant routing is a later concern).
"""

from pydantic_settings import SettingsConfigDict

from metis_core import BaseServiceSettings
from metis_protocol import ModelCapability

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

    # The built React SPA (apps/web -> dist) to serve at /. Set in the deploy image to the copied
    # build; unset = serve the legacy single-file operator console instead. A directory without an
    # index.html is ignored (treated as unset).
    web_dist: str | None = None

    # "memory" (in-process) or "postgres" (durable: Postgres + object store + memory index).
    # The Postgres backend reads DB/object-store config from the core settings (METIS_CORE_*).
    backend: str = "memory"

    # Local model runtime (Ollama). Set the endpoint to answer with a local LLM and (on the Postgres
    # backend) retrieve with local embeddings; unset = extractive answers + stub vectors.
    model_endpoint: str | None = None  # e.g. http://localhost:11434
    chat_model: str = "gemma4:e4b"
    embedding_model: str = "bge-m3"

    # Cloud chat providers (optional). With a key set, that provider serves the STANDARD/FRONTIER
    # tiers for non-restricted data; restricted data always routes local (router-enforced). An HF
    # model served behind an OpenAI-compatible server (vLLM/TGI) plugs in via openai_base_url.
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_chat_model: str = "gpt-4o-mini"

    # Self-hosted / Hugging Face models, each enabled only by a capability manifest (no
    # name-based auto-selection). A chat manifest's base_url is the OpenAI-compatible URL of its
    # TGI/vLLM server, registered as a router provider; routing is driven by the declared
    # capabilities. Set as a JSON list in METIS_GATEWAY_MODEL_MANIFESTS.
    model_manifests: tuple[ModelCapability, ...] = ()

    # Google OAuth consent flow: with a client id/secret set, /oauth/{connector}/authorize starts
    # the consent and /oauth/callback stores the resulting refresh token in the encrypted credential
    # store (keyed by cred_store_key) for the ingest worker to use. Empty = the flow is disabled.
    google_client_id: str = ""
    google_client_secret: str = ""
    google_auth_url: str = "https://accounts.google.com/o/oauth2/v2/auth"
    google_token_url: str = "https://oauth2.googleapis.com/token"
    google_redirect_uri: str = ""
    google_scopes: str = "https://www.googleapis.com/auth/drive.readonly"
    cred_store_key: str = ""  # Fernet key for the encrypted credential store (tokens at rest)

    # Opt-in Telegram TDLib personal-account login (history backfill + followed channels). With an
    # api id/hash set (and a cred store), POST /telegram/tdlib/connect drives the per-user QR/2FA
    # login and stores only the TDLib database-encryption key. Empty api id = the flow is disabled.
    telegram_api_id: int = 0  # a Telegram app api_id (https://my.telegram.org); 0 = disabled
    telegram_api_hash: str = ""
    telegram_tdlib_data_root: str = "/var/lib/metis/tdlib"  # per-user TDLib database dirs live here
    telegram_tdlib_library: str = ""  # path to libtdjson; empty = platform library discovery
    telegram_tdlib_poll_seconds: float = 1.0  # the login pump's per-update receive timeout
