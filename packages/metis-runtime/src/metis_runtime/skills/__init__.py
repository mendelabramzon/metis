"""Skill runtime (Stage 9): discover, sandbox, policy-gate, and audit skill execution.

``metis-skills`` owns the package format and ships skills; this package owns running them safely:
the manifest is enforced as a deny-by-default security contract, outbound/destructive runs need
human approval, execution is isolated in a subprocess sandbox, and outputs/artifacts are
schema-checked, captured, and audited. The agent loop that *chooses* skills is Stage 10.
"""

from __future__ import annotations

from metis_runtime.skills.approval import ApprovalQueue, ApprovalRequest, SkillApprovalStatus
from metis_runtime.skills.capture import ArtifactCapture
from metis_runtime.skills.policy import SkillPolicy
from metis_runtime.skills.registry import SkillRegistry, ToolDoc
from metis_runtime.skills.runner import SkillRunner
from metis_runtime.skills.sandbox import CapturedFile, Sandbox, SandboxResult, SubprocessSandbox

__all__ = [
    "ApprovalQueue",
    "ApprovalRequest",
    "ArtifactCapture",
    "CapturedFile",
    "Sandbox",
    "SandboxResult",
    "SkillApprovalStatus",
    "SkillPolicy",
    "SkillRegistry",
    "SkillRunner",
    "SubprocessSandbox",
    "ToolDoc",
]
