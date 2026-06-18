"""Structural invariants across all schemas.

Every artifact carries id + schema_version + provenance + policy, and the
evidence-citation minimums (a claim cites >=1 span, a contradiction >=2 claims,
etc.) hold by construction.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from metis_protocol.artifacts import Artifact
from metis_protocol.examples import EXAMPLE_BUILDERS
from metis_protocol.versioning import SCHEMA_REGISTRY

_ARTIFACT_NAMES = sorted(
    name for name, model in SCHEMA_REGISTRY.items() if issubclass(model, Artifact)
)
_REQUIRED_ARTIFACT_FIELDS = {"id", "schema_version", "provenance", "policy", "created_at"}


def test_registry_contains_artifacts() -> None:
    assert _ARTIFACT_NAMES  # guard against the introspection silently matching nothing


@pytest.mark.parametrize("name", _ARTIFACT_NAMES)
def test_artifact_declares_required_fields(name: str) -> None:
    fields = set(SCHEMA_REGISTRY[name].model_fields)
    assert fields >= _REQUIRED_ARTIFACT_FIELDS


@pytest.mark.parametrize("name", _ARTIFACT_NAMES)
def test_artifact_example_carries_provenance_and_policy(name: str) -> None:
    obj = EXAMPLE_BUILDERS[name]()
    dumped = obj.model_dump()
    assert dumped["provenance"]["workspace_id"]
    assert "sensitivity" in dumped["policy"]


@pytest.mark.parametrize(
    ("name", "field", "min_items"),
    [
        ("Claim", "source_spans", 1),
        ("MemCell", "source_spans", 1),
        ("Foresight", "claims", 1),
        ("Contradiction", "claims", 2),
    ],
)
def test_evidence_minimums_enforced(name: str, field: str, min_items: int) -> None:
    model = SCHEMA_REGISTRY[name]
    data = EXAMPLE_BUILDERS[name]().model_dump()
    data[field] = data[field][: min_items - 1]  # one short of the minimum
    with pytest.raises(ValidationError):
        model.model_validate(data)
