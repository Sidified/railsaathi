"""Unit tests for self_check (pure function, no LLM)."""
from src.agent.answer import self_check
from src.agent.classify import Classification

CHUNK = {"chunk_id": "x#01", "text": "Cancellation 50% of fare, minimum Rs 180 for 3A.",
         "title": "t", "section": "s", "pages": [1], "effective_from": "2026-04-01",
         "applies_to": "all_trains", "status": "current", "authority": "official", "note": "",
         "source_url": "u"}
TOOL = {"refund_total": "925.00", "deduction_total": "925.00", "rule": "R7"}


def state(answer, tool=TOOL, tool_name="calculate_refund", question="3A Rs 1850, 20h?"):
    return {"answer": answer, "question": question, "chunks": [CHUNK], "history": [],
            "tool_result": tool, "tool_name": tool_name,
            "classification": Classification(intent="refund_calc", language="en", search_query="q")}


def test_correct_answer_passes():
    assert self_check(state("You get Rs 925.00 back; 50% is deducted [1].")) == []


def test_amount_written_without_decimals_still_matches():
    assert self_check(state("You get ₹925 back [1].")) == []


def test_amounts_from_question_and_chunks_are_allowed():
    assert self_check(state("Your fare Rs 1,850; minimum charge Rs 180 [1]. Refund Rs 925.")) == []


def test_invented_amount_fails():
    problems = self_check(state("You get Rs 925 back, plus Rs 40 GST is charged [1]."))
    assert any("Rs 40" in p for p in problems)


def test_missing_refund_total_fails():
    problems = self_check(state("You will lose half the fare [1]."))
    assert any("missing" in p for p in problems)


def test_invalid_citation_fails():
    assert any("invalid citations" in p for p in self_check(state("Rs 925 [7].")))


def test_rupees_word_is_checked():
    assert self_check(state("You get 999 rupees [1]. Total 925.")) != []


def test_empty_answer_fails():
    assert self_check(state("   ")) == ["empty answer"]




def test_stale_note_only_when_question_uses_old_cutoffs():
    from src.agent.answer import mentions_old_rule
    assert mentions_old_rule("Under the 48-hour rule I lose only the flat charge, right?")
    assert mentions_old_rule("48 ghante se pehle cancel karu toh?")
    assert mentions_old_rule("is it 12 hours before departure for 50%?")
    assert not mentions_old_rule("Cancelling my 3AC ticket of Rs 1850, 20 hours before departure")
    assert not mentions_old_rule("Train is 4 hours late, I won't travel")   # a delay, not a cut-off