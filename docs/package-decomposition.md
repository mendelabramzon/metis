# Metis Engine Package Decomposition

This document shows the proposed responsibility zones and interconnections for a swappable Metis engine architecture.

Core rule: packages depend inward on shared contracts, but runtime data moves through versioned artifacts, events, and core storage APIs.

## Responsibility Map

```mermaid
flowchart TB
    protocol["metis-protocol<br/>Shared contracts<br/>Schemas, events, interfaces, policy vocabulary"]

    core["metis-core<br/>Durable substrate<br/>Artifact store, claim store, memory store, wiki store, audit, jobs"]

    ingestion["metis-ingestion<br/>Evidence production<br/>Connectors, parsers, segmentation, extraction"]

    maintainer["metis-maintainer<br/>Memory maintenance<br/>Contradictions, episode revision, consolidation, foresight, wiki patches"]

    runtime["metis-runtime<br/>User-facing intelligence<br/>Chat, retrieval, context packing, skill execution, action approval"]

    skills["metis-skills<br/>Reusable capabilities<br/>Python skill packages, templates, fixtures, tests"]

    deploy["metis-deploy<br/>Operations<br/>Compose, migrations wiring, env profiles, observability"]

    protocol --> core
    protocol --> ingestion
    protocol --> maintainer
    protocol --> runtime
    protocol --> skills

    core <--> ingestion
    core <--> maintainer
    core <--> runtime

    skills --> runtime
    skills -. optional ingestion enrichers .-> ingestion

    deploy -. runs .-> core
    deploy -. runs .-> ingestion
    deploy -. runs .-> maintainer
    deploy -. runs .-> runtime
```

## Dependency Direction

`metis-protocol` is the lowest-level shared package. It must not import from any other Metis package.

```mermaid
graph LR
    protocol["metis-protocol"]
    core["metis-core"]
    ingestion["metis-ingestion"]
    maintainer["metis-maintainer"]
    runtime["metis-runtime"]
    skills["metis-skills"]
    deploy["metis-deploy"]

    core --> protocol
    ingestion --> protocol
    maintainer --> protocol
    runtime --> protocol
    skills --> protocol

    ingestion --> core
    maintainer --> core
    runtime --> core

    runtime --> skills
    ingestion -. controlled use .-> skills

    deploy --> core
    deploy --> ingestion
    deploy --> maintainer
    deploy --> runtime
```

Allowed:

| Package | May depend on | Must not own |
|---|---|---|
| `metis-protocol` | Third-party schema/runtime basics only | Database code, LLM calls, connector code, skill execution |
| `metis-core` | `metis-protocol` | Source connectors, chat planning, skill logic |
| `metis-ingestion` | `metis-protocol`, `metis-core` | Background memory revision, user action execution |
| `metis-maintainer` | `metis-protocol`, `metis-core` | Connectors, UI/chat runtime, outbound actions |
| `metis-runtime` | `metis-protocol`, `metis-core`, `metis-skills` | Canonical ingestion parsing, storage internals |
| `metis-skills` | `metis-protocol` | Core stores, long-running schedulers |
| `metis-deploy` | All runtime packages | Business logic |

## Runtime Artifact Flow

```mermaid
sequenceDiagram
    participant Source as External Sources
    participant Ingest as metis-ingestion
    participant Core as metis-core
    participant Maint as metis-maintainer
    participant Runtime as metis-runtime
    participant Skills as metis-skills

    Source->>Ingest: discover/fetch
    Ingest->>Core: store RawArtifact
    Core-->>Ingest: artifact_id

    Ingest->>Ingest: normalize, parse, segment, extract
    Ingest->>Core: write NormalizedDoc, Segment, Claim, Entity, Event, MemCell
    Core-->>Maint: emit claims.extracted / memcell.created

    Maint->>Core: read claims, memcells, scenes, profiles
    Maint->>Maint: detect contradictions, revise episodes, build foresights
    Maint->>Core: write MemoryPatch, Contradiction, Foresight, WikiPatch

    Runtime->>Core: retrieve evidence and memory
    Runtime->>Runtime: plan, pack context, verify sufficiency
    Runtime->>Skills: run approved skill package
    Skills-->>Runtime: SkillResult and generated artifacts
    Runtime->>Core: write answer artifact, action log, optional file-back/wiki patch
```

## Core Truth Hierarchy

```mermaid
flowchart LR
    raw["RawArtifact<br/>Evidence truth"]
    extracted["Claims, entities, events<br/>Machine truth"]
    memory["MemCells, scenes, profile, foresights<br/>Interpreted memory"]
    wiki["Wiki pages<br/>Compiled human-facing projection"]
    runtime["Answers and actions<br/>Runtime products"]

    raw --> extracted
    extracted --> memory
    memory --> wiki
    extracted --> wiki
    memory --> runtime
    extracted --> runtime
    wiki --> runtime

    runtime -. file-back .-> extracted
    runtime -. proposed patch .-> wiki
```

The wiki is important, but it should not be the machine source of truth. It should compile from claim IDs, memory objects, source spans, and validation state.

## Swappable Interfaces

These interfaces live in `metis-protocol`. Implementations live in the owning package.

```mermaid
classDiagram
    class Connector {
        <<Protocol>>
        discover(cursor) SourceRef[]
        fetch(ref) RawArtifact
        normalize(raw) NormalizedDoc
    }

    class Extractor {
        <<Protocol>>
        extract(parsed_doc) ExtractionBatch
    }

    class Consolidator {
        <<Protocol>>
        consolidate(batch) MemoryPatch
    }

    class ContradictionDetector {
        <<Protocol>>
        detect(scope) Contradiction[]
    }

    class ForesightBuilder {
        <<Protocol>>
        build(scope) Foresight[]
    }

    class Retriever {
        <<Protocol>>
        retrieve(query) EvidenceSet
    }

    class ContextPacker {
        <<Protocol>>
        pack(query, evidence) ContextBundle
    }

    class Skill {
        <<Protocol>>
        run(input, context) SkillResult
    }

    class ArtifactStore {
        <<Protocol>>
        put(raw) ArtifactRef
        get(ref) RawArtifact
    }

    class ClaimStore {
        <<Protocol>>
        write(batch) ClaimWriteResult
        query(filter) Claim[]
    }
```

Example implementation ownership:

| Interface | Example implementation | Owning package |
|---|---|---|
| `Connector` | `SlackConnector`, `LocalFolderConnector`, `ImapConnector` | `metis-ingestion` |
| `Extractor` | `PdfExtractor`, `DocxExtractor`, `EmailThreadExtractor` | `metis-ingestion` |
| `Consolidator` | `SceneConsolidator` | `metis-maintainer` |
| `ContradictionDetector` | `ClaimContradictionDetector` | `metis-maintainer` |
| `ForesightBuilder` | `TimelineForesightBuilder` | `metis-maintainer` |
| `Retriever` | `HybridRetriever`, `SceneRetriever` | `metis-runtime` |
| `ContextPacker` | `BudgetedContextPacker` | `metis-runtime` |
| `Skill` | `DeepWebSearchSkill`, `ExcelAnalysisSkill`, `WordReportSkill` | `metis-skills`, executed by `metis-runtime` |
| `ArtifactStore` | `PostgresMinioArtifactStore` | `metis-core` |
| `ClaimStore` | `PostgresClaimStore` | `metis-core` |

## Skill Placement

```mermaid
flowchart TB
    manifest["Skill package<br/>SKILL.md, manifest.yaml, input schema, output schema, main.py, tests"]
    runtime["metis-runtime<br/>Primary executor"]
    ingestion["metis-ingestion<br/>Optional controlled executor"]
    core["metis-core<br/>Stores results and audit"]

    manifest --> runtime
    manifest -. restricted ingestion mode .-> ingestion

    runtime -->|"deep web search, Excel, Word, browser automation, actions"| core
    ingestion -->|"file parsing, table extraction, metadata enrichment"| core
```

Skill usage modes:

| Mode | Owner | Allowed behavior |
|---|---|---|
| Query/action mode | `metis-runtime` | Search, analyze files, generate reports, execute approved actions, write answer artifacts |
| Ingestion enrichment mode | `metis-ingestion` | Parse unusual files, extract tables, classify docs, enrich metadata |
| Maintenance mode | `metis-maintainer` | Specialized lint, contradiction scans, repair proposals |

Ingestion-mode skills should not directly edit the wiki, revise memory, send messages, or perform broad network actions unless the manifest and policy explicitly allow it.

## Package Contract Summary

```mermaid
flowchart TD
    protocol["metis-protocol defines<br/>what messages mean"]
    core["metis-core enforces<br/>what gets persisted"]
    ingestion["metis-ingestion produces<br/>evidence"]
    maintainer["metis-maintainer improves<br/>memory"]
    runtime["metis-runtime uses<br/>memory to answer and act"]
    skills["metis-skills extends<br/>runtime capabilities"]

    protocol --> core
    protocol --> ingestion
    protocol --> maintainer
    protocol --> runtime
    protocol --> skills

    ingestion -->|"versioned artifacts/events"| core
    maintainer -->|"memory patches/wiki patches"| core
    runtime -->|"queries/action logs/file-back"| core
    skills -->|"skill result artifacts"| runtime
```
