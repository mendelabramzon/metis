"""Small internal helpers shared across core."""

from __future__ import annotations

from datetime import UTC, datetime

from metis_protocol import AgentKind, Attribution


def now_utc() -> datetime:
    return datetime.now(UTC)


def system_actor() -> Attribution:
    return Attribution(agent_kind=AgentKind.SYSTEM, agent="metis-core")
