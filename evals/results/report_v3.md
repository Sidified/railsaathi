# RailSaathi eval report

Questions: 135 (69 real, 66 drafted) | answered: 135 | errors: 0 | not run: 0

## Code-checked metrics (no LLM judge)

| Metric | All | Real | Drafted | Hinglish |
|---|---|---|---|---|
| routing | 96% (129/135) | 94% (65/69) | 97% (64/66) | 97% (38/39) |
| no_false_refusal | 100% (122/122) | 100% (60/60) | 100% (62/62) | 100% (35/35) |
| abstain | 91% (102/112) | 81% (44/54) | 100% (58/58) | 97% (31/32) |
| has_sources | 99% (101/102) | 98% (43/44) | 100% (58/58) | 100% (31/31) |
| hinglish_detected | 100% (39/39) | 100% (19/19) | 100% (20/20) | 100% (39/39) |
| refund_exact | 96% (43/45) | 0% (0/1) | 98% (43/44) | 100% (13/13) |
| refuse_out_of_scope | 100% (13/13) | 100% (9/9) | 100% (4/4) | 100% (4/4) |
| no_old_rule_stale | 100% (10/10) | 100% (6/6) | 100% (4/4) | 100% (3/3) |
| tdr_situation | 93% (13/14) | n/a | 93% (13/14) | 100% (4/4) |

## Routing by slice

| Slice | Correct route |
|---|---|
| missing_info | 90% (9/10) |
| out_of_scope | 100% (13/13) |
| refund | 100% (41/41) |
| rule | 91% (30/33) |
| stale_trap | 90% (9/10) |
| tdr | 96% (27/28) |

## Cost and speed

- LLM calls per question: mean 1.83, max 2
- Latency: p50 3.0 s, p95 3.6 s
- Fallback rate: 0% (0/135)
