"""Regenerating a page from unchanged inputs is byte-stable (reviewable diffs)."""

from metis_maintainer.wiki import WikiCompiler
from metis_protocol.examples import CLM2, claim

_SLUG = "entity/ada"


async def test_compilation_is_order_independent_and_stable() -> None:
    claims = [claim(), claim().model_copy(update={"id": CLM2, "text": "Ada chairs the board."})]
    compiler = WikiCompiler()

    first = await compiler.compile(title="Ada", slug=_SLUG, claims=claims)
    # Same claims, reversed input order: the compiler sorts internally.
    second = await compiler.compile(title="Ada", slug=_SLUG, claims=list(reversed(claims)))

    assert first.body_markdown == second.body_markdown  # stable body -> empty diff
    assert first.id == second.id  # stable patch identity


async def test_surfaces_contradictions_rather_than_hiding_them() -> None:
    # Same subject + predicate, conflicting values -> an Open questions section, both cited.
    conflicting = claim().model_copy(update={"id": CLM2, "text": "Ada is the CEO of Acme."})
    patch = await WikiCompiler().compile(title="Ada", slug=_SLUG, claims=[claim(), conflicting])

    assert "## Open questions" in patch.body_markdown
    assert {str(ref.claim_id) for ref in patch.claims} == {str(claim().id), str(CLM2)}
