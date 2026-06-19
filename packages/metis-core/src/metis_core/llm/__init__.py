"""The model router and call path: swappable, policy-bound, audited LLM access.

Lives in ``metis_core.llm`` (not ``metis_core.models``, which is the ORM layer); the
placement and Anthropic/model-tier choices are recorded in ADR 0013.
"""

from __future__ import annotations

from metis_core.llm.audit_fields import build_model_audit_event, model_run_hash
from metis_core.llm.budget import (
    BudgetEstimate,
    WorkspaceLedger,
    enforce_budget,
    estimate,
    estimate_tokens,
)
from metis_core.llm.call import ModelCaller
from metis_core.llm.capability import chat_provider_from_capability
from metis_core.llm.errors import (
    BudgetExceededError,
    ModelError,
    ModelRefusalError,
    NoEligibleProviderError,
    StructuredOutputError,
)
from metis_core.llm.evaluation import ExtractionEvalResult, compare_providers, evaluate_extraction
from metis_core.llm.pricing import cost_usd
from metis_core.llm.prompts import PromptRegistry, PromptTemplate, default_registry
from metis_core.llm.provider import AnthropicProvider, OpenAICompatProvider, StubProvider
from metis_core.llm.repair import call_with_repair
from metis_core.llm.router import MetisModelRouter, RoutableProvider
from metis_core.llm.routing_config import (
    DEFAULT_TIER_MODELS,
    BudgetConfig,
    RoutingConfig,
    task_tier,
)
from metis_core.llm.structured import parse_structured, schema_for

__all__ = [
    "DEFAULT_TIER_MODELS",
    "AnthropicProvider",
    "BudgetConfig",
    "BudgetEstimate",
    "BudgetExceededError",
    "ExtractionEvalResult",
    "MetisModelRouter",
    "ModelCaller",
    "ModelError",
    "ModelRefusalError",
    "NoEligibleProviderError",
    "OpenAICompatProvider",
    "PromptRegistry",
    "PromptTemplate",
    "RoutableProvider",
    "RoutingConfig",
    "StructuredOutputError",
    "StubProvider",
    "WorkspaceLedger",
    "build_model_audit_event",
    "call_with_repair",
    "chat_provider_from_capability",
    "compare_providers",
    "cost_usd",
    "default_registry",
    "enforce_budget",
    "estimate",
    "estimate_tokens",
    "evaluate_extraction",
    "model_run_hash",
    "parse_structured",
    "schema_for",
    "task_tier",
]
