"""The agent answers directly when no tool is needed — no skill is selected, proposed, or run."""

from metis_protocol.examples import WS
from metis_runtime.agent import AgentRequest, TaskStatus


async def test_plain_question_is_answered_without_tools(make_loop, audit_sink) -> None:
    loop = make_loop(text="The launch is in March.", sufficient=True)

    run = await loop.run(AgentRequest(workspace_id=WS, instruction="When is the launch?"))

    assert run.status is TaskStatus.COMPLETED
    assert run.actions == ()  # nothing was executed
    assert run.pending_approvals == ()
    assert run.answer is not None
    assert "March" in run.answer.text

    actions = [event.action for event in audit_sink.events]
    assert "agent.run.started" in actions
    assert "agent.run.finished" in actions
    # the loop never reached for a skill: no action proposal, no skill run
    assert not any(action.startswith("agent.action") for action in actions)
    assert not any(action.startswith("skill.run") for action in actions)
