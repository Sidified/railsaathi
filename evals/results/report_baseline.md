# RailSaathi eval report

Questions: 135 (69 real, 66 drafted) | answered: 135 | errors: 0 | not run: 0

## Code-checked metrics (no LLM judge)

| Metric | All | Real | Drafted | Hinglish |
|---|---|---|---|---|
| routing | 76% (102/135) | 55% (38/69) | 97% (64/66) | 74% (29/39) |
| no_false_refusal | 100% (122/122) | 100% (60/60) | 100% (62/62) | 100% (35/35) |
| abstain | 89% (81/91) | 71% (25/35) | 100% (56/56) | 96% (25/26) |
| hinglish_detected | 100% (39/39) | 100% (19/19) | 100% (20/20) | 100% (39/39) |
| refund_exact | 98% (44/45) | 0% (0/1) | 100% (44/44) | 100% (13/13) |
| has_sources | 100% (81/81) | 100% (25/25) | 100% (56/56) | 100% (25/25) |
| refuse_out_of_scope | 54% (7/13) | 33% (3/9) | 100% (4/4) | 50% (2/4) |
| no_old_rule_stale | 100% (10/10) | 100% (6/6) | 100% (4/4) | 100% (3/3) |
| tdr_situation | 86% (12/14) | n/a | 86% (12/14) | 100% (4/4) |

## Routing by slice

| Slice | Correct route |
|---|---|
| missing_info | 90% (9/10) |
| out_of_scope | 54% (7/13) |
| refund | 100% (41/41) |
| rule | 42% (14/33) |
| stale_trap | 90% (9/10) |
| tdr | 79% (22/28) |

## Cost and speed

- LLM calls per question: mean 1.67, max 2
- Latency: p50 2.8 s, p95 4.0 s
- Fallback rate: 0% (0/135)
