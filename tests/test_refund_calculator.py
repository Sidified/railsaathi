"""Unit tests: the known examples from docs/refund_calculator_spec.md (exact values)."""
from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.tools.refund_calculator import RefundRequest, calculate_refund


def refund(**kw) -> Decimal:
    return calculate_refund(RefundRequest(**kw)).refund_total


@pytest.mark.parametrize("kw, expected, rule", [
    (dict(travel_class="3A", fare_per_passenger=1850, hours_before_departure=20), "925.00", "R7"),
    (dict(travel_class="SL", fare_per_passenger=400, hours_before_departure=100), "280.00", "R5"),
    (dict(travel_class="SL", fare_per_passenger=400, hours_before_departure=30), "280.00", "R6"),   # min applies
    (dict(travel_class="3A", fare_per_passenger=1850, hours_before_departure=30), "1387.50", "R6"),  # 25% applies
    (dict(travel_class="2S", fare_per_passenger=50, hours_before_departure=100), "0.00", "R5"),     # capped (A6)
    (dict(travel_class="3A", fare_per_passenger=1850, hours_before_departure=5), "0.00", "R8"),
    (dict(travel_class="SL", fare_per_passenger=400, passengers=2, ticket_status="rac",
          hours_before_departure=3), "680.00", "R3"),
    (dict(travel_class="SL", fare_per_passenger=400, ticket_status="waitlisted",
          hours_before_departure=0.25), "0.00", "R4"),
    (dict(travel_class="SL", fare_per_passenger=600, quota="tatkal", hours_before_departure=50), "0.00", "R2"),
    (dict(travel_class="SL", fare_per_passenger=600, quota="tatkal", ticket_status="waitlisted",
          hours_before_departure=50), "540.00", "R3"),
    (dict(train_type="vb_sleeper_amrit_bharat_2", travel_class="3A", fare_per_passenger=2000,
          hours_before_departure=100), "1500.00", "R9"),
    (dict(train_type="vb_sleeper_amrit_bharat_2", travel_class="3A", fare_per_passenger=2000,
          hours_before_departure=10), "1000.00", "R10"),
    (dict(travel_class="1A", fare_per_passenger=4000, passengers=3, hours_before_departure=1,
          train_cancelled=True), "12000.00", "R1"),
])
def test_known_examples(kw, expected, rule):
    result = calculate_refund(RefundRequest(**kw))
    assert result.refund_total == Decimal(expected)
    assert result.rule_id == rule


@pytest.mark.parametrize("hours, rule", [
    (72.01, "R5"), (72, "R6"), (24, "R6"), (23.99, "R7"), (8, "R7"), (7.99, "R8"),
])
def test_slab_boundaries(hours, rule):
    """Assumption A3: exactly 72h and 24h -> 25% band, exactly 8h -> 50% band."""
    r = calculate_refund(RefundRequest(travel_class="3A", fare_per_passenger=1000, hours_before_departure=hours))
    assert r.rule_id == rule


def test_result_has_sources_and_assumptions():
    r = calculate_refund(RefundRequest(travel_class="3A", fare_per_passenger=1850, hours_before_departure=20))
    assert "2026-03-24_pib_cancellation_reform#01" in r.sources
    assert {"A1", "A2", "A5"} <= set(r.assumptions)        # A5 = GST note on AC class
    assert any("GST" in n for n in r.notes)


def test_no_gst_note_for_sleeper():
    r = calculate_refund(RefundRequest(travel_class="SL", fare_per_passenger=400, hours_before_departure=30))
    assert "A5" not in r.assumptions


@pytest.mark.parametrize("bad", [
    dict(travel_class="3A", fare_per_passenger=0, hours_before_departure=10),        # fare must be > 0
    dict(travel_class="3A", fare_per_passenger=100, passengers=7, hours_before_departure=10),
    dict(travel_class="4A", fare_per_passenger=100, hours_before_departure=10),      # unknown class
    dict(travel_class="SL", fare_per_passenger=100, quota="premium_tatkal", hours_before_departure=10),
])
def test_invalid_input_is_rejected(bad):
    with pytest.raises(ValidationError):
        RefundRequest(**bad)