"""Check the classify node on a small labelled set (evals/classify_dev.jsonl).

Scores: intent accuracy, language accuracy, and field accuracy (every expected
ticket field / TDR situation must match exactly).
Usage:  python -m evals.classify_eval
LLM calls: 1 per question (12). Sleeps 5 s between calls to stay under 15 RPM.
"""
import json
import time
from datetime import date
from pathlib import Path

from src.agent.classify import classify

DEV_FILE = Path("evals/classify_dev.jsonl")
RESULTS_DIR = Path("evals/results")


def get_value(c, key):
    if key in ("intent", "language", "tdr_situation"):
        return getattr(c, key)
    return getattr(c.ticket, key)


def main() -> None:
    rows, totals = [], {"intent": 0, "language": 0, "fields": 0}
    cases = [json.loads(line) for line in DEV_FILE.open(encoding="utf-8")]
    for i, case in enumerate(cases):
        if i:
            time.sleep(5)
        c = classify(case["question"], case.get("history"))
        wrong = {k: (get_value(c, k), v) for k, v in case["expect"].items() if get_value(c, k) != v}
        ok_intent = "intent" not in wrong
        ok_lang = "language" not in wrong
        ok_fields = not {k for k in wrong if k not in ("intent", "language")}
        totals["intent"] += ok_intent
        totals["language"] += ok_lang
        totals["fields"] += ok_fields
        status = "OK  " if not wrong else "FAIL"
        print(f"{case['id']} {status} intent={c.intent:13} lang={c.language:8} query='{c.search_query}'")
        for k, (got, exp) in wrong.items():
            print(f"        {k}: got {got!r}, expected {exp!r}")
        rows.append({**case, "got": c.model_dump(), "wrong": {k: list(v) for k, v in wrong.items()}})

    n = len(cases)
    print(f"\nintent accuracy:   {totals['intent']}/{n}")
    print(f"language accuracy: {totals['language']}/{n}")
    print(f"field accuracy:    {totals['fields']}/{n}")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / f"classify_{date.today()}.json"
    out.write_text(json.dumps({"totals": totals, "n": n, "rows": rows}, indent=1, default=str), encoding="utf-8")
    print(f"Saved {out}")


if __name__ == "__main__":
    main()