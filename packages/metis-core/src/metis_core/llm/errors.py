"""Errors raised by the model router/call path."""

from __future__ import annotations


class ModelError(Exception):
    """Base class for model-layer errors."""


class NoEligibleProviderError(ModelError):
    """No provider may serve a request under the active policy/allowlist."""


class ModelRefusalError(ModelError):
    """The provider declined the request (a hard refusal — surfaced, not retried)."""


class StructuredOutputError(ModelError):
    """The model output failed validation against the requested schema."""


class BudgetExceededError(ModelError):
    """A call was rejected pre-flight because it would exceed a budget cap."""
