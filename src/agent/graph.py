"""The RailSaathi agent as a LangGraph state graph (see docs/agent_graph.md).

classify (LLM 1) -> route -> tools -> retrieve -> generate (LLM 2) -> self_check -> finalize/fallback.
LLM calls: at most 2 per question.
"""
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

from src.agent import classify as classify_module
from src.agent.answer import fallback_node, finalize_node, generate_node, self_check_node
from src.agent.classify import Classification
from src.retrieval.search import hybrid_search
from src.tools.refund_calculator import RefundRequest, calculate_refund
from src.tools.tdr_eligibility import TDRRequest, check_tdr_eligibility

TOP_K = 5
REQUIRED_FOR_REFUND = {
    "travel_class": ("class (e.g. SL, 3A, 2A)", "class (jaise SL, 3A, 2A)"),
    "fare_per_passenger": ("fare paid per passenger (Rs)", "har passenger ka kiraya (Rs)"),
    "hours_before_departure": ("how many hours before departure you are cancelling",
                               "train chalne se kitne ghante pehle cancel kar rahe hain"),
}
# Used when the user did not say; always shown to the user as an assumption.
REFUND_DEFAULTS = {"train_type": "normal", "quota": "general", "ticket_status": "confirmed", "passengers": 1}


class AgentState(TypedDict, total=False):
    question: str
    history: list[dict]
    classification: Classification
    missing: list[str]
    defaults_used: dict[str, Any]
    tool_name: str
    tool_result: dict
    chunks: list[dict]
    answer: str
    check_problems: list[str]
    fallback_used: bool
    sources: list[dict]
    disclaimer: str
    path: list[str]          # node names visited, for tests and tracing
    llm_calls: int


# ----------------------------------------------------------------- nodes
def classify_node(state: AgentState) -> AgentState:
    c = classify_module.classify(state["question"], state.get("history"))
    return {"classification": c, "path": ["classify"], "llm_calls": 1}


def refuse_node(state: AgentState) -> AgentState:
    hinglish = state["classification"].language == "hinglish"
    answer = ("Maaf kijiye, main sirf Indian Railways ke ticket rules (cancellation, refund, TDR, Tatkal, "
              "waitlist, boarding change, luggage) mein madad karta hoon. Live PNR ya train status ke liye "
              "NTES / RailOne app ya 139 dekhein."
              if hinglish else
              "Sorry, I only help with Indian Railways ticket rules (cancellation, refunds, TDR, Tatkal, "
              "waitlist, boarding change, luggage). For live PNR or train status, please use the "
              "NTES / RailOne app or call 139.")
    return {"answer": answer, "path": state["path"] + ["refuse"]}


def check_refund_details(state: AgentState) -> AgentState:
    t = state["classification"].ticket
    missing = [f for f in REQUIRED_FOR_REFUND if getattr(t, f) is None]
    if t.train_cancelled and "hours_before_departure" in missing:
        missing.remove("hours_before_departure")       # timing does not matter if the train is cancelled
    return {"missing": missing, "path": state["path"] + ["check_refund_details"]}


def check_tdr_details(state: AgentState) -> AgentState:
    missing = [] if state["classification"].tdr_situation else ["tdr_situation"]
    return {"missing": missing, "path": state["path"] + ["check_tdr_details"]}


def ask_missing_node(state: AgentState) -> AgentState:
    hinglish = state["classification"].language == "hinglish"
    if state["missing"] == ["tdr_situation"]:
        answer = ("Kya hua tha? Jaise: train 3 ghante se zyada late thi, AC kharab tha, train divert hui, "
                  "lower class mila, ya connecting train chhoot gayi?"
                  if hinglish else
                  "What happened? For example: train late by more than 3 hours, AC not working, train "
                  "diverted, given a lower class, or missed a connecting train?")
    else:
        idx = 1 if hinglish else 0
        items = [REQUIRED_FOR_REFUND[f][idx] for f in state["missing"]]
        lead = ("Exact refund batane ke liye mujhe yeh chahiye: " if hinglish
                else "To calculate your exact refund I need: ")
        answer = lead + "; ".join(items) + "."
    return {"answer": answer, "path": state["path"] + ["ask_missing"]}


def calculator_node(state: AgentState) -> AgentState:
    given = {k: v for k, v in state["classification"].ticket.model_dump().items() if v is not None}
    defaults_used = {k: v for k, v in REFUND_DEFAULTS.items() if k not in given}
    if given.get("train_cancelled") and "hours_before_departure" not in given:
        given["hours_before_departure"] = 0
    try:
        result = calculate_refund(RefundRequest(**{**defaults_used, **given}))
        tool_result = result.model_dump(mode="json")
    except ValidationError as e:
        tool_result = {"error": f"Invalid ticket details: {e.errors()[0]['msg']}"}
    return {"tool_name": "calculate_refund", "tool_result": tool_result,
            "defaults_used": defaults_used, "path": state["path"] + ["calculator"]}


def tdr_node(state: AgentState) -> AgentState:
    c = state["classification"]
    result = check_tdr_eligibility(TDRRequest(situation=c.tdr_situation,
                                              booking_type=c.booking_type or "e_ticket"))
    return {"tool_name": "check_tdr_eligibility", "tool_result": result.model_dump(mode="json"),
            "defaults_used": {} if c.booking_type else {"booking_type": "e_ticket"},
            "path": state["path"] + ["tdr_tool"]}


def retrieve_node(state: AgentState) -> AgentState:
    chunks = hybrid_search(state["classification"].search_query, k=TOP_K)
    return {"chunks": chunks, "path": state["path"] + ["retrieve"]}


# ----------------------------------------------------------------- routing
def route_intent(state: AgentState) -> str:
    return {"out_of_scope": "refuse", "rule_question": "retrieve",
            "refund_calc": "check_refund_details", "tdr": "check_tdr_details"}[state["classification"].intent]


def route_refund(state: AgentState) -> str:
    return "ask_missing" if state["missing"] else "calculator"


def route_tdr(state: AgentState) -> str:
    return "ask_missing" if state["missing"] else "tdr_tool"


def route_check(state: AgentState) -> str:
    return "fallback" if state["check_problems"] else "finalize"


# ----------------------------------------------------------------- graph
def build_graph():
    g = StateGraph(AgentState)
    g.add_node("classify", classify_node)
    g.add_node("refuse", refuse_node)
    g.add_node("check_refund_details", check_refund_details)
    g.add_node("check_tdr_details", check_tdr_details)
    g.add_node("ask_missing", ask_missing_node)
    g.add_node("calculator", calculator_node)
    g.add_node("tdr_tool", tdr_node)
    g.add_node("retrieve", retrieve_node)
    g.add_node("generate", generate_node)
    g.add_node("self_check", self_check_node)
    g.add_node("fallback", fallback_node)
    g.add_node("finalize", finalize_node)

    g.add_edge(START, "classify")
    g.add_conditional_edges("classify", route_intent,
                            ["refuse", "retrieve", "check_refund_details", "check_tdr_details"])
    g.add_conditional_edges("check_refund_details", route_refund, ["ask_missing", "calculator"])
    g.add_conditional_edges("check_tdr_details", route_tdr, ["ask_missing", "tdr_tool"])
    g.add_edge("calculator", "retrieve")
    g.add_edge("tdr_tool", "retrieve")
    g.add_edge("retrieve", "generate")
    g.add_edge("generate", "self_check")
    g.add_conditional_edges("self_check", route_check, ["fallback", "finalize"])
    g.add_edge("fallback", "finalize")
    g.add_edge("refuse", "finalize")
    g.add_edge("ask_missing", "finalize")
    g.add_edge("finalize", END)
    return g.compile()


graph = build_graph()


def run(question: str, history: list[dict] | None = None) -> AgentState:
    return graph.invoke({"question": question, "history": history or []})


if __name__ == "__main__":
    import sys
    s = run(" ".join(sys.argv[1:]))
    c = s["classification"]
    print(f"\nQ: {s['question']}\n\n{s['answer']}\n")
    for i, src in enumerate(s.get("sources", []), start=1):
        pages = ",".join(map(str, src["pages"]))
        print(f"  source {i}: {src['title']} (p. {pages}, effective {src['effective_from']})\n            {src['source_url']}")
    print(f"\n{s['disclaimer']}")
    print(f"\npath: {' -> '.join(s['path'])}")
    print(f"intent: {c.intent} | language: {c.language} | LLM calls: {s['llm_calls']} | "
          f"fallback: {s.get('fallback_used')} | check problems: {s.get('check_problems')}")