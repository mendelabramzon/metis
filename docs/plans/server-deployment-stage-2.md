# Server Deployment Stage 2 Detailed Plan: Connectors, Skills, and Deep Research

Parent: [server-deployment-product-roadmap.md](server-deployment-product-roadmap.md), Stage 2.
Builds on Server Deployment Stage 1 ([server-deployment-stage-1.md](server-deployment-stage-1.md)).

This stage expands data reach and action capability *without weakening source truth, policy, or
audit*. It adds official-API connectors on the live `Transport` seam from Stage 1, a controlled
browser skill for authenticated sources, an iterative deep-research workflow that upgrades the
single-shot `web_search` skill, and a hardened skill platform (signing, sandboxing, secrets,
eval). The numbering mirrors the roadmap's workstreams 2.1–2.4.

## Objective

- Add connectors for official-API sources (Slack/Teams, Calendar/CalDAV, Notion/Confluence,
  GitHub/GitLab, SharePoint/OneDrive, web clip/URL, RSS) behind the existing connector spine.
- Add a Playwright-based browser skill for user-directed research on authenticated sites, designed
  as controlled remote work with per-run approval and evidence capture.
- Turn `web_search` into a budgeted deep-research workflow with an explicit task tree and a
  re-planning loop, producing a cited research artifact.
- Harden the skill platform: signed packages, reproducible environments, stronger sandbox profiles,
  a per-skill secrets broker, injection/exfiltration eval fixtures, and optional MCP client/server.

Non-goals: cross-company exchange (Stage 3); scraping-at-scale "connectors" for sites without a
stable API/permission model (those are browser *skills*, deliberately).

## Invariants Preserved

- **Untrusted content is data, never control.** Browser-captured pages, fetched URLs, and search
  results flow through the single taint chokepoint; none can become a tool instruction. Deep
  research re-planning reads only trusted task state + the research question, never fetched text.
- **Citation invariant.** Research "read" steps extract claims with source spans exactly like
  ingestion; the synthesized brief cites them. Captured web content enters memory only as an
  external-source artifact, after approval.
- **Approval-gated, audited side effects.** The browser skill never mutates account state; outbound
  effects require human approval and land in the audit log.
- **Connector/skill separation.** Official API + stable permissions ⇒ connector. Logged-in browser
  ⇒ skill with explicit scope.
- **Execution state separate from semantic memory.** The research task tree is execution state;
  failed branches and stale findings never pollute active memory.

## Package Ownership

- `metis-ingestion` (+ `services/ingest-worker`): new connectors on the Stage 1 transports.
- `metis-skills` + `metis-runtime/skills`: the browser skill, the deep-research skill, and the
  platform hardening (`metis-runtime/security` for the taint/injection surface).
- `metis-runtime/agent`: the re-planning loop that makes research iterative.
- `metis-protocol`: research-artifact and skill-signing schemas; optional MCP resource mappings.

## Workstream 2.1 — Connectors Before Browser Automation

**Files (each connector = a live transport + a `_render`/`discover` pair behind `BaseConnector`):**

```text
packages/metis-ingestion/src/metis_ingestion/connectors/
  slack.py            # channels, threads, files (official API)
  calendar.py         # Google Calendar / CalDAV
  notion.py           # pages/databases
  confluence.py       # spaces/pages
  github.py           # issues, PRs, discussions, repo docs (GitLab variant)
  sharepoint.py       # SharePoint/OneDrive (Microsoft 365)
  web_clip.py         # (extend) URL fetcher / clipper
  rss.py              # feeds
packages/metis-ingestion/fixtures/connectors/   # recorded responses per new connector
```

**Steps:**

1. Implement each connector against the Stage 1 live `Transport` (HTTP/API) + the unchanged
   normalize→parse→segment→extract pipeline; emit `RawArtifact`/`NormalizedDoc` only.
2. Map each source's ACL/permission model to Metis sensitivity (the floor rule); persist
   `SourceCursor`/`ConnectorRun`.
3. Record replay fixtures per connector (including a rate-limit/error case) so the suite runs
   credential-free.
4. Apply the connector rule explicitly: anything lacking an official API + stable permission model
   is *not* a connector — it routes to the browser skill (2.2).

## Workstream 2.2 — Browser Skill for Authenticated Sources

**Files:**

```text
skills/browser_research/
  SKILL.md
  manifest.yaml          # network + browser permissions; domain allowlist; no-mutation contract
  input_schema.json      # typed task contract (domains, scope, budget) — from the trusted caller
  output_schema.json     # screenshots, URLs, timestamps, extracted snippets (evidence)
  main.py                # Playwright driver
packages/metis-runtime/src/metis_runtime/skills/
  sandbox_profiles.py    # (extend) stronger profile for browser/network skills
  browser_auth.py        # browser auth state stored as a secret-grade artifact
```

**Steps:**

1. Build a Playwright skill that runs in a stronger sandbox profile; the task contract (domains,
   scope, budget) comes from the trusted caller only.
2. Store browser auth state via the secrets broker (2.4) as a secret-grade artifact — never in git
   or normal object storage; require user-initiated login + domain allowlists.
3. Require per-run approval for collection scope; capture screenshots/URLs/timestamps/snippets as
   reviewable evidence; ingest into memory only after review.
4. Enforce safety: never post/message/follow/like/mutate; rate-limit; stop on CAPTCHA or
   account-risk signals; treat captured content as untrusted data.

**Anti-goals:** a scrape-at-scale "LinkedIn connector"; driving a logged-in browser without a typed
task contract; letting captured content become trusted instructions.

## Workstream 2.3 — Deep Research Skill

**Files:**

```text
skills/deep_research/
  SKILL.md
  manifest.yaml
  input_schema.json      # research request + budget caps
  output_schema.json     # ResearchArtifact: brief, citations, confidence, open questions, claims
  main.py                # plan → search → fetch → triage → read → synthesize → persist
packages/metis-protocol/src/metis_protocol/
  research.py            # ResearchArtifact, ResearchTask (task-tree node) schemas
packages/metis-runtime/src/metis_runtime/agent/
  loop.py                # (extend) re-planning: plan → act → observe → re-plan under a budget
  research_state.py      # task tree (execution state), kept separate from semantic memory
```

**Steps:**

1. Add `ResearchArtifact`/`ResearchTask` schemas to `metis-protocol`.
2. Implement the workflow stages: **plan** (questions + sources + stop conditions), **search**
   (multiple providers for diversity), **fetch** (HTTP/browser with extraction), **triage**
   (credibility, recency, dedup, conflict), **read** (claims + source spans), **synthesize** (a
   cited brief), **persist** (optional approved ingestion as external-source artifacts).
3. Extend the agent loop with a bounded re-planning step so research is iterative, not single-shot;
   the re-planner reads trusted task state only (taint boundary).
4. Maintain the task tree as execution state with hard budgets (searches, pages, tokens, browser
   time, wall-clock); failed branches and stale findings stay out of active context.
5. Output a `ResearchArtifact` with citations, confidence, unresolved questions, and a
   machine-readable claim set.

## Workstream 2.4 — Skill Platform

**Files:**

```text
packages/metis-runtime/src/metis_runtime/skills/
  signing.py             # signed skill packages (verify signature on discovery/registration)
  environments.py        # dependency lockfiles + reproducible environments
  secrets_broker.py      # per-skill scoped secrets (browser auth, API keys)
  sandbox_profiles.py    # network/browser profiles
packages/metis-runtime/src/metis_runtime/mcp/   # optional MCP client + server
eval/fixtures/skills/    # injection + data-exfiltration fixtures (extend existing harness)
```

**Steps:**

1. Sign skill packages and verify signatures at discovery/registration (extends the existing
   `SkillRegistry.discover`).
2. Pin dependencies with lockfiles and build reproducible per-skill environments.
3. Add a secrets broker with per-skill scopes; secrets never reach skill code unless declared.
4. Add stronger sandbox profiles for browser/network skills.
5. Add skill eval fixtures for prompt injection and data exfiltration to the Stage 13 harness.
6. (Optional) Add MCP client/server so Metis can consume external tools and expose selected
   tools/context without bespoke integrations.

## Tests And Fixtures

- **Connector contract/replay:** every new connector emits valid `RawArtifact`/`NormalizedDoc`,
  replays from fixtures credential-free, and maps ACL → sensitivity correctly.
- **Taint:** an injected instruction inside a fetched page / browser capture / connector doc never
  reaches the planner or triggers a tool (extend `test_untrusted_cannot_instruct`).
- **Browser skill:** runs against recorded pages; never issues a mutating request (asserted);
  stops on a CAPTCHA fixture; auth state is stored via the broker, not on disk.
- **Deep research:** budgets are enforced (search/page/token/time caps); a failed branch does not
  pollute the final brief; the artifact's claims all carry source spans.
- **Skill platform:** an unsigned/tampered package is rejected; a skill cannot read undeclared
  secrets; injection/exfiltration fixtures fail closed.

## Acceptance Criteria

- New official-API connectors ingest end-to-end and replay from fixtures with no live credentials.
- The browser skill performs a user-directed, approved research run and returns reviewable evidence
  without mutating account state.
- Deep research returns a cited `ResearchArtifact` (brief + confidence + open questions +
  machine-readable claims) within its budget, with execution state isolated from semantic memory.
- Signed skills only; per-skill secret scoping enforced; injection/exfiltration eval fixtures pass.

## Risks And Open Questions

- **Browser automation is fragile and legally sensitive.** Keep it user-driven, allowlisted,
  approval-gated, and artifact-focused; assume selectors and anti-automation defenses change.
- **Research cost grows quickly.** Budgets are mandatory and enforced, not advisory.
- **Connector permission-model fidelity.** Slack/SharePoint/GitHub ACLs are intricate; a wrong
  mapping leaks restricted content downstream — test ACL → sensitivity per connector.
- **MCP trust boundary.** External MCP tools are untrusted; their outputs are data, and exposing
  Metis tools must respect workspace policy and approval.
- **Signing/key management.** Decide the signing trust root and rotation before depending on it.

## Sequencing

Roadmap Milestone D: deep research (2.3) and the skill-platform hardening (2.4) first, since they
gate safe browser use; then the browser skill (2.2); official connectors (2.1) proceed in parallel
as their APIs are prioritized by user need.
