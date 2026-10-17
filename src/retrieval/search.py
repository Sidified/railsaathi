"""Retrieval: find the chunks that best match a question.

Step 3a: vector search only (baseline). Hybrid search is added in Step 3b.
LLM calls: 0
"""
from src.embeddings import embed_query
from src.ingestion.index import get_collection


def vector_search(query: str, k: int = 5) -> list[dict]:
    """Return the top-k chunks by meaning (cosine similarity)."""
    res = get_collection().query(query_embeddings=[embed_query(query)], n_results=k)
    return [
        {"chunk_id": cid, "score": 1 - dist, "text": doc, **meta}
        for cid, dist, doc, meta in zip(
            res["ids"][0], res["distances"][0], res["documents"][0], res["metadatas"][0]
        )
    ]