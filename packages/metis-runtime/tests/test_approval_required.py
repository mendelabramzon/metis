"""Outbound/destructive skills require human approval before they execute (approval-by-default)."""

from metis_protocol import SkillInput, SkillOutcome


async def test_outbound_action_is_held_then_runs_after_approval(
    skill_runner, skill_registry, bundle
) -> None:
    loaded = skill_registry.get("notify", "1.0.0")  # requires_approval + outbound_action
    skill_input = SkillInput(
        skill_name="notify", skill_version="1.0.0", arguments={"message": "hi"}
    )

    held = await skill_runner.run(loaded.manifest, skill_input, bundle)
    assert held.outcome is SkillOutcome.NEEDS_APPROVAL
    assert held.approval_required

    pending = skill_runner.approvals.pending()
    assert len(pending) == 1
    skill_runner.approvals.approve(pending[0].key)

    executed = await skill_runner.run(loaded.manifest, skill_input, bundle)
    assert executed.outcome is SkillOutcome.SUCCESS
    assert executed.output == {"sent": True}
