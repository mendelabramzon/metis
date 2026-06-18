"""Canonical example instances — exactly one per registered schema.

These power the committed JSON fixtures, seed the contract-test suites, and give
downstream stages ready-made, valid inputs. IDs and timestamps are fixed so the
fixtures regenerate deterministically (no spurious diffs).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from metis_protocol.artifacts import (
    NormalizedDoc,
    ParsedDoc,
    RawArtifact,
    Segment,
    SourceSpan,
)
from metis_protocol.audit import AuditEvent
from metis_protocol.claims import Claim, Entity, Event, ExtractionBatch
from metis_protocol.enums import (
    AgentKind,
    ArtifactKind,
    ContradictionStatus,
    EntityKind,
    ForesightStatus,
    MemoryOp,
    ProfileScope,
    SegmentKind,
    Sensitivity,
    SkillOutcome,
    WikiOp,
)
from metis_protocol.errors import SchemaVersionError
from metis_protocol.events import EventEnvelope, EventName, Job
from metis_protocol.ids import (
    ArtifactId,
    AuditId,
    BatchId,
    ClaimId,
    ContextBundleId,
    ContradictionId,
    DocId,
    EntityId,
    EnvelopeId,
    EventId,
    EvidenceSetId,
    ForesightId,
    JobId,
    MemCellId,
    MemoryPatchId,
    MemSceneId,
    ModelRunId,
    ParsedDocId,
    PrefixedId,
    ProfileId,
    QueryId,
    SegmentId,
    SkillResultId,
    SourceSpanId,
    WikiPageId,
    WikiPatchId,
    WorkspaceId,
)
from metis_protocol.memory import (
    Contradiction,
    Foresight,
    MemCell,
    MemoryPatch,
    MemScene,
    Profile,
    ProfileFact,
)
from metis_protocol.policy import PolicyState
from metis_protocol.provenance import Attribution, Derivation, ModelRun, Provenance
from metis_protocol.query import (
    ContextBundle,
    ContextSection,
    EvidenceSet,
    QueryRequest,
)
from metis_protocol.refs import (
    ArtifactRef,
    ClaimRef,
    EntityRef,
    MemCellRef,
    SourceSpanRef,
)
from metis_protocol.skills import SkillInput, SkillManifest, SkillResult
from metis_protocol.tasks import ModelTaskClass
from metis_protocol.versioning import SCHEMA_REGISTRY, VersionedModel
from metis_protocol.wiki import WikiPage, WikiPatch

_T = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
_T_LATER = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)


def _fixed[IdT: PrefixedId](id_type: type[IdT], n: int) -> IdT:
    """A deterministic ID of the given type: ``_fixed(ClaimId, 1)`` -> ``clm_0..01``."""
    return id_type(f"{id_type.prefix}_{n:032x}")


# Fixed IDs reused across examples.
WS = _fixed(WorkspaceId, 1)
ART = _fixed(ArtifactId, 1)
DOC = _fixed(DocId, 1)
PDOC = _fixed(ParsedDocId, 1)
SEG = _fixed(SegmentId, 1)
SPAN = _fixed(SourceSpanId, 1)
ENT = _fixed(EntityId, 1)
CLM1 = _fixed(ClaimId, 1)
CLM2 = _fixed(ClaimId, 2)
MC = _fixed(MemCellId, 1)
SCN = _fixed(MemSceneId, 1)

# Shared sub-objects (frozen, so safe to reuse).
ATTR = Attribution(agent_kind=AgentKind.EXTRACTOR, agent="baseline-extractor")
MODEL_RUN = ModelRun(
    id=_fixed(ModelRunId, 1),
    task_class=ModelTaskClass.EXTRACT_CLAIMS,
    provider="local",
    model="demo-1",
    prompt_version="extract_claims@1",
    sensitivity=Sensitivity.INTERNAL,
    input_tokens=128,
    output_tokens=64,
    started_at=_T,
    finished_at=_T,
)
DERIV = Derivation(operation="extract_claims", inputs=(ART, PDOC), model_run=MODEL_RUN)
PROV = Provenance(
    workspace_id=WS, attribution=ATTR, derivation=DERIV, trace_id="trace-1", received_at=_T
)
POLICY = PolicyState(sensitivity=Sensitivity.INTERNAL)
SPAN_REF = SourceSpanRef(source_span_id=SPAN, artifact_id=ART, doc_id=DOC)
ENTITY_REF = EntityRef(entity_id=ENT)
CLAIM_REF1 = ClaimRef(claim_id=CLM1)
CLAIM_REF2 = ClaimRef(claim_id=CLM2)
MC_REF = MemCellRef(mem_cell_id=MC)


def _envelope(id_: PrefixedId) -> dict[str, object]:
    """The shared Artifact envelope kwargs."""
    return {"id": id_, "provenance": PROV, "policy": POLICY, "created_at": _T}


def source_span() -> SourceSpan:
    return SourceSpan(id=SPAN, artifact_id=ART, doc_id=DOC, char_start=0, char_end=42, page=1)


def raw_artifact() -> RawArtifact:
    return RawArtifact(
        **_envelope(ART),
        kind=ArtifactKind.FILE,
        content_hash="0" * 64,
        media_type="text/plain",
        byte_size=42,
        storage_ref="raw/2026/01/demo.txt",
        filename="demo.txt",
    )


def normalized_doc() -> NormalizedDoc:
    return NormalizedDoc(
        **_envelope(DOC),
        artifact_id=ART,
        media_type="text/plain",
        text="Ada joined Acme as CTO in 2026.",
        title="demo.txt",
        lang="en",
    )


def parsed_doc() -> ParsedDoc:
    return ParsedDoc(
        **_envelope(PDOC), doc_id=DOC, segment_ids=(SEG,), title="demo.txt", page_count=1
    )


def segment() -> Segment:
    return Segment(
        **_envelope(SEG),
        parsed_doc_id=PDOC,
        doc_id=DOC,
        kind=SegmentKind.PARAGRAPH,
        order=0,
        text="Ada joined Acme as CTO in 2026.",
        char_start=0,
        char_end=31,
        page=1,
    )


def entity() -> Entity:
    return Entity(
        **_envelope(ENT),
        kind=EntityKind.PERSON,
        name="Ada Lovelace",
        aliases=("Ada",),
        description="Engineer",
        source_spans=(SPAN_REF,),
    )


def event() -> Event:
    return Event(
        **_envelope(_fixed(EventId, 1)),
        summary="Ada joined Acme as CTO.",
        occurred_at=_T,
        participants=(ENTITY_REF,),
        source_spans=(SPAN_REF,),
    )


def claim() -> Claim:
    return Claim(
        **_envelope(CLM1),
        text="Ada is the CTO of Acme.",
        predicate="role_of",
        subject_ref=ENTITY_REF,
        source_spans=(SPAN_REF,),
        confidence=0.9,
    )


def extraction_batch() -> ExtractionBatch:
    return ExtractionBatch(
        id=_fixed(BatchId, 1),
        workspace_id=WS,
        parsed_doc_id=PDOC,
        provenance=PROV,
        claims=(claim(),),
        entities=(entity(),),
        events=(event(),),
    )


def mem_cell() -> MemCell:
    return MemCell(
        **_envelope(MC),
        summary="Ada became Acme's CTO in 2026.",
        content="On 2026-01-01, Ada Lovelace joined Acme as CTO.",
        claims=(CLAIM_REF1,),
        source_spans=(SPAN_REF,),
        occurred_at=_T,
        salience=0.7,
    )


def mem_scene() -> MemScene:
    return MemScene(
        **_envelope(SCN),
        title="Acme leadership",
        summary="Leadership changes at Acme.",
        mem_cells=(MC_REF,),
        claims=(CLAIM_REF1,),
        topic="org",
        started_at=_T,
    )


def profile() -> Profile:
    return Profile(
        **_envelope(_fixed(ProfileId, 1)),
        scope=ProfileScope.COMPANY,
        label="Acme",
        subject=ENTITY_REF,
        facts=(ProfileFact(key="cto", value="Ada Lovelace", claims=(CLAIM_REF1,)),),
    )


def foresight() -> Foresight:
    return Foresight(
        **_envelope(_fixed(ForesightId, 1)),
        statement="Acme will announce a new product line.",
        predicted_state="product_launch",
        valid_from=_T,
        valid_to=_T_LATER,
        status=ForesightStatus.ACTIVE,
        claims=(CLAIM_REF1,),
        confidence=0.6,
    )


def contradiction() -> Contradiction:
    return Contradiction(
        **_envelope(_fixed(ContradictionId, 1)),
        summary="Conflicting CTO claims.",
        explanation="One source says Ada is CTO; another says Grace is CTO.",
        status=ContradictionStatus.OPEN,
        claims=(CLAIM_REF1, CLAIM_REF2),
    )


def memory_patch() -> MemoryPatch:
    return MemoryPatch(
        **_envelope(_fixed(MemoryPatchId, 1)),
        op=MemoryOp.SUPERSEDE,
        target_id=MC,
        supersedes_id=str(_fixed(MemCellId, 2)),
        reason="Newer evidence corrects the role.",
    )


def wiki_page() -> WikiPage:
    return WikiPage(
        **_envelope(_fixed(WikiPageId, 1)),
        title="Ada Lovelace",
        slug="ada-lovelace",
        body_markdown="Ada is the CTO of Acme.[^clm1]",
        claims=(CLAIM_REF1,),
        entity=ENTITY_REF,
    )


def wiki_patch() -> WikiPatch:
    return WikiPatch(
        **_envelope(_fixed(WikiPatchId, 1)),
        op=WikiOp.CREATE,
        title="Ada Lovelace",
        slug="ada-lovelace",
        body_markdown="Ada is the CTO of Acme.[^clm1]",
        claims=(CLAIM_REF1,),
        rationale="New entity page from extracted claims.",
    )


def query_request() -> QueryRequest:
    return QueryRequest(
        id=_fixed(QueryId, 1),
        workspace_id=WS,
        text="Who is the CTO of Acme?",
        max_sensitivity=Sensitivity.CONFIDENTIAL,
        top_k=10,
    )


def evidence_set() -> EvidenceSet:
    return EvidenceSet(
        id=_fixed(EvidenceSetId, 1),
        query_id=_fixed(QueryId, 1),
        claims=(CLAIM_REF1,),
        source_spans=(SPAN_REF,),
    )


def context_bundle() -> ContextBundle:
    return ContextBundle(
        id=_fixed(ContextBundleId, 1),
        query_id=_fixed(QueryId, 1),
        sections=(
            ContextSection(heading="CTO", text="Ada is the CTO of Acme.", claims=(CLAIM_REF1,)),
        ),
        token_estimate=64,
        sufficiency=0.8,
    )


def skill_manifest() -> SkillManifest:
    return SkillManifest(
        name="deep_web_search",
        version="1.0.0",
        description="Search the web and summarize.",
        network=True,
        requires_approval=True,
        timeout_seconds=120.0,
    )


def skill_input() -> SkillInput:
    return SkillInput(
        skill_name="deep_web_search",
        skill_version="1.0.0",
        arguments={"query": "Acme CTO"},
        context_bundle_id=_fixed(ContextBundleId, 1),
    )


def skill_result() -> SkillResult:
    return SkillResult(
        **_envelope(_fixed(SkillResultId, 1)),
        skill_name="deep_web_search",
        skill_version="1.0.0",
        outcome=SkillOutcome.SUCCESS,
        output={"summary": "Ada Lovelace is the CTO of Acme."},
        artifacts=(ArtifactRef(artifact_id=ART),),
    )


def audit_event() -> AuditEvent:
    return AuditEvent(
        id=_fixed(AuditId, 1),
        workspace_id=WS,
        occurred_at=_T,
        actor=ATTR,
        action="model.call",
        target_id=str(CLM1),
        target_kind="Claim",
        model_run=MODEL_RUN,
        sensitivity=Sensitivity.INTERNAL,
    )


def event_envelope() -> EventEnvelope:
    return EventEnvelope(
        envelope_id=_fixed(EnvelopeId, 1),
        event_name=EventName.CLAIMS_EXTRACTED,
        event_version=1,
        occurred_at=_T,
        workspace_id=WS,
        trace_id="trace-1",
        payload_schema_version="1.0",
        payload={"note": "example payload"},
    )


def job() -> Job:
    return Job(
        id=_fixed(JobId, 1),
        workspace_id=WS,
        kind="ingest_artifact",
        payload={"artifact_id": str(ART)},
        created_at=_T,
    )


#: One builder per registered schema name.
EXAMPLE_BUILDERS: dict[str, Callable[[], VersionedModel]] = {
    "SourceSpan": source_span,
    "RawArtifact": raw_artifact,
    "NormalizedDoc": normalized_doc,
    "ParsedDoc": parsed_doc,
    "Segment": segment,
    "Entity": entity,
    "Event": event,
    "Claim": claim,
    "ExtractionBatch": extraction_batch,
    "MemCell": mem_cell,
    "MemScene": mem_scene,
    "Profile": profile,
    "Foresight": foresight,
    "Contradiction": contradiction,
    "MemoryPatch": memory_patch,
    "WikiPage": wiki_page,
    "WikiPatch": wiki_patch,
    "QueryRequest": query_request,
    "EvidenceSet": evidence_set,
    "ContextBundle": context_bundle,
    "SkillManifest": skill_manifest,
    "SkillInput": skill_input,
    "SkillResult": skill_result,
    "AuditEvent": audit_event,
    "EventEnvelope": event_envelope,
    "Job": job,
}


def build_examples() -> dict[str, VersionedModel]:
    """Build one example per registered schema, asserting full coverage."""
    examples = {name: build() for name, build in EXAMPLE_BUILDERS.items()}
    registered = set(SCHEMA_REGISTRY)
    missing = registered - set(examples)
    extra = set(examples) - registered
    if missing or extra:
        raise SchemaVersionError(f"example coverage mismatch: missing={missing} extra={extra}")
    return examples
