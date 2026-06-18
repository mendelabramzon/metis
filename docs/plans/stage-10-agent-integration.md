# Stage 10 Detailed Plan: Runtime-Agent Integration

Parent: [high-level-implementation-plan.md](high-level-implementation-plan.md), Stage 10. Builds on Stages 0–9.

This stage combines retrieval, memory, and skills into an action-capable assistant. It implements a ReAct-style loop (reason → act → observe) with a tool/skill planner, context-aware skill selection, action approval, an inspectable execution trace, and file-back of useful outputs. The security spine: retrieved content is untrusted data, model output is a proposal, and outbound actions are approval-gated by default.

## Objective

- Implement the agent loop `user request → classify → retrieve context → plan → call tools/skills → observe → verify → answer/action proposal → commit approved outputs`.
- Implement the tool/skill planner and context-aware skill selection.
- Implement an action approval UX/API, an execution trace model, and task state persistence.
- File generated artifacts and compound useful outputs back into memory/wiki through patches.

Non-goals: defining new skills (Stage 9) or new retrievers (Stage 8) — this stage orchestrates them. Network connectors are Stage 11.

## Package Ownership

- Owns: `metis-runtime` (+ `services/runtime-worker`).
- Uses the Stage 8 retrieval/answer pipeline, the Stage 9 `SkillRunner`, and the Stage 4 router (`skill_plan`, `skill_execute`).
- The model-side tool-use mechanism is provided by the provider (e.g., Claude tool use); Metis owns the loop, the sandbox, the policy, and the approval gate.

## Concrete Files And Modules To Create

```text
packages/metis-runtime/src/metis_runtime/agent/
  loop.py                # ReAct loop: reason -> act -> observe -> verify
  classify.py            # classify request: answer-only vs tool-requiring
  planner.py             # tool/skill planner; selects skills via the registry tool-doc index
  select.py              # context-aware skill selection (Gorilla-style retrieval over tool docs)
  trace.py               # execution trace model (inspectable)
  state.py               # task state persistence (resumable runs)
  taint.py               # taint tracking: retrieved/untrusted content cannot directly instruct tools
  commit.py              # commit approved outputs; file-back to memory/wiki via patches
  approval.py            # action approval flow (wraps Stage 9 approval queue)

packages/metis-runtime/tests/
  test_answer_without_tools.py
  test_skill_selection.py
  test_untrusted_cannot_instruct.py
  test_trace_inspectable.py
  test_fileback_compounding.py
```

## Schemas And Interfaces Touched

- Consumes `ContextBundle`, `SkillManifest`/`SkillInput`/`SkillResult`, and produces answer/action artifacts and an execution trace.
- Reuses the Stage 8 `Retriever`/`ContextPacker` and Stage 9 `SkillRunner`; routes planning/execution through the Stage 4 router.
- Emits events: `agent.run.started/finished`, `agent.action.proposed/committed`, `agent.fileback.proposed`.
- Enforces the taint boundary: untrusted retrieved content is data, never instructions to tools.

## Implementation Steps

1. Implement `classify.py` (answer-only vs tool-requiring) and `loop.py` (the ReAct cycle with verification before answering/acting).
2. Implement `planner.py` + `select.py`: plan the tool/skill sequence and select skills via the registry's tool-doc index based on task context.
3. Implement `taint.py`: mark retrieved/untrusted content so it cannot directly drive tool calls or actions (prompt-injection containment).
4. Implement `trace.py` and `state.py`: record an inspectable execution trace and persist task state for resumable, auditable runs.
5. Implement `approval.py` + `commit.py`: outbound/destructive actions go through approval; approved outputs are filed and can compound back into memory/wiki via patches (never direct writes).
6. Integrate with the Stage 8 answer pipeline so the agent can answer without tools when tools are unnecessary.

## Tests And Fixtures

- **Answer without tools** (`test_answer_without_tools.py`): the agent answers directly when no tool is needed.
- **Skill selection** (`test_skill_selection.py`): the agent selects the appropriate skill based on context.
- **Untrusted cannot instruct** (`test_untrusted_cannot_instruct.py`): injected instructions inside retrieved content do not trigger tool calls/actions (the headline security test).
- **Trace inspectable** (`test_trace_inspectable.py`): action traces are complete and inspectable.
- **Compounding file-back** (`test_fileback_compounding.py`): useful outputs compound back into memory/wiki through patches.

Fixtures: a no-tool question, a skill-requiring task, a prompt-injection document, and an output worth filing back.

## Acceptance Criteria

Traces to the Stage 10 "Validation" list:

- The agent can answer without tools when tools are unnecessary.
- The agent can choose skills based on context and task.
- Untrusted retrieved content cannot directly instruct tools.
- Action traces are inspectable.
- Useful outputs can compound back into memory/wiki through patches.

## Risks And Open Questions

- **Prompt-injection containment**: the taint boundary is the hardest and most important piece; validate against AgentDojo-style scenarios (deepened in Stage 14). Model output is a proposal, not authority.
- **Planner reliability**: over-eager tool use wastes cost and adds risk; classify aggressively so simple questions stay answer-only.
- **Build vs Managed Agents**: a provider's managed-agent surface could run the loop and host tool execution, but Metis requires local policy, provenance, sandboxing, and approval — so the loop and sandbox are owned here; a managed surface is at most an alternative execution backend to evaluate later.
- **State persistence semantics**: resumable runs need careful trace/state modeling so a resumed run remains auditable and idempotent.
- **Approval UX latency**: approval gates add human latency; design for async approval without blocking unrelated work (ties to Stage 12 inbox).
- **File-back loops**: compounding outputs back into memory/wiki risks feedback loops; always go through validated patches with provenance.
