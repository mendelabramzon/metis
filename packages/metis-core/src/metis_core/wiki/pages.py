"""Wiki page kinds, slug conventions, and deterministic file rendering.

The wiki is a *projection*, not machine truth, so page kind is encoded in the slug namespace
(``entity/ada-lovelace``, ``topic/...``, ``project/...``, plus the singleton ``index`` and
``log`` pages) rather than added to the protocol ``WikiPage`` schema. Each slug maps to one file
path; rendering prepends deterministic frontmatter so regenerating a page from unchanged inputs
produces a byte-identical file (reviewable diffs).
"""

from __future__ import annotations

import re
from enum import StrEnum

from metis_protocol import WikiPage

INDEX_SLUG = "index"
LOG_SLUG = "log"


class WikiPageKind(StrEnum):
    ENTITY = "entity"
    TOPIC = "topic"
    PROJECT = "project"
    INDEX = "index"
    LOG = "log"


def slugify(name: str) -> str:
    """A stable, filesystem-safe slug fragment (lowercase, non-alphanumerics -> hyphen)."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "untitled"


def entity_slug(name: str) -> str:
    return f"{WikiPageKind.ENTITY.value}/{slugify(name)}"


def topic_slug(name: str) -> str:
    return f"{WikiPageKind.TOPIC.value}/{slugify(name)}"


def project_slug(name: str) -> str:
    return f"{WikiPageKind.PROJECT.value}/{slugify(name)}"


def kind_of(slug: str) -> WikiPageKind:
    if slug == INDEX_SLUG:
        return WikiPageKind.INDEX
    if slug == LOG_SLUG:
        return WikiPageKind.LOG
    prefix = slug.split("/", 1)[0]
    try:
        return WikiPageKind(prefix)
    except ValueError:
        return WikiPageKind.TOPIC  # unnamespaced slugs default to a topic page


def repo_path(slug: str) -> str:
    """The markdown file path (relative to the wiki repo root) for a slug."""
    return f"{slug}.md"


def render_page(page: WikiPage) -> str:
    """Render a page to its on-disk markdown: deterministic frontmatter + the compiled body."""
    frontmatter = "\n".join(
        [
            "---",
            f"title: {page.title}",
            f"slug: {page.slug}",
            f"kind: {kind_of(page.slug).value}",
            f"claims: {len(page.claims)}",
            f"unresolved: {len(page.unresolved)}",
            "---",
        ]
    )
    return f"{frontmatter}\n\n{page.body_markdown.rstrip()}\n"
