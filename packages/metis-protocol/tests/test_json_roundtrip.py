"""Every schema round-trips through JSON with equality preserved.

The committed fixtures are the canonical examples (regenerate with
``scripts/regenerate.py`` if a fixture assertion fails), plus a hypothesis
property test for character-offset edge cases.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from metis_protocol.artifacts import SourceSpan
from metis_protocol.examples import EXAMPLE_BUILDERS
from metis_protocol.ids import ArtifactId, SourceSpanId, new_id
from metis_protocol.versioning import SCHEMA_REGISTRY

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


@pytest.mark.parametrize("name", sorted(SCHEMA_REGISTRY))
def test_fixture_roundtrips_and_matches_example(name: str) -> None:
    model = SCHEMA_REGISTRY[name]
    loaded = model.model_validate_json((_FIXTURES / f"{name}.json").read_text())
    # The fixture is the canonical example; regenerate fixtures if this drifts.
    assert loaded == EXAMPLE_BUILDERS[name]()
    # Equality survives a full JSON round-trip.
    assert model.model_validate_json(loaded.model_dump_json()) == loaded


@given(
    start=st.integers(min_value=0, max_value=10**9),
    length=st.integers(min_value=0, max_value=10**9),
)
def test_source_span_roundtrips_over_offsets(start: int, length: int) -> None:
    span = SourceSpan(
        id=new_id(SourceSpanId),
        artifact_id=new_id(ArtifactId),
        char_start=start,
        char_end=start + length,
    )
    assert SourceSpan.model_validate_json(span.model_dump_json()) == span
