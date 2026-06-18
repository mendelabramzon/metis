"""Backlink computation and index/log page generation (the navigable substrate).

Backlinks are derived from page cross-references — markdown links ``](slug.md)`` and wiki-links
``[[slug]]`` — so navigation stays consistent with the prose. The index page lists every page;
both are navigation projections (no claims), generated deterministically for stable diffs.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from metis_core.wiki import INDEX_SLUG, LOG_SLUG
from metis_maintainer.memory._build import maintainer_provenance, now_utc, stable_id
from metis_protocol import (
    PolicyState,
    WikiOp,
    WikiPage,
    WikiPageRef,
    WikiPatch,
    WikiPatchId,
    WorkspaceId,
)

_MD_LINK = re.compile(r"\]\(([^)]+?)\.md\)")
_WIKI_LINK = re.compile(r"\[\[([^\]]+?)\]\]")


def referenced_slugs(body_markdown: str) -> set[str]:
    """Slugs this body links to (markdown ``](slug.md)`` or wiki ``[[slug]]``)."""
    return {*_MD_LINK.findall(body_markdown), *_WIKI_LINK.findall(body_markdown)}


def compute_backlinks(pages: Sequence[WikiPage]) -> dict[str, tuple[WikiPageRef, ...]]:
    """Map each page slug to refs of the pages that link to it."""
    by_slug = {page.slug: page for page in pages}
    backlinks: dict[str, list[WikiPageRef]] = {page.slug: [] for page in pages}
    for page in pages:
        for target in sorted(referenced_slugs(page.body_markdown)):
            if target in by_slug and target != page.slug:
                backlinks[target].append(WikiPageRef(wiki_page_id=page.id))
    return {slug: tuple(refs) for slug, refs in backlinks.items()}


def build_index_patch(
    pages: Sequence[WikiPage], *, workspace_id: WorkspaceId, policy: PolicyState | None = None
) -> WikiPatch:
    """A deterministic index page linking to every content page (navigation, no claims)."""
    listed = sorted(
        (page for page in pages if page.slug not in (INDEX_SLUG, LOG_SLUG)), key=lambda p: p.slug
    )
    items = [f"- [{page.title}]({page.slug}.md)" for page in listed] or ["_No pages yet._"]
    body = "\n".join(["# Index", "", *items])
    return WikiPatch(
        id=stable_id(WikiPatchId, f"{INDEX_SLUG}:" + "|".join(page.slug for page in listed)),
        provenance=maintainer_provenance(
            workspace_id, agent="wiki-indexer", operation="wiki_compile"
        ),
        policy=policy if policy is not None else PolicyState(),
        created_at=now_utc(),
        op=WikiOp.CREATE,
        title="Index",
        slug=INDEX_SLUG,
        body_markdown=body,
        rationale=f"index of {len(listed)} page(s)",
    )
