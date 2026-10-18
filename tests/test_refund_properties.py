"""Property-based tests: hypothesis generates thousands of random tickets and checks
that the invariants from docs/refund_calculator_spec.md ALWAYS hold."""
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from src.tools.refund_calculator import RefundRequest, calculate_refund

# --- Random ticket generators -------------------------------------------------
fares = st.decimals(min_value=Decimal("1"), max_value=Decimal("20000"), places=2)
hours = st.floats(min_value=-48, max_value=24 * 60, allow_nan=False, allow_infinity=False)
ticket = st.fixed_dictionaries({
    "train_type": st.sampled_from(["normal", "vb_sleeper_amrit_bharat_2"]),
    "travel_class": st.sampled_from(["1A", "EC", "2A", "FC", "3A", "3E", "CC", "SL", "2S"]),
    "quota": st.sampled_from(["general", "tatkal"]),
    "ticket_status": st.sampled_from(["confirmed", "rac", "waitlisted", "partially_confirmed"]),
    "fare_per_passenger": fares,
    "passengers": st.integers(min_value=1, max_value=6),
    "hours_before_departure": hours,
    "train_cancelled": st.booleans(),
})

SETTINGS = settings(max_examples=2000, deadline=None)


def run(**kw):
    return calculate_refund(RefundRequest(**kw))


# --- Invariant 1: 0 <= refund <= fare paid --------------------------------------
@SETTINGS
@given(ticket)
def test_refund_is_never_negative_and_never_more_than_paid(t):
    r = run(**t)
    paid = t["fare_per_passenger"] * t["passengers"]
    assert Decimal(0) <= r.refund_total <= paid


# --- Invariant 2: refund never increases as departure gets closer -------------
@SETTINGS
@given(ticket, hours, hours)
def test_refund_never_increases_closer_to_departure(t, h1, h2):
    early, late = max(h1, h2), min(h1, h2)          # 'late' = closer to departure
    r_early = run(**{**t, "hours_before_departure": early})
    r_late = run(**{**t, "hours_before_departure": late})
    assert r_late.refund_total <= r_early.refund_total


# --- Invariant 3: N passengers = N x one passenger ----------------------------
@SETTINGS
@given(ticket)
def test_refund_scales_with_passengers(t):
    one = run(**{**t, "passengers": 1})
    many = run(**t)
    assert many.refund_total == one.refund_total * t["passengers"]


# --- Invariant 4: train cancelled -> full refund ------------------------------
@SETTINGS
@given(ticket)
def test_train_cancelled_always_gives_full_refund(t):
    r = run(**{**t, "train_cancelled": True})
    assert r.refund_total == t["fare_per_passenger"] * t["passengers"]
    assert r.deduction_total == 0


# --- Extra checks -------------------------------------------------------------
@SETTINGS
@given(ticket)
def test_refund_plus_deduction_equals_fare(t):
    """No money appears or disappears: refund + deduction = what was paid."""
    r = run(**t)
    assert r.refund_total + r.deduction_total == t["fare_per_passenger"] * t["passengers"]


@SETTINGS
@given(ticket)
def test_every_result_cites_a_source(t):
    """Every answer must be traceable to at least one source chunk."""
    assert run(**t).sources


@SETTINGS
@given(ticket)
def test_confirmed_tatkal_never_refunds_unless_train_cancelled(t):
    r = run(**{**t, "quota": "tatkal", "ticket_status": "confirmed", "train_cancelled": False})
    assert r.refund_total == 0