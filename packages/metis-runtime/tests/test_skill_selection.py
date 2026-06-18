"""The agent selects the right skill for the task, and outbound actions are approval-gated."""

from metis_protocol.examples import WS
from metis_runtime.agent import AgentRequest, TaskStatus, select_skills, trusted


def test_selection_ranks_the_matching_tool_first(skill_registry) -> None:
    docs = skill_registry.tool_docs()

    file_match = select_skills(trusted("clean up and save the file notes.txt"), docs)
    assert [candidate.tool.name for candidate in file_match][:1] == ["writer"]

    send_match = select_skills(trusted("send a notification message to the team"), docs)
    assert [candidate.tool.name for candidate in send_match][:1] == ["notify"]


async def test_selects_and_runs_a_non_approval_skill(make_loop) -> None:
    loop = make_loop()

    run = await loop.run(
        AgentRequest(
            workspace_id=WS,
            instruction="Please clean up and save the file notes.txt",
            arguments={"name": "notes.txt", "content": "summary"},
        )
    )

    assert run.status is TaskStatus.COMPLETED
    assert len(run.actions) == 1
    action = run.actions[0]
    assert action.skill_name == "writer"
    assert action.succeeded
    assert action.output == {"written": "notes.txt"}
    assert action.artifacts  # the generated file was captured


async def test_outbound_action_is_held_then_runs_after_approval(make_loop, skill_runner) -> None:
    loop = make_loop()
    request = AgentRequest(
        workspace_id=WS,
        instruction="send a notification message to the team",
        arguments={"message": "hi"},
    )

    held = await loop.run(request)
    assert held.awaiting_approval
    assert held.status is TaskStatus.AWAITING_APPROVAL
    assert held.actions == ()  # the action did not run before approval
    assert len(held.pending_approvals) == 1

    skill_runner.approvals.approve(held.pending_approvals[0].key)
    done = await loop.resume(request.run_id)

    assert done.status is TaskStatus.COMPLETED
    assert len(done.actions) == 1
    assert done.actions[0].skill_name == "notify"
    assert done.actions[0].succeeded
    assert done.actions[0].output == {"sent": True}

    # Resuming a finished run is a no-op (idempotent), not a re-run.
    again = await loop.resume(request.run_id)
    assert again.status is TaskStatus.COMPLETED
    assert len(again.actions) == 1
