"""Shared embedding helper (used when building the index AND when searching).

Model: BAAI/bge-small-en-v1.5 via fastembed (ONNX, runs on CPU, no PyTorch).
- 384-dimensional vectors, ~130 MB download (cached after the first run).
- BGE expects a short instruction in front of QUERIES (not documents).
"""
from functools import lru_cache

from fastembed import TextEmbedding

MODEL_NAME = "BAAI/bge-small-en-v1.5"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


@lru_cache(maxsize=1)
def get_model() -> TextEmbedding:
    """Load the model once and reuse it (loading takes a few seconds)."""
    return TextEmbedding(model_name=MODEL_NAME)


def embed_documents(texts: list[str]) -> list[list[float]]:
    return [v.tolist() for v in get_model().embed(texts)]


def embed_query(query: str) -> list[float]:
    return next(get_model().embed([QUERY_PREFIX + query])).tolist()