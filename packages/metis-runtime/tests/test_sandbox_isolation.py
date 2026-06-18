"""A skill cannot reach undeclared secrets, connectors, or network (the security contract)."""

from metis_protocol import SkillInput, SkillOutcome
from metis_runtime.skills import SkillPolicy


async def test_skill_without_declarations_sees_no_capabilities(
    skill_runner, skill_registry, bundle, monkeypatch
) -> None:
    # Even with the secret present in the parent environment, the scrubbed sandbox env hides it.
    monkeypatch.setenv("METIS_TEST_SECRET", "leak")
    loaded = skill_registry.get("probe", "1.0.0")

    result = await skill_runner.run(
        loaded.manifest,
        SkillInput(skill_name="probe", skill_version="1.0.0", arguments={}),
        bundle,
    )

    assert result.outcome is SkillOutcome.SUCCESS
    assert result.output == {"saw_secret": False, "connectors": [], "network": False}


def test_policy_denies_everything_not_declared(skill_registry) -> None:
    policy = SkillPolicy(skill_registry.get("probe", "1.0.0").manifest)
    assert not policy.allows_connector("slack")  # undeclared connector
    assert not policy.allows_network()  # network not declared
    assert not policy.allows_secrets()  # SECRETS permission not declared
