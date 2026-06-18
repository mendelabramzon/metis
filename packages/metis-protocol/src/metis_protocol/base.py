"""The shared pydantic base for every protocol value object."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ProtocolModel(BaseModel):
    """Frozen, strict base for all protocol models.

    - ``frozen=True``: protocol objects are immutable value types (and hashable
      when all their fields are hashable — prefer ``tuple`` over ``list`` for
      collections so models stay hashable).
    - ``extra="forbid"``: unknown fields raise loudly, so schema drift surfaces at
      the boundary instead of being silently dropped.
    - bytes are base64 in JSON so every model round-trips losslessly.
    - ``validate_default=True``: defaults (e.g. ``schema_version``) are validated,
      not trusted.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        ser_json_bytes="base64",
        val_json_bytes="base64",
        validate_default=True,
        # We legitimately use "model_*" field names (model_version, model_tier,
        # model_run); none clash with BaseModel members, so drop the guard.
        protected_namespaces=(),
    )
