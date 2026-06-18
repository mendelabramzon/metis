"""Backlinks point back to linking pages; the index lists every content page."""

from metis_core.wiki import INDEX_SLUG
from metis_maintainer.wiki import build_index_patch, compute_backlinks
from metis_protocol import WikiPage, WikiPageId, WikiPageRef
from metis_protocol.examples import WS, wiki_page


def _page(n: int, slug: str, title: str, body: str) -> WikiPage:
    return wiki_page().model_copy(
        update={
            "id": WikiPageId("page_" + format(n, "032x")),
            "slug": slug,
            "title": title,
            "body_markdown": body,
        }
    )


def test_backlinks_point_to_linking_pages() -> None:
    target = _page(2, "topic/b", "B", "About B.")
    linker = _page(1, "topic/a", "A", "See [B](topic/b.md) for context.")

    links = compute_backlinks([linker, target])
    assert links["topic/b"] == (WikiPageRef(wiki_page_id=linker.id),)
    assert links["topic/a"] == ()  # nothing links to A


def test_index_lists_every_content_page() -> None:
    pages = [_page(1, "topic/a", "A", "x"), _page(2, "topic/b", "B", "y")]
    patch = build_index_patch(pages, workspace_id=WS)
    assert patch.slug == INDEX_SLUG
    assert "topic/a.md" in patch.body_markdown
    assert "topic/b.md" in patch.body_markdown
