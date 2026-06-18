"""Extraction prompt seam.

Stage 3 extraction is deterministic (no model), so these are placeholders. Stage 4's
policy-bound router owns prompt versioning and replaces the model access in
``BaselineExtractor``; the version string is recorded here so provenance can reference
it once a model is in the loop.
"""

from __future__ import annotations

EXTRACT_CLAIMS_PROMPT_VERSION = "extract_claims@0-deterministic"

EXTRACT_CLAIMS_PROMPT = """\
Extract atomic, self-contained, source-grounded claims from the document segments.
Each claim must be supported by a span of the provided text. Do not invent facts.
"""
