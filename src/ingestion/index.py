"""Step 2e: Embed every chunk and store it in a local Chroma vector database.

Rebuilds the index from scratch on every run, so it always matches chunks.jsonl.
Output: data/index/chroma/   (generated, not committed to Git)
LLM calls: 0
"""
import json
import time
from pathlib import Path

import chromadb
from chromadb.config import Settings

from src.embeddings import MODEL_NAME, embed_documents, embed_query

CHUNKS_FILE = Path("data/processed/chunks.jsonl")
INDEX_DIR = Path("data/index/chroma")
COLLECTION = "railsaathi_rules"

# Chroma metadata values must be str / int / float / bool (no lists).
META_FIELDS = ["doc", "title", "section", "source_url", "effective_from",
               "applies_to", "status", "authority", "doc_type", "note", "superseded_by"]


def get_collection(reset: bool = False):
    client = chromadb.PersistentClient(
        path=str(INDEX_DIR), settings=Settings(anonymized_telemetry=False)
    )
    if reset:
        try:
            client.delete_collection(COLLECTION)
        except Exception:
            pass   # first run: nothing to delete
    return client.get_or_create_collection(
        name=COLLECTION,
        metadata={"hnsw:space": "cosine", "embedding_model": MODEL_NAME},
        embedding_function=None,   # we always pass our own vectors
    )


def main() -> None:
    chunks = [json.loads(line) for line in CHUNKS_FILE.open(encoding="utf-8")]

    t0 = time.perf_counter()
    vectors = embed_documents([c["text"] for c in chunks])
    t_embed = time.perf_counter() - t0

    col = get_collection(reset=True)
    col.add(
        ids=[c["chunk_id"] for c in chunks],
        embeddings=vectors,
        documents=[c["text"] for c in chunks],
        metadatas=[
            {**{k: c[k] for k in META_FIELDS},
             "pages": ",".join(map(str, c["pages"])), "words": c["words"]}
            for c in chunks
        ],
    )
    print(f"Indexed {col.count()} chunks ({len(vectors[0])}-dim) in {t_embed:.1f}s -> {INDEX_DIR}")

    # Quick sanity check: does the top result make sense?
    tests = [
        "Cancelling 3AC ticket 20 hours before departure, how much refund?",
        "Train is 4 hours late and I did not travel. Full refund?",
        "Tatkal booking time for sleeper class",
        "Free luggage allowance in AC 2 tier",
        "mera ticket RAC hai, cancel karu toh kitna paisa milega?",
    ]
    for q in tests:
        res = col.query(query_embeddings=[embed_query(q)], n_results=3)
        print(f"\nQ: {q}")
        for cid, dist in zip(res["ids"][0], res["distances"][0]):
            print(f"   {1 - dist:.3f}  {cid}")


if __name__ == "__main__":
    main()