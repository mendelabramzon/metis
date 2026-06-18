# Stage 7 Detailed Plan: Wiki Compiler And Human-Facing Knowledge

Parent: [high-level-implementation-plan.md](high-level-implementation-plan.md), Stage 7. Builds on Stages 0–6.

This stage compiles evidence and memory into navigable markdown — entity/topic/project pages, indexes, backlinks — without making the wiki the machine source of truth. It adopts the WiCER compile/evaluate/refine loop with diagnostic probes for dropped facts, and the LLM-Wiki ideas of a navigable, self-evolving substrate plus an Error Book for corrections. Every wiki statement is supportable by claim IDs/source spans or explicitly marked unresolved.

## Objective

- Initialize a git-backed wiki repository and define the page schema.
- Generate entity/topic/project pages, index/log pages, and backlinks.
- Implement the wiki patch model, patch validation, and an approval/commit flow.
- Implement the WiCER-style compile → evaluate → refine loop with diagnostic probes.
- Implement an Error Book (correction memory) for compilation mistakes.

Non-goals: serving the wiki in a UI (Stage 12 surfaces it), retrieval over wiki pages for answering (Stage 8 consumes compiled pages).

## Package Ownership

- Compiler + patch validation + refine loop: `metis-maintainer` (it proposes/validates; deepens the Stage 6 `compile_wiki_patches` job).
- Wiki store + git repository management: `metis-core`.
- Uses the Stage 4 router (`wiki_compile`) and the Stage 5 memory objects.

## Concrete Files And Modules To Create

```text
packages/metis-maintainer/src/metis_maintainer/wiki/
  compile.py             # claims + memory + existing pages -> proposed WikiPatch
  evaluate.py            # diagnostic probes: did compilation drop supported facts?
  refine.py              # refine loop driven by probe failures (WiCER)
  backlinks.py           # backlink/index generation
  validate.py            # patch validation: no unsupported claims introduced
  error_book.py          # correction memory of past compilation errors
  prompts.py             # wiki_compile prompts (registry-managed)

packages/metis-core/src/metis_core/wiki/
  repo.py                # git-backed wiki repository init + commit
  pages.py               # page schema (entity/topic/project/index/log) + read/write
  patch_apply.py         # apply approved WikiPatch -> page + commit; index/search update
  approval.py            # approval/commit state machine

packages/metis-maintainer/tests/
  test_patch_rejects_unsupported.py
  test_compilation_probes.py
  test_page_regeneration_stable.py
packages/metis-core/tests/
  test_wiki_commit_flow.py
  test_backlinks.py
```

## Schemas And Interfaces Touched

- Produces/consumes `WikiPatch`, `WikiPage`; writes through the core `WikiStore` and git repo.
- Reads `Claim`/`SourceSpan`/memory objects; every page statement carries claim-ID/source-span support or an explicit unresolved marker.
- Emits events: `wiki_patch.proposed`, `wiki_patch.approved`, `wiki_page.updated`.
- Approval/commit integrates with the Stage 12 approval inbox.

## Implementation Steps

1. Implement the git-backed `repo.py` and the `pages.py` schema (entity/topic/project/index/log page kinds).
2. Implement `compile.py`: from claims + memory + existing pages, propose a `WikiPatch` (via the `wiki_compile` task class).
3. Implement `validate.py`: reject patches that introduce unsupported claims; require claim-ID citations; surface contradictions rather than hiding them.
4. Implement `evaluate.py` (diagnostic probes that check whether supported facts were dropped in compilation) and `refine.py` (re-compile guided by probe failures) — the WiCER loop.
5. Implement `backlinks.py` and index/log page generation.
6. Implement `patch_apply.py` + `approval.py`: approved patches commit to git and update index/search; page regeneration is stable enough for clean diffs.
7. Implement `error_book.py`: record compilation errors and feed them back into future compiles.

## Tests And Fixtures

- **Unsupported statements rejected** (`test_patch_rejects_unsupported.py`): a patch introducing an unsupported claim fails validation.
- **Compilation probes** (`test_compilation_probes.py`): diagnostic probes catch a deliberately dropped supported fact and trigger refine.
- **Stable regeneration** (`test_page_regeneration_stable.py`): regenerating a page from unchanged inputs yields a stable diff.
- **Commit flow** (`test_wiki_commit_flow.py`): approved patch commits to git and updates the index.
- **Backlinks** (`test_backlinks.py`): backlinks are generated and consistent.

Fixtures: a small claim/memory set sufficient to compile an entity page and a topic page, plus a probe set for compilation-loss detection.

## Acceptance Criteria

Traces to the Stage 7 "Validation" list:

- Wiki statements cite claim IDs/source spans.
- Wiki patches fail if unsupported claims are introduced.
- Contradictions are surfaced rather than hidden.
- Page regeneration is stable enough for diffs.
- Wiki compilation loss is measured against diagnostic probes.

## Risks And Open Questions

- **Lossy compilation**: the central risk WiCER targets — measure compilation loss with probes and gate on it; never accept blind one-shot generation.
- **Wiki-as-truth drift**: keep the wiki a projection; all page statements must resolve to claim IDs or be marked unresolved, and machine reasoning must read claims/memory, not pages.
- **Diff stability**: LLM-generated prose is unstable across runs; constrain structure (templated sections, deterministic ordering) so diffs are reviewable.
- **Approval throughput**: human approval is a bottleneck; batch related patches and provide clear claim-backed diffs to reviewers (ties to Stage 12).
- **Git scaling**: large workspaces produce many pages/commits; consider per-entity files and periodic compaction, but keep portability.
- **Error Book usefulness**: only valuable if corrections actually feed back into compiles; measure whether repeat errors decline.
