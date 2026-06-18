"""Skill schemas: the manifest that declares a capability's permissions, the input
to a run, and the audited result.
"""

from __future__ import annotations

from pydantic import Field, JsonValue

from metis_protocol.artifacts import Artifact
from metis_protocol.enums import ModelTier, PermissionScope, Sensitivity, SkillOutcome
from metis_protocol.ids import ContextBundleId, SkillResultId
from metis_protocol.refs import ArtifactRef
from metis_protocol.versioning import VersionedModel, schema


@schema
class SkillManifest(VersionedModel):
    """Declares a skill and the policy envelope it runs under. Natural key: name+version."""

    name: str
    version: str
    description: str = ""
    entrypoint: str = "main:run"
    permissions: tuple[PermissionScope, ...] = ()
    network: bool = False
    allowed_connectors: tuple[str, ...] = ()
    allowed_model_tiers: tuple[ModelTier, ...] = ()
    sensitivity_ceiling: Sensitivity = Sensitivity.INTERNAL
    requires_approval: bool = True
    timeout_seconds: float | None = Field(default=None, gt=0.0)
    max_output_bytes: int | None = Field(default=None, ge=0)


@schema
class SkillInput(VersionedModel):
    """The arguments and context handed to a skill run."""

    skill_name: str
    skill_version: str
    arguments: JsonValue = Field(default_factory=dict)
    context_bundle_id: ContextBundleId | None = None


@schema
class SkillResult(Artifact[SkillResultId]):
    """The audited outcome of a skill run, including any generated artifacts."""

    skill_name: str
    skill_version: str
    outcome: SkillOutcome
    output: JsonValue = Field(default_factory=dict)
    artifacts: tuple[ArtifactRef, ...] = ()
    logs: str | None = None
    error: str | None = None
    approval_required: bool = False
