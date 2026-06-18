"""Reusable column types: JSONB body, fixed-dimension pgvector embedding, tz-aware datetime.

IDs and protocol enums are stored as strings (the protocol layer owns their typing
and validation). The pgvector column was reserved dimensionless in Stage 2 (ADR 0011);
Stage 5 fixes the embedding model and so locks the dimension here (``EMBEDDING_DIM``,
ADR 0014). A model change is therefore a re-index — never a silent dimension mismatch —
and the HNSW indexes (which require a fixed dimension) are created in migration 0002.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Final

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import mapped_column

#: Fixed embedding dimension for every vector column (bge-m3 default; ADR 0014).
#: ``metis_core.memory_index`` owns the model/version that produces these vectors.
EMBEDDING_DIM: Final = 1024

# Annotated column types for SQLAlchemy 2.0 `Mapped[...]` mapping.
Id = Annotated[str, mapped_column(String(80))]
Enum = Annotated[str, mapped_column(String(48))]
Body = Annotated[dict[str, Any], mapped_column(JSONB)]
TZDateTime = Annotated[datetime, mapped_column(DateTime(timezone=True))]
Embedding = Annotated[list[float] | None, mapped_column(Vector(EMBEDDING_DIM), nullable=True)]

__all__ = ["EMBEDDING_DIM", "JSONB", "Body", "Embedding", "Enum", "Id", "TZDateTime", "Vector"]
