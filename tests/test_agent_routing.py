"""Routing tests for the agent graph. classify() is replaced by a fake, so these
tests make NO LLM calls and can run in CI on every push."""
import pytest

from src.agent import classify as classify_module
from src.agent.classify import Classification, TicketDetails
from src.agent.graph import run


@pytest.fixture
def fake_classify(monkeypatch):
    """Make classify() return a fixed Classification instead of calling Gemini."""
    def set_result(**kw):
        result = Classification(**{"language": "en", "search_query": "test query", **kw})
        monkeypatch.setattr(classify_module, "classify", lambda q, h=None: result)
    return set_result


def test_out_of_scope_stops_after_one_llm_call(fake_classify):
    fake_classify(intent="out_of_scope")
    s = run("Who won the IPL?")
    assert s["path"] == ["classify", "refuse"]
    assert s["llm_calls"] == 1
    assert "only help" in s["answer"]


def test_out_of_scope_hinglish_reply(fake_classify):
    fake_classify(intent="out_of_scope", language="hinglish")
    assert "Maaf kijiye" in run("IPL kisne jeeta?")["answer"]


def test_rule_question_goes_to_retrieve(fake_classify):
    fake_classify(intent="rule_question", search_query="boarding station change")
    s = run("Can I change my boarding station?")
    assert s["path"] == ["classify", "retrieve"]
    assert len(s["chunks"]) == 5


def test_refund_with_missing_details_asks_instead_of_guessing(fake_classify):
    fake_classify(intent="refund_calc", ticket=TicketDetails(ticket_status="waitlisted", hours_before_departure=48))
    s = run("WL 38, train in 2 days, cancel or wait?")
    assert s["path"] == ["classify", "check_refund_details", "ask_missing"]
    assert set(s["missing"]) == {"travel_class", "fare_per_passenger"}
    assert "tool_result" not in s                 # calculator never ran


def test_refund_complete_runs_calculator_then_retrieve(fake_classify):
    fake_classify(intent="refund_calc",
                  ticket=TicketDetails(travel_class="3A", fare_per_passenger=1850, hours_before_departure=20))
    s = run("3A Rs 1850, 20 hours before, refund?")
    assert s["path"] == ["classify", "check_refund_details", "calculator", "retrieve"]
    assert s["tool_result"]["refund_total"] == "925.00"
    assert s["tool_result"]["rule_id"] == "R7"
    assert s["defaults_used"] == {"train_type": "normal", "quota": "general",
                                  "ticket_status": "confirmed", "passengers": 1}


def test_train_cancelled_does_not_need_hours(fake_classify):
    fake_classify(intent="refund_calc",
                  ticket=TicketDetails(travel_class="SL", fare_per_passenger=500, train_cancelled=True))
    s = run("Train cancelled, SL Rs 500")
    assert "calculator" in s["path"]
    assert s["tool_result"]["refund_total"] == "500.00"


def test_tdr_without_situation_asks(fake_classify):
    fake_classify(intent="tdr")
    s = run("How do I file a TDR?")
    assert s["path"] == ["classify", "check_tdr_details", "ask_missing"]


def test_tdr_with_situation_runs_tool(fake_classify):
    fake_classify(intent="tdr", tdr_situation="ac_failure")
    s = run("AC was not working")
    assert s["path"] == ["classify", "check_tdr_details", "tdr_tool", "retrieve"]
    assert s["tool_result"]["rule_id"] == "T3"
    assert s["defaults_used"] == {"booking_type": "e_ticket"}


@pytest.mark.parametrize("intent", ["rule_question", "refund_calc", "tdr", "out_of_scope"])
def test_every_path_uses_exactly_one_llm_call_so_far(fake_classify, intent):
    fake_classify(intent=intent)
    assert run("anything")["llm_calls"] == 1