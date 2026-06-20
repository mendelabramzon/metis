"""Declarative routing: task class -> quality tier, the external-provider block floor,
and budget caps. The task->tier map is the single source of truth shared by the router
(provider selection) and the providers (model selection).
"""

from __future__ import annotations

from metis_protocol import ModelTaskClass, ModelTier, ProtocolModel, Sensitivity

# Quality floor per task class. Restricted data still routes to a local provider
# regardless of the tier here (enforced by the router).
_TASK_TIER: dict[ModelTaskClass, ModelTier] = {
    ModelTaskClass.PARSE_ASSIST: ModelTier.LOCAL,
    ModelTaskClass.SEGMENT: ModelTier.LOCAL,
    ModelTaskClass.EXTRACT_CLAIMS: ModelTier.STANDARD,
    ModelTaskClass.EXTRACT_ENTITIES: ModelTier.STANDARD,
    ModelTaskClass.EXTRACT_EVENTS: ModelTier.STANDARD,
    ModelTaskClass.SUMMARIZE_EPISODE: ModelTier.STANDARD,
    ModelTaskClass.CONSOLIDATE_MEMORY: ModelTier.FRONTIER,
    ModelTaskClass.DETECT_CONTRADICTION: ModelTier.FRONTIER,
    ModelTaskClass.BUILD_FORESIGHT: ModelTier.FRONTIER,
    ModelTaskClass.WIKI_COMPILE: ModelTier.FRONTIER,
    ModelTaskClass.QUERY_REWRITE: ModelTier.LOCAL,
    ModelTaskClass.QUERY_ANSWER: ModelTier.FRONTIER,
    ModelTaskClass.QUERY_VERIFY: ModelTier.STANDARD,
    ModelTaskClass.SKILL_PLAN: ModelTier.FRONTIER,
    ModelTaskClass.SKILL_EXECUTE: ModelTier.STANDARD,
    ModelTaskClass.INTERPRET_COMMAND: ModelTier.STANDARD,
}

#: Default Anthropic model per tier (LOCAL is served by a local provider).
DEFAULT_TIER_MODELS: dict[ModelTier, str] = {
    ModelTier.STANDARD: "claude-sonnet-4-6",
    ModelTier.FRONTIER: "claude-opus-4-8",
}


def task_tier(task_class: ModelTaskClass) -> ModelTier:
    return _TASK_TIER.get(task_class, ModelTier.STANDARD)


class BudgetConfig(ProtocolModel):
    max_tokens_per_call: int = 200_000
    max_cost_usd_per_call: float = 5.0
    max_tokens_per_workspace_day: int = 50_000_000


class RoutingConfig(ProtocolModel):
    budget: BudgetConfig = BudgetConfig()
    # Sensitivity at or above this level forbids external providers (local only).
    external_block_floor: Sensitivity = Sensitivity.RESTRICTED
