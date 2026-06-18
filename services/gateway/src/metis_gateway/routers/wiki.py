"""Wiki: browse compiled pages and list proposed patches (approval runs through the inbox)."""

from __future__ import annotations

from fastapi import APIRouter

from metis_gateway.deps import BackendDep, OperatorDep, UserDep
from metis_gateway.schemas import WikiPageView, WikiPatchView

router = APIRouter(prefix="/wiki", tags=["wiki"])


@router.get("/pages", response_model=list[WikiPageView])
async def list_pages(backend: BackendDep, _principal: UserDep) -> list[WikiPageView]:
    # The durable wiki projection (Stage 7 store) is wired in deployment; none compiled in-memory.
    return []


@router.get("/patches", response_model=list[WikiPatchView])
async def list_patches(backend: BackendDep, _principal: OperatorDep) -> list[WikiPatchView]:
    return [
        WikiPatchView(
            id=str(review.patch.id),
            summary=review.patch.title or review.patch.rationale or str(review.patch.id),
            status=review.status.value,
        )
        for review in backend.wiki.pending()
    ]
