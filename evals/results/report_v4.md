# RailSaathi eval report

Questions: 135 (69 real, 66 drafted) | answered: 135 | errors: 0 | not run: 0

## Code-checked metrics (no LLM judge)

| Metric | All | Real | Drafted | Hinglish |
|---|---|---|---|---|
| routing | 93% (126/135) | 91% (63/69) | 95% (63/66) | 95% (37/39) |
| no_false_refusal | 100% (122/122) | 100% (60/60) | 100% (62/62) | 100% (35/35) |
| abstain | 88% (99/113) | 75% (41/55) | 100% (58/58) | 94% (32/34) |
| has_sources | 100% (99/99) | 100% (41/41) | 100% (58/58) | 100% (32/32) |
| hinglish_detected | 100% (39/39) | 100% (19/19) | 100% (20/20) | 100% (39/39) |
| refund_exact | 96% (43/45) | 0% (0/1) | 98% (43/44) | 100% (13/13) |
| refuse_out_of_scope | 92% (12/13) | 89% (8/9) | 100% (4/4) | 75% (3/4) |
| no_old_rule_stale | 100% (10/10) | 100% (6/6) | 100% (4/4) | 100% (3/3) |
| tdr_situation | 86% (12/14) | n/a | 86% (12/14) | 75% (3/4) |

## Routing by slice

| Slice | Correct route |
|---|---|
| missing_info | 90% (9/10) |
| out_of_scope | 92% (12/13) |
| refund | 100% (41/41) |
| rule | 91% (30/33) |
| stale_trap | 80% (8/10) |
| tdr | 93% (26/28) |

## Cost and speed

- LLM calls per question: mean 1.84, max 2
- Latency: p50 3.1 s, p95 3.8 s
- Fallback rate: 1% (2/135)
