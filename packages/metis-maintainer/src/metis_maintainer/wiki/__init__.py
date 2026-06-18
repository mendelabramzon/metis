"""Wiki compilation (Stage 7): claims/memory -> validated, probe-checked wiki patches.

The maintainer *proposes and validates* (compile, validate, the WiCER evaluate->refine loop,
backlinks/index, the error book); ``metis-core`` owns storage and the git-backed approval/commit
flow. Every compiled statement is claim-cited, contradictions are surfaced (not hidden), and the
deterministic structure keeps regeneration diffs stable.
"""

from __future__ import annotations

from metis_maintainer.wiki.backlinks import (
    build_index_patch,
    compute_backlinks,
    referenced_slugs,
)
from metis_maintainer.wiki.compile import WikiCompiler
from metis_maintainer.wiki.error_book import CompilationError, ErrorBook
from metis_maintainer.wiki.evaluate import ProbeResult, probe_patch
from metis_maintainer.wiki.prompts import WikiLede, wiki_registry
from metis_maintainer.wiki.refine import RefineResult, SupportsCompile, compile_with_refine
from metis_maintainer.wiki.validate import is_valid, validate_patch

__all__ = [
    "CompilationError",
    "ErrorBook",
    "ProbeResult",
    "RefineResult",
    "SupportsCompile",
    "WikiCompiler",
    "WikiLede",
    "build_index_patch",
    "compile_with_refine",
    "compute_backlinks",
    "is_valid",
    "probe_patch",
    "referenced_slugs",
    "validate_patch",
    "wiki_registry",
]
