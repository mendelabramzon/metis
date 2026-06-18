"""The extraction-eval seed compares providers on schema-validity and claim count."""

from metis_core.llm import StubProvider, compare_providers
from metis_protocol import ModelTaskClass
from metis_protocol.examples import extraction_batch


async def test_eval_compares_providers() -> None:
    valid = extraction_batch().model_dump(mode="json")
    good = StubProvider(name="good", responses={ModelTaskClass.EXTRACT_CLAIMS.value: ("", valid)})
    bad = StubProvider(
        name="bad", responses={ModelTaskClass.EXTRACT_CLAIMS.value: ("not json", None)}
    )

    results = await compare_providers([good, bad], document_text="Ada is the CTO of Acme.")
    by_name = {r.provider: r for r in results}

    assert by_name["good"].schema_valid
    assert by_name["good"].claim_count == 1
    assert not by_name["bad"].schema_valid
    assert by_name["bad"].error is not None
