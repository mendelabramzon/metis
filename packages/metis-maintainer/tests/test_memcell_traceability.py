"""A MemCell traces back to exactly the claims and source spans it was built from."""

import pytest

from metis_maintainer.memory import MemCellBuilder
from metis_protocol.examples import CLM1, SPAN, WS, claim, event


async def test_memcell_binds_its_claims_and_source_spans() -> None:
    builder = MemCellBuilder()  # no caller -> deterministic, evidence-only summary
    cell = await builder.build(workspace_id=WS, claims=[claim()], events=[event()])

    # Traceability: the cell carries the claim ref and the source span(s) it interpreted.
    assert {str(ref.claim_id) for ref in cell.claims} == {str(CLM1)}
    assert {str(ref.source_span_id) for ref in cell.source_spans} == {str(SPAN)}
    # The deterministic summary invents nothing beyond the evidence text.
    assert "Ada" in cell.content


async def test_memcell_id_is_stable_for_the_same_evidence() -> None:
    builder = MemCellBuilder()
    first = await builder.build(workspace_id=WS, claims=[claim()])
    second = await builder.build(workspace_id=WS, claims=[claim()])
    assert first.id == second.id  # re-consolidating the same evidence is idempotent


async def test_memcell_without_source_spans_is_refused() -> None:
    with pytest.raises(ValueError, match="without any source spans"):
        await MemCellBuilder().build(workspace_id=WS, claims=[], events=[])
