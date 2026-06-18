"""Proposed wiki patches cite claim IDs; statements lacking claim support are rejected."""

from metis_maintainer.jobs import (
    CompileWikiPatchesJob,
    claim_support_issues,
    compile_patch,
    lint_issues,
)
from metis_protocol import BatchId, ExtractionBatch, new_id
from metis_protocol.examples import CLM2, PDOC, PROV, WS, claim


def test_compiled_patch_cites_its_claims_and_passes_validation() -> None:
    claims = [claim(), claim().model_copy(update={"id": CLM2, "text": "Ada chairs the board."})]
    patch = compile_patch(WS, claims, title="Ada Lovelace", slug="ada-lovelace")

    assert {str(ref.claim_id) for ref in patch.claims} == {str(claims[0].id), str(CLM2)}
    assert lint_issues(patch) == []
    assert claim_support_issues(patch) == []  # supported


def test_unsupported_statement_is_rejected() -> None:
    patch = compile_patch(WS, [claim()], title="Ada", slug="ada")
    unsupported = patch.model_copy(update={"claims": ()})  # body content, no citations
    assert claim_support_issues(unsupported), "a body citing no claims must be flagged"


async def test_compile_job_proposes_a_supported_patch(deps) -> None:
    await deps.claim_store.write(
        ExtractionBatch(
            id=new_id(BatchId),
            workspace_id=WS,
            parsed_doc_id=PDOC,
            provenance=PROV,
            claims=(claim(),),
        )
    )
    outcome = await CompileWikiPatchesJob().run(
        deps, {"workspace_id": str(WS), "title": "Acme", "slug": "acme"}
    )
    assert outcome.counts["proposed"] == 1
    assert outcome.counts["rejected"] == 0
