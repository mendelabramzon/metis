"""Action traces are complete and inspectable: ordered phases, recorded outcomes, JSON-able."""

import json

from metis_protocol.examples import WS
from metis_runtime.agent import AgentRequest, StepKind


async def test_trace_records_every_phase_and_serializes(make_loop) -> None:
    loop = make_loop(text="context", sufficient=True)

    run = await loop.run(
        AgentRequest(
            workspace_id=WS,
            instruction="Please clean up and save the file out.txt",
            arguments={"name": "out.txt", "content": "x"},
        )
    )

    kinds = run.trace.kinds()
    for expected in (
        StepKind.CLASSIFY,
        StepKind.RETRIEVE,
        StepKind.PLAN,
        StepKind.ACT,
        StepKind.OBSERVE,
        StepKind.VERIFY,
    ):
        assert expected in kinds

    # The phases are in ReAct order.
    order = kinds.index
    assert order(StepKind.CLASSIFY) < order(StepKind.PLAN) < order(StepKind.ACT)
    assert order(StepKind.ACT) < order(StepKind.OBSERVE) < order(StepKind.VERIFY)

    # The executed action and its outcome are on the record.
    observe = next(step for step in run.trace.steps if step.kind is StepKind.OBSERVE)
    assert "writer -> success" in observe.summary

    # Every step is timestamped, and the whole trace round-trips to JSON for an operator surface.
    assert all(step.at is not None for step in run.trace.steps)
    encoded = json.loads(json.dumps(run.trace.to_dict()))
    assert encoded["run_id"] == str(run.run_id)
    assert any(step["kind"] == "act" for step in encoded["steps"])
