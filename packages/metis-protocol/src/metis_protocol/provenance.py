"""Provenance model (W3C PROV-inspired): how every artifact came to be.

``Provenance`` is embedded on every :class:`~metis_protocol.artifacts.Artifact`.
``ModelRun`` is the carrier of the cross-stage invariant that *every model call*
records task class, model, prompt version, sensitivity, token/cost metadata, and
an audit hash.
"""

from __future__ import annotations

from pydantic import AwareDatetime

from metis_protocol.base import ProtocolModel
from metis_protocol.enums import AgentKind, Sensitivity
from metis_protocol.ids import ModelRunId, WorkspaceId
from metis_protocol.tasks import ModelTaskClass
from metis_protocol.versioning import VersionedModel


class Attribution(ProtocolModel):
    """Who/what produced an artifact (PROV ``Agent`` + attribution)."""

    agent_kind: AgentKind
    agent: str  # connector name, model id, skill name, user id, ...
    role: str | None = None


class ModelRun(VersionedModel):
    """Metadata for a single LLM call."""

    id: ModelRunId
    task_class: ModelTaskClass
    provider: str
    model: str
    model_version: str | None = None
    prompt_version: str | None = None
    sensitivity: Sensitivity
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    latency_ms: float | None = None
    cache_hit: bool | None = None
    audit_hash: str | None = None
    started_at: AwareDatetime
    finished_at: AwareDatetime | None = None


class Derivation(ProtocolModel):
    """How an artifact was produced (PROV ``Activity`` + derivation)."""

    operation: str  # e.g. "parse", "segment", "extract_claims", "consolidate"
    inputs: tuple[str, ...] = ()  # IDs of the artifacts this was derived from
    model_run: ModelRun | None = None
    code_version: str | None = None


class Provenance(ProtocolModel):
    """The provenance envelope embedded on every artifact."""

    workspace_id: WorkspaceId
    attribution: Attribution
    derivation: Derivation | None = None  # None for raw, ingested-as-is artifacts
    trace_id: str | None = None
    received_at: AwareDatetime | None = None
