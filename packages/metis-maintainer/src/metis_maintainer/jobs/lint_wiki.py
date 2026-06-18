"""Structural lint for proposed wiki patches (cheap consistency checks before commit).

Returns a list of issues; an empty list means the patch is structurally well-formed. This is
deliberately deterministic and shallow — the deep compile/evaluate/refine loop is Stage 7.
"""

from __future__ import annotations

from collections.abc import Sequence

from metis_protocol import WikiOp, WikiPatch


def lint_issues(patch: WikiPatch) -> Sequence[str]:
    issues: list[str] = []
    if patch.op is WikiOp.CREATE:
        if not patch.title:
            issues.append("CREATE patch is missing a title")
        if not patch.slug:
            issues.append("CREATE patch is missing a slug")
        if not (patch.body_markdown or "").strip():
            issues.append("CREATE patch has an empty body")
    elif patch.page_id is None:
        issues.append(f"{patch.op.value} patch is missing page_id")
    if patch.slug and " " in patch.slug:
        issues.append("slug must not contain spaces")
    return issues
