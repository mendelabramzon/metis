"""metis-eval: the evaluation harness.

Golden fixtures and quality comparisons that make model/pipeline changes measurable. Stage 5
seeds the memory-vs-naive-RAG comparison (:mod:`metis_eval.memory`); the broader benchmark
runner and golden-workspace fixtures land in Stage 13. The harness may import any Metis
package (it is a consumer, not a layer), so it is intentionally outside the import-boundary
contracts.
"""

__version__ = "0.0.0"
