"""Generated artifacts are stored (object store) and audited."""

from metis_protocol import SkillInput, SkillOutcome


async def test_generated_file_is_captured_and_audited(
    skill_runner, skill_registry, bundle, object_store, audit_sink
) -> None:
    loaded = skill_registry.get("writer", "1.0.0")
    result = await skill_runner.run(
        loaded.manifest,
        SkillInput(
            skill_name="writer",
            skill_version="1.0.0",
            arguments={"name": "report.txt", "content": "hello world"},
        ),
        bundle,
    )

    assert result.outcome is SkillOutcome.SUCCESS
    assert len(result.artifacts) == 1  # the written file became a captured artifact
    assert object_store.objects  # ...stored in the object store
    assert b"hello world" in object_store.objects.values()
    assert any(event.action == "skill.artifact.captured" for event in audit_sink.events)
    assert any(event.action == "skill.run.finished" for event in audit_sink.events)
