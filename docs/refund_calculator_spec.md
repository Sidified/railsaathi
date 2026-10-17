# Refund Calculator Spec v1

Status: approved 2026-10-17
Code: `src/tools/refund_calculator.py` · Tests: `tests/test_refund_calculator.py`

## Scope
Voluntary cancellation of **reserved e-tickets** under the **current** rules (from April 2026),
plus "train cancelled by Railways". The calculator only computes **current** rules — it never
calculates with the old 48/12/4-hour rules, so it cannot give a stale answer.

## Inputs
| Field | Values |
|---|---|
| `train_type` | `normal` · `vb_sleeper_amrit_bharat_2` |
| `travel_class` | `1A, EC, 2A, FC, 3A, 3E, CC, SL, 2S` |
| `quota` | `general` · `tatkal` |
| `ticket_status` | `confirmed` · `rac` · `waitlisted` · `partially_confirmed` |
| `fare_per_passenger` | Rs actually paid per passenger, **excluding** IRCTC convenience fee |
| `passengers` | 1–6 |
| `hours_before_departure` | hours left before *scheduled* departure when cancelling |
| `train_cancelled` | true if Railways cancelled the train |

## Rules (checked in this order; first match wins)
| # | Case | Result | Source chunk |
|---|---|---|---|
| R1 | `train_cancelled` | Full refund, no deduction | refund #07, RailOne PIB #01 |
| R2 | Tatkal + confirmed | No refund | refund #13, Tatkal FAQ #08 |
| R3 | RAC / waitlisted / partially confirmed (incl. Tatkal RAC/WL), ≥ 0.5 h before | Deduct Rs 60 clerkage per passenger | refund #04, #05, #13 |
| R4 | Same, < 0.5 h before | No refund | refund #04 |
| R5 | Normal train, confirmed, > 72 h | Deduct flat charge per passenger | refund #02(a) + PIB #01 windows |
| R6 | Normal, confirmed, 72 h ≥ h ≥ 24 h | Deduct 25% of fare, minimum = flat charge | NIS #01, PIB #01 |
| R7 | Normal, confirmed, 24 h > h ≥ 8 h | Deduct 50% of fare, minimum = flat charge | NIS #01, PIB #01 |
| R8 | Normal, confirmed, < 8 h | No refund | NIS #01, PIB #01 |
| R9 | VB Sleeper / Amrit Bharat II, confirmed, > 72 h | Deduct 25% (no minimum) | G.S.R. 41(E) #03 |
| R10 | VB, confirmed, 72 h ≥ h ≥ 8 h | Deduct 50% (no minimum) | G.S.R. 41(E) #03 |
| R11 | VB, confirmed, < 8 h | No refund | G.S.R. 41(E) #03 |

## Flat charges per passenger (refund #02(a))
| Class | Flat charge |
|---|---|
| 1A, EC | Rs 240 |
| 2A, FC | Rs 200 |
| 3A, CC, 3E | Rs 180 |
| SL | Rs 120 |
| 2S | Rs 60 |

## Formula (per passenger)
`deduction = min(fare, max(pct × fare, minimum))`
`refund = fare − deduction`, then multiplied by number of passengers.
Money is kept exact to the paisa (Python `Decimal`).

## Assumptions (shown in every answer that depends on them)
| ID | Assumption | Why |
|---|---|---|
| A1 | Flat charges unchanged since 2015 | No 2026 document gives new amounts; these are the latest official figures |
| A2 | Minimum = flat charge still applies in the 25% / 50% bands | 2015 rule + news ("subject to minimum charge"); NIS/PIB do not mention it |
| A3 | Exactly 72 h → 25% band; exactly 24 h → 25%; exactly 8 h → 50% | Follows the 2015 wording pattern ("between X and up to Y") |
| A4 | RAC/waitlist clerkage (Rs 60, 30-minute limit) unchanged in 2026 | The April 2026 change only mentions confirmed tickets |
| A5 | GST is not added; answers say "plus GST on AC classes" | GST rate is not in our sources — we do not invent it |
| A6 | Deduction never exceeds the fare (refund ≥ Rs 0) | Matters for cheap 2S tickets where Rs 60 > fare |
| A7 | April 2026 rules apply to all cancellations from 2026-04-15 | Rollout was "phased 1–15 April" |

## Out of scope for v1 (calculator rejects or another tool handles)
- Premium Tatkal
- Counter (PRS) ticket rules
- Cancelling only *some* passengers on a ticket
- Fully waitlisted e-tickets dropped at charting (refund is automatic)
- Train late > 3 h → handled by the TDR tool

## Known examples (exact-value unit tests)
| Case | Expected refund |
|---|---|
| 3A, Rs 1,850, confirmed, 20 h | 50% = 925 > 180 → **Rs 925.00** |
| SL, Rs 400, confirmed, 100 h | flat 120 → **Rs 280.00** |
| SL, Rs 400, confirmed, 30 h | 25% = 100 < min 120 → **Rs 280.00** |
| 3A, Rs 1,850, confirmed, 30 h | 25% = 462.50 > 180 → **Rs 1,387.50** |
| 2S, Rs 50, confirmed, 100 h | flat 60 > fare → capped → **Rs 0.00** |
| 3A, Rs 1,850, confirmed, 5 h | **Rs 0.00** |
| SL, Rs 400 × 2, RAC, 3 h | (400 − 60) × 2 = **Rs 680.00** |
| SL, Rs 400, waitlisted, 0.25 h | **Rs 0.00** |
| Tatkal SL, Rs 600, confirmed, 50 h | **Rs 0.00** |
| Tatkal SL, Rs 600, waitlisted, 50 h | 600 − 60 = **Rs 540.00** |
| VB Sleeper 3A, Rs 2,000, confirmed, 100 h | 25% → **Rs 1,500.00** |
| VB Sleeper 3A, Rs 2,000, confirmed, 10 h | 50% → **Rs 1,000.00** |
| 1A, Rs 4,000 × 3, train cancelled | full fare → **Rs 12,000.00** |

## Invariants (property tests with `hypothesis`)
1. 0 ≤ refund ≤ fare × passengers
2. Refund never increases as departure gets closer (all other inputs fixed)
3. Refund for N passengers = N × refund for 1 passenger
4. Train cancelled → refund = full fare, always