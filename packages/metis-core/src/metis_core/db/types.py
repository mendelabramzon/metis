"""Reusable column types: JSONB body, reserved pgvector embedding, tz-aware datetime.

IDs and protocol enums are stored as strings (the protocol layer owns their typing
and validation); the pgvector column is reserved dimensionless here and indexed in
the retrieval stage once an embedding model is fixed (ADR 0011).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import mapped_column

# Annotated column types for SQLAlchemy 2.0 `Mapped[...]` mapping.
Id = Annotated[str, mapped_column(String(80))]
Enum = Annotated[str, mapped_column(String(48))]
Body = Annotated[dict[str, Any], mapped_column(JSONB)]
TZDateTime = Annotated[datetime, mapped_column(DateTime(timezone=True))]
Embedding = Annotated[list[float] | None, mapped_column(Vector(), nullable=True)]

__all__ = ["JSONB", "Body", "Embedding", "Enum", "Id", "TZDateTime", "Vector"]
