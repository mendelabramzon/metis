"""Compile claims (and memory) into a proposed wiki patch — structured and claim-cited.

The body is built deterministically from claims sorted by id: a Facts section cites each
non-conflicting claim with a footnote, an Open questions section surfaces same-subject /
same-predicate conflicts (rather than silently picking a winner), and a Citations footer maps
every footnote to its claim id. Because structure and ordering are fixed, regenerating from
unchanged inputs yields a byte-identical body — the WiCER discipline of constraining structure
so diffs are reviewable. An optional model adds only a prose lede over the already-cited claims.
"""

from __future__ import annotations

from collections.abc import Sequence

from metis_core import propagate_policy
from metis_core.llm import ModelCaller
from metis_core.wiki import kind_of
from metis_maintainer.memory._build import maintainer_provenance, now_utc, stable_id
from metis_maintainer.wiki.prompts import WikiLede
from metis_protocol import (
    Claim,
    ClaimRef,
    ModelTaskClass,
    WikiOp,
    WikiPage,
    WikiPatch,
    WikiPatchId,
    WorkspaceId,
)


def _conflicting_ids(claims: Sequence[Claim]) -> set[str]:
    """Ids of claims in a same-(subject, predicate) group that holds two or more values."""
    groups: dict[tuple[str, str], list[Claim]] = {}
    for claim in claims:
        if claim.predicate is None:
            continue
        subject = str(claim.subject_ref.entity_id) if claim.subject_ref is not None else ""
        groups.setdefault((subject, claim.predicate), []).append(claim)
    conflicting: set[str] = set()
    for group in groups.values():
        if len({claim.text for claim in group}) > 1:
            conflicting.update(str(claim.id) for claim in group)
    return conflicting


def _render_body(title: str, claims: Sequence[Claim], lede: str | None) -> str:
    numbering = {str(claim.id): index for index, claim in enumerate(claims, 1)}
    conflicting = _conflicting_ids(claims)
    facts = [c for c in claims if str(c.id) not in conflicting]
    conflicts = [c for c in claims if str(c.id) in conflicting]

    lines = [f"# {title}", ""]
    if lede:
        lines += [lede, ""]
    lines += ["## Facts", ""]
    lines += [f"- {c.text}[^{numbering[str(c.id)]}]" for c in facts] or ["_No uncontested facts._"]
    if conflicts:
        lines += ["", "## Open questions", "", "The evidence conflicts and is left unresolved:"]
        lines += [f"- {c.text}[^{numbering[str(c.id)]}]" for c in conflicts]
    lines += ["", "## Citations", ""]
    lines += [f"[^{numbering[str(c.id)]}]: {c.id}" for c in claims]
    return "\n".join(lines)


class WikiCompiler:
    def __init__(self, *, caller: ModelCaller | None = None) -> None:
        self._caller = caller  # optional prose lede; the citation scaffold is deterministic

    async def compile(
        self,
        *,
        title: str,
        slug: str,
        claims: Sequence[Claim],
        existing: WikiPage | None = None,
    ) -> WikiPatch:
        if not claims:
            raise ValueError("cannot compile a wiki page from no claims")
        ordered = sorted(claims, key=lambda claim: str(claim.id))
        workspace_id = ordered[0].provenance.workspace_id

        lede = await self._lede(workspace_id, title, ordered)
        body = _render_body(title, ordered, lede)
        return WikiPatch(
            id=stable_id(
                WikiPatchId,
                f"{slug}:" + "|".join(str(claim.id) for claim in ordered),
            ),
            provenance=maintainer_provenance(
                workspace_id,
                agent="wiki-compiler",
                operation="wiki_compile",
                inputs=[str(claim.id) for claim in ordered],
            ),
            policy=propagate_policy([claim.policy for claim in ordered]),
            created_at=now_utc(),
            op=WikiOp.UPDATE if existing is not None else WikiOp.CREATE,
            page_id=existing.id if existing is not None else None,
            title=title,
            slug=slug,
            body_markdown=body,
            claims=tuple(ClaimRef(claim_id=claim.id) for claim in ordered),
            rationale=f"compiled {kind_of(slug).value} page from {len(ordered)} claim(s)",
        )

    async def _lede(
        self, workspace_id: WorkspaceId, title: str, claims: Sequence[Claim]
    ) -> str | None:
        if self._caller is None:
            return None
        drafted = await self._caller.call_structured(
            task_class=ModelTaskClass.WIKI_COMPILE,
            workspace_id=workspace_id,
            user_content=f"Title: {title}\nClaims:\n"
            + "\n".join(f"- {claim.text}" for claim in claims),
            output_type=WikiLede,
            sensitivity=propagate_policy([claim.policy for claim in claims]).sensitivity,
        )
        return drafted.lede
