"""Shared enumerations used across schemas, policy, and events.

All are ``StrEnum`` so they serialize to readable strings and round-trip through
JSON as their value.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final


class Sensitivity(StrEnum):
    """Data sensitivity, ordered least to most restrictive (see ``SENSITIVITY_ORDER``)."""

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


#: Sensitivity from least to most restrictive; index doubles as the rank.
SENSITIVITY_ORDER: Final[tuple[Sensitivity, ...]] = (
    Sensitivity.PUBLIC,
    Sensitivity.INTERNAL,
    Sensitivity.CONFIDENTIAL,
    Sensitivity.RESTRICTED,
)


class ModelTier(StrEnum):
    """Quality/cost tier a task may be routed to."""

    LOCAL = "local"
    STANDARD = "standard"
    FRONTIER = "frontier"


class JobState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"


class ArtifactKind(StrEnum):
    """The category of a raw artifact, independent of media type."""

    FILE = "file"
    EMAIL = "email"
    CHAT_MESSAGE = "chat_message"
    WEB_PAGE = "web_page"
    CALENDAR_EVENT = "calendar_event"
    API_RECORD = "api_record"
    UNKNOWN = "unknown"


class SegmentKind(StrEnum):
    PARAGRAPH = "paragraph"
    HEADING = "heading"
    TABLE = "table"
    LIST = "list"
    CODE = "code"
    OTHER = "other"


class EntityKind(StrEnum):
    PERSON = "person"
    ORGANIZATION = "organization"
    PROJECT = "project"
    LOCATION = "location"
    PRODUCT = "product"
    CONCEPT = "concept"
    DOCUMENT = "document"
    OTHER = "other"


class AgentKind(StrEnum):
    """What kind of agent produced an artifact (PROV ``Agent``)."""

    CONNECTOR = "connector"
    PARSER = "parser"
    EXTRACTOR = "extractor"
    MODEL = "model"
    SKILL = "skill"
    MAINTAINER = "maintainer"
    HUMAN = "human"
    SYSTEM = "system"


class ProfileScope(StrEnum):
    WORKSPACE = "workspace"
    USER = "user"
    COMPANY = "company"
    PERSON = "person"


class MemoryOp(StrEnum):
    """Append-only memory revision operations."""

    CREATE = "create"
    SUPERSEDE = "supersede"
    RETRACT = "retract"


class WikiOp(StrEnum):
    CREATE = "create"
    UPDATE = "update"
    TOMBSTONE = "tombstone"


class ForesightStatus(StrEnum):
    ACTIVE = "active"
    CONFIRMED = "confirmed"
    EXPIRED = "expired"
    REFUTED = "refuted"


class ContradictionStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class SkillOutcome(StrEnum):
    SUCCESS = "success"
    ERROR = "error"
    REJECTED = "rejected"
    NEEDS_APPROVAL = "needs_approval"


class PermissionScope(StrEnum):
    """Capabilities a skill (or other actor) can be granted; enforced outside prompts."""

    NETWORK = "network"
    FILESYSTEM_READ = "filesystem_read"
    FILESYSTEM_WRITE = "filesystem_write"
    CONNECTOR = "connector"
    SECRETS = "secrets"
    OUTBOUND_ACTION = "outbound_action"
    MODEL_CALL = "model_call"
    SUBPROCESS = "subprocess"


class WorkspaceKind(StrEnum):
    """What a workspace is for; ``EXTERNAL`` is reserved for federated/imported context."""

    PERSONAL = "personal"
    SHARED = "shared"
    EXTERNAL = "external"


class Role(StrEnum):
    """A user's role in a workspace.

    Any role grants read. ``MEMBER`` and above may write; ``ADMIN``/``OWNER`` may
    administer membership. ``AUDITOR`` is read-only (it may read, including audit, but
    never writes) and so sits outside the write ladder — see the ``role_*`` helpers in
    ``policy`` rather than ordering these values directly.
    """

    AUDITOR = "auditor"
    VIEWER = "viewer"
    MEMBER = "member"
    ADMIN = "admin"
    OWNER = "owner"
