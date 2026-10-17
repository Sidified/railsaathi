"""Retrieval: find the chunks that best match a question.

Three methods (so we can compare them in evals/retrieval_eval.py):
  vector_search  - meaning-based (BGE-small embeddings in Chroma)
  bm25_search    - keyword-based (exact words like TDR, RAC, Tatkal, 3A)
  hybrid_search  - both, merged with Reciprocal Rank Fusion, plus two rule-aware steps:
                   1. train-type filter (hide Vande Bharat Sleeper rules unless asked)
                   2. supersession expansion (an outdated chunk pulls in its newer source)
LLM calls: 0
"""
import json
import re
from functools import lru_cache
from pathlib import Path

from rank_bm25 import BM25Okapi

from src.embeddings import embed_query
from src.ingestion.index import get_collection

CHUNKS_FILE = Path("data/processed/chunks.jsonl")
RRF_K = 60          # standard constant in Reciprocal Rank Fusion
CANDIDATES = 20     # how many results each method contributes before fusion

STOPWORDS = set("""a an the is are was were be been to of in on for at by with and or
if my i me we you your it this that do does did can will would should what when how
which who much many any some from as about after before than then so not no""".split())
VB_TRAINS = re.compile(r"vande\s*bharat\s*sleeper|amrit\s*bharat", re.I)


def tokenize(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOPWORDS]


@lru_cache(maxsize=1)
def load_chunks() -> dict[str, dict]:
    with CHUNKS_FILE.open(encoding="utf-8") as f:
        return {c["chunk_id"]: c for c in map(json.loads, f)}


@lru_cache(maxsize=1)
def get_bm25() -> tuple[BM25Okapi, list[str]]:
    chunks = load_chunks()
    ids = list(chunks)
    return BM25Okapi([tokenize(chunks[i]["text"]) for i in ids]), ids


def _result(chunk_id: str, score: float) -> dict:
    c = load_chunks()[chunk_id]
    return {"chunk_id": chunk_id, "score": score, **{k: v for k, v in c.items() if k != "chunk_id"}}


def vector_search(query: str, k: int = 5) -> list[dict]:
    """Top-k chunks by meaning (cosine similarity)."""
    res = get_collection().query(query_embeddings=[embed_query(query)], n_results=k)
    return [_result(cid, 1 - dist) for cid, dist in zip(res["ids"][0], res["distances"][0])]


def bm25_search(query: str, k: int = 5) -> list[dict]:
    """Top-k chunks by keyword overlap (BM25)."""
    bm25, ids = get_bm25()
    scores = bm25.get_scores(tokenize(query))
    ranked = sorted(zip(ids, scores), key=lambda x: x[1], reverse=True)[:k]
    return [_result(cid, float(s)) for cid, s in ranked]


def rrf_merge(*ranked_lists: list[dict]) -> list[tuple[str, float]]:
    """Reciprocal Rank Fusion: score = sum of 1 / (RRF_K + rank) over all lists.
    Uses only ranks, so we never have to compare cosine scores with BM25 scores."""
    fused: dict[str, float] = {}
    for results in ranked_lists:
        for rank, r in enumerate(results, start=1):
            fused[r["chunk_id"]] = fused.get(r["chunk_id"], 0.0) + 1 / (RRF_K + rank)
    return sorted(fused.items(), key=lambda x: x[1], reverse=True)


def expand_superseded(ranked: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """If an outdated chunk is in the results, put its newer source just BEFORE it,
    so the current rule is always seen first (and the old one only as context)."""
    chunks = load_chunks()
    position = {cid: i for i, (cid, _) in enumerate(ranked)}
    out, seen = [], set()
    for cid, score in ranked:
        for newer_doc in filter(None, (d.strip() for d in chunks[cid]["superseded_by"].split(";"))):
            # the newer document's best-ranked chunk (or its first chunk if none was found)
            candidates = [c for c in chunks if chunks[c]["doc"] == newer_doc]
            best = min(candidates, key=lambda c: position.get(c, len(ranked) + int(c[-2:])))
            if best not in seen:
                out.append((best, score))
                seen.add(best)
        if cid not in seen:
            out.append((cid, score))
            seen.add(cid)
    return out


def hybrid_search(query: str, k: int = 5) -> list[dict]:
    ranked = rrf_merge(vector_search(query, CANDIDATES), bm25_search(query, CANDIDATES))
    if not VB_TRAINS.search(query):     # most trains are normal trains
        chunks = load_chunks()
        ranked = [(c, s) for c, s in ranked if chunks[c]["applies_to"] != "vb_sleeper_amrit_bharat_2"]
    ranked = expand_superseded(ranked)
    return [_result(cid, score) for cid, score in ranked[:k]]