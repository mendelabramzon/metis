"""HTTP routers: thin projections of the engine onto the API surface.

Each router maps requests to backend calls and protocol objects to wire DTOs — no business logic.
"""

from __future__ import annotations

from metis_gateway.routers import (
    approvals,
    audit,
    ingestion,
    jobs,
    query,
    skills,
    sources,
    wiki,
)

ALL_ROUTERS = (
    sources.router,
    ingestion.router,
    query.router,
    wiki.router,
    skills.router,
    approvals.router,
    jobs.router,
    audit.router,
)

__all__ = ["ALL_ROUTERS"]
