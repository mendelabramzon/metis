"""Budget pre-flight: over-budget calls are rejected before generation."""

import pytest

from metis_core.llm import (
    BudgetConfig,
    BudgetExceededError,
    WorkspaceLedger,
    enforce_budget,
    estimate,
)
from metis_protocol import ModelMessage, ModelRequest, ModelTaskClass, Sensitivity


def _request(content: str, max_tokens: int) -> ModelRequest:
    return ModelRequest(
        task_class=ModelTaskClass.EXTRACT_CLAIMS,
        messages=(ModelMessage(role="user", content=content),),
        sensitivity=Sensitivity.INTERNAL,
        max_tokens=max_tokens,
    )


def test_over_token_budget_rejected() -> None:
    est = estimate(_request("x" * 40, max_tokens=1000), charge_external=False)
    with pytest.raises(BudgetExceededError):
        enforce_budget(est, BudgetConfig(max_tokens_per_call=100))


def test_over_cost_budget_rejected() -> None:
    est = estimate(_request("x" * 4000, max_tokens=4000), charge_external=True)
    assert est.estimated_cost_usd > 0
    with pytest.raises(BudgetExceededError):
        enforce_budget(est, BudgetConfig(max_cost_usd_per_call=0.0001))


def test_local_calls_are_free() -> None:
    est = estimate(_request("x" * 4000, max_tokens=4000), charge_external=False)
    assert est.estimated_cost_usd == 0.0
    enforce_budget(est, BudgetConfig())  # within token cap, no cost charged


def test_within_budget_passes() -> None:
    est = estimate(_request("hello", max_tokens=100), charge_external=True)
    enforce_budget(est, BudgetConfig())  # no raise


def test_workspace_daily_cap() -> None:
    ledger = WorkspaceLedger(BudgetConfig(max_tokens_per_workspace_day=100))
    ledger.check_and_add("ws_1", 60)
    with pytest.raises(BudgetExceededError):
        ledger.check_and_add("ws_1", 60)
