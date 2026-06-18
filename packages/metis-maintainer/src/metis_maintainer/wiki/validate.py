"""Validate a proposed wiki patch before it can be approved.

A patch is rejected if it is structurally malformed, asserts body content without citing any
claim, or — the key wiki invariant — cites a claim that does not resolve to real evidence
(an *introduced*, unsupported claim). Reuses the Stage 6 structural lint and claim-support
checks and adds the resolve-against-evidence check.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence

from metis_core.wiki import WikiPageKind, kind_of
from metis_maintainer.jobs import claim_support_issues, lint_issues
from metis_protocol import WikiPatch

_NAVIGATION = frozenset({WikiPageKind.INDEX, WikiPageKind.LOG})


def validate_patch(patch: WikiPatch, *, known_claim_ids: Collection[str]) -> Sequence[str]:
    """Return validation issues; empty means the patch may be approved."""
    issues = list(lint_issues(patch))
    # Index/log pages are navigation projections (no claims); only content pages must cite.
    if not patch.slug or kind_of(patch.slug) not in _NAVIGATION:
        issues += list(claim_support_issues(patch))
    known = set(known_claim_ids)
    introduced = [str(ref.claim_id) for ref in patch.claims if str(ref.claim_id) not in known]
    if introduced:
        issues.append(
            f"patch introduces {len(introduced)} unsupported claim(s) not in evidence: "
            + ", ".join(sorted(introduced))
        )
    return issues


def is_valid(patch: WikiPatch, *, known_claim_ids: Collection[str]) -> bool:
    return not validate_patch(patch, known_claim_ids=known_claim_ids)
