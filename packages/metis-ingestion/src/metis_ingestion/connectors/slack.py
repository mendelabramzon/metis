"""Slack connector: render a channel's messages to markdown, mapping channel ACL to sensitivity.

A private channel is more sensitive than a public one, and that distinction has to survive into the
artifact's policy or restricted chatter leaks downstream — so a private channel floors the doc at
``CONFIDENTIAL`` (never below the connector's own default). Messages render to markdown the pipeline
parses like any note; the channel's newest message timestamp is its cursor.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, TypeAdapter

from metis_ingestion import mime
from metis_ingestion._build import stable_id
from metis_ingestion.connectors.base import BaseConnector, ConnectorError, RenderedPayload
from metis_ingestion.mime import MediaInfo
from metis_protocol import ArtifactKind, Sensitivity, SourceId, SourceRef, max_sensitivity

_CHANNELS_KEY = "channels.json"


class _Message(BaseModel):
    user: str = "unknown"
    ts: str
    text: str = ""


class _Channel(BaseModel):
    name: str
    is_private: bool = False
    messages: tuple[_Message, ...] = ()

    @property
    def latest(self) -> str:
        return max((message.ts for message in self.messages), default="")


_CHANNELS = TypeAdapter(tuple[_Channel, ...])


class SlackConnector(BaseConnector):
    connector = "slack"

    def _channels(self) -> tuple[_Channel, ...]:
        return _CHANNELS.validate_json(self._read(_CHANNELS_KEY))

    async def discover(self, cursor: str | None) -> Sequence[SourceRef]:
        refs: list[SourceRef] = []
        for channel in self._channels():
            if cursor is not None and channel.latest <= cursor:
                continue
            refs.append(
                SourceRef(
                    source_id=stable_id(SourceId, f"slack:{channel.name}"),
                    connector=self.connector,
                    locator=channel.name,
                    cursor=channel.latest or None,
                )
            )
        return refs

    def _render(self, locator: str) -> RenderedPayload:
        for channel in self._channels():
            if channel.name == locator:
                lines = [f"# #{channel.name}", ""]
                lines += [
                    f"**{message.user}** ({message.ts}): {message.text}"
                    for message in channel.messages
                ]
                floor = Sensitivity.CONFIDENTIAL if channel.is_private else Sensitivity.PUBLIC
                return RenderedPayload(
                    data=("\n".join(lines) + "\n").encode("utf-8"),
                    media=MediaInfo(mime.MD, ArtifactKind.CHAT_MESSAGE),
                    policy=self._policy(max_sensitivity(self._sensitivity, floor)),
                )
        raise ConnectorError(f"unknown slack channel {locator!r}")
