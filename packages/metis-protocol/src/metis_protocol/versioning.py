"""Schema versioning and the JSON-Schema export registry.

Versioning is additive: a backward-compatible change keeps the same
``schema_version``; a breaking change bumps it. ``extra="forbid"`` (from
``ProtocolModel``) makes drift loud, and the snapshot test forces an intentional
bump rather than a silent break.
"""

from __future__ import annotations

from typing import Annotated, Final

from pydantic import Field, StringConstraints

from metis_protocol.base import ProtocolModel
from metis_protocol.errors import SchemaVersionError

#: A ``"<major>.<minor>"`` version string.
SchemaVersion = Annotated[str, StringConstraints(pattern=r"^\d+\.\d+$")]

SCHEMA_VERSION_V1: Final[SchemaVersion] = "1.0"


class VersionedModel(ProtocolModel):
    """A protocol model that carries its schema version."""

    schema_version: SchemaVersion = Field(default=SCHEMA_VERSION_V1)


#: Top-level schemas exported to JSON Schema and snapshot-tested.
SCHEMA_REGISTRY: dict[str, type[VersionedModel]] = {}


def schema[M: VersionedModel](cls: type[M]) -> type[M]:
    """Class decorator: register a top-level schema for export and snapshots."""
    existing = SCHEMA_REGISTRY.get(cls.__name__)
    if existing is not None and existing is not cls:
        raise SchemaVersionError(f"duplicate schema name registered: {cls.__name__}")
    SCHEMA_REGISTRY[cls.__name__] = cls
    return cls


def export_json_schema(model: type[VersionedModel]) -> dict[str, object]:
    """Return the JSON Schema for a single model."""
    return model.model_json_schema()


def export_all_schemas() -> dict[str, dict[str, object]]:
    """Return ``{schema_name: json_schema}`` for every registered schema, sorted."""
    return {name: model.model_json_schema() for name, model in sorted(SCHEMA_REGISTRY.items())}
