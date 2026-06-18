"""The subprocess entrypoint that runs one skill, isolated from the runner process.

Invoked as ``python -m metis_runtime.skills.sandbox.harness`` inside the sandbox: it reads a
JSON payload (the skill's ``main.py`` path, arguments, and context) from stdin, imports the
skill by path, calls ``run(arguments, context)``, and writes a JSON result to stdout. An
exception is caught and reported (so a skill crash is observable, not fatal to the runner). The
process runs with a scrubbed environment and a scratch working directory set by the sandbox.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import traceback
from typing import Any


def _load_run(main_path: str) -> Any:
    spec = importlib.util.spec_from_file_location("metis_skill_main", main_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load skill main from {main_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.run


def main() -> None:
    payload = json.loads(sys.stdin.read() or "{}")
    try:
        run = _load_run(payload["main_path"])
        output = run(payload.get("arguments", {}), payload.get("context", {}))
        result: dict[str, Any] = {"ok": True, "output": output}
    except Exception as exc:  # a misbehaving/erroring skill must not crash the runner
        result = {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
        }
    sys.stdout.write(json.dumps(result))


if __name__ == "__main__":
    main()
