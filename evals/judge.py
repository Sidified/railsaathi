"""Step 7i: LLM-judge metrics with DeepEval (Faithfulness + Answer Relevancy).

Judged: answers that went through RETRIEVAL as the main route and did not say "not sure".
(Calculator / TDR-tool answers are already checked exactly by score.py.)
The judge model is JUDGE_MODEL from .env - a stronger model than the app's model.

    python -m evals.judge --answers v3_answers.jsonl --limit 3   # quick test
    python -m evals.judge --answers v3_answers.jsonl             # full run, resumable
"""
import argparse
import json
import os
import re
import statistics
from pathlib import Path

os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")

from deepeval.metrics import AnswerRelevancyMetric, FaithfulnessMetric
from deepeval.models import DeepEvalBaseLLM
from deepeval.test_case import LLMTestCase
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()
RESULTS = Path("evals/results")
SET = Path("evals/eval_set.jsonl")
ABSTAIN = re.compile(r"not sure based on the official rules|pakka nahi|official rules mein nahi", re.I)
# The assumptions sentence is written by code, not the LLM, and is not in the documents -> don't judge it.
ASSUMPTIONS = re.compile(r"\n*(Assumed \(you did not say\)|Maine maana hai).*$", re.S)


class GeminiJudge(DeepEvalBaseLLM):
    """Lets DeepEval use a Gemini model as the judge."""

    def __init__(self, model_name: str):
        self.model_name = model_name
        super().__init__(model_name)

    def load_model(self):
        return ChatGoogleGenerativeAI(model=self.model_name)

    def generate(self, prompt: str, schema=None):
        if schema is None:
            return self.model.invoke(prompt).content
        try:
            return self.model.with_structured_output(schema).invoke(prompt)
        except Exception:
            # fallback: ask for plain JSON and parse it ourselves
            text = self.model.invoke(prompt + "\nReturn only valid JSON.").content
            text = re.sub(r"^```(json)?|```$", "", text.strip(), flags=re.M).strip()
            return schema.model_validate_json(text)

    async def a_generate(self, prompt: str, schema=None):
        return self.generate(prompt, schema)

    def get_model_name(self) -> str:
        return self.model_name


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--answers", default="v3_answers.jsonl")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    qs = {json.loads(l)["id"]: json.loads(l) for l in SET.read_text(encoding="utf-8").splitlines() if l.strip()}
    answers = [json.loads(l) for l in (RESULTS / args.answers).read_text(encoding="utf-8").splitlines() if l.strip()]
    out = RESULTS / f"judge_{args.answers.replace('_answers.jsonl', '')}.jsonl"
    done = {json.loads(l)["id"] for l in out.read_text(encoding="utf-8").splitlines()} if out.exists() else set()

    todo = [a for a in answers
            if "error" not in a and a["route"][:1] == ["retrieve"]
            and not ABSTAIN.search(a["answer"]) and a.get("chunks") and a["id"] not in done][: args.limit]
    print(f"{len(done)} already judged, judging {len(todo)}")

    judge = GeminiJudge(os.environ["JUDGE_MODEL"])
    for i, a in enumerate(todo, 1):
        q = qs[a["id"]]
        case = LLMTestCase(input=q["question"], actual_output=ASSUMPTIONS.sub("", a["answer"]).strip(),
                           retrieval_context=[c["text"] for c in a["chunks"]])
        row = {"id": a["id"], "slice": q["slice"], "lang": q["lang"], "origin": q["origin"]}
        for name, metric in (("faithfulness", FaithfulnessMetric(threshold=0.8, model=judge, async_mode=False)),
                             ("relevancy", AnswerRelevancyMetric(threshold=0.7, model=judge, async_mode=False))):
            try:
                metric.measure(case)
                row[name], row[f"{name}_reason"] = metric.score, metric.reason
            except Exception as e:
                row[name], row[f"{name}_reason"] = None, f"ERROR {type(e).__name__}: {e}"[:300]
        with out.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"[{i}/{len(todo)}] {a['id']:5} faithfulness={row['faithfulness']} relevancy={row['relevancy']}")

    rows = [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines() if l.strip()]
    for name, thr in (("faithfulness", 0.8), ("relevancy", 0.7)):
        vals = [r[name] for r in rows if r[name] is not None]
        if not vals:
            continue
        print(f"{name}: mean {statistics.mean(vals):.2f}, passing (>= {thr}) {sum(v >= thr for v in vals)}/{len(vals)}, "
              f"errors {sum(r[name] is None for r in rows)}")
    low = sorted((r for r in rows if r["faithfulness"] is not None and r["faithfulness"] < 0.8), key=lambda r: r["faithfulness"])
    for r in low:
        print(f"  low faithfulness {r['id']} {r['faithfulness']:.2f}: {r['faithfulness_reason'][:160]}")


if __name__ == "__main__":
    main()