"""A skill crash is an observable ERROR result; the runner survives and stays usable."""

from metis_protocol import SkillInput, SkillOutcome


async def test_crashing_skill_yields_error_not_exception(
    skill_runner, skill_registry, bundle
) -> None:
    loaded = skill_registry.get("crasher", "1.0.0")
    result = await skill_runner.run(
        loaded.manifest,
        SkillInput(skill_name="crasher", skill_version="1.0.0", arguments={}),
        bundle,
    )
    assert result.outcome is SkillOutcome.ERROR
    assert "intentional skill failure" in (result.error or "")


async def test_runner_recovers_after_a_failed_run(skill_runner, skill_registry, bundle) -> None:
    await skill_runner.run(
        skill_registry.get("crasher", "1.0.0").manifest,
        SkillInput(skill_name="crasher", skill_version="1.0.0", arguments={}),
        bundle,
    )
    # A subsequent good run still works — the failure was contained and recoverable.
    ok = await skill_runner.run(
        skill_registry.get("writer", "1.0.0").manifest,
        SkillInput(
            skill_name="writer", skill_version="1.0.0", arguments={"name": "a.txt", "content": "x"}
        ),
        bundle,
    )
    assert ok.outcome is SkillOutcome.SUCCESS
