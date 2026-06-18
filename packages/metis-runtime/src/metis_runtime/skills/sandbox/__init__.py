"""Skill sandboxes. ``SubprocessSandbox`` is the Phase-0 isolation (separate process, scratch
cwd, scrubbed env, time/output limits); stronger OS-level isolation for untrusted skills is a
deferred trust tier (see ADR 0018)."""

from __future__ import annotations

from metis_runtime.skills.sandbox.process import (
    CapturedFile,
    Sandbox,
    SandboxResult,
    SubprocessSandbox,
)

__all__ = ["CapturedFile", "Sandbox", "SandboxResult", "SubprocessSandbox"]
