"""Propose wiki patches from claims — every statement carries a claim citation.

Stage 6 only *proposes*: it compiles a patch whose body footnotes each statement to the claim
that supports it, then lints it and checks claim support. Validation/commit (the approval and
compile/evaluate/refine loop) is Stage 7, so this job does not apply the patch to a page; it
surfaces a proposal (recorded in the maintenance audit trail). The patch id is stable for a
``(slug, claim set)`` so re-proposing the same content does not flood downstream.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from metis_core import propagate_policy
from metis_maintainer.jobs.base import JobOutcome, MaintainerDeps, Trigger, workspace_of
from metis_maintainer.jobs.lint_wiki import lint_issues
from metis_maintainer.jobs.validate_claim_support import claim_support_issues
from metis_maintainer.memory._build import maintainer_provenance, now_utc, stable_id
from metis_protocol import (
    Claim,
    ClaimFilter,
    ClaimRef,
    WikiOp,
    WikiPatch,
    WikiPatchId,
    WorkspaceId,
)


def compile_patch(
    workspace_id: WorkspaceId, claims: Sequence[Claim], *, title: str, slug: str
) -> WikiPatch:
    """Compile a CREATE patch whose body cites each claim by footnote."""
    statements = [f"- {claim.text}[^{index}]" for index, claim in enumerate(claims, 1)]
    citations = [f"[^{index}]: {claim.id}" for index, claim in enumerate(claims, 1)]
    body = "\n".join([f"# {title}", "", *statements, "", *citations])
    return WikiPatch(
        id=stable_id(
            WikiPatchId,
            f"{workspace_id}:{slug}:" + "|".join(sorted(str(claim.id) for claim in claims)),
        ),
        provenance=maintainer_provenance(
            workspace_id,
            agent="wiki-compiler",
            operation="wiki_compile",
            inputs=[str(claim.id) for claim in claims],
        ),
        policy=propagate_policy([claim.policy for claim in claims]),
        created_at=now_utc(),
        op=WikiOp.CREATE,
        title=title,
        slug=slug,
        body_markdown=body,
        claims=tuple(ClaimRef(claim_id=claim.id) for claim in claims),
        rationale=f"compiled from {len(claims)} claim(s)",
    )


class CompileWikiPatchesJob:
    kind = "compile_wiki_patches"
    triggers: tuple[Trigger, ...] = (Trigger.PERIODIC,)

    def idempotency_key(self, payload: Mapping[str, Any]) -> str:
        slug = str(payload.get("slug", "workspace-summary"))
        return f"{slug}:{payload.get('bucket') or payload.get('batch_id') or ''}"

    async def run(self, deps: MaintainerDeps, payload: Mapping[str, Any]) -> JobOutcome:
        workspace_id = workspace_of(payload)
        title = str(payload.get("title", "Workspace summary"))
        slug = str(payload.get("slug", "workspace-summary"))
        claims = await deps.claim_store.query(ClaimFilter(workspace_id=workspace_id))
        if not claims:
            return JobOutcome(kind=self.kind, summary="no claims; nothing to compile")

        patch = compile_patch(workspace_id, claims, title=title, slug=slug)
        issues = [*lint_issues(patch), *claim_support_issues(patch)]
        proposed = 0 if issues else 1  # propose only; invalid proposals are dropped, not committed
        return JobOutcome(
            kind=self.kind,
            summary=f"proposed {proposed} patch citing {len(patch.claims)} claim(s)"
            + (f"; {len(issues)} issue(s)" if issues else ""),
            counts={"proposed": proposed, "rejected": 1 - proposed, "claims": len(claims)},
        )
