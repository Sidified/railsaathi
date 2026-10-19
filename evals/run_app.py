"""Step 7d: run every eval question through the agent once and save the raw results.

Calls the agent directly (not via HTTP, so the API rate limiter doesn't get in the way).
Resumable: questions already in the output file are skipped, so you can stop with Ctrl+C
or hit the daily quota and just run it again later.

    python -m evals.run_app --limit 3     # quick test
    python -m evals.run_app               # full run (~25 min)
"""
import argparse
import json
import time
from pathlib import Path

from src.agent.graph import run

SET = Path("evals/eval_set.jsonl")
OUT = Path("evals/results/answers.jsonl")
ROUTES = ("refuse", "ask_missing", "calculator", "tdr_tool", "retrieve")
PAUSE = 1          # seconds between questions: max 2 calls each -> stays under 15 calls/minute


def is_quota_error(e: Exception) -> bool:
    s = str(e)
    return "429" in s or "RESOURCE_EXHAUSTED" in s or "quota" in s.lower()


def record(q: dict, s: dict, latency_ms: int) -> dict:
    tr = s.get("tool_result") or {}
    c = s.get("classification")
    return {
        "id": q["id"],
        "route": [p for p in s["path"] if p in ROUTES],
        "path": s["path"],
        "intent": getattr(c, "intent", None),
        "language": getattr(c, "language", None),
        "llm_calls": s.get("llm_calls"),
        "latency_ms": latency_ms,
        "answer": s.get("answer", ""),
        "fallback_used": s.get("fallback_used", False),
        "check_problems": s.get("check_problems") or [],
        "tool_name": s.get("tool_name"),
        "tool_rule_id": tr.get("rule_id"),
        "tool_refund_total": str(tr["refund_total"]) if tr.get("refund_total") is not None else None,
        "sources": [{"chunk_id": x["chunk_id"], "status": x["status"]} for x in s.get("sources", [])],
        # retrieved text is kept so the judge can check faithfulness later without re-running
        "chunks": [{"chunk_id": x["chunk_id"], "text": x["text"]} for x in s.get("chunks", [])],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    questions = [json.loads(l) for l in SET.read_text(encoding="utf-8").splitlines() if l.strip()]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if OUT.exists():
        done = {json.loads(l)["id"] for l in OUT.read_text(encoding="utf-8").splitlines() if l.strip()}
    todo = [q for q in questions if q["id"] not in done][: args.limit]
    print(f"{len(done)} already done, running {len(todo)}")

    for i, q in enumerate(todo, 1):
        for attempt in range(3):
            try:
                t0 = time.perf_counter()
                s = run(q["question"])
                rec = record(q, s, int((time.perf_counter() - t0) * 1000))
                break
            except Exception as e:
                if is_quota_error(e) and attempt < 2:
                    print(f"  quota hit, waiting 65 s (attempt {attempt + 1})")
                    time.sleep(65)
                    continue
                if is_quota_error(e):
                    print("Still over quota (probably the daily limit). Stopping - run again later to resume.")
                    return
                rec = {"id": q["id"], "error": f"{type(e).__name__}: {e}"}
                break
        with OUT.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"[{i}/{len(todo)}] {q['id']:5} {q['slice']:13} route={rec.get('route')} "
              f"calls={rec.get('llm_calls')} {rec.get('latency_ms', 0) / 1000:.1f}s"
              + (f"  ERROR {rec['error'][:80]}" if "error" in rec else ""))
        time.sleep(PAUSE)


if __name__ == "__main__":
    main()