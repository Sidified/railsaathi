"""Tests for the TDR eligibility tool (docs/tdr_tool_spec.md)."""
import itertools
import typing

import pytest
from pydantic import ValidationError

from src.tools.tdr_eligibility import BookingType, Situation, TDRRequest, check_tdr_eligibility

ALL_SITUATIONS = typing.get_args(Situation)
ALL_BOOKINGS = typing.get_args(BookingType)
ALL_COMBOS = list(itertools.product(ALL_SITUATIONS, ALL_BOOKINGS))


def check(situation, booking_type="e_ticket"):
    return check_tdr_eligibility(TDRRequest(situation=situation, booking_type=booking_type))


@pytest.mark.parametrize("situation, rule_id, tdr_needed, deadline_contains", [
    ("train_cancelled", "T1", "no", None),
    ("train_late_3h_not_travelled", "T2", "yes", "ACTUAL departure"),
    ("ac_failure", "T3", "yes", "20 hours"),
    ("train_diverted_not_travelled", "T4", "yes", "72 hours"),
    ("train_terminated_short", "T5", "yes", "72 hours"),
    ("lower_class_travelled", "T6", "conditional", "2 days"),
    ("not_travelled_lower_class_or_coach_damage", "T7", "yes", "3 hours"),
    ("partial_travel", "T8", "yes", "72 hours"),
    ("missed_connecting_train", "T9", "yes", "3 hours"),
    ("did_not_travel_own_choice", "T10", "no", "Cancel"),
])
def test_each_situation(situation, rule_id, tdr_needed, deadline_contains):
    r = check(situation)
    assert r.rule_id == rule_id
    assert r.tdr_needed == tdr_needed
    if deadline_contains:
        assert deadline_contains in r.deadline


def test_ac_failure_needs_tte_certificate():
    assert any("TTE" in d for d in check("ac_failure").documents)


def test_counter_ticket_train_cancelled_goes_to_counter():
    r = check("train_cancelled", "counter_ticket")
    assert "counter" in r.deadline.lower()
    assert "only for e-tickets" in r.refund


@pytest.mark.parametrize("booking_type, expected_source", [
    ("e_ticket", "#15"), ("counter_ticket", "#19"), ("agent", "#20"),
])
def test_filing_steps_depend_on_booking_type(booking_type, expected_source):
    r = check("ac_failure", booking_type)
    assert any(s.endswith(expected_source) for s in r.sources)


# --- Invariants over ALL situation x booking combinations (10 x 3 = 30) ---------
@pytest.mark.parametrize("situation, booking_type", ALL_COMBOS)
def test_every_result_has_a_source(situation, booking_type):
    assert check(situation, booking_type).sources


@pytest.mark.parametrize("situation, booking_type", ALL_COMBOS)
def test_every_yes_has_deadline_and_filing_steps(situation, booking_type):
    r = check(situation, booking_type)
    if r.tdr_needed in ("yes", "conditional"):
        assert r.deadline and r.how_to_file
        assert "B1" in r.assumptions        # deadlines assumed unchanged in 2026


@pytest.mark.parametrize("booking_type", ALL_BOOKINGS)
def test_did_not_travel_never_says_file_tdr(booking_type):
    r = check("did_not_travel_own_choice", booking_type)
    assert r.tdr_needed == "no"
    assert not r.how_to_file
    assert "8 hours" in r.refund             # current rule, not the old 4 hours


def test_train_cancelled_eticket_never_asks_for_tdr():
    r = check("train_cancelled", "e_ticket")
    assert r.tdr_needed == "no" and not r.how_to_file


def test_unknown_situation_is_rejected():
    with pytest.raises(ValidationError):
        TDRRequest(situation="lost_my_luggage")