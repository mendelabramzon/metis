"""A compiled patch cites its claims; one introducing an unsupported claim fails validation."""

from metis_core.wiki import entity_slug
from metis_maintainer.wiki import WikiCompiler, is_valid, validate_patch
from metis_protocol.examples import claim


async def test_patch_citing_known_claims_is_valid() -> None:
    patch = await WikiCompiler().compile(
        title="Ada Lovelace", slug=entity_slug("Ada Lovelace"), claims=[claim()]
    )
    assert {str(ref.claim_id) for ref in patch.claims} == {str(claim().id)}
    assert is_valid(patch, known_claim_ids={str(claim().id)})


async def test_patch_introducing_unsupported_claim_is_rejected() -> None:
    patch = await WikiCompiler().compile(
        title="Ada Lovelace", slug=entity_slug("Ada Lovelace"), claims=[claim()]
    )
    # The cited claim resolves to nothing in evidence -> introduced/unsupported.
    issues = validate_patch(patch, known_claim_ids=set())
    assert issues
    assert any("unsupported" in issue for issue in issues)
