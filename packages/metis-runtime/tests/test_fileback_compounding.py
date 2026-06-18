"""Useful outputs compound back into memory through patch *proposals*, never direct writes."""

from metis_protocol import ClaimId, ClaimRef, new_id
from metis_protocol.examples import WS
from metis_runtime.agent import AgentRequest, TaskStatus


async def test_grounded_answer_proposes_a_memory_fileback(make_loop, audit_sink) -> None:
    claims = (ClaimRef(claim_id=new_id(ClaimId)),)
    loop = make_loop(text="The vendor is Acme.", sufficient=True, claims=claims)

    run = await loop.run(AgentRequest(workspace_id=WS, instruction="Who is the vendor?"))

    assert run.status is TaskStatus.COMPLETED
    assert len(run.filebacks) == 1
    proposal = run.filebacks[0]
    assert proposal.kind == "memory"  # filed back as a proposal, applied by the patch path
    assert proposal.claims == claims  # carries its grounding
    assert "Who is the vendor?" in proposal.summary

    # Emitted as a proposal event — the patch path applies it; the runtime never writes directly.
    assert "agent.fileback.proposed" in [event.action for event in audit_sink.events]


async def test_ungrounded_answer_does_not_file_back(make_loop, audit_sink) -> None:
    loop = make_loop(text="I don't have enough evidence.", sufficient=False)

    run = await loop.run(AgentRequest(workspace_id=WS, instruction="Who is the vendor?"))

    assert run.filebacks == ()
    assert "agent.fileback.proposed" not in [event.action for event in audit_sink.events]
