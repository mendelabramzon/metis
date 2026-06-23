"""Query rewrite (the ``query_rewrite`` seam) used for corrective retrieval.

Default is a deterministic passthrough so retrieval is reproducible without a model. When a
caller is wired, the LLM rewrites/expands the query (e.g. HyDE-style) — most useful on the
corrective retry after a sufficiency miss. Rewriting never changes the workspace or policy
ceiling; it only reshapes the query text. A model that refuses or returns malformed structured
output falls back to the original text, so a flaky model degrades retrieval but never 500s a query.
"""

from __future__ import annotations

from metis_core.llm import ModelCaller, ModelError
from metis_protocol import ModelTaskClass, WorkspaceId
from metis_runtime.query.prompts import RewrittenQuery


async def rewrite_query(
    text: str, *, workspace_id: WorkspaceId, caller: ModelCaller | None = None
) -> str:
    if caller is None:
        return text
    try:
        rewritten = await caller.call_structured(
            task_class=ModelTaskClass.QUERY_REWRITE,
            workspace_id=workspace_id,
            user_content=text,
            output_type=RewrittenQuery,
        )
    except ModelError:  # model refused/malformed — fall back to the original query text
        return text
    return rewritten.query.strip() or text
