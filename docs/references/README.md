# Metis Research References

This directory tracks the research and engineering references that should shape Metis development.

These are not a generic RAG reading list. They are the papers, standards, and implementation references that map directly to the intended engine:

- evidence-first ingestion
- compounding memory and wiki projection
- background contradiction/revision/foresight jobs
- query-time retrieval, context packing, and skill execution
- security, provenance, evaluation, and observability

Current files:

- [frontier-approaches.md](frontier-approaches.md): research papers and design patterns we should actively use or benchmark against.
- [engineering-refs.md](engineering-refs.md): implementation libraries, standards, protocols, and operational references.

Review cadence:

- Re-check links and model/tool recommendations monthly while the architecture is moving.
- Promote a paper from "watch" to "adopt" only after it affects a concrete module contract, benchmark, or implementation decision.
- Keep implementation choices replaceable behind `metis-protocol` contracts.

