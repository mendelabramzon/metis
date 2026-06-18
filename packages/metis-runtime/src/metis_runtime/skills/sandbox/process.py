"""The subprocess sandbox: run a skill in an isolated child process (the Phase-0 sandbox).

Each run gets a fresh scratch directory as its working dir, the *exact* environment the runner
hands it (the runner scrubs it and injects only declared secrets), and hard limits on wall-clock
time and output size. The child is a separate process, so a crash, hang, or runaway output is
contained and observable. Files the skill leaves in the scratch dir are returned for capture.

This isolates environment, working directory, lifetime, and output. Hard OS-level filesystem and
network isolation for *untrusted* skills is a stronger sandbox (gVisor/Firecracker/Docker
``--network none``) deferred to the hardening/deployment stages — a documented trust-tier seam.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

_HARNESS_MODULE = "metis_runtime.skills.sandbox.harness"
_MAX_CAPTURED_FILES = 32


@dataclass(frozen=True)
class CapturedFile:
    name: str
    data: bytes


@dataclass(frozen=True)
class SandboxResult:
    ok: bool
    output: Any
    error: str | None
    logs: str
    files: tuple[CapturedFile, ...] = ()
    truncated: bool = False


@runtime_checkable
class Sandbox(Protocol):
    async def execute(
        self,
        *,
        main_path: Path,
        arguments: Any,
        context: Any,
        env: Mapping[str, str],
        timeout_seconds: float | None,
        max_output_bytes: int | None,
    ) -> SandboxResult: ...


class SubprocessSandbox:
    async def execute(
        self,
        *,
        main_path: Path,
        arguments: Any,
        context: Any,
        env: Mapping[str, str],
        timeout_seconds: float | None,
        max_output_bytes: int | None,
    ) -> SandboxResult:
        scratch = Path(tempfile.mkdtemp(prefix="metis-skill-"))
        payload = json.dumps(
            {"main_path": str(main_path), "arguments": arguments, "context": context}
        )
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                _HARNESS_MODULE,
                cwd=str(scratch),
                env=dict(env),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(payload.encode()), timeout=timeout_seconds
                )
            except TimeoutError:
                proc.kill()
                await proc.wait()
                return SandboxResult(False, None, "skill timed out", "")

            logs = stderr.decode(errors="replace")
            if max_output_bytes is not None and len(stdout) > max_output_bytes:
                return SandboxResult(
                    False, None, f"output exceeded {max_output_bytes} bytes", logs, truncated=True
                )

            files = _collect_files(scratch)
            try:
                harness = json.loads(stdout.decode(errors="replace") or "{}")
            except json.JSONDecodeError:
                return SandboxResult(False, None, "skill produced no parseable result", logs, files)
            if not harness.get("ok"):
                detail = "\n".join(filter(None, [logs, harness.get("traceback")]))
                return SandboxResult(
                    False, None, harness.get("error", "skill failed"), detail, files
                )
            return SandboxResult(True, harness.get("output"), None, logs, files)
        finally:
            shutil.rmtree(scratch, ignore_errors=True)


def _collect_files(scratch: Path) -> tuple[CapturedFile, ...]:
    captured: list[CapturedFile] = []
    for path in sorted(scratch.rglob("*")):
        if path.is_file():
            captured.append(
                CapturedFile(name=str(path.relative_to(scratch)), data=path.read_bytes())
            )
            if len(captured) >= _MAX_CAPTURED_FILES:
                break
    return tuple(captured)
