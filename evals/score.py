"""Step 7e: score the saved answers with code-only metrics (no LLM calls).

    python -m evals.score

Reads evals/eval_set.jsonl + evals/results/answers.jsonl, writes
evals/results/report.md (the numbers) and evals/results/failures.csv (what to look at).
"""
import csv
import json
import re
import statistics
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path

SET = Path("evals/eval_set.jsonl")
ANS = Path("evals/results/answers.jsonl")
REPORT = Path("evals/results/report.md")
FAILS = Path("evals/results/failures.csv")

# Old 2015 cut-offs presented as the rule. Crude on purpose: every hit is listed in failures.csv
# so a human can confirm it.
OLD_RULE = re.compile(r"\b(48|12|4)\s*(-|to)?\s*(hours?|hrs?|h|ghante)\b", re.I)
MONEY = re.compile(r"(?:Rs\.?|₹|INR)\s*([\d,]+(?:\.\d{1,2})?)", re.I)


def load(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def amounts(text: str) -> set[Decimal]:
    out = set()
    for m in MONEY.finditer(text or ""):
        try:
            out.add(Decimal(m.group(1).replace(",", "")))
        except InvalidOperation:
            pass
    return out


def pct(hits: int, n: int) -> str:
    return f"{100 * hits / n:.0f}% ({hits}/{n})" if n else "n/a"


def main() -> None:
    qs = {q["id"]: q for q in load(SET)}
    ans = {a["id"]: a for a in load(ANS)}
    missing = [i for i in qs if i not in ans]
    errors = [a["id"] for a in ans.values() if "error" in a]

    checks = defaultdict(list)          # metric -> list of (id, passed)
    fails = []

    def check(metric, q, ok, detail=""):
        checks[metric].append((q, ok))
        if not ok:
            fails.append({"metric": metric, "id": q["id"], "slice": q["slice"], "lang": q["lang"],
                          "origin": q["origin"], "question": q["question"], "detail": detail})

    for qid, q in qs.items():
        a = ans.get(qid)
        if not a or "error" in a:
            continue
        main_route = a["route"][0] if a["route"] else None

        # 1. Routing: the first route taken must be one of the accepted ones
        check("routing", q, main_route in q["expected_route"],
              f"got {main_route}, expected {q['expected_route']}")

        # 2. Refund exactness: tool total == expected AND the amount appears in the answer
        if q.get("expected_refund") is not None:
            exp = Decimal(q["expected_refund"])
            tool = a.get("tool_refund_total")
            tool_ok = tool is not None and Decimal(tool) == exp
            text_ok = exp in amounts(a["answer"]) or (exp == 0 and re.search(r"no refund|nahi milega|kuch nahi|Rs\.? ?0\b", a["answer"], re.I))
            check("refund_exact", q, bool(tool_ok and text_ok),
                  f"expected {exp}, tool {tool}, amounts in answer {sorted(amounts(a['answer']))}")

        # 3. TDR situation
        if q.get("expected_tdr"):
            check("tdr_situation", q, a.get("tool_rule_id") == q["expected_tdr"],
                  f"expected {q['expected_tdr']}, got {a.get('tool_rule_id')} via {main_route}")

        # 4. Refusal: out-of-scope refused; in-scope NOT refused
        if q["slice"] == "out_of_scope":
            check("refuse_out_of_scope", q, main_route == "refuse", f"got {main_route}")
        else:
            check("no_false_refusal", q, main_route != "refuse", "refused an in-scope question")

        # 5. Every answer that went through retrieval cites at least one source
        if main_route in ("retrieve", "calculator", "tdr_tool"):
            check("has_sources", q, len(a.get("sources", [])) > 0, "no sources attached")

        # 6. Old-rule check on stale traps (and everywhere, as a warning)
        if q["slice"] == "stale_trap":
            hit = OLD_RULE.search(a["answer"])
            check("no_old_rule_stale", q, not hit, f"mentions '{hit.group(0)}'" if hit else "")

        # 7. Language: Hinglish question -> Hinglish answer (as classified)
        if q["lang"] == "hinglish":
            check("hinglish_detected", q, a.get("language") == "hinglish", f"classified as {a.get('language')}")

    answered = [a for a in ans.values() if "error" not in a]
    lat = sorted(a["latency_ms"] for a in answered)
    p95 = lat[max(0, int(round(0.95 * len(lat))) - 1)]

    def rate(metric, pred=lambda q: True):
        rows = [(q, ok) for q, ok in checks[metric] if pred(q)]
        return pct(sum(ok for _, ok in rows), len(rows))

    lines = ["# RailSaathi eval report", "",
             f"Questions: {len(qs)} ({sum(q['origin'] == 'real' for q in qs.values())} real, "
             f"{sum(q['origin'] == 'drafted' for q in qs.values())} drafted) | "
             f"answered: {len(answered)} | errors: {len(errors)} | not run: {len(missing)}", "",
             "## Code-checked metrics (no LLM judge)", "",
             "| Metric | All | Real | Drafted | Hinglish |", "|---|---|---|---|---|"]
    for m in checks:
        lines.append(f"| {m} | {rate(m)} | {rate(m, lambda q: q['origin'] == 'real')} | "
                     f"{rate(m, lambda q: q['origin'] == 'drafted')} | {rate(m, lambda q: q['lang'] == 'hinglish')} |")

    lines += ["", "## Routing by slice", "", "| Slice | Correct route |", "|---|---|"]
    for s in sorted({q["slice"] for q in qs.values()}):
        lines.append(f"| {s} | {rate('routing', lambda q, s=s: q['slice'] == s)} |")

    lines += ["", "## Cost and speed", "",
              f"- LLM calls per question: mean {statistics.mean(a['llm_calls'] for a in answered):.2f}, "
              f"max {max(a['llm_calls'] for a in answered)}",
              f"- Latency: p50 {statistics.median(lat) / 1000:.1f} s, p95 {p95 / 1000:.1f} s",
              f"- Fallback rate: {pct(sum(a['fallback_used'] for a in answered), len(answered))}", ""]
    REPORT.write_text("\n".join(lines), encoding="utf-8")

    with FAILS.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["metric", "id", "slice", "lang", "origin", "question", "detail"])
        w.writeheader()
        w.writerows(sorted(fails, key=lambda r: (r["metric"], r["id"])))

    print(REPORT.read_text(encoding="utf-8"))
    print(f"{len(fails)} failed checks -> {FAILS}")


if __name__ == "__main__":
    main()