# UX/UI Implementation Tickets

Derived from [`../uxui.md`](../uxui.md). Scope: build the team-facing frontend (a real SPA) on top of
the completed Stage 1 backend, plus the small gateway additions the frontend trust/onboarding features
require. Assumes the deployment is already running.

**Legend.** Layer: `GW` gateway/backend, `FE` frontend. Size: `S` ≤1 day, `M` 1–3 days, `L` 3–5 days.
"Depends" lists hard prerequisites only. Acceptance lines trace back to `uxui.md`'s acceptance criteria.

## Recommended milestone order

- **M0 — Unblockers:** A1–A4 (trust-feature response fields), A6 (invites, if onboarding lands early).
- **M1 — Shell:** B1–B4; optionally C1–C3 to make the existing single-file console product-shaped first.
- **M2 — Core loop:** D1–D3, D7, E1–E4 → a cited answer works end to end in the SPA.
- **M3 — Onboarding/activation:** A5, A6, H1–H4, H6 → the smooth first-run.
- **M4 — Trust differentiators:** D4–D6, E6 (consume A2/A3/A4) → the "why Metis over ChatGPT" surfaces.
- **M5 — Review/Activity/Settings/Operator:** F1–F3, G1–G5.
- **M6 — Return loop:** A7, F4, H5.

The three highest-leverage tickets (the product differentiators): **D2** (per-citation scope/sensitivity),
**D4** (answer-time "sources disagree"), **E6 + D6** (erasure + blocked-by-policy).

---

## Epic A — Gateway unblockers

Small backend additions; the frontend trust and onboarding tickets depend on them. Each preserves the
existing invariants (no new memory writes, policy stays in the router).

### A1 — Per-citation scope label in query response · `GW` · `S`
Add the owning workspace + scope (personal/shared) to each citation in the `/workspaces/{ws}/query`
response. Sensitivity is already carried.
Acceptance: every citation carries scope + sensitivity; mixed queries label each citation's origin.
Depends: —

### A2 — Per-answer routing-outcome flag · `GW` · `S`
Expose whether the answer was produced on a local/on-device provider or an external one (a flag the
router already knows), without leaking the provider/model name.
Acceptance: query response includes a `routed_local|routed_external` outcome.
Depends: —

### A3 — Surface contradictions at query time · `GW` · `M`
The query runtime already detects contradictions (Stage 8); include the relevant conflicting claims +
their spans in the query response so the UI can show them at answer time, not only in Review.
Acceptance: an answer over conflicting evidence returns both sides with source spans.
Depends: —

### A4 — Typed policy/sensitivity block result · `GW` · `S`
When the router/policy blocks a request (e.g. restricted data, EXTERNAL action), return a typed,
human-readable block result distinct from an error.
Acceptance: a blocked request returns a `blocked` result with a reason code + message, not a 5xx.
Depends: —

### A5 — Generated starter questions · `GW` · `M`
Endpoint that, given a workspace with freshly ingested content, returns ~3 grounded starter questions
(a small generation call over recent artifacts/claims).
Acceptance: after a source ingests, the endpoint returns 3 answerable questions citing that source.
Depends: —

### A6 — Invite links · `GW` · `M`
Create/redeem invite tokens over the existing membership model (membership already exists; this is the
token + redemption path).
Acceptance: an admin mints an invite; redeeming it signs the user in and provisions a personal workspace.
Depends: —

### A7 — Weekly digest + "while you were away" summary · `GW` · `M`
Scheduled summarization over the maintainer's existing output (synced items, reconciled facts, new
contradictions/proposals); plus an on-demand "since last visit" summary per user/workspace.
Acceptance: a per-user summary is available on login and as an opt-in weekly digest.
Depends: —

---

## Epic B — App shell & platform

### B1 — Design system, tokens, a11y baseline · `FE` · `M`
Calm visual direction: restrained color, status colors only for meaningful status, calm (non-alarming)
styling for scope/sensitivity/routing, compact cards. Semantic structure, keyboard nav, contrast from
the start.
Acceptance: shared components (cards, badges, drawer, empty/error/blocked states) pass keyboard +
contrast checks.
Depends: —

### B2 — App shell + 5-section nav + role-based hiding · `FE` · `M`
Header (logo, workspace switcher slot, scope badge, user menu); left nav Ask/Sources/Review/Activity/
Settings; nav items hidden by granted role.
Acceptance: nav shows ≤5 persistent sections; items the role can't access are hidden.
Depends: B1

### B3 — Login/session + dual principals · `FE` · `M`
Sign-in UI; handle the user principal (per-workspace surfaces) vs the operator principal (Operations);
session persistence.
Acceptance: a user reaches per-workspace surfaces; operator surfaces require the operator principal.
Depends: B1; A6 (for invite redeem)

### B4 — Workspace switcher + scope selector · `FE` · `S`
Switch active workspace (`GET /workspaces`); Personal/Shared/Mixed scope selector; both persisted
across sessions and always visible.
Acceptance: scope is always visible and restored from last session.
Depends: B2

---

## Epic C — Phase 1a: console reorg (optional early win)

Reorganize the existing single-file console before the SPA, to reduce distraction. Skip if going
straight to the SPA.

### C1 — Relabel to five areas + relocate admin tabs · `FE` · `S`
Rename tabs into the five areas; move audit, jobs, providers, spend under Settings/Operations.
Acceptance: no top-level tabs for providers/jobs/audit/contradictions/Telegram/spend.
Depends: —

### C2 — Sign-in selector / bootstrap · `FE` · `S`
Replace raw user-id / operator-token fields with a sign-in selector or bootstrap screen.
Acceptance: no raw id/token entry in normal use.
Depends: —

### C3 — Collapse developer details · `FE` · `S`
Move ids/JSON/traces/job data behind a "Developer details" disclosure.
Acceptance: no raw ids/JSON in default views.
Depends: —

---

## Epic D — Ask

### D1 — Ask screen layout + states · `FE` · `M`
Answer area, composer fixed at bottom (desktop+mobile), compact context strip, citation drawer (right
on desktop, bottom sheet on mobile). Wire the state machine: no-context / asking / sufficient /
conflicting / insufficient / blocked / action-proposal / error.
Acceptance: all listed states render distinctly.
Depends: B2, B4

### D2 — Citation cards + drawer (scope + sensitivity) · `FE` · `M`
Source cards under the answer; each expands to quote/source/date/page + scope + sensitivity. Mixed-scope
answers visually distinguish personal- vs shared-sourced evidence. Ids only under Developer details.
Acceptance: each citation shows scope + sensitivity; mixed answers split personal vs shared.
Depends: D1, A1

### D3 — Sufficiency framing · `FE` · `S`
"Answered from your sources" vs "Not enough evidence yet" with inline next actions (upload, connect,
broaden scope). No numeric confidence score.
Acceptance: insufficient-evidence answers offer inline add-context actions.
Depends: D1

### D4 — "Sources disagree" panel · `FE` · `M`
At answer time, show conflicting claims (each side: snippet/source/scope/date); do not silently pick.
Link to open the contradiction in Review.
Acceptance: conflicting evidence is surfaced at answer time, never merged.
Depends: D1, A3

### D5 — Routing-outcome note · `FE` · `S`
Quiet "kept on-device / used an external model" note on the answer.
Acceptance: a restricted answer shows it was kept on-device; policy can't be overridden from the UI.
Depends: D1, A2

### D6 — Blocked-by-policy state · `FE` · `S`
Calm explanation for a policy/sensitivity block, with a next step; no naive retry.
Acceptance: a blocked request renders calmly, distinct from an error.
Depends: D1, A4

### D7 — Proposed-action cards · `FE` · `M`
One Ask flow (merge command+ask): effectful requests return an action card (type, target source/
workspace, risk label, expected outcome, evidence). Approve/reject → execute dispatch. Read-only kinds
run without approval; EXTERNAL shown as blocked.
Acceptance: read-only actions create no approval noise; memory/wiki/source/sync changes are explicit
and approval-gated; risk labels are Read only / Updates memory / Changes source / External action.
Depends: D1

---

## Epic E — Sources

### E1 — Sources screen · `FE` · `M`
Source health summary (Healthy/Needs attention/Syncing); cards grouped by workspace; add-source modal;
upload dropzone as first card when empty.
Acceptance: source states render (empty/syncing/connected/needs-re-auth/awaiting-login/parse-warning/
failed); no job ids as primary status.
Depends: B2

### E2 — File upload flow · `FE` · `M`
Batch upload (`/workspaces/{ws}/upload`) with progress and per-file parse status (parsed/warning/
failed) and retry.
Acceptance: every supported format ingests with visible parse status; a failed file gives a next step
without blocking the batch.
Depends: E1

### E3 — Connector setup (catalog + OAuth) · `FE` · `M`
Catalog-driven add-source (`GET /sources/connectors`); OAuth redirect for Drive/Gmail; scope selection
(mailbox/folder/chat); sensitivity confirm. No connector JSON for normal users; credentials never
re-shown.
Acceptance: a source connects without JSON; only selected scopes ingest.
Depends: E1

### E4 — Telegram bot connect + chat selection · `FE` · `M`
Bot connect; chat discovery (`GET /telegram/chats`); explicit chat selection → add as source; per-chat
sensitivity default.
Acceptance: a user selects specific chats; unselected conversations are not ingested.
Depends: E3

### E5 — Telegram TDLib login sub-flow · `FE` · `M`
Guided interactive login (`POST /telegram/tdlib/connect[/code|/password]`) with states: awaiting QR /
awaiting code / awaiting 2FA / ready / failed. Stays inside Sources; never blocks the rest of the screen.
Acceptance: login sub-flow completes with its own states; codes/2FA never shown after entry.
Depends: E3

### E6 — Erasure flow · `FE` · `M`
"Remove from this workspace" vs "Permanently delete everywhere"; explicit non-default confirm; messaging
that erasure tombstones derived artifacts.
Acceptance: erased content stops appearing in answers/evidence; remove vs delete are clearly distinct.
Depends: E1

---

## Epic F — Review & Activity

### F1 — Review queue · `FE` · `M`
One queue (merge approvals + contradictions): pending by default; selected-item details; evidence panel;
decision controls; completed/dismissed behind a filter.
Acceptance: a reviewer decides from one screen; resolved items leave the pending queue.
Depends: B2

### F2 — Contradiction + proposal cards · `FE` · `M`
Contradiction cards (conflicting claims + snippets; resolve/dismiss/request more); memory/wiki proposal
cards with diffs.
Acceptance: decisions are made from source evidence, not summaries; memory/wiki changes show diffs.
Depends: F1

### F3 — Activity timeline + audit filtering · `FE` · `M`
Timeline grouped by day; event detail drawer; audit translated to user language. Filtering rule: a user
sees their own actions + events in workspaces they can access; cross-actor/operator audit stays in
Operations.
Acceptance: everyday Activity excludes operator-level and cross-actor audit.
Depends: B2

### F4 — "While you were away" on entry · `FE` · `S`
Quiet summary line on return when the maintainer did meaningful work.
Acceptance: returning users see a summary when there is one.
Depends: A7

---

## Epic G — Settings & operator

### G1 — Settings shell · `FE` · `S`
Subsections: Workspace, Members, Permissions, Model policy, Data & erasure, Operations (operator-only).
Acceptance: settings are separate from everyday ask/source flows.
Depends: B2

### G2 — Members + invite · `FE` · `M`
Invite (mint link), list, remove members; role assignment.
Acceptance: an admin invites/removes members and assigns roles.
Depends: G1, A6

### G3 — Source permissions + sensitivity defaults · `FE` · `S`
Per-source permission + workspace sensitivity defaults.
Acceptance: admins set sensitivity defaults; private sources default more restrictive.
Depends: G1

### G4 — Model policy + spend caps · `FE` · `M`
Admin view: workspace model policy (external allowed?) + per-workspace spend caps; read spend.
Acceptance: spend is visible; caps are settable; policy feeds the router (not overridable per-answer).
Depends: G1

### G5 — Operations (operator-only) · `FE` · `M`
Compact health dashboard; failed-job drilldown; provider config; audit search; backup/restore status.
Acceptance: operator surfaces use the operator principal and are not in the default experience.
Depends: G1, B3

---

## Epic H — Onboarding & activation

### H1 — First-admin bootstrap · `FE` · `M`
Claim deployment → name org (one field) → land in the **personal** workspace empty state. Team/share
offered only after the first verified answer.
Acceptance: a new admin reaches a cited answer in their personal workspace before any team/org config.
Depends: B3

### H2 — Invited-member path · `FE` · `S`
Invite link → sign in → personal workspace; one-line note of shared workspaces joined.
Acceptance: an invited member reaches a first cited answer with no org/setup steps.
Depends: A6, B3

### H3 — First Value loop · `FE` · `L`
Foreground one dense source → connect with privacy shown in place → honest ingest progress → generated
starter questions → first answer → verify-click nudge. Then offer expansion.
Acceptance: from empty workspace to verified cited answer in one session without docs.
Depends: A5, E1, E2/E3/E4, D2

### H4 — Forgiving first-run states · `FE` · `S`
Not-enough-evidence / parse-fail / still-backfilling / blocked-by-policy as next steps, not dead ends.
Acceptance: each first-run failure offers a clear next action.
Depends: D3, E2, D6

### H5 — Weekly-digest opt-in · `FE` · `S`
Offer the digest during onboarding (defaulted on for the first admin); introduce Review as the
"brought to you" surface.
Acceptance: digest is opt-in and discoverable at onboarding.
Depends: A7

### H6 — Activation instrumentation · `FE` · `S`
Emit the activation event = connected dense source + asked a question + opened a citation.
Acceptance: activation is measurable per user.
Depends: D2, E3
