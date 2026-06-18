"""Restricted evidence is not surfaced to a requester whose ceiling is lower."""

from metis_protocol import PolicyState, QueryId, QueryRequest, Sensitivity, new_id
from metis_protocol.examples import WS, claim, mem_cell


async def test_restricted_cell_is_filtered_for_lower_clearance(query_engine, seed) -> None:
    restricted = mem_cell().model_copy(
        update={
            "policy": PolicyState(sensitivity=Sensitivity.RESTRICTED),
            "summary": "Ada compensation.",
            "content": "Ada's compensation at Acme is confidential.",
        }
    )
    await seed(restricted, [claim()])

    internal = QueryRequest(
        id=new_id(QueryId),
        workspace_id=WS,
        text="What is Ada's compensation at Acme?",
        max_sensitivity=Sensitivity.INTERNAL,
    )
    answer = await query_engine.answer(internal)
    assert not answer.sufficient  # the restricted cell was filtered out before packing
    assert answer.claims == ()

    cleared = internal.model_copy(
        update={"id": new_id(QueryId), "max_sensitivity": Sensitivity.RESTRICTED}
    )
    cleared_answer = await query_engine.answer(cleared)
    assert cleared_answer.sufficient  # a cleared requester does see it
