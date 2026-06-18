"""Commit useful outputs: file them back into memory/wiki as patch *proposals*, never writes.

Compounding is the point of a memory engine — a good, grounded answer should make the next
question easier — but the runtime never mutates the substrate directly. So commit turns a finished
answer into a Stage 8 :class:`~metis_runtime.query.FilebackProposal` (claim-cited) that the
maintainer/approval/patch path (Stage 6/7/12) validates and applies. Only *sufficient, grounded*
answers file back (``propose_fileback`` returns ``None`` otherwise), which is what stops the
file-back loop from laundering an unverified model claim into machine truth. Generated skill
artifacts are already stored and audited by the ``SkillRunner``; promoting one into the wiki is a
job for the ``wiki_file_back`` skill, not a direct shortcut here.
"""

from __future__ import annotations

from dataclasses import dataclass

from metis_protocol import QueryRequest
from metis_runtime.query import Answer, FilebackProposal, propose_fileback


@dataclass(frozen=True)
class CommitResult:
    """The file-back proposals produced from a run's useful outputs."""

    filebacks: tuple[FilebackProposal, ...] = ()


def commit_outputs(query: QueryRequest, answer: Answer | None) -> CommitResult:
    """Propose filing a grounded answer back into memory (a proposal, never a direct write)."""
    proposals: list[FilebackProposal] = []
    if answer is not None:
        proposal = propose_fileback(query, answer, kind="memory")
        if proposal is not None:
            proposals.append(proposal)
    return CommitResult(filebacks=tuple(proposals))
