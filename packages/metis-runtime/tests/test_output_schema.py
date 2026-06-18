"""Skill I/O is schema-checked: violations are rejected, not passed through."""

from metis_protocol import SkillInput, SkillOutcome


async def test_output_violating_schema_is_rejected(skill_runner, skill_registry, bundle) -> None:
    loaded = skill_registry.get("bad_output", "1.0.0")
    result = await skill_runner.run(
        loaded.manifest,
        SkillInput(skill_name="bad_output", skill_version="1.0.0", arguments={}),
        bundle,
    )
    assert result.outcome is SkillOutcome.REJECTED
    assert "output schema" in (result.error or "")


async def test_input_violating_schema_is_rejected(skill_runner, skill_registry, bundle) -> None:
    loaded = skill_registry.get("writer", "1.0.0")
    result = await skill_runner.run(
        loaded.manifest,
        SkillInput(
            skill_name="writer", skill_version="1.0.0", arguments={"name": "x"}
        ),  # no content
        bundle,
    )
    assert result.outcome is SkillOutcome.REJECTED
    assert "input schema" in (result.error or "")
