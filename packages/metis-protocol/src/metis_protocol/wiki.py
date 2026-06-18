"""The compiled, human-facing wiki projection: pages and the patches that write
them. The wiki is not machine truth — every statement is supportable by claim IDs
or explicitly marked unresolved.
"""

from __future__ import annotations

from metis_protocol.artifacts import Artifact
from metis_protocol.enums import WikiOp
from metis_protocol.ids import WikiPageId, WikiPatchId
from metis_protocol.refs import ClaimRef, EntityRef, WikiPageRef
from metis_protocol.versioning import schema


@schema
class WikiPage(Artifact[WikiPageId]):
    """A compiled markdown page projecting claims and memory for humans."""

    title: str
    slug: str
    body_markdown: str
    claims: tuple[ClaimRef, ...] = ()  # citations supporting the body
    backlinks: tuple[WikiPageRef, ...] = ()
    entity: EntityRef | None = None
    unresolved: tuple[str, ...] = ()  # statements lacking claim support


@schema
class WikiPatch(Artifact[WikiPatchId]):
    """A proposed change to the wiki. Must cite the claims it introduces."""

    op: WikiOp
    page_id: WikiPageId | None = None  # None when creating a new page
    title: str | None = None
    slug: str | None = None
    body_markdown: str | None = None
    claims: tuple[ClaimRef, ...] = ()
    rationale: str = ""
