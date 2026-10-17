"""Refund calculator for cancelling a reserved e-ticket under the CURRENT rules.

Pure Python, no LLM. Follows docs/refund_calculator_spec.md exactly.
Every result says which rule (R1-R11) was applied, which chunks are the source,
and which assumptions (A1-A7) it depends on.
"""
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from pydantic import BaseModel, Field

TrainType = Literal["normal", "vb_sleeper_amrit_bharat_2"]
TravelClass = Literal["1A", "EC", "2A", "FC", "3A", "3E", "CC", "SL", "2S"]
Quota = Literal["general", "tatkal"]
TicketStatus = Literal["confirmed", "rac", "waitlisted", "partially_confirmed"]

# Flat cancellation charge per passenger (refund rules #02(a)); see assumption A1.
FLAT_CHARGE = {
    "1A": Decimal(240), "EC": Decimal(240),
    "2A": Decimal(200), "FC": Decimal(200),
    "3A": Decimal(180), "CC": Decimal(180), "3E": Decimal(180),
    "SL": Decimal(120),
    "2S": Decimal(60),
}
CLERKAGE = Decimal(60)             # RAC / waitlist, per passenger (refund rules #04)
AC_CLASSES = {"1A", "EC", "2A", "3A", "3E", "CC"}

REFUND = "2015_refund_rules_irctc_updated_2026-01"
PIB = "2026-03-24_pib_cancellation_reform#01"
NIS = "2026-04_new_india_samachar_refund_slabs#01"
GSR = "2026-01-16_gsr41e_vb_sleeper_refund#03"

ASSUMPTIONS = {
    "A1": "Flat cancellation charges are unchanged since 2015 (no 2026 document gives new amounts).",
    "A2": "The minimum charge (= flat charge) still applies in the 25% and 50% bands.",
    "A3": "Exactly 72h counts in the 25% band, exactly 24h in the 25% band, exactly 8h in the 50% band.",
    "A4": "RAC/waitlist clerkage (Rs 60, up to 30 minutes before departure) is unchanged in 2026.",
    "A5": "GST is not added; on AC classes the actual deduction is slightly higher (plus GST).",
    "A6": "The deduction never exceeds the fare (refund is never negative).",
    "A7": "The April 2026 rules apply to all cancellations made from 15 April 2026.",
}


class RefundRequest(BaseModel):
    train_type: TrainType = "normal"
    travel_class: TravelClass
    quota: Quota = "general"
    ticket_status: TicketStatus = "confirmed"
    fare_per_passenger: Decimal = Field(gt=0, description="Rs paid per passenger, excluding IRCTC convenience fee")
    passengers: int = Field(default=1, ge=1, le=6)
    hours_before_departure: float = Field(description="Hours left before scheduled departure (negative = after)")
    train_cancelled: bool = False


class RefundResult(BaseModel):
    rule_id: str
    rule: str
    refund_total: Decimal
    deduction_total: Decimal
    refund_per_passenger: Decimal
    deduction_per_passenger: Decimal
    sources: list[str]
    assumptions: dict[str, str]
    notes: list[str]


def _money(x: Decimal) -> Decimal:
    return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _pick_rule(r: RefundRequest) -> tuple[str, str, Decimal | None, Decimal, list[str], list[str]]:
    """Return (rule_id, description, pct or None, minimum, sources, assumption_ids).
    pct=None means 'deduct the minimum only'; pct=1 means 'no refund'."""
    h = r.hours_before_departure
    flat = FLAT_CHARGE[r.travel_class]

    if r.train_cancelled:
        return "R1", "Train cancelled by Railways: full refund", Decimal(0), Decimal(0), \
            [f"{REFUND}#07", "2026-08-12_pib_railone_auto_refund#01"], []
    if r.quota == "tatkal" and r.ticket_status == "confirmed":
        return "R2", "Confirmed Tatkal ticket: no refund on cancellation", Decimal(1), Decimal(0), \
            [f"{REFUND}#13", "2024_irctc_tatkal_faq#08"], []
    if r.ticket_status in ("rac", "waitlisted", "partially_confirmed"):
        src = [f"{REFUND}#04", f"{REFUND}#05"] + ([f"{REFUND}#13"] if r.quota == "tatkal" else [])
        if h >= 0.5:
            return "R3", "RAC/waitlisted ticket cancelled 30+ minutes before departure: Rs 60 clerkage per passenger", \
                None, CLERKAGE, src, ["A4", "A6"]
        return "R4", "RAC/waitlisted ticket cancelled less than 30 minutes before departure: no refund", \
            Decimal(1), Decimal(0), src, ["A4"]

    if r.train_type == "vb_sleeper_amrit_bharat_2":
        src = [GSR, f"{REFUND}#03"]
        if h > 72:
            return "R9", "Vande Bharat Sleeper / Amrit Bharat II, more than 72h before: 25% deduction", \
                Decimal("0.25"), Decimal(0), src, ["A3"]
        if h >= 8:
            return "R10", "Vande Bharat Sleeper / Amrit Bharat II, 72h to 8h before: 50% deduction", \
                Decimal("0.50"), Decimal(0), src, ["A3"]
        return "R11", "Vande Bharat Sleeper / Amrit Bharat II, less than 8h before: no refund", \
            Decimal(1), Decimal(0), src, []

    src = [PIB, NIS, f"{REFUND}#02"]
    if h > 72:
        return "R5", "Confirmed ticket, more than 72h before departure: flat cancellation charge", \
            None, flat, src, ["A1", "A3", "A6", "A7"]
    if h >= 24:
        return "R6", "Confirmed ticket, 72h to 24h before departure: 25% of fare (minimum = flat charge)", \
            Decimal("0.25"), flat, src, ["A1", "A2", "A3", "A6", "A7"]
    if h >= 8:
        return "R7", "Confirmed ticket, 24h to 8h before departure: 50% of fare (minimum = flat charge)", \
            Decimal("0.50"), flat, src, ["A1", "A2", "A3", "A6", "A7"]
    return "R8", "Confirmed ticket, less than 8h before departure: no refund", \
        Decimal(1), Decimal(0), [PIB, NIS], ["A7"]


def calculate_refund(request: RefundRequest) -> RefundResult:
    rule_id, rule, pct, minimum, sources, assumption_ids = _pick_rule(request)
    fare = _money(request.fare_per_passenger)

    pct_part = fare * pct if pct is not None else Decimal(0)
    deduction = min(fare, max(pct_part, minimum))          # A6: never more than the fare
    deduction = _money(deduction)
    refund = fare - deduction

    notes = []
    if request.travel_class in AC_CLASSES and deduction > 0 and rule_id not in ("R2", "R4", "R8", "R11"):
        notes.append("Plus GST on the cancellation charge for AC classes (not included here).")
        assumption_ids = sorted(set(assumption_ids) | {"A5"})
    notes.append("Fare should exclude the IRCTC convenience fee, which is not refunded.")

    n = request.passengers
    return RefundResult(
        rule_id=rule_id,
        rule=rule,
        refund_total=refund * n,
        deduction_total=deduction * n,
        refund_per_passenger=refund,
        deduction_per_passenger=deduction,
        sources=sources,
        assumptions={a: ASSUMPTIONS[a] for a in assumption_ids},
        notes=notes,
    )