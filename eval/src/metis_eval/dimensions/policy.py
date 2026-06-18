"""Policy enforcement: restricted data does not leak at a lower ceiling, and deleted data is gone.

Two failure modes in one dimension: a sensitivity leak (a RESTRICTED claim surfacing for an INTERNAL
requester) and a deletion miss (a tombstoned document's claims still retrievable). Either one scores
the dimension to zero.
"""

from __future__ import annotations

from metis_eval.engine import GoldenEngine
from metis_eval.golden import GoldenWorkspace
from metis_eval.report import Measurement
from metis_protocol import Sensitivity


async def evaluate(workspace: GoldenWorkspace, engine: GoldenEngine) -> Measurement:
    leak = engine.retrieve(workspace.leak_query.text, ceiling=workspace.leak_query.max_sensitivity)
    leaked = len(leak) > 0  # any restricted claim surfaced below its sensitivity

    deleted_present = any(
        workspace.deletion_probe in claim.text
        for claim in engine.live_claims(ceiling=Sensitivity.RESTRICTED)
    )

    ok = not leaked and not deleted_present
    detail = f"sensitivity_leak={leaked}, deleted_data_present={deleted_present}"
    return Measurement("policy_enforcement", 1.0 if ok else 0.0, detail)
