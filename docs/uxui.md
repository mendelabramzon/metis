# Metis UX/UI Product Plan

Status: ready for implementation (2026-06-21)

Audience: product, design, and frontend workstreams (with gateway for the small response additions noted below)

Scope: replace the single-file console with a calm, team-facing workspace product for a small team.

## What This Builds On

Server-deployment Stage 1 is complete. The product *surfaces* this plan dresses already exist behind
the gateway and are exercised today by a single-file console at `/`:

- Identity + RBAC (orgs/users/workspaces/memberships; roles owner/admin/member/viewer/auditor), with
  the workspace-isolation gate enforced before retrieval.
- Workspace-scoped **ask** and **file upload** with per-file parse status.
- **Source setup**: a connector catalog, OAuth connect, Telegram chat discovery, and the opt-in
  Telegram TDLib interactive login (QR / code / 2FA).
- **Proposed actions** with risk-gated execution dispatch, and **evidence drill-down**
  (claim → spans/quotes → artifact; memory cell → claims).
- **Contradictions**, **spend**, and **provider** surfaces; durable job/action/approval/wiki state;
  an **erasure** path that tombstones derived artifacts.

This plan adds **no new subsystem**. It is a frontend effort: re-present the above as a product. A few
places need a *small gateway response addition* (a per-citation scope label, a per-answer routing-
outcome flag, surfacing already-detected contradictions at answer time, a typed policy-block result).
Each is called out inline and listed in [Backend Surfaces This Builds On](#backend-surfaces-this-builds-on);
none is a new store or pipeline.

## Product Intent

Metis should feel like a trustworthy workspace memory system — not a busy admin console and not a
generic chatbot. A user should understand three things within the first minute:

- What context is connected.
- What workspace and scope they are asking.
- Why an answer can be trusted: the source evidence behind it, and whether the sources agree.

The UI keeps the evidence-first nature of Metis visible without forcing users to read raw ids, jobs,
model names, or audit records during normal work. It also makes **scope, sensitivity, and model
routing legible** — because those, not fluency, are the reasons to trust Metis over a generic chatbot.

## Design Principles

1. Start from the user's job, not from backend objects.
2. Use one obvious primary action per screen.
3. Prefer progressive disclosure over many visible controls.
4. Keep workspace scope always visible.
5. Show evidence as source snippets first, internal ids second.
6. Attach scope and sensitivity to the evidence itself, not only to the workspace globally.
7. Surface disagreement; never silently merge or pick between conflicting sources.
8. Make the privacy outcome visible (kept on-device vs. sent to an external model) without exposing
   model controls.
9. Treat a policy or sensitivity block as a calm, explained state — not an error.
10. Separate daily user work from admin and operator work.
11. Make risky actions explicit, reviewable, and calm.
12. Avoid vanity dashboards; the one legitimate dashboard is the operator Operations view.
13. Onboarding ingests; it does not configure — manufacture a dense first source and a verified first
    answer before asking for any org, team, or admin setup.

## Primary Users

Roles are the system roles — owner, admin, member, viewer, auditor. "Reviewer" and "Operator" below
are **capabilities layered on a person**, not separate logins: one person in a 10-user deployment is
commonly member + admin + reviewer, and the navigation adapts to the roles granted. Operator surfaces
are reached with the deployment's operator principal; everyday per-workspace surfaces use the user
principal (see [Access And Role Rules](#access-and-role-rules)).

### Team Member

Wants to ask questions, upload files, inspect citations, and understand what Metis knows.

Core needs:

- Sign in without handling tokens or generated ids.
- Choose personal, shared, or mixed context.
- Ask a question in plain language.
- See whether the answer is grounded, whether the sources agree, and the cited snippets behind it.
- See the scope and sensitivity of each cited source.
- Add files or connect an approved source when context is missing.

### Workspace Admin

Wants to set up sources, invite people, handle failed ingestion, and manage sensitivity.

Core needs:

- Invite and remove members.
- Connect Drive, email, Slack, Telegram, or uploads.
- See sync health without reading job tables.
- Resolve source errors.
- Review spend and model policy only when needed.

### Reviewer (capability)

Wants to approve proposed changes, inspect contradictions, and verify evidence.

Core needs:

- A single review queue.
- Clear risk and sensitivity labels.
- Side-by-side evidence and proposed outcome.
- Approve, reject, dismiss, or request changes with a note.

### Operator (capability / deployment principal)

Wants deployment health, provider config, failed jobs, audit, and backups.

Core needs:

- Compact operational status.
- Failed job drilldown.
- Provider and spend settings.
- Audit search.

Operator views are never part of the default workspace experience.

## Information Architecture

Use a small persistent navigation model:

1. Ask
2. Sources
3. Review
4. Activity
5. Settings

Keep operator-only views behind Settings > Operations, visible only with the operator principal.

Do not keep separate top-level tabs for providers, jobs, approvals, audit, contradictions, evidence,
Telegram, and spend. These are important, but they are supporting states inside the five areas above.

### Ask

The default screen after onboarding.

Contains:

- Workspace scope switcher: Personal, Shared, Mixed.
- Question input.
- Answer stream.
- Citation cards, each tagged with its source scope and sensitivity.
- A "sources disagree" panel when the evidence conflicts.
- A quiet routing note (kept on-device / used an external model) for sensitivity-aware users.
- "Add missing context" prompt only when evidence is insufficient.

Avoid:

- Raw claim ids in the primary answer.
- Separate "command" and "ask" modes unless the system is clearly proposing an action.
- Visible model/provider controls (the routing *outcome* is fine; the *controls* are not).
- A single numeric confidence score presented as the trust signal.

### Sources

The place to add and monitor context.

Contains:

- Source health summary.
- Connected sources list, grouped by workspace.
- Add source button.
- File upload dropzone.
- Source-specific setup flows, including the Telegram bot connect and the opt-in TDLib login
  (QR / code / 2FA) as a guided sub-flow — not a separate page.
- Parse status and sync errors.
- A per-source "Remove and erase" entry point (see [Flow 8](#flow-8-erase-a-source-or-your-data)).

Avoid:

- Connector JSON textareas for normal users.
- A separate Telegram page.
- Job ids as primary status.

### Review

One queue for anything that needs human judgment.

Contains:

- Proposed actions.
- Wiki or memory proposals.
- Contradictions.
- Risk and sensitivity labels.
- Evidence snippets.
- Approve, reject, resolve, dismiss.

Avoid:

- Separate approval and contradiction pages.
- Showing low-risk completed history before pending work.

### Activity

A readable timeline of recent work.

Contains:

- Uploads and source syncs.
- Questions asked and answered.
- Failed source events.
- Reviews completed.
- Important audit events, translated into user language.

Filtering principle (Activity is itself a disclosure surface): a user sees their own actions and
events in workspaces they can access; a member does not see, for example, that an admin opened a
source in another workspace. Cross-actor and operator-level audit lives in Settings > Operations,
not in everyday Activity.

Avoid:

- Full audit log by default.
- Raw provider calls or internal traces unless the user drills into diagnostics.

### Settings

Workspace and account configuration.

Subsections:

- Workspace name and members.
- Source permissions.
- Sensitivity defaults.
- Model policy and spend caps for admins.
- Data & erasure (delete a member's data, a source, or a workspace, with tombstone propagation).
- Operations for operators.

Avoid:

- Mixing settings with everyday ask/source workflows.

## Activation & First-Run (Onboarding)

Scope: the deployment is already running (Compose stack up, providers configured). This section
covers only the *human* onboarding after that — the first admin and every invited member. The goal is
not "usable in five minutes"; it is **"caught it being right in five minutes."**

### The cold-start problem this design solves

Metis is most valuable when it holds a lot of context and is judged when it holds none. So first-run
must manufacture value *before* asking for any setup:

1. Land the user in their own (personal) workspace.
2. Ingest one *dense* source they already have.
3. Propose questions for them.
4. Get them to a *verified* cited answer.

Only after that does it ask for org/team/admin configuration. **Configuration is deferred until the
user has already seen value.**

**Activation** = the user connected a dense source, asked a question, and **opened a citation to
confirm the answer against the real source**. Track this as the onboarding success event; everything
in first-run drives toward it.

### Path A: First admin (bootstrap)

The first person to sign in to a fresh deployment.

1. **Sign in / claim the deployment.** Bootstrap the first admin account. One screen, no token
   handling.
2. **Name the organization.** One field — the org exists so members and shared workspaces have a
   home, but it is *not* where value starts.
3. **Land in your personal workspace**, empty state front and center. Not a shared workspace, not a
   settings tour. Single-player value first.
4. Continue into **First Value** below.
5. *After* the first verified answer, offer the team step: "Invite your team" and "Create a shared
   workspace." Multiplayer on demand, never as the entry gate.

### Path B: Invited member

Everyone after the first admin.

1. **Open the invite link and sign in.** No org creation, no setup.
2. **Land in your personal workspace** with the same value-first first-run, plus a one-line note of
   any shared workspaces you have been added to.
3. Continue into **First Value** below.

### First Value (shared by both paths)

1. **"Add your first source," with one dense option foregrounded.** Lead with whatever the user has a
   lot of — connect Telegram and backfill a few real chats, connect email/Drive, or drag a folder.
   Other options stay visible but quiet. Never open onto an empty grid of connectors.
2. **Connect with privacy shown in place.** During auth, state plainly what is and is not done with
   the data ("kept on your server," "restricted content never leaves," which scope is ingested). For
   Telegram, run the bot connect or the opt-in TDLib login sub-flow; for Drive/Gmail, the standard
   OAuth redirect.
3. **Watch it ingest, honestly.** Show real progress and per-item parse status. As soon as there is
   *any* usable evidence, advance — do not wait for the whole backfill to finish.
4. **Offer three generated starter questions** from what just landed ("You added the Acme thread —
   try: *What did we agree on pricing?*"). The product imagines the value so the user does not have
   to. A free-text box is always available too.
5. **First answer → nudge the verify click.** Surface the citation cards and prompt once: "Open a
   citation to see the exact source." When the user opens it and sees the real quote from their real
   document, they are activated.
6. **Then, and only then, offer expansion:** invite teammates, create or share a workspace, add more
   sources, turn on the weekly digest.

### Forgiving first-run states

The first session will hit rough edges; each is a next step, not a dead end.

- **Not enough evidence yet:** "I don't have enough in this workspace to answer that — add a source
  or broaden scope," with the actions inline.
- **Parse warning/failure on an upload:** name the file and offer a clear retry; never block the rest
  of the batch.
- **Source still backfilling:** answer from what is available and note "still importing — answers
  improve as this finishes."
- **Blocked by sensitivity policy:** a calm explanation, not an error, with no naive retry.

### Plant the return reason

A memory product is *pull* (visited only when a question arises) and is forgotten without a *push*.
During onboarding, plant the loop:

- Offer a **weekly digest** ("what synced, what changed, what needs review") — opt-in, defaulted on
  for the first admin.
- Introduce the **Review queue** as the place the system brings things *to you* (new contradictions,
  proposals), so the user expects to be pulled back.
- On return, lead with a quiet **"while you were away"** line (synced N items, reconciled M facts,
  found K contradictions) so the background maintainer work is *felt* — the substrate looks alive,
  not like a database the user forgot they had.

### Returning User: Daily Entry

Goal: answer a question or add context without re-learning the product.

1. Land on Ask.
2. Workspace scope is already selected from the last session.
3. A quiet "while you were away" summary if the maintainer did meaningful work.
4. Recent useful sources in a compact context strip.
5. If the workspace is still empty, one empty-state action: Add context.

### Empty States

Empty states explain the next action, not the whole system.

Ask empty state:

- "Add a file or connect a source to start asking grounded questions."
- Primary action: Add context.

Sources empty state:

- "Start with files, Drive, or email."
- Primary action: Upload files.
- Secondary action: Connect source.

Review empty state:

- "Nothing needs review."

Activity empty state:

- "Uploads, syncs, answers, and reviews will appear here."

## Core Flows

### Flow 1: Upload And Ask

1. User opens Ask.
2. Empty state suggests Add context.
3. User uploads one or more files.
4. Upload panel shows parsed, warning, or failed per file.
5. Successful files appear as available context.
6. User asks a question.
7. Answer displays source cards.
8. User opens a citation to see the quote, file, page, scope, sensitivity, and artifact details.

Acceptance:

- User does not need to know doc ids, claim ids, span ids, jobs, or tokens.
- Parse warnings are visible but not alarming.
- Failed files include a clear next step.

### Flow 2: Connect A Source

1. Admin opens Sources.
2. Clicks Add source.
3. Chooses source type from a short recommended list (from the connector catalog).
4. Completes provider-specific auth — OAuth redirect for Drive/Gmail; for Telegram, connect the bot
   and pick from discovered chats, or run the opt-in TDLib login sub-flow (QR / code / 2FA) for
   history backfill and followed channels.
5. Selects mailbox, folder, chat, or channel scope.
6. Confirms sensitivity (private chats default to a more restrictive tier).
7. Sync starts in the background.
8. Source health card shows progress.

Acceptance:

- No connector config JSON is required in the normal flow.
- Credentials are never shown after entry; login codes and 2FA secrets are never persisted.
- Only selected source scopes are ingested.
- The TDLib login presents its own states (awaiting QR scan, awaiting code, awaiting 2FA, ready,
  failed) and never blocks the rest of Sources.

### Flow 3: Ask With Evidence

1. User asks a question.
2. Metis answers only if the evidence is sufficient.
3. Citations appear as source cards under the answer, each tagged with scope and sensitivity.
4. Each citation expands to quote, source, date, page/location, scope, and sensitivity.
5. A quiet routing note states whether the answer was kept on-device or used an external model.
6. "Not enough evidence" includes suggested actions: upload, connect source, or broaden scope.

Acceptance:

- The answer and citations are readable without internal identifiers.
- In a Mixed-scope answer, personal-sourced and shared-sourced evidence are visually distinguished.
- The trust signal is grounding + citations + source agreement, not a numeric confidence score.
- Internal ids remain available behind "Developer details" for debugging.

### Flow 4: Ask When Sources Disagree

1. User asks a question whose evidence contains a contradiction (the query runtime already surfaces
   these; the UI presents them at answer time).
2. The answer shows a "sources disagree" panel: each side, its snippet, source, scope, and date.
3. Metis does not silently pick a side; it states the disagreement plainly.
4. The user can open the contradiction in Review (if they have the capability) to resolve it.

Acceptance:

- Conflicting evidence is never merged into a single confident claim.
- The disagreement is legible at answer time, not only in the Review queue.
- Resolving it in Review updates future answers.

### Flow 5: Proposed Action

1. User asks Metis to do something effectful.
2. Metis returns a proposed action card instead of executing immediately.
3. Card shows action type, target source/workspace, risk, expected outcome, and evidence.
4. User approves or rejects.
5. Completed action appears in Activity.

Acceptance:

- Read-only actions (answer, find evidence, inspect source, draft) run without approval noise.
- Memory writes, wiki writes, sync changes, and source changes are explicit and approval-gated.
- External side effects are blocked in this stage and shown as such — not offered as a retry.
- Risk labels are understandable: Read only, Updates memory, Changes source, External action.

### Flow 6: Review Contradiction

1. Reviewer opens Review.
2. Contradiction card shows conflicting claims and source snippets.
3. Reviewer resolves, dismisses, or requests more context.
4. Decision is recorded in Activity and audit.

Acceptance:

- The reviewer can decide from source evidence, not just summaries.
- Resolved items move out of the pending queue.

### Flow 7: Admin Checks Health

1. Admin opens Sources or Activity.
2. Failed syncs and parse failures are grouped by source.
3. Admin sees the plain-language reason and a retry action.
4. Detailed job view is one drilldown away.

Acceptance:

- Normal users do not see operational noise.
- Admins can retry or inspect failures without opening a raw jobs table.

### Flow 8: Erase A Source Or Your Data

1. From Sources (a source) or Settings > Data & erasure (a member or workspace), the user chooses
   Remove and erase.
2. The UI states plainly what will be removed and that it propagates to derived artifacts
   (claims, memory, wiki references) as tombstones.
3. The user confirms with an explicit, non-default action.
4. Erasure runs; Activity records it; erased content no longer appears in answers or evidence.

Acceptance:

- Erasure is explicit and clearly distinguished from deactivating or disconnecting a source.
- The copy distinguishes "remove from this workspace" from "permanently delete everywhere."
- Erased evidence stops appearing in retrieval and citations.

## Screen-Level Plan

### App Shell

Header:

- Metis logo/name.
- Active workspace switcher.
- Current scope badge: Personal, Shared, or Mixed.
- User menu.

Left navigation:

- Ask
- Sources
- Review
- Activity
- Settings

Rules:

- Hide navigation items the user's roles cannot access.
- Keep the primary content width readable.
- Do not add persistent secondary toolbars unless the current screen needs them.

### Ask Screen

Primary action: Ask.

Layout:

- Conversation or answer area.
- Composer fixed at the bottom on desktop and mobile.
- Compact context strip above the composer.
- Citation drawer on the right for desktop, bottom sheet for mobile.

States:

- No context.
- Asking.
- Answer with sufficient evidence.
- Answer with conflicting evidence (sources disagree).
- Answer blocked by insufficient evidence.
- Answer blocked by sensitivity/policy (calm, explained, no naive retry).
- Action proposal.
- Error with retry.

### Sources Screen

Primary action: Add source.

Layout:

- Source health summary: Healthy, Needs attention, Syncing.
- Source cards grouped by workspace.
- Upload dropzone as the first card when no source exists.
- Add source modal with simple choices.

States:

- Empty.
- Syncing.
- Connected.
- Needs re-auth.
- Awaiting Telegram login (QR / code / 2FA).
- Parse warnings.
- Failed sync.

### Review Screen

Primary action: Decide the selected pending item.

Layout:

- Pending queue.
- Selected item details.
- Evidence panel.
- Decision controls.

Filters:

- Pending by default.
- Completed and dismissed behind a filter.

### Activity Screen

Primary action: none by default.

Layout:

- Timeline grouped by day.
- Search and filters collapsed by default.
- Event detail drawer.

### Settings Screen

Primary action depends on subsection.

Subsections:

- Workspace
- Members
- Permissions
- Model policy
- Data & erasure
- Operations

Operations uses the operator principal only.

## Visual Direction

Metis should feel quiet, work-focused, and inspectable.

Use:

- Neutral layout with restrained color.
- Status colors only for meaningful status: success, warning, error, pending.
- Calm, non-alarming styling for scope, sensitivity, and routing indicators (they are reassurance,
  not warnings).
- Compact cards for repeated sources, citations, and review items.
- Tables only for dense admin data.
- Icons for common actions, with labels where ambiguity matters.
- Short labels and stable placement.

Avoid:

- Marketing-style hero sections inside the app.
- Decorative gradients or visual noise.
- Large top-level dashboards for everyday users (the operator Operations view is the one legitimate
  dashboard — keep it compact and operator-only).
- Multiple primary buttons on one screen.
- Raw JSON or internal ids in normal flows.
- Alert fatigue from successful background work.

## Copy Guidelines

Use user language:

- "Source" instead of "connector".
- "Needs review" instead of "approval inbox".
- "Could not sync" instead of "job failed".
- "Evidence" instead of "claim/span graph".
- "Sources agree" / "Sources disagree" instead of "no contradiction" / "contradiction".
- "Answered from your sources" / "Not enough evidence yet" instead of "sufficiency gate".
- "Kept on-device" / "Used an external model" instead of "provider routing".
- "Blocked by sensitivity policy" instead of "policy denial".
- "Remove from this workspace" vs. "Permanently delete everywhere" for source removal vs. erasure.
- "Developer details" for raw ids, JSON, traces, and job data.

Every empty, loading, error, and blocked state should answer:

- What happened?
- What can I do next?
- Do I need to act now?

## Access And Role Rules

Roles are owner, admin, member, viewer, auditor; Reviewer and Operator are capabilities layered on
top, and the navigation adapts to what is granted.

Owner:

- Everything Admin can do.
- Manage the organization and workspaces; set spend caps.

Admin:

- Manage members.
- Add and remove sources.
- Set sensitivity defaults.
- Review source failures.
- View workspace spend.

Member:

- Ask.
- Upload if allowed by workspace role.
- Inspect sources and evidence.
- See their own activity.

Viewer:

- Ask and inspect evidence; no uploads or changes.

Auditor:

- Read-only access to audit and activity; no content changes.

Reviewer (capability):

- Access Review.
- Decide proposals and contradictions according to permissions.

Operator (deployment principal):

- Access Operations.
- Configure providers.
- Inspect failed jobs and audit.
- Manage deployment health.

## Progressive Disclosure Rules

Show by default:

- Workspace and scope.
- Source name.
- Human-readable status.
- Answer.
- Evidence snippet, with its scope and sensitivity.
- Whether sources agree.
- Routing outcome (kept on-device / used an external model).
- Primary next action.

Hide behind drilldown:

- Claim ids, artifact ids, span ids, job ids.
- The specific provider/model name and routing internals (the *outcome* is shown; the *details* are not).
- Raw audit entries.
- JSON configs.
- Prompt/model traces.

## Implementation Phases

The backend exists; this is a frontend sequence. Differentiating trust signals are pulled forward
where the data is already available.

### Phase 1a: Reorganize The Existing Console (cheap)

Goal: reduce distraction without changing interaction models.

- Relabel tabs into the five product areas.
- Move audit, jobs, providers, and spend under Settings / Operations.
- Replace user-id and operator-token fields with a sign-in selector or bootstrap screen.
- Collapse developer details.

### Phase 1b: Merge The Interaction Models (real work)

Goal: one coherent mental model over the existing endpoints.

- Merge command and ask into one Ask flow with proposed-action cards.
- Merge approvals and contradictions into one Review queue.
- Show citations as source cards, tagged with scope and sensitivity.

### Phase 2: Build The First Real App Shell

Goal: a usable workspace app for a small team, accessible from the start.

- Implement login/session UI.
- Add the workspace switcher and scope selector.
- Build Ask, Sources, Review, Activity, Settings routes.
- Add source-specific setup flows, including Telegram bot connect and the TDLib login sub-flow.
- Add upload progress and parse-result cards.
- Add the citation drawer with scope/sensitivity tags and the routing note.
- Add the erasure flow.
- Add role-based navigation.
- Bake in accessibility (semantic structure, keyboard, contrast) and a responsive composer — not
  deferred to a later phase.

### Phase 3: Trust And Production Surfaces

Goal: make the UI safe for real private data and complete the differentiators.

- Add the answer-time "sources disagree" panel.
- Add the "blocked by sensitivity/policy" state.
- Add invite/member management.
- Add source permission and sensitivity review.
- Add provider/model policy UI and spend caps.
- Add durable activity and review history.
- Add audit search for operators.
- Verify accessibility and mobile against acceptance.

### Priorities: If You Build Only Three Things First

These convert the calm console into the trustable product, and are why a team would choose Metis over
a generic chatbot:

1. **Per-citation scope + sensitivity provenance** (and the Mixed-answer personal/shared split) —
   the signal that makes the personal/shared model safe.
2. **The answer-time "sources disagree" panel** — surfaces the contradiction invariant where it
   creates value, not only in a back-office queue.
3. **The erasure flow + the "blocked by policy" state** — the two governance surfaces that make
   Metis's regulated-buyer differentiators visible to a user.

## Backend Surfaces This Builds On

Map of UI areas to existing gateway surfaces, plus the small response additions this plan assumes.

Existing (Stage 1):

- Identity/session: user principal (per-workspace surfaces) and operator principal (operator
  surfaces); `GET /workspaces` for the switcher.
- Ask: `POST /workspaces/{ws}/query` — returns citations and surfaces contradictions.
- Upload: `POST /workspaces/{ws}/upload` — per-file parse status.
- Sources: connector catalog (`GET /sources/connectors`), `POST /sources`, OAuth connect, Telegram
  chat discovery (`GET /telegram/chats`), TDLib login (`POST /telegram/tdlib/connect[/code|/password]`).
- Actions: interpret → propose → approve/reject; `POST /actions/{id}/execute`, risk-gated. Read-only
  kinds (answer / find_evidence / draft / inspect_source) run from PROPOSED; START_SYNC,
  CREATE_MEMORY, CREATE_WIKI_PATCH, PROPOSE_SOURCE_CHANGE run after approval; EXTERNAL is blocked.
- Review: durable approval inbox, wiki inbox, and contradictions; memory-review and wiki routers.
- Evidence drill-down: claim → spans/quotes → artifact; memory cell → claims.
- Erasure: tombstone propagation across derived artifacts.
- Operators: provider config and per-task-class spend.
- Sensitivity tiers (incl. CONFIDENTIAL / RESTRICTED); private Telegram chats default to a more
  restrictive tier.

Small additions this plan assumes (presentation/response-shaping, not new subsystems):

- A per-citation **scope label** in the query response (sensitivity is already carried).
- A per-answer **routing-outcome flag** (kept on-device vs. external).
- **Answer-time presentation** of contradictions the query runtime already surfaces.
- A typed **policy/sensitivity block** result the UI renders calmly (the router already blocks; the
  UI needs the reason).

The activation loop also assumes three light *features* (more than presentation, but small):

- **Generated starter questions** from freshly ingested content (a small generation call).
- **Invite links** for new members (a token over the existing membership model).
- A **weekly digest** and a **"while you were away"** summary (scheduled summarization over the
  maintainer's existing output).

## Acceptance Criteria

The UI is ready for the 10-user product target when:

- A new admin can sign in, connect a source in their *personal* workspace, and reach a grounded,
  cited answer without reading docs — before any team or org configuration.
- A new admin can then create a shared workspace and invite members.
- An invited member reaches a first cited answer via an invite link with no org or setup steps.
- After a dense source is connected, the user is offered generated starter questions.
- Activation — a connected source, a question, and an opened citation — is reachable in one session.
- A returning user sees a "while you were away" summary when the maintainer did meaningful work.
- A normal user can understand which workspace and source scope they are asking.
- A user can verify an answer from source snippets without seeing raw ids.
- Each citation shows its scope and sensitivity, and a Mixed-scope answer visibly distinguishes
  personal-sourced from shared-sourced evidence.
- When sources conflict, the answer surfaces the disagreement rather than silently choosing.
- A sensitivity-restricted answer shows it was kept on-device, and the policy cannot be overridden
  from the UI.
- A user can erase a source or their data and see it removed from answers and evidence.
- A policy or sensitivity block is shown as a calm explanation with a clear next step, not an error.
- A failed upload or sync gives a clear next step.
- A reviewer can approve or reject a proposed action from one screen.
- Normal users do not see provider, job, audit, or raw configuration details.
- Admin and operator controls are available but not visually dominant; operator surfaces use the
  operator principal.
- The main navigation has no more than five persistent sections.

## Non-Goals

- A marketing landing page.
- A generic analytics dashboard.
- A full audit explorer for every user.
- A numeric confidence percentage presented as the primary trust signal (grounding, citations, and
  source agreement are the trust signals).
- Exposing every API route as a separate UI page.
- A separate Telegram page.
- Browser automation or advanced skills as first-run onboarding.
