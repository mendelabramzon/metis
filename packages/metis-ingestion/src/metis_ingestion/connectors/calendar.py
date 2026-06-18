"""Calendar / CalDAV connector: render events to text, honoring an event's visibility class.

Each event becomes a small text doc (summary, time, place, notes); a ``private``/``confidential``
visibility class floors the artifact's sensitivity so a private meeting does not normalize to the
same policy as a public one. The event's ``updated`` timestamp is its cursor, so a changed event is
re-ingested and dedups on content downstream.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, TypeAdapter

from metis_ingestion import mime
from metis_ingestion._build import stable_id
from metis_ingestion.connectors.base import BaseConnector, ConnectorError, RenderedPayload
from metis_ingestion.mime import MediaInfo
from metis_protocol import ArtifactKind, Sensitivity, SourceId, SourceRef, max_sensitivity

_EVENTS_KEY = "events.json"
_CLASS_FLOOR = {
    "private": Sensitivity.CONFIDENTIAL,
    "confidential": Sensitivity.CONFIDENTIAL,
}


class _Event(BaseModel):
    uid: str
    summary: str = ""
    start: str = ""
    end: str = ""
    location: str = ""
    description: str = ""
    updated: str = ""
    classification: str = "public"  # "public" | "private" | "confidential"


_EVENTS = TypeAdapter(tuple[_Event, ...])


class CalendarConnector(BaseConnector):
    connector = "calendar"

    def _events(self) -> tuple[_Event, ...]:
        return _EVENTS.validate_json(self._read(_EVENTS_KEY))

    async def discover(self, cursor: str | None) -> Sequence[SourceRef]:
        refs: list[SourceRef] = []
        for event in self._events():
            if cursor is not None and event.updated <= cursor:
                continue
            refs.append(
                SourceRef(
                    source_id=stable_id(SourceId, f"calendar:{event.uid}"),
                    connector=self.connector,
                    locator=event.uid,
                    cursor=event.updated or None,
                )
            )
        return refs

    def _render(self, locator: str) -> RenderedPayload:
        for event in self._events():
            if event.uid == locator:
                lines = [
                    event.summary or "(untitled event)",
                    "",
                    f"When: {event.start} - {event.end}",
                ]
                if event.location:
                    lines.append(f"Where: {event.location}")
                if event.description:
                    lines += ["", event.description]
                floor = _CLASS_FLOOR.get(event.classification, Sensitivity.PUBLIC)
                return RenderedPayload(
                    data=("\n".join(lines) + "\n").encode("utf-8"),
                    media=MediaInfo(mime.TXT, ArtifactKind.CALENDAR_EVENT),
                    policy=self._policy(max_sensitivity(self._sensitivity, floor)),
                )
        raise ConnectorError(f"unknown calendar event {locator!r}")
