# RailSaathi eval report

Questions: 135 (69 real, 66 drafted) | answered: 135 | errors: 0 | not run: 0

## Code-checked metrics (no LLM judge)

| Metric | All | Real | Drafted | Hinglish |
|---|---|---|---|---|
| routing | 94% (127/135) | 93% (64/69) | 95% (63/66) | 97% (38/39) |
| no_false_refusal | 100% (122/122) | 100% (60/60) | 100% (62/62) | 100% (35/35) |
| abstain | 90% (101/112) | 80% (43/54) | 100% (58/58) | 97% (32/33) |
| has_sources | 100% (101/101) | 100% (43/43) | 100% (58/58) | 100% (32/32) |
| hinglish_detected | 100% (39/39) | 100% (19/19) | 100% (20/20) | 100% (39/39) |
| refund_exact | 96% (43/45) | 0% (0/1) | 98% (43/44) | 100% (13/13) |
| refuse_out_of_scope | 100% (13/13) | 100% (9/9) | 100% (4/4) | 100% (4/4) |
| no_old_rule_stale | 90% (9/10) | 83% (5/6) | 100% (4/4) | 67% (2/3) |
| tdr_situation | 86% (12/14) | n/a | 86% (12/14) | 75% (3/4) |

## Routing by slice

| Slice | Correct route |
|---|---|
| missing_info | 90% (9/10) |
| out_of_scope | 100% (13/13) |
| refund | 100% (41/41) |
| rule | 91% (30/33) |
| stale_trap | 80% (8/10) |
| tdr | 93% (26/28) |

## Cost and speed

- LLM calls per question: mean 1.83, max 2
- Latency: p50 2.6 s, p95 3.4 s
- Fallback rate: 1% (1/135)
