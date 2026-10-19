"""Routing tests for the full agent graph. Both LLM calls (classify + generate) are
replaced by fakes, so these tests make NO API calls and can run in CI on every push."""
import pytest

from src.agent import answer as answer_module
from src.agent import classify as classify_module
from src.agent.classify import Classification, TicketDetails
from src.agent.graph import run


@pytest.fixture
def fake_llm(monkeypatch):
    """fake_llm(answer=..., **classification) fixes both LLM outputs."""
    def set_result(answer="Here is the rule [1].", **kw):
        result = Classification(**{"language": "en", "search_query": "test query", **kw})
        monkeypatch.setattr(classify_module, "classify", lambda q, h=None: result)
        monkeypatch.setattr(answer_module, "call_llm", lambda messages: answer)
    return set_result


def test_out_of_scope_stops_after_one_llm_call(fake_llm):
    fake_llm(intent="out_of_scope")
    s = run("Who won the IPL?")
    assert s["path"] == ["classify", "refuse", "finalize"]
    assert s["llm_calls"] == 1
    assert "only help" in s["answer"]
    assert "Unofficial" in s["disclaimer"]


def test_out_of_scope_hinglish_reply(fake_llm):
    fake_llm(intent="out_of_scope", language="hinglish")
    assert "Maaf kijiye" in run("IPL kisne jeeta?")["answer"]


def test_rule_question_full_path(fake_llm):
    fake_llm(intent="rule_question", search_query="boarding station change")
    s = run("Can I change my boarding station?")
    assert s["path"] == ["classify", "retrieve", "generate", "self_check", "finalize"]
    assert s["llm_calls"] == 2
    assert len(s["sources"]) == 1                  # the answer cited [1]


def test_refund_with_missing_details_asks_instead_of_guessing(fake_llm):
    fake_llm(intent="refund_calc", ticket=TicketDetails(ticket_status="waitlisted", hours_before_departure=48))
    s = run("WL 38, train in 2 days, cancel or wait?")
    assert s["path"] == ["classify", "check_refund_details", "ask_missing", "finalize"]
    assert set(s["missing"]) == {"travel_class", "fare_per_passenger"}
    assert "tool_result" not in s and s["llm_calls"] == 1


def test_refund_good_answer_passes_self_check(fake_llm):
    fake_llm(intent="refund_calc", answer="You will get Rs 925.00 back. 50% is deducted [1].",
             ticket=TicketDetails(travel_class="3A", fare_per_passenger=1850, hours_before_departure=20))
    s = run("3A Rs 1850, 20 hours before, refund?")
    assert s["path"][-3:] == ["generate", "self_check", "finalize"]
    assert s["tool_result"]["refund_total"] == "925.00"
    assert not s["fallback_used"]
    assert any(src["chunk_id"] == "2026-03-24_pib_cancellation_reform#01" for src in s["sources"])  # tool source


def test_refund_wrong_amount_triggers_fallback(fake_llm):
    fake_llm(intent="refund_calc", answer="You will get Rs 1387.50 back [1].",     # wrong slab!
             ticket=TicketDetails(travel_class="3A", fare_per_passenger=1850, hours_before_departure=20))
    s = run("3A Rs 1850, 20 hours before, refund?")
    assert s["path"][-3:] == ["self_check", "fallback", "finalize"]
    assert s["fallback_used"]
    assert "Rs 925.00" in s["answer"]              # fallback uses the calculator's number
    assert s["llm_calls"] == 2                     # no retry call


def test_invalid_citation_triggers_fallback(fake_llm):
    fake_llm(intent="rule_question", answer="Yes you can [9].")
    s = run("Can I change my boarding station?")
    assert s["fallback_used"]
    assert "not sure" in s["answer"]


def test_train_cancelled_does_not_need_hours(fake_llm):
    fake_llm(intent="refund_calc", answer="Full refund of Rs 500.00 [1].",
             ticket=TicketDetails(travel_class="SL", fare_per_passenger=500, train_cancelled=True))
    s = run("Train cancelled, SL Rs 500")
    assert s["tool_result"]["refund_total"] == "500.00"
    assert not s["fallback_used"]


def test_tdr_without_situation_asks(fake_llm):
    fake_llm(intent="tdr")
    s = run("How do I file a TDR?")
    assert s["path"] == ["classify", "check_tdr_details", "ask_missing", "finalize"]


def test_tdr_with_situation_runs_tool(fake_llm):
    fake_llm(intent="tdr", tdr_situation="ac_failure", answer="File a TDR within 20 hours [1].")
    s = run("AC was not working")
    assert s["path"] == ["classify", "check_tdr_details", "tdr_tool", "retrieve",
                         "generate", "self_check", "finalize"]
    assert s["tool_result"]["rule_id"] == "T3"
    assert s["defaults_used"] == {"booking_type": "e_ticket"}


@pytest.mark.parametrize("intent, calls", [
    ("rule_question", 2), ("refund_calc", 1), ("tdr", 1), ("out_of_scope", 1),
])
def test_llm_call_budget_never_above_two(fake_llm, intent, calls):
    fake_llm(intent=intent)                        # refund/tdr without details -> ask_missing
    assert run("anything")["llm_calls"] == calls


def test_tool_result_tags_are_removed_not_failed(fake_llm):
    fake_llm(intent="refund_calc", answer="You get Rs 925.00 back [TOOL RESULT]. 50% deducted [1].",
             ticket=TicketDetails(travel_class="3A", fare_per_passenger=1850, hours_before_departure=20))
    s = run("3A Rs 1850, 20 hours before, refund?")
    assert not s["fallback_used"]
    assert "TOOL" not in s["answer"]


def test_assumptions_line_is_written_by_code_and_correct(fake_llm):
    fake_llm(intent="refund_calc", language="hinglish", answer="Aapko Rs 390.00 milega [1].",
             ticket=TicketDetails(travel_class="SL", ticket_status="rac", fare_per_passenger=450,
                                  hours_before_departure=10))
    s = run("sleeper RAC 450, 10 ghante, kitna milega?")
    assert s["tool_result"]["refund_total"] == "390.00"
    assert "Maine maana hai" in s["answer"]
    assert "confirmed" not in s["answer"]          # status was RAC, so it must NOT say confirmed
    assert "1 passenger" in s["answer"]


def test_tdr_assumption_mentions_eticket(fake_llm):
    fake_llm(intent="tdr", tdr_situation="ac_failure", answer="File a TDR within 20 hours [1].")
    s = run("AC was not working")
    assert "e-ticket" in s["answer"] and "confirmed" not in s["answer"]