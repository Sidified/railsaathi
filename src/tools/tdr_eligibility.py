"""TDR (Ticket Deposit Receipt) eligibility tool.

Pure Python, no LLM. Follows docs/tdr_tool_spec.md.
Given a situation, returns: is a TDR needed, what refund to expect, the deadline,
documents needed, how to file, sources and assumptions.
"""
from typing import Literal

from pydantic import BaseModel

Situation = Literal[
    "train_cancelled",                       # T1
    "train_late_3h_not_travelled",           # T2
    "ac_failure",                            # T3
    "train_diverted_not_travelled",          # T4
    "train_terminated_short",                # T5
    "lower_class_travelled",                 # T6
    "not_travelled_lower_class_or_coach_damage",  # T7
    "partial_travel",                        # T8
    "missed_connecting_train",               # T9
    "did_not_travel_own_choice",             # T10
]
BookingType = Literal["e_ticket", "counter_ticket", "agent"]

R = "2015_refund_rules_irctc_updated_2026-01"
TTE_CERT = "Certificate from the ticket checking staff (TTE) - GC/EFT - sent by post to IRCTC"

ASSUMPTIONS = {
    "B1": "TDR deadlines for delays, AC failure, diversion etc. are unchanged in 2026 "
          "(the March 2026 PIB change only removed TDR for cancellations).",
    "B2": "The exact IRCTC menu path for filing is not given (not in official sources; menus change).",
    "B3": "For counter tickets, only 'get the TDR at the station' is covered.",
}

# One entry per situation: (id, tdr_needed, refund, deadline, documents, sources)
RULES: dict[str, tuple] = {
    "train_cancelled": (
        "T1", "no", "Full refund, processed automatically for e-tickets.",
        None, [], ["2026-08-12_pib_railone_auto_refund#01", f"{R}#07", f"{R}#17"]),
    "train_late_3h_not_travelled": (
        "T2", "yes", "Full fare refund (no cancellation charge).",
        "Before the train's ACTUAL departure from your boarding station. "
        "No refund if filed after the train has left.",
        [], [f"{R}#08", f"{R}#17"]),
    "ac_failure": (
        "T3", "yes", "Difference between the AC fare and the lower-class fare, for the part of the "
        "journey without AC. Amount is decided by the Railway.",
        "Within 20 hours of the train's actual arrival at your destination.",
        [TTE_CERT], [f"{R}#11", f"{R}#18"]),
    "train_diverted_not_travelled": (
        "T4", "yes", "Full fare refund.",
        "Within 72 hours of the train's scheduled departure from your boarding station.",
        [], [f"{R}#17"]),
    "train_terminated_short": (
        "T5", "yes", "Refund for the part of the journey not travelled.",
        "Within 72 hours of the train's scheduled arrival at your destination.",
        [], [f"{R}#18"]),
    "lower_class_travelled": (
        "T6", "conditional", "Difference between the fare paid and the fare of the class actually used.",
        "If the lower class was given at charting: no TDR, refund is automatic. "
        "If given after charting: within 2 days of the certificate (not counting the day it was issued).",
        [TTE_CERT + " (only if given after charting)"], [f"{R}#12", f"{R}#18"]),
    "not_travelled_lower_class_or_coach_damage": (
        "T7", "yes", "Full fare refund.",
        "Within 3 hours of the train's ACTUAL departure from your boarding station.",
        [], [f"{R}#18"]),
    "partial_travel": (
        "T8", "yes", "Refund for the passengers or part of the journey not used.",
        "Within 72 hours (counted from the train's scheduled departure, or from actual arrival for "
        "waitlisted passengers on a partly confirmed ticket - see source).",
        [TTE_CERT], [f"{R}#10", f"{R}#17", f"{R}#18"]),
    "missed_connecting_train": (
        "T9", "yes", "Refund for the missed connecting journey (only if the PNRs were linked).",
        "Within 3 hours of the actual arrival of the first (late) train.",
        [], [f"{R}#18"]),
    "did_not_travel_own_choice": (
        "T10", "no", "This is a cancellation, not a TDR case. Use the refund calculator: for a "
        "confirmed ticket cancelled less than 8 hours before departure there is no refund.",
        "Cancel the ticket before departure.",
        [], ["2026-03-24_pib_cancellation_reform#01"]),
}


class TDRRequest(BaseModel):
    situation: Situation
    booking_type: BookingType = "e_ticket"


class TDRResult(BaseModel):
    rule_id: str
    tdr_needed: Literal["yes", "no", "conditional"]
    refund: str
    deadline: str | None
    documents: list[str]
    how_to_file: list[str]
    notes: list[str]
    sources: list[str]
    assumptions: dict[str, str]


def _how_to_file(booking_type: str) -> tuple[list[str], list[str]]:
    """Return (steps, extra sources)."""
    if booking_type == "counter_ticket":
        return ["Get a TDR from the railway station (station master / reservation office)."], [f"{R}#19"]
    if booking_type == "agent":
        return ["Ask the agent you booked with to file the TDR within the deadline."], [f"{R}#20"]
    return ["File the TDR online on IRCTC (website or app) for this PNR, choosing the matching reason."], [f"{R}#15"]


def check_tdr_eligibility(request: TDRRequest) -> TDRResult:
    rule_id, tdr_needed, refund, deadline, documents, sources = RULES[request.situation]
    sources = list(sources)
    notes: list[str] = []
    assumption_ids: list[str] = []

    if rule_id == "T1" and request.booking_type == "counter_ticket":
        refund = "Full refund. Automatic refunds are only for e-tickets."
        deadline = "Visit the nearest reservation (PRS) counter."
        how_to_file = ["Take the ticket to the nearest PRS counter to get the refund."]
    elif tdr_needed == "no":
        how_to_file = []
    else:
        how_to_file, extra = _how_to_file(request.booking_type)
        sources += extra
        notes.append("The refund decision is made by the Zonal Railway, not IRCTC, so it is not guaranteed.")
        assumption_ids += ["B1", "B2"]
        if request.booking_type == "counter_ticket":
            assumption_ids.append("B3")

    return TDRResult(
        rule_id=rule_id,
        tdr_needed=tdr_needed,
        refund=refund,
        deadline=deadline,
        documents=documents,
        how_to_file=how_to_file,
        notes=notes,
        sources=sources,
        assumptions={a: ASSUMPTIONS[a] for a in assumption_ids},
    )