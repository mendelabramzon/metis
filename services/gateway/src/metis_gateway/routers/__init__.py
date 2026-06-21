"""HTTP routers: thin projections of the engine onto the API surface.

Each router maps requests to backend calls and protocol objects to wire DTOs — no business logic.
"""

from __future__ import annotations

from metis_gateway.routers import (
    actions,
    admin,
    approvals,
    audit,
    contradictions,
    documents,
    evidence,
    ingestion,
    invites,
    jobs,
    memory,
    oauth,
    providers,
    query,
    runtime,
    skills,
    sources,
    telegram,
    upload,
    users,
    wiki,
    workspaces,
)

ALL_ROUTERS = (
    users.router,
    workspaces.router,
    invites.router,
    actions.router,
    sources.router,
    telegram.router,
    ingestion.router,
    upload.router,
    documents.router,
    query.router,
    runtime.router,
    evidence.router,
    contradictions.router,
    memory.router,
    wiki.router,
    skills.router,
    approvals.router,
    jobs.router,
    audit.router,
    providers.router,
    oauth.router,
    admin.router,
)

__all__ = ["ALL_ROUTERS"]
