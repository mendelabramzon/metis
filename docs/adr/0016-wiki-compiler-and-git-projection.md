# ADR 0016: Wiki compiler — git projection, deterministic structure, and the WiCER loop

- Status: Accepted
- Date: 2026-06-18
- Deciders: Metis maintainers

## Context

Stage 7 compiles evidence and memory into navigable markdown (entity/topic/project pages,
index, backlinks) without making the wiki the machine source of truth. The central risk
(WiCER) is *lossy compilation* — dropping supported facts — and the cross-stage invariant is
that every wiki statement resolves to claim ids or is explicitly unresolved. The plan left
open how to store the projection, how to keep LLM-generated pages stable and reviewable, and
how approval/commit works ahead of the Stage 12 inbox.

## Decision

**The wiki is a projection with two mirrors, never machine truth.** ``metis-core/wiki`` owns
storage: the DB ``WikiStore`` rows (record of record) and a **git-backed markdown repo**
(``WikiRepo``, driven via ``subprocess git`` — no new dependency, commit identity passed
inline). ``metis-maintainer/wiki`` owns *compiling and validating*. Machine reasoning reads
claims/memory, never pages.

**Page kind is encoded in the slug namespace, not the protocol.** ``entity/…``, ``topic/…``,
``project/…``, plus singleton ``index`` and ``log`` pages, each mapping to one file path. This
keeps the Stage 1 ``WikiPage`` schema unchanged (no migration, no snapshot churn); ``pages.py``
owns kind detection, slug builders, and deterministic file rendering (frontmatter + body).

**Compilation is deterministic-structured; the model only writes a lede.** The body is built
from claims sorted by id into fixed sections — Facts (each claim footnoted), Open questions
(same-subject/same-predicate conflicts, surfaced not resolved), and a Citations footer mapping
every footnote to its claim id. So regenerating from unchanged inputs is byte-identical
(reviewable diffs), every statement is claim-cited, and contradictions are visible. An optional
``wiki_compile`` model call adds only a prose lede over the already-cited claims; it never
chooses sides or invents facts.

**Compilation is gated by diagnostic probes (WiCER).** Each input claim is a probe: covered iff
the patch both cites it and prints its id in the citation footer. ``compile_with_refine`` loops
compile → probe → (record drop in the Error Book, re-compile) until complete or a round cap. A
complete deterministic compiler converges in one round; a stochastic/LLM compiler gets retries.
The Error Book is in-process for now (the mechanism); ``repeat_drops`` surfaces chronic loss to
feed back into future compiles.

**Validation rejects unsupported and uncited statements.** ``validate_patch`` runs the structural
lint and claim-support checks and adds the key check: a cited claim must resolve to real evidence
(``known_claim_ids``); an *introduced* claim fails. Index/log pages are navigation projections and
are exempt from the claim-citation requirement.

**Approval is a pure state machine; commit goes through both mirrors.** ``WikiPatchReview``
transitions ``PROPOSED → APPROVED → COMMITTED`` (or ``→ REJECTED``); only an approved patch may
be committed. ``apply_and_commit`` writes through the DB store, then renders and commits the page
to git. Committing identical content is a no-op, so re-running yields a stable history. Durable
review storage and the operator inbox are Stage 12.

## Consequences

- The five acceptance checks hold: pages cite claim ids; patches that introduce unsupported
  claims fail validation; contradictions appear in an Open questions section rather than being
  resolved away; regeneration from unchanged inputs is byte-stable; and compilation loss is
  measured by probes that drive the refine loop.
- The wiki is portable (plain markdown + git) and every change is a reviewable commit; the DB
  store stays the queryable record of record.
- ``subprocess git`` ties the wiki to a local git binary (fine for single-node; revisit for
  remote/scale). Per-entity files keep diffs small; compaction is deferred.
- Stage 8 consumes compiled pages for retrieval; Stage 12 adds the approval inbox and serves the
  wiki; ``lint_wiki``/``validate_claim_support`` will graduate to page-scanning jobs once pages
  accumulate.

## Alternatives considered

- **Adding a ``kind`` field to the protocol ``WikiPage``**: cleaner typing, but a schema change
  and migration for what slug namespacing already expresses; rejected.
- **One-shot LLM page generation**: unstable diffs and silent fact loss — exactly what WiCER
  targets; rejected for deterministic structure + probe-gated refine, with the model limited to a
  lede.
- **A git library (GitPython/pygit2)**: another dependency for a handful of plumbing commands;
  subprocess is sufficient and portable.
- **Persisting the approval queue now**: the durable inbox is Stage 12; Stage 7 implements the
  state-machine logic and the commit action, leaving storage/UI to the surfaces stage.
