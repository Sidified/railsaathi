"""Step 7j: check the LLM judge against a human (you).

    python -m evals.human_check pack     # writes label_pack.md (to read) + human_labels.csv (to fill)
    python -m evals.human_check agree    # after filling: how often you and the judge agree

Sample: all answers the judge FAILED on faithfulness + the same number it PASSED (random, fixed seed).
The pack is shuffled and does NOT show the judge's score, so you label blind.
"""
import csv
import json
import random
import sys
from pathlib import Path

R = Path("evals/results")
JUDGE = R / "judge_v3.jsonl"
ANS = R / "v3_answers.jsonl"
SET = Path("evals/eval_set.jsonl")
PACK = R / "label_pack.md"
LABELS = R / "human_labels.csv"
THR = 0.8


def load(p):
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def pack():
    judged = [r for r in load(JUDGE) if r["faithfulness"] is not None]
    failed = [r for r in judged if r["faithfulness"] < THR]
    passed = [r for r in judged if r["faithfulness"] >= THR]
    rng = random.Random(42)
    sample = failed + rng.sample(passed, min(len(failed), len(passed)))
    rng.shuffle(sample)
    ans = {a["id"]: a for a in load(ANS)}
    qs = {q["id"]: q for q in load(SET)}

    lines = ["# Label pack (blind)", "",
             "For each answer: is EVERY claim supported by the chunks below it?",
             "- `yes` = nothing in the answer contradicts or goes beyond the chunks",
             "- `no` = at least one claim is wrong or not in the chunks",
             "Leaving out a detail is NOT a 'no' - only wrong or unsupported claims are.", ""]
    for i, r in enumerate(sample, 1):
        a = ans[r["id"]]
        lines += [f"## {i}. {r['id']}", "", f"**Question:** {qs[r['id']]['question']}", "",
                  "**Answer:**", "", a["answer"], "", "<details><summary>Chunks the answer was based on</summary>", ""]
        for c in a["chunks"]:
            lines += [f"**{c['chunk_id']}**", "", c["text"], ""]
        lines += ["</details>", ""]
    PACK.write_text("\n".join(lines), encoding="utf-8")
    with LABELS.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["n", "id", "faithful_yes_no", "note"])
        for i, r in enumerate(sample, 1):
            w.writerow([i, r["id"], "", ""])
    print(f"{len(sample)} answers ({len(failed)} judge-failed + {len(sample) - len(failed)} judge-passed, shuffled)")
    print(f"read {PACK}, fill column faithful_yes_no in {LABELS}")


def agree():
    judge = {r["id"]: r for r in load(JUDGE)}
    rows = [r for r in csv.DictReader(LABELS.open(encoding="utf-8")) if r["faithful_yes_no"].strip()]
    both = [(r["faithful_yes_no"].strip().lower().startswith("y"), judge[r["id"]]["faithfulness"] >= THR, r) for r in rows]
    agree_n = sum(h == j for h, j, _ in both)
    tp = sum(h and j for h, j, _ in both); tn = sum(not h and not j for h, j, _ in both)
    fp = sum(j and not h for h, j, _ in both); fn = sum(h and not j for h, j, _ in both)
    print(f"Agreement: {agree_n}/{len(both)} = {100 * agree_n / len(both):.0f}%")
    print(f"  both say faithful: {tp} | both say NOT faithful: {tn}")
    print(f"  judge passed, you failed (judge too lenient): {fp}")
    print(f"  judge failed, you passed (judge too strict): {fn}")
    for h, j, r in both:
        if h != j:
            print(f"  disagree {r['id']}: you={'yes' if h else 'no'} judge={judge[r['id']]['faithfulness']:.2f} | {r['note']}")


if __name__ == "__main__":
    {"pack": pack, "agree": agree}[sys.argv[1]]()