"""Reset the local dev database: drop everything, then re-apply migrations.

uv run python -m metis_core.dev.reset
"""

from __future__ import annotations

from metis_core.config import CoreSettings
from metis_core.dev.testing import run_downgrade, run_upgrade


def main() -> int:
    url = CoreSettings().database_url
    run_downgrade(url)
    run_upgrade(url)
    print(f"reset database at {url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
