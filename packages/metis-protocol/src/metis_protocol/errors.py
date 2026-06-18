"""Typed protocol error hierarchy.

These are raised by protocol helpers and by implementers of the interfaces.
``metis-protocol`` itself performs no I/O, so these are validation/contract
errors, not operational ones.
"""

from __future__ import annotations


class ProtocolError(Exception):
    """Base class for all errors defined by ``metis-protocol``."""


class IdValidationError(ProtocolError, ValueError):
    """A prefixed ID was malformed. Subclasses ``ValueError`` so it is converted
    into a pydantic ``ValidationError`` when raised inside a validator."""


class SchemaVersionError(ProtocolError):
    """A schema version was invalid, unknown, or registered twice."""


class UnknownEventError(ProtocolError, KeyError):
    """An event name has no registered payload spec."""


class PolicyViolationError(ProtocolError):
    """An operation was rejected by policy."""


class ContractViolationError(ProtocolError):
    """An interface implementation violated its declared contract."""
