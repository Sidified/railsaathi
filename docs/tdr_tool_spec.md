# TDR Eligibility Tool Spec v1

Status: approved 2026-10-18
Code: `src/tools/tdr_eligibility.py` · Tests: `tests/test_tdr_eligibility.py`

TDR = Ticket Deposit Receipt: how a passenger claims a refund when something goes wrong
after the normal cancellation window.

## What it does
Given the situation, returns: is a TDR needed, what refund to expect, the filing deadline,
documents needed, how to file, sources and assumptions.
It does NOT calculate amounts (refund calculator does), check live train status, or file anything.

## Inputs
| Field | Values |
|---|---|
| `situation` | one of T1–T10 below |
| `booking_type` | `e_ticket` · `counter_ticket` · `agent` |

## Situations
| # | Situation | TDR? | Refund | Deadline | Documents | Source chunk |
|---|---|---|---|---|---|---|
| T1 | Train cancelled by Railways | No (e-ticket) | Full, automatic | — (counter ticket: visit PRS counter) | — | RailOne PIB #01, refund #07, #17 |
| T2 | Train late > 3 h, did not travel | Yes | Full fare | Before train's ACTUAL departure from boarding station | — | refund #08, #17 |
| T3 | AC not working | Yes | Fare difference for that part | Within 20 h of actual arrival at destination | TTE certificate (GC/EFT) | refund #11, #18 |
| T4 | Train diverted, did not travel | Yes | Full fare | Within 72 h of scheduled departure from boarding station | — | refund #17 |
| T5 | Train terminated short | Yes | For part not travelled | Within 72 h of scheduled arrival at destination | — | refund #18 |
| T6 | Given a lower class | Conditional | Fare difference | At charting: automatic. After charting: within 2 days of certificate | TTE certificate (after charting) | refund #12, #18 |
| T7 | Did not travel: lower class given / coach damage | Yes | Full fare | Within 3 h of train's actual departure | — | refund #18 |
| T8 | Some passengers did not travel / journey ended midway | Yes | For unused part | Within 72 h (see source) | TTE certificate | refund #10, #17, #18 |
| T9 | Missed connecting train (linked PNRs) | Yes | For missed journey | Within 3 h of actual arrival of first train | — | refund #18 |
| T10 | Did not travel by own choice | No — this is a cancellation | Use refund calculator (confirmed < 8 h → no refund) | Cancel before departure | — | PIB #01 |

## How to file (for every "Yes")
- e-ticket: file TDR online on IRCTC for the PNR, choosing the matching reason (refund #15)
- counter ticket: get the TDR from the railway station (refund #19)
- agent booking: ask the agent to file it (refund #20)
- Always noted: the refund decision is made by the Zonal Railway, not IRCTC — not guaranteed (refund #17)

## Assumptions
| ID | Assumption | Why |
|---|---|---|
| B1 | TDR deadlines for T2–T9 unchanged in 2026 | PIB (Mar 2026) only removed TDR for cancellations |
| B2 | Exact IRCTC menu path not given | Not in official sources; menus change |
| B3 | Counter tickets: only "get TDR at station" covered | Sources detail e-tickets, counter tickets only briefly |

## Out of scope (v2 later)
Calculating AC-failure / lower-class fare differences (needs fare tables) · checking if a
deadline has passed (needs live train times) · Premium Special Trains.

## Tests
- Each situation returns the right rule, TDR status and deadline
- Invariants over all 30 situation × booking combinations: every result has a source;
  every "yes"/"conditional" has a deadline and filing steps; T10 never says "file TDR";
  T1 e-ticket never asks for a TDR