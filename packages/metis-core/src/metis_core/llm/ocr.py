"""Adapt a ``ModelCaller`` into the ingestion OCR transcriber seam (one vision call per page image).

Ingestion stays free of a hard model dependency: it asks for a ``transcribe(media_type, data,
sensitivity) -> str`` callable, and this builds one over ``ModelCaller.call_vision_text``. When no
vision model is eligible (none configured, or restricted data with only an external VLM), it returns
"" so OCR degrades to a no-op rather than failing the ingest.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from metis_core.llm.call import ModelCaller
from metis_core.llm.errors import NoEligibleProviderError
from metis_protocol import ImagePart, ModelTaskClass, Sensitivity, WorkspaceId

_OCR_INSTRUCTION = (
    "Transcribe all text in this image exactly, preserving line breaks. Output only the text."
)


def model_transcriber(
    caller: ModelCaller, workspace_id: WorkspaceId
) -> Callable[[str, bytes, Sensitivity], Awaitable[str]]:
    """A transcribe callable over a ModelCaller for a workspace ("" when no VLM is eligible)."""

    async def _transcribe(media_type: str, data: bytes, sensitivity: Sensitivity) -> str:
        try:
            return await caller.call_vision_text(
                task_class=ModelTaskClass.PARSE_ASSIST,
                workspace_id=workspace_id,
                user_content=_OCR_INSTRUCTION,
                images=(ImagePart(media_type=media_type, data=data),),
                sensitivity=sensitivity,
            )
        except NoEligibleProviderError:
            return ""  # no vision model -> no OCR text, the deterministic result stands

    return _transcribe
