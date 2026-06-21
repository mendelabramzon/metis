"""Operator deployment config: model provider keys + Google/Telegram credentials, set at runtime.

These are normally env config (:class:`GatewaySettings`); this surface lets an operator set them
without a redeploy. Overrides persist encrypted (durable + cross-process on Postgres) and are
applied to the live backend by rebuilding the chat model plane + OAuth/Telegram wiring in place — no
restart. Secrets are never returned in clear (masked to a last-4 hint). Embeddings stay env-only
(changing them is a re-index, ADR 0014). Operator-gated, like the other deployment surfaces.
"""

from __future__ import annotations

from fastapi import APIRouter

from metis_gateway.backend import Backend
from metis_gateway.config_store import effective_settings, status, status_fields
from metis_gateway.deps import BackendDep, OperatorDep
from metis_gateway.errors import ConflictError
from metis_gateway.schemas import (
    ConfigFieldView,
    ConfigStatusView,
    ConfigUpdate,
    DeploymentConfigView,
)

router = APIRouter(prefix="/admin/config", tags=["admin"])


def _config_view(backend: Backend) -> DeploymentConfigView:
    base = backend.base_settings
    if base is None:  # only the build functions wire this; defensive for a hand-built backend
        raise ConflictError("the deployment config surface is unavailable")
    overrides = backend.config_store.overrides() if backend.config_store is not None else {}
    effective = effective_settings(base, overrides)
    st = status(effective)
    return DeploymentConfigView(
        status=ConfigStatusView(
            chat_provider=st.chat_provider,
            embeddings_source=st.embeddings_source,
            google_oauth_configured=st.google_oauth_configured,
            telegram_tdlib_configured=st.telegram_tdlib_configured,
            runtime_config_enabled=backend.config_store is not None,
        ),
        fields=[
            ConfigFieldView(key=f.key, secret=f.secret, set=f.set, value=f.value)
            for f in status_fields(effective)
        ],
    )


@router.get("", response_model=DeploymentConfigView)
async def get_config(backend: BackendDep, _principal: OperatorDep) -> DeploymentConfigView:
    """The effective model + connector-auth config (secrets masked) and readiness status."""
    return _config_view(backend)


@router.put("", response_model=DeploymentConfigView)
async def put_config(
    body: ConfigUpdate, backend: BackendDep, _principal: OperatorDep
) -> DeploymentConfigView:
    """Persist provider/connector-auth overrides and apply them to the live backend (no restart)."""
    if backend.config_store is None or backend.base_settings is None:
        raise ConflictError(
            "runtime configuration requires a credential-store key "
            "(set METIS_GATEWAY_CRED_STORE_KEY)"
        )
    try:
        backend.config_store.set_many(body.values)
    except KeyError as exc:
        raise ConflictError(f"unknown config key {exc}") from exc
    except ValueError as exc:
        raise ConflictError(f"invalid config value: {exc}") from exc
    effective = effective_settings(backend.base_settings, backend.config_store.overrides())
    await backend.reconfigure_models(effective)
    return _config_view(backend)
