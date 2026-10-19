# RailSaathi eval report

Questions: 135 (69 real, 66 drafted) | answered: 134 | errors: 0 | not run: 1

## Code-checked metrics (no LLM judge)

| Metric | All | Real | Drafted | Hinglish |
|---|---|---|---|---|
| routing | 94% (126/134) | 96% (66/69) | 92% (60/65) | 97% (37/38) |
| no_false_refusal | 99% (120/121) | 98% (59/60) | 100% (61/61) | 100% (34/34) |
| abstain | 89% (101/114) | 80% (43/54) | 97% (58/60) | 97% (32/33) |
| has_sources | 100% (101/101) | 100% (43/43) | 100% (58/58) | 100% (32/32) |
| hinglish_detected | 100% (38/38) | 100% (19/19) | 100% (19/19) | 100% (38/38) |
| refund_exact | 98% (43/44) | 0% (0/1) | 100% (43/43) | 100% (12/12) |
| refuse_out_of_scope | 100% (13/13) | 100% (9/9) | 100% (4/4) | 100% (4/4) |
| no_old_rule_stale | 89% (8/9) | 83% (5/6) | 100% (3/3) | 50% (1/2) |
| tdr_situation | 86% (12/14) | n/a | 86% (12/14) | 100% (4/4) |

## Routing by slice

| Slice | Correct route |
|---|---|
| missing_info | 60% (6/10) |
| out_of_scope | 100% (13/13) |
| refund | 100% (41/41) |
| rule | 94% (31/33) |
| stale_trap | 100% (9/9) |
| tdr | 93% (26/28) |

## Cost and speed

- LLM calls per question: mean 1.85, max 2
- Latency: p50 3.5 s, p95 17.5 s
- Fallback rate: 2% (3/134)
