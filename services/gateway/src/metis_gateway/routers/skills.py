"""Skills: list the registered tool docs and run a skill (gated by the Stage 9 runner)."""

from __future__ import annotations

from fastapi import APIRouter

from metis_gateway.deps import BackendDep, OperatorDep, UserDep
from metis_gateway.errors import NotFoundError
from metis_gateway.schemas import SkillRunRequest, SkillRunResponse, SkillView
from metis_protocol import ContextBundle, ContextBundleId, QueryId, SkillInput, new_id

router = APIRouter(prefix="/skills", tags=["skills"])


@router.get("", response_model=list[SkillView])
async def list_skills(backend: BackendDep, _principal: UserDep) -> list[SkillView]:
    return [
        SkillView(
            name=doc.name,
            version=doc.version,
            description=doc.description,
            category=doc.category.value,
            requires_approval=doc.requires_approval,
        )
        for doc in backend.skills.tool_docs()
    ]


@router.post("/run", response_model=SkillRunResponse)
async def run_skill(
    body: SkillRunRequest, backend: BackendDep, _principal: OperatorDep
) -> SkillRunResponse:
    loaded = backend.skills.get(body.name, body.version)
    if loaded is None:
        raise NotFoundError(f"no skill {body.name}@{body.version}")
    bundle = ContextBundle(id=new_id(ContextBundleId), query_id=new_id(QueryId))
    result = await backend.skill_runner.run(
        loaded.manifest,
        SkillInput(skill_name=body.name, skill_version=body.version, arguments=body.arguments),
        bundle,
    )
    return SkillRunResponse(
        outcome=result.outcome,
        output=result.output,
        error=result.error,
        approval_required=result.approval_required,
        artifacts=len(result.artifacts),
    )
