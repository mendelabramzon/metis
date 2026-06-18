"""The skill package format: the loader validates packages and the example skill runs."""

import importlib.util

import pytest

from metis_skills import SkillFormatError, bundled_skills_root, load_skill


def _run(main_path) -> object:
    spec = importlib.util.spec_from_file_location("skill_under_test", main_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.run


def test_text_stats_loads_with_its_declared_contract() -> None:
    skill = load_skill(bundled_skills_root() / "text_stats")
    assert skill.manifest.name == "text_stats"
    assert skill.manifest.requires_approval is False
    assert skill.manifest.network is False
    assert skill.input_schema["required"] == ["text"]


def test_text_stats_runs() -> None:
    run = _run((bundled_skills_root() / "text_stats").joinpath("main.py"))
    assert run({"text": "hello world\nsecond line"}, {}) == {
        "words": 4,
        "characters": 23,
        "lines": 2,
    }


def test_malformed_package_fails_to_load(tmp_path) -> None:
    (tmp_path / "manifest.yaml").write_text('name: broken\nversion: "1.0.0"\n')
    # No input/output schemas and no main.py -> must fail closed, not load partially.
    with pytest.raises(SkillFormatError):
        load_skill(tmp_path)
