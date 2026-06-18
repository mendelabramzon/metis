"""Retrieval-quality evaluation: span recall@k, measured independently of answer generation."""

from __future__ import annotations

from metis_eval.retrieval.compare import RetrievalReport, run_retrieval_eval

__all__ = ["RetrievalReport", "run_retrieval_eval"]
