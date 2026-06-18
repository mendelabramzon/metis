"""Retrieval interfaces: Retriever (async I/O) and ContextPacker (pure transform)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from metis_protocol.query import ContextBundle, EvidenceSet, QueryRequest


@runtime_checkable
class Retriever(Protocol):
    async def retrieve(self, query: QueryRequest) -> EvidenceSet: ...


@runtime_checkable
class ContextPacker(Protocol):
    def pack(self, query: QueryRequest, evidence: EvidenceSet) -> ContextBundle: ...
