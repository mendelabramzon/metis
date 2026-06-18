"""Pre-flight budget estimation and enforcement.

Token counts are estimated with a heuristic (real ``count_tokens`` is provider-specific
and reconciled against actual usage from the ``ModelRun``). Cost is charged at the tier
model's rate only when the call is routed externally; local calls are treated as free.
"""

from __future__ import annotations

from dataclasses import dataclass

from metis_core.llm.errors import BudgetExceededError
from metis_core.llm.pricing import cost_usd
from metis_core.llm.routing_config import DEFAULT_TIER_MODELS, BudgetConfig, task_tier
from metis_protocol import ModelRequest

_CHARS_PER_TOKEN = 4


def estimate_tokens(request: ModelRequest) -> int:
    input_chars = sum(len(message.content) for message in request.messages)
    return input_chars // _CHARS_PER_TOKEN + (request.max_tokens or 0)


@dataclass(frozen=True)
class BudgetEstimate:
    estimated_tokens: int
    estimated_cost_usd: float


def estimate(request: ModelRequest, *, charge_external: bool) -> BudgetEstimate:
    tokens = estimate_tokens(request)
    if not charge_external:
        return BudgetEstimate(tokens, 0.0)
    model = DEFAULT_TIER_MODELS.get(task_tier(request.task_class), "claude-opus-4-8")
    cost = cost_usd(model, tokens, request.max_tokens or 0) or 0.0
    return BudgetEstimate(tokens, cost)


def enforce_budget(estimate: BudgetEstimate, config: BudgetConfig) -> None:
    if estimate.estimated_tokens > config.max_tokens_per_call:
        raise BudgetExceededError(
            f"estimated {estimate.estimated_tokens} tokens exceeds per-call cap "
            f"{config.max_tokens_per_call}"
        )
    if estimate.estimated_cost_usd > config.max_cost_usd_per_call:
        raise BudgetExceededError(
            f"estimated ${estimate.estimated_cost_usd:.4f} exceeds per-call cap "
            f"${config.max_cost_usd_per_call:.2f}"
        )


class WorkspaceLedger:
    """In-memory per-workspace token accounting for the daily cap."""

    def __init__(self, config: BudgetConfig) -> None:
        self._config = config
        self._used: dict[str, int] = {}

    def check_and_add(self, workspace_id: str, tokens: int) -> None:
        used = self._used.get(workspace_id, 0)
        if used + tokens > self._config.max_tokens_per_workspace_day:
            raise BudgetExceededError(
                f"workspace {workspace_id} would exceed the daily token cap "
                f"{self._config.max_tokens_per_workspace_day}"
            )
        self._used[workspace_id] = used + tokens
