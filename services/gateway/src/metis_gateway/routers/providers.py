"""Model providers: the operator's view of which models are enabled by a capability manifest.

A model — notably a self-hosted Hugging Face endpoint behind TGI/vLLM/TEI — is enabled only by a
declared :class:`ModelCapability`, so listing the manifests is listing exactly what the router may
route to and why (context window, tiers, tool/JSON support, privacy tier).
"""

from __future__ import annotations

from fastapi import APIRouter

from metis_gateway.deps import BackendDep, OperatorDep
from metis_gateway.schemas import ProviderView
from metis_protocol import ModelCapability

router = APIRouter(prefix="/providers", tags=["providers"])


def _view(manifest: ModelCapability) -> ProviderView:
    return ProviderView(
        provider=manifest.provider,
        model_id=manifest.model_id,
        kind=manifest.kind,
        privacy_tier=manifest.privacy_tier,
        tiers=list(manifest.tiers),
        context_window=manifest.context_window,
        max_output_tokens=manifest.max_output_tokens,
        supports_tools=manifest.supports_tools,
        supports_json=manifest.supports_json,
        embedding_dim=manifest.embedding_dim,
    )


@router.get("", response_model=list[ProviderView])
async def list_providers(backend: BackendDep, _principal: OperatorDep) -> list[ProviderView]:
    return [_view(manifest) for manifest in backend.model_manifests]
