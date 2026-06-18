# Frontier Approaches For Metis

Last reviewed: 2026-06-18.

This file maps the major research directions we should use while building Metis. The intended architecture is not "plain RAG"; it is an evidence-first memory engine with a compiled wiki projection, background maintenance, and action-capable skills.

## Design Stance

Metis should combine four lines of work:

1. Retrieval-augmented generation for grounded access to external knowledge.
2. Long-term agent memory for evolving user/workspace state.
3. Structured/graph/wiki memory for multi-hop and global workspace reasoning.
4. Agent tool execution for deep search, document work, spreadsheets, and actions.

The key product constraint: every generated memory, wiki page, answer, and action must trace back to source spans, claim IDs, policy state, and model/prompt versions.

## Core Memory And Wiki Layer

| Reference | Link | Use In Metis | Stance |
|---|---|---|---|
| EverMemOS: A Self-Organizing Memory Operating System for Structured Long-Horizon Reasoning | https://arxiv.org/abs/2601.02163 | MemCell/MemScene/Foresight lifecycle; reconstructive recollection; background profile updates; sufficiency-driven retrieval. | Adopt as primary memory lifecycle inspiration, but adapt beyond chat to documents, files, and workspace events. |
| Retrieval as Reasoning: Self-Evolving Agent-Native Retrieval via LLM-Wiki | https://arxiv.org/abs/2605.25480 | Wiki as navigable, self-evolving, agent-native retrieval substrate; file-back; Error Book pattern. | Adopt the wiki/tooling idea, but keep claims and raw evidence as machine truth. |
| WiCER: Wiki-memory Compile, Evaluate, Refine Iterative Knowledge Compilation for LLM Wiki Systems | https://arxiv.org/abs/2605.07068 | Compile/evaluate/refine loop for wiki pages; diagnostic probes for dropped facts; prevent blind lossy compilation. | Strongly adopt for wiki compiler and regression tests. |
| MemGPT: Towards LLMs as Operating Systems | https://arxiv.org/abs/2310.08560 | Virtual context management; tiered memory; explicit movement between short/long-term memory. | Adopt conceptually for context/memory tiers, not necessarily implementation. |
| Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory | https://arxiv.org/abs/2504.19413 | Practical long-term memory extraction, consolidation, retrieval, graph memory comparison, latency/cost framing. | Benchmark against. Useful for production constraints. |
| Zep: A Temporal Knowledge Graph Architecture for Agent Memory | https://arxiv.org/abs/2501.13956 | Temporal graph memory; enterprise-style cross-session temporal reasoning. | Watch/adapt for temporal KG design. |
| Generative Agents: Interactive Simulacra of Human Behavior | https://arxiv.org/abs/2304.03442 | Memory/reflection/planning loop; reflection as scheduled maintenance. | Historical foundation for maintainer jobs. |

## Retrieval And Context Construction

| Reference | Link | Use In Metis | Stance |
|---|---|---|---|
| Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks | https://arxiv.org/abs/2005.11401 | Baseline grounding architecture: parametric model plus external non-parametric memory. | Baseline only; Metis should exceed flat RAG. |
| BEIR: A Heterogeneous Benchmark for Zero-shot Evaluation of Information Retrieval Models | https://arxiv.org/abs/2104.08663 | Retriever evaluation discipline; BM25 as serious baseline; cross-domain robustness. | Use to guide retrieval benchmarks. |
| ColBERT: Efficient and Effective Passage Search via Contextualized Late Interaction | https://arxiv.org/abs/2004.12832 | Late-interaction reranking/retrieval for high-quality evidence selection. | Benchmark if pgvector/BM25 is not enough. |
| SPLADE: Sparse Lexical and Expansion Model for First Stage Ranking | https://arxiv.org/abs/2107.05720 | Learned sparse retrieval as a stronger lexical layer than BM25. | Watch; adopt only if simple FTS underperforms. |
| HyDE: Precise Zero-Shot Dense Retrieval without Relevance Labels | https://arxiv.org/abs/2212.10496 | Query expansion via hypothetical document embeddings. | Use as optional query rewrite strategy. |
| Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection | https://arxiv.org/abs/2310.11511 | Decide when retrieval is needed; critique retrieved evidence and generations. | Use as design pattern for verifier/sufficiency checks. |
| Corrective Retrieval Augmented Generation | https://arxiv.org/abs/2401.15884 | Retrieval quality evaluator; corrective path to web search or alternate retrieval when local context is weak. | Adopt pattern for runtime fallback and deep-search skills. |
| RAPTOR: Recursive Abstractive Processing for Tree-Organized Retrieval | https://arxiv.org/abs/2401.18059 | Hierarchical summaries for long documents and global questions. | Use selectively for document-level summaries and scene summaries. |
| Recursive Abstractive Processing for Retrieval in Dynamic Datasets | https://arxiv.org/abs/2410.01736 | Updating RAPTOR-style summaries under changing data. | Watch if hierarchical summaries become central. |

## Graph, Wiki, And Global Reasoning

| Reference | Link | Use In Metis | Stance |
|---|---|---|---|
| From Local to Global: A Graph RAG Approach to Query-Focused Summarization | https://arxiv.org/abs/2404.16130 | Entity graph plus community summaries for broad workspace questions. | Adopt the local/global distinction; avoid expensive full GraphRAG initially. |
| LightRAG: Simple and Fast Retrieval-Augmented Generation | https://arxiv.org/abs/2410.05779 | Lightweight graph/text dual-level retrieval with incremental update concerns. | Benchmark for graph retrieval design. |
| HippoRAG: Neurobiologically Inspired Long-Term Memory for LLMs | https://arxiv.org/abs/2405.14831 | KG plus Personalized PageRank for associative multi-hop retrieval. | Use as graph retrieval inspiration. |
| From RAG to Memory: Non-Parametric Continual Learning for LLMs / HippoRAG 2 | https://arxiv.org/abs/2502.14802 | Improve factual, sense-making, and associative memory beyond vector retrieval. | Benchmark for memory retrieval. |
| RAG vs. GraphRAG: A Systematic Evaluation and Key Insights | https://arxiv.org/abs/2502.11371 | Decide when graph retrieval helps and when plain/hybrid RAG is better. | Use to avoid graph overengineering. |
| LEGO-GraphRAG: Modularizing Graph-based RAG | https://arxiv.org/abs/2411.05844 | Decompose graph RAG design space into swappable blocks. | Useful for `metis-protocol` interfaces. |
| PersonalAI 2.0 | https://arxiv.org/abs/2605.13481 | Dynamic multistage graph traversal and clue-query planning for personalized agents. | Watch; relevant to future runtime planner. |

## Document Ingestion And Structured Extraction

| Reference | Link | Use In Metis | Stance |
|---|---|---|---|
| Docling Technical Report | https://arxiv.org/abs/2408.09869 | PDF conversion, layout analysis, table recognition, markdown/document representation. | Adopt or benchmark for PDF/DOC ingestion. |
| Docling: An Efficient Open-Source Toolkit for AI-driven Document Conversion | https://arxiv.org/abs/2501.17887 | Unified structured representation for popular document formats. | Strong candidate for ingestion package. |
| Document Parsing Unveiled: Techniques, Challenges, and Prospects for Structured Information Extraction | https://arxiv.org/abs/2410.21169 | Survey of layout detection, tables, formulas, VLM parsing, and parsing failure modes. | Use as design checklist for parsers. |

Metis ingestion should output layered artifacts:

```text
RawArtifact -> NormalizedDoc -> ParsedDoc -> Segment -> Claim/Event/Entity -> MemCell
```

Do not let a parser directly produce final memory or wiki pages. It should produce evidence and structured extraction batches.

## Agent Skills And Action Runtime

| Reference | Link | Use In Metis | Stance |
|---|---|---|---|
| ReAct: Synergizing Reasoning and Acting in Language Models | https://arxiv.org/abs/2210.03629 | Interleaved reasoning/action/observation loop. | Foundational runtime pattern. |
| Toolformer: Language Models Can Teach Themselves to Use Tools | https://arxiv.org/abs/2302.04761 | Tool-selection framing: when to call APIs, with what arguments, and how to use results. | Conceptual reference. |
| Gorilla: Large Language Model Connected with Massive APIs | https://arxiv.org/abs/2305.15334 | API selection with retrieval over tool docs; reducing hallucinated tool calls. | Use for skill registry/tool-doc retrieval. |
| Executable Code Actions Elicit Better LLM Agents / CodeAct | https://arxiv.org/abs/2402.01030 | Python code as compositional action space for data work, Excel, Word, scraping, analysis. | Strongly relevant to skill execution. Must pair with sandboxing. |
| OpenCodeInterpreter | https://arxiv.org/abs/2402.14658 | Generate-execute-refine loop for Python tasks. | Reference for skill error-recovery. |
| Voyager: An Open-Ended Embodied Agent with LLMs | https://arxiv.org/abs/2305.16291 | Skill library as compounding executable capabilities. | Use conceptually for skill reuse/versioning. |
| SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering | https://arxiv.org/abs/2405.15793 | Agent-computer interface design; shell/file operations as first-class UX for agents. | Relevant to sandbox and tool ergonomics. |

Metis skill rule:

```text
Skills may generate code and perform actions.
They may not silently mutate canonical memory or perform outbound side effects without policy and audit.
```

## Security And Agent Robustness

| Reference | Link | Use In Metis | Stance |
|---|---|---|---|
| Prompt Injection attack against LLM-integrated Applications | https://arxiv.org/abs/2306.05499 | Threat model for LLM apps that process untrusted content. | Required security baseline. |
| Automatic and Universal Prompt Injection Attacks against LLMs | https://arxiv.org/abs/2403.04957 | Adversarial evaluation; do not overtrust prompt-only defenses. | Use for red-team tests. |
| AgentDojo: Dynamic Environment to Evaluate Prompt Injection Attacks and Defenses for LLM Agents | https://arxiv.org/abs/2406.13352 | Realistic agent prompt-injection benchmark with tools and untrusted data. | Use to design security evals. |
| AgentDyn: Dynamic Open-Ended Benchmark for Prompt Injection Attacks | https://arxiv.org/abs/2602.03117 | Newer benchmark showing current defenses are not enough for real-world agents. | Watch; use once skill runtime becomes powerful. |
| OWASP Top 10 for LLM Applications | https://owasp.org/www-project-top-10-for-large-language-model-applications/ | Risk taxonomy: prompt injection, excessive agency, sensitive disclosure, supply chain, etc. | Required security checklist. |

Security design implication:

```text
retrieved content = untrusted data
skill code = untrusted-ish code
model output = proposal, not authority
outbound action = approval-gated by default
```

## Evaluation

| Reference | Link | Use In Metis | Stance |
|---|---|---|---|
| RAGAS: Automated Evaluation of Retrieval Augmented Generation | https://arxiv.org/abs/2309.15217 | Faithfulness, context precision/recall, answer relevance. | Useful starting metrics. |
| ARES: Automated Evaluation Framework for RAG Systems | https://arxiv.org/abs/2311.09476 | Context relevance, answer faithfulness, answer relevance with lightweight judges and PPI. | Use for CI-style eval harness. |
| Evaluation of Retrieval-Augmented Generation: A Survey | https://arxiv.org/abs/2405.07437 | Taxonomy of retrieval/generation metrics and benchmark limitations. | Use to design eval matrix. |

Metis-specific evals should go beyond generic RAG metrics:

- claim extraction accuracy
- source-span citation accuracy
- contradiction recall/precision
- wiki compilation loss rate
- deletion/erasure correctness
- sensitivity leakage tests
- retrieval sufficiency
- answer groundedness
- action safety and approval correctness
- cost/latency per task class

## Long-Context And KV Cache Work

| Reference | Link | Use In Metis | Stance |
|---|---|---|---|
| CacheBlend: Fast LLM Serving for RAG with Cached Knowledge Fusion | https://arxiv.org/abs/2405.16444 | Reuse cached chunks/KV state for repeated workspace context. | Future optimization after correctness. |
| TurboRAG: Accelerating RAG with Precomputed KV Caches for Chunked Text | https://arxiv.org/abs/2410.07590 | Precompute KV caches for document chunks. | Watch; useful if local inference latency dominates. |
| Efficient Memory Management for Large Language Model Serving with PagedAttention | https://arxiv.org/abs/2309.06180 | vLLM/PagedAttention serving model. | Use via vLLM rather than implementing directly. |

Do not optimize for KV-cache serving before the claim/evidence layer and evaluation harness exist.

## What We Should Benchmark Against

Minimum baselines:

- lexical retrieval with Postgres FTS and/or a true BM25 implementation
- dense vector retrieval with pgvector
- hybrid BM25 + vector with reciprocal rank fusion
- reranked hybrid retrieval
- naive chunk RAG
- RAPTOR-style document summary retrieval
- graph/wiki retrieval over compiled pages
- MemCell/MemScene retrieval

Target comparisons:

- Metis memory retrieval vs naive RAG on long-horizon workspace questions.
- Wiki compiler with WiCER-style refinement vs one-shot wiki generation.
- Hybrid retrieval vs graph/wiki traversal on multi-hop questions.
- Runtime skills with approval/sandbox vs direct tool-calling agent.
