# RailSaathi evaluation

Everything here is reproducible from files in this folder:
`eval_set.jsonl` (questions + labels) → `run_app.py` (answers, saved once) → `score.py` (code metrics)
→ `judge.py` (LLM judge) → `human_check.py` (judge vs human).

## The eval set: 135 questions

| Slice        | Real   | Drafted | What "correct" means                                          |
| ------------ | ------ | ------- | ------------------------------------------------------------- |
| refund       | 1      | 40      | exact ₹ refund                                                |
| tdr          | 14     | 14      | right TDR situation (T1–T10) and route                        |
| rule         | 33     | 0       | right route; judged for faithfulness and relevancy            |
| out_of_scope | 9      | 4       | refused                                                       |
| missing_info | 6      | 4       | asks for the missing details                                  |
| stale_trap   | 6      | 4       | corrects the old 48/12/4-hour rules; exact ₹ where calculable |
| **Total**    | **69** | **66**  | 39 questions in Hinglish                                      |

- **Real questions** were collected from public Reddit/Quora posts, rewritten in my own words, and anonymised. 20 links were spot-checked, with 0 failures.
- **Drafted questions** fill the slices that real users rarely produce. For example, only 1 real question had enough details to calculate an exact refund.
- **Expected refunds** were computed by an independent re-implementation of the spec (`build_set.py`), not by the app's calculator: this is differential testing. I also checked 10 of them by hand, and all 10 matched.

## Results

Scores are always reported separately for real and drafted questions, because the drafted ones are cleaner and score higher.

### Routing: baseline vs fixed classifier

|                         | Baseline | v2   | **v3 run 1** | **v3 run 2** |
| ----------------------- | -------- | ---- | ------------ | ------------ |
| Routing, real questions | 55%      | 96%  | **94%**      | **93%**      |
| Routing, all questions  | 76%      | 94%  | **96%**      | **94%**      |
| Out-of-scope refused    | 54%      | 100% | **100%**     | –            |

- **Root cause found by the baseline:** the classifier treated any question that mentions "refund" or "cancel" as a request to calculate a refund. So "is there a fee for waitlisted tickets?" got "tell me your class and fare".
- **Fix:** sharper intent definitions, written with new examples and never examples copied from the eval set (to avoid test-set leakage). In addition, a TDR question with no single situation is now answered from the rules instead of asking the user to pick one.
- **Noise:** I ran v3 twice with no changes, and **7 of 135 questions (5%) changed route** between the two runs. Differences smaller than about 5 points are treated as noise. The baseline → v3 gain is far above that.

### Code-checked metrics (v3, no LLM involved)

| Metric                                                     | Result                                                                    |
| ---------------------------------------------------------- | ------------------------------------------------------------------------- |
| Refund amount exact (calculator questions)                 | **43 / 44** (the one miss was a routing failure, not a calculation error) |
| No in-scope question refused                               | **122 / 122**                                                             |
| Hinglish detected                                          | **39 / 39**                                                               |
| TDR situation correct                                      | **13 / 14**                                                               |
| Stale-trap answers correct the old rule                    | **10 / 10** and **9 / 10** (run 1 / run 2)                                |
| Answers with sources (excluding honest "not sure" answers) | **101 / 102**                                                             |
| LLM calls per question                                     | **1.83** on average, max 2                                                |
| Latency                                                    | p50 **3.0 s**, p95 **3.6 s**                                              |
| Safe-fallback rate                                         | **0%**                                                                    |

### LLM judge (DeepEval, Gemini 3 Flash as judge)

Judged: the 40 answers written from retrieved rules. Calculator and TDR-tool answers are already checked exactly by code.

| Metric                           | Mean | Passing |
| -------------------------------- | ---- | ------- |
| Faithfulness (threshold 0.8)     | 0.91 | 32 / 40 |
| Answer relevancy (threshold 0.7) | 0.92 | 35 / 40 |

### Checking the judge

I labelled a 16-answer sample myself: all 8 answers the judge failed, plus 8 it passed, shuffled and with the judge's scores hidden. A second LLM (Claude) labelled the same sample, and I resolved the disagreements.

- **Judge agreement with the human labels: 9 / 16 (56%).**
- **6 of the 7 disagreements:** the judge was **too strict**. It penalised answers for *leaving out* details, which is not what faithfulness should measure. Example: "No refund on confirmed Tatkal" scored 0.00 even though both source chunks say exactly that.
- **1 disagreement:** the judge was **too lenient**. It passed an answer with an unsupported claim.
- **Human-checked result on the sample: 3 of 16 answers contained an unsupported claim.** So the judge's 32/40 is a rough signal, not a final number.

## Known failures (not fixed; this set was used for tuning)

- **d065:** a stale-trap question with full details was routed to rules instead of the calculator. The rule it gave was correct, but no amount was given.
- **q018:** confirmed Tatkal with no fare. The agent asks for the fare, even though the refund is ₹0 whatever the fare is.
- **q080:** a Hinglish stale-trap question. The old 48-hour premise was corrected in one run but not the other.
- **q035:** a waitlisted ticket that gets RAC was described as "treated as reserved". The rule says only a *confirmed* ticket is.
- **q020:** says a waitlisted e-ticket must be cancelled by the user to get a refund. The full-waitlist refund is actually automatic.
- **q019:** assumes the user has a waitlisted/RAC ticket they never mentioned.
- **Abstains on 2 topics that are in the documents:** q012 (fee on auto-cancelled WL) and q055 (luggage charges). This is a retrieval gap.
- **q023:** one answer contained a typo ("based onado").

## Limitations

- **These are development-set results.** The prompt was tuned on this same set in 3 rounds, then frozen. A clean number needs a fresh held-out set run exactly once.
- Human labels come from one annotator on a 16-answer sample.
- Exact-refund questions are mostly drafted, because real users rarely give class, fare and timing together.