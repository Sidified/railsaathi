"""Measure retrieval quality on the small labelled dev set (evals/retrieval_dev.jsonl).

For each question we know which chunk(s) contain the answer ("relevant").
Metrics:
  hit@k  - % of questions where at least one relevant chunk is in the top k
  MRR    - mean reciprocal rank: 1/rank of the first relevant chunk (0 if not in top 10)

Usage:  python -m evals.retrieval_eval --method vector
LLM calls: 0
"""
import argparse
import json
from datetime import date
from pathlib import Path

from src.retrieval import search

DEV_FILE = Path("evals/retrieval_dev.jsonl")
RESULTS_DIR = Path("evals/results")
K_MAX = 10


def first_hit_rank(results: list[dict], relevant: list[str]) -> int | None:
    for rank, r in enumerate(results, start=1):
        if r["chunk_id"] in relevant:
            return rank
    return None


def summarize(rows: list[dict]) -> dict:
    n = len(rows)
    ranks = [r["rank"] for r in rows]
    return {
        "n": n,
        "hit@1": sum(1 for x in ranks if x and x <= 1) / n,
        "hit@3": sum(1 for x in ranks if x and x <= 3) / n,
        "hit@5": sum(1 for x in ranks if x and x <= 5) / n,
        "mrr": sum(1 / x for x in ranks if x) / n,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--method", default="vector")
    args = parser.parse_args()
    search_fn = getattr(search, f"{args.method}_search")

    questions = [json.loads(line) for line in DEV_FILE.open(encoding="utf-8")]
    rows = []
    for q in questions:
        results = search_fn(q["query"], k=K_MAX)
        rank = first_hit_rank(results, q["relevant"])
        rows.append({**q, "rank": rank, "top3": [r["chunk_id"] for r in results[:3]]})
        mark = f"rank {rank}" if rank else "MISS"
        print(f"{q['id']} [{q['lang']:8}] {mark:>7}  {q['query'][:65]}")

    report = {"method": args.method, "date": str(date.today()),
              "all": summarize(rows),
              "en": summarize([r for r in rows if r["lang"] == "en"]),
              "hinglish": summarize([r for r in rows if r["lang"] == "hinglish"])}
    print(f"\n{'slice':10} {'n':>3} {'hit@1':>6} {'hit@3':>6} {'hit@5':>6} {'MRR':>6}")
    for name in ("all", "en", "hinglish"):
        s = report[name]
        print(f"{name:10} {s['n']:>3} {s['hit@1']:>6.0%} {s['hit@3']:>6.0%} {s['hit@5']:>6.0%} {s['mrr']:>6.2f}")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / f"retrieval_{args.method}_{date.today()}.json"
    out.write_text(json.dumps({"summary": report, "rows": rows}, indent=1), encoding="utf-8")
    print(f"\nSaved {out}")


if __name__ == "__main__":
    main()