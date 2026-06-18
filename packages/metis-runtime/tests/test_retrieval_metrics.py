"""Retrieval quality is measurable on its own — recall computed without any generation."""

from metis_protocol import QueryId, QueryRequest, new_id
from metis_protocol.examples import WS, claim, mem_cell


async def test_span_recall_measured_independently_of_generation(retriever, seed) -> None:
    cell = mem_cell().model_copy(
        update={"summary": "Ada CTO Acme.", "content": "Ada is the CTO of Acme."}
    )
    await seed(cell, [claim()])
    expected_spans = {str(ref.source_span_id) for ref in cell.source_spans}

    query = QueryRequest(id=new_id(QueryId), workspace_id=WS, text="Ada CTO Acme", top_k=5)
    _evidence, cells = await retriever.retrieve_cells(query)

    retrieved_spans = {str(ref.source_span_id) for c in cells for ref in c.source_spans}
    recall = len(retrieved_spans & expected_spans) / len(expected_spans)
    assert recall == 1.0  # the relevant cell's spans were retrieved — no answer generated
