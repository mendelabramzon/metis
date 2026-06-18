"""The hybrid memory lookup returns the right cells, isolates embedding versions, and
respects supersession.

Uses the deterministic :class:`StubEmbedder` so the ranking is reproducible without a
model; semantic quality against a real embedding model is the eval's job (``metis_eval``).
"""

from metis_core.memory_index import EmbeddingRouter, MemoryIndexer, MemoryIndexLookup, StubEmbedder
from metis_core.stores import PostgresMemoryStore
from metis_protocol import ClaimRef, MemCellId, MemoryOp
from metis_protocol.examples import CLM2, WS, mem_cell, memory_patch


def _cell(n: int, summary: str, content: str):
    return mem_cell().model_copy(
        update={
            "id": MemCellId("mc_" + format(n, "032x")),
            "summary": summary,
            "content": content,
            "claims": (ClaimRef(claim_id=CLM2),),
        }
    )


async def test_returns_the_most_relevant_cell(sessionmaker) -> None:
    store = PostgresMemoryStore(sessionmaker)
    indexer = MemoryIndexer(sessionmaker, EmbeddingRouter([StubEmbedder()]))
    lookup = MemoryIndexLookup(sessionmaker, EmbeddingRouter([StubEmbedder()]))

    ada = mem_cell()  # "Ada became Acme's CTO ..."
    grace = _cell(2, "Grace was named Acme's CFO in 2025.", "Grace Hopper became Acme's CFO.")
    for cell in (ada, grace):
        await store.write_mem_cell(cell)
        await indexer.index_mem_cell(cell)

    hits = await lookup.search_mem_cells(workspace_id=WS, query_text="Who is the CTO of Acme?")
    assert hits, "expected at least one hit"
    assert hits[0].item.id == ada.id  # the CTO cell, not the CFO cell


async def test_embedding_version_isolates_the_vector_ranker(sessionmaker) -> None:
    store = PostgresMemoryStore(sessionmaker)
    cell = mem_cell()
    await store.write_mem_cell(cell)
    # Index under version "v2".
    await MemoryIndexer(sessionmaker, EmbeddingRouter([StubEmbedder(version="v2")])).index_mem_cell(
        cell
    )

    # A "v1" query can still find it lexically (FTS), but the vector ranker skips it,
    # because comparing distances across embedding models is meaningless.
    hits_v1 = await MemoryIndexLookup(
        sessionmaker, EmbeddingRouter([StubEmbedder(version="v1")])
    ).search_mem_cells(workspace_id=WS, query_text=cell.summary)
    hit_v1 = next(hit for hit in hits_v1 if hit.item.id == cell.id)
    assert hit_v1.vector_rank is None
    assert hit_v1.fts_rank is not None

    # A "v2" query (matching the stored version) does use the vector ranker.
    hits_v2 = await MemoryIndexLookup(
        sessionmaker, EmbeddingRouter([StubEmbedder(version="v2")])
    ).search_mem_cells(workspace_id=WS, query_text=cell.summary)
    hit_v2 = next(hit for hit in hits_v2 if hit.item.id == cell.id)
    assert hit_v2.vector_rank is not None


async def test_superseded_cells_are_excluded(sessionmaker) -> None:
    store = PostgresMemoryStore(sessionmaker)
    lookup = MemoryIndexLookup(sessionmaker, EmbeddingRouter([StubEmbedder()]))
    cell = mem_cell()
    await store.write_mem_cell(cell)
    await MemoryIndexer(sessionmaker, EmbeddingRouter([StubEmbedder()])).index_mem_cell(cell)

    # memory_patch() supersedes mem_cell() (same target id).
    assert memory_patch().op is MemoryOp.SUPERSEDE
    await store.apply_patch(memory_patch())

    hits = await lookup.search_mem_cells(workspace_id=WS, query_text=cell.summary)
    assert all(hit.item.id != cell.id for hit in hits)
