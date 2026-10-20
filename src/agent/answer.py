"""Agent nodes for the answer: generate (LLM call 2), self_check, fallback, finalize.

- generate: writes the answer from the tool result (numbers locked) + retrieved chunks.
- self_check: pure code. Valid citations? Every Rs amount traceable? Refund total present?
- fallback: if self_check fails, a safe answer built directly from the tool output (no LLM).
- finalize: attaches the sources list (by code), disclaimer and "rules last verified" date.
"""
import os
import re
from decimal import Decimal, InvalidOperation

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from src.rag.answer import build_citations, format_sources
from src.retrieval.search import load_chunks

RULES_LAST_VERIFIED = "2026-10-17"
DISCLAIMER = "Unofficial assistant - not affiliated with Indian Railways or IRCTC. Rules last verified on {date}."

SYSTEM_PROMPT = """You are RailSaathi, an UNOFFICIAL assistant for Indian Railways passenger rules.

Write a short, clear answer for a passenger using ONLY:
  - the TOOL RESULT (if given): its numbers are exact and final. Copy amounts exactly as written.
  - the numbered SOURCES: cite them like [1] or [2][3] after each rule you state.

Rules:
1. Never calculate, round or change any number. Never invent an amount that is not in the
   TOOL RESULT, the question or the SOURCES.
2. Cite ONLY the numbered sources [1]-[5]. The TOOL RESULT needs no citation.
3. Mention important notes from the TOOL RESULT (GST, convenience fee, deadline, documents).
   Do not mention assumed ticket details - they are added automatically. State the main amount in one plain sentence (e.g. "You will get Rs X back.");
   do not copy the labelled lines.
4. Some sources are marked OUTDATED IN PART: follow the note; the newer rule wins.
5. If the sources and tool result do not answer the question, say "I'm not sure based on the
   official rules I have" and suggest IRCTC or 139. Do not guess.
6. Do not predict whether a waitlisted ticket will be confirmed.
7. Write in {language}. Simple words. Under 150 words. Do not add a sources list - it is added
   automatically."""

MONEY = re.compile(
    r"(?:Rs\.?|₹|INR)\s*([\d,]+(?:\.\d+)?)"            # Rs 925, ₹925.00, INR 1,850
    r"|([\d,]+(?:\.\d+)?)\s*(?:/-\s*)?(?:rupees|rupaye|rupay|rs\b)",  # 925 rupees, 925 rs
    re.IGNORECASE,
)
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
TOOL_TAG = re.compile(r"\s*\[\s*tool[^\]]*\]", re.IGNORECASE)     # e.g. "[TOOL RESULT]"

# Human labels for tool fields (the LLM should never see raw names like "refund_total").
LABELS = {
    "rule": "Rule applied", "refund_total": "Total refund (Rs)", "deduction_total": "Total deduction (Rs)",
    "refund_per_passenger": "Refund per passenger (Rs)", "deduction_per_passenger": "Deduction per passenger (Rs)",
    "tdr_needed": "TDR needed", "refund": "Refund", "deadline": "Deadline to file",
    "documents": "Documents needed", "how_to_file": "How to file", "notes": "Notes",
}
# How to say each default, in English and Hinglish.
DEFAULT_PHRASES = {
    ("train_type", "normal"): ("a normal train (not Vande Bharat Sleeper)", "normal train (Vande Bharat Sleeper nahi)"),
    ("quota", "general"): ("general quota (not Tatkal)", "general quota (Tatkal nahi)"),
    ("ticket_status", "confirmed"): ("a confirmed ticket", "confirmed ticket"),
    ("passengers", 1): ("1 passenger", "1 passenger"),
    ("booking_type", "e_ticket"): ("an e-ticket booked online", "online e-ticket"),
}


def get_llm() -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(model=os.environ["GEMINI_MODEL"])


def call_llm(messages) -> str:
    """Single place where generation calls the LLM (tests replace this)."""
    return get_llm().invoke(messages).text


def _to_decimal(s: str) -> Decimal | None:
    try:
        return Decimal(s.replace(",", ""))
    except InvalidOperation:
        return None


def _numbers_in(text: str) -> set[Decimal]:
    return {d for d in (_to_decimal(m) for m in NUMBER.findall(text)) if d is not None}


def format_tool_result(tool_name: str | None, result: dict | None) -> str:
    """Tool output as plain labelled lines (no internal field names)."""
    if not tool_name or not result:
        return "(no tool was used)"
    if "error" in result:
        return f"TOOL ERROR: {result['error']}"
    lines = []
    for key, label in LABELS.items():
        value = result.get(key)
        if value in (None, [], ""):
            continue
        lines.append(f"{label}: {'; '.join(value) if isinstance(value, list) else value}")
    if result.get("assumptions"):
        lines.append("Rule assumptions: " + " | ".join(result["assumptions"].values()))
    return "\n".join(lines)


def assumptions_line(defaults: dict | None, hinglish: bool) -> str:
    """Deterministic sentence listing the details we assumed (written by code, not the LLM)."""
    if not defaults:
        return ""
    phrases = [DEFAULT_PHRASES.get((k, v), (f"{k} = {v}", f"{k} = {v}"))[1 if hinglish else 0]
               for k, v in defaults.items()]
    if hinglish:
        return "Maine maana hai (aapne nahi bataya): " + ", ".join(phrases) + ". Agar alag hai to bataiye."
    return "Assumed (you did not say): " + ", ".join(phrases) + ". Tell me if any of this is different."


# Only when the user's question itself relies on the 2015 cut-offs (48h/12h/"4 hours before")
OLD_RULE_Q = re.compile(
    r"\b(48|12)[\s-]*(hours?|hrs?|h|ghante)\b|\b4[\s-]*(hours?|hrs?|h|ghante)\s*(before|pehle)\b|48\s*/\s*12", re.I)
STALE_NOTE = ("\n\nThe question assumes an OLD rule (48, 12 or 4 hours as cancellation cut-offs). "
              "First say clearly that this rule was replaced, then answer with the current rule. "
              "Never repeat the user's old cut-off as if it were a rule.")


def mentions_old_rule(question: str) -> bool:
    return bool(OLD_RULE_Q.search(question))


# ----------------------------------------------------------------- nodes
def generate_node(state: dict) -> dict:
    c = state["classification"]
    language = "Hinglish (Hindi in Roman letters)" if c.language == "hinglish" else "English"
    tool_text = format_tool_result(state.get("tool_name"), state.get("tool_result"))
    user = (f"TOOL RESULT:\n{tool_text}\n\nSOURCES:\n\n{format_sources(state['chunks'])}"
            f"\n\nQUESTION: {state['question']}")
    system = SYSTEM_PROMPT.format(language=language)
    if mentions_old_rule(state["question"]):
        system += STALE_NOTE
    text = call_llm([SystemMessage(content=system), HumanMessage(content=user)])
    text = TOOL_TAG.sub("", text)        # defensive: drop "[TOOL RESULT]"-style tags if the LLM adds them
    return {"answer": text, "llm_calls": state["llm_calls"] + 1, "path": state["path"] + ["generate"]}


def self_check(state: dict) -> list[str]:
    """Return a list of problems (empty list = pass). Pure code, no LLM."""
    answer = state.get("answer") or ""
    problems = []
    if not answer.strip():
        return ["empty answer"]

    _, invalid = build_citations(answer, state.get("chunks", []))
    if invalid:
        problems.append(f"invalid citations: {invalid}")

    # Every Rs amount must come from the tool result, the question, or a retrieved chunk.
    tool = state.get("tool_result") or {}
    allowed = (_numbers_in(str(tool)) | _numbers_in(state["question"])
               | set().union(*(_numbers_in(ch["text"]) for ch in state.get("chunks", [])))
               | set().union(*(_numbers_in(h["content"]) for h in state.get("history", []))))
    for m in MONEY.finditer(answer):
        amount = _to_decimal(m.group(1) or m.group(2))
        if amount is not None and amount not in allowed:
            problems.append(f"amount not from any source: {m.group(0).strip()}")

    if state.get("tool_name") == "calculate_refund" and "refund_total" in tool:
        if Decimal(tool["refund_total"]) not in _numbers_in(answer):
            problems.append(f"refund total {tool['refund_total']} missing from answer")
    return problems


def self_check_node(state: dict) -> dict:
    return {"check_problems": self_check(state), "path": state["path"] + ["self_check"]}


def fallback_node(state: dict) -> dict:
    """Safe answer built only from the tool output (no LLM)."""
    hinglish = state["classification"].language == "hinglish"
    r, name = state.get("tool_result") or {}, state.get("tool_name")
    if name == "calculate_refund" and "refund_total" in r:
        lines = [f"Estimated refund: Rs {r['refund_total']} (deduction Rs {r['deduction_total']}).",
                 f"Rule applied: {r['rule']}."]
        lines += r.get("notes", [])
    elif name == "check_tdr_eligibility" and "rule_id" in r:
        lines = [f"TDR needed: {r['tdr_needed']}.", f"Refund: {r['refund']}"]
        if r.get("deadline"):
            lines.append(f"Deadline: {r['deadline']}")
        if r.get("documents"):
            lines.append("Documents: " + "; ".join(r["documents"]))
        lines += r.get("how_to_file", []) + r.get("notes", [])
    else:
        lines = ["Main official rules ke basis par pakka nahi bata sakta. Kripya IRCTC check karein ya 139 par call karein."
                 if hinglish else
                 "I'm not sure based on the official rules I have. Please check IRCTC or call 139."]
    return {"answer": "\n".join(lines), "fallback_used": True, "path": state["path"] + ["fallback"]}


def renumber_citations(answer: str, cited: list[dict]) -> str:
    """Make citation numbers match the order of the sources list: if only [2] and [4] are
    cited, they become [1] and [2]. So "[1]" in the answer = first source shown in the UI."""
    mapping = {c["n"]: i for i, c in enumerate(cited, start=1)}
    return re.sub(r"\[(\d+)\]", lambda m: f"[{mapping.get(int(m.group(1)), m.group(1))}]", answer)


def finalize_node(state: dict) -> dict:
    """Attach sources (cited chunks + the tool's own source chunks) and the disclaimer."""
    answer = state.get("answer", "")
    cited, _ = build_citations(answer, state.get("chunks", []))
    answer = renumber_citations(answer, cited)
    all_chunks = load_chunks()
    tool_ids = (state.get("tool_result") or {}).get("sources", [])
    seen, sources = set(), []
    for ch in cited + [all_chunks[i] for i in tool_ids if i in all_chunks]:
        if ch["chunk_id"] in seen:
            continue
        seen.add(ch["chunk_id"])
        sources.append({k: ch[k] for k in ("chunk_id", "title", "section", "pages", "effective_from",
                                           "source_url", "status", "note")})
    if state.get("tool_result") and "error" not in state["tool_result"]:
        line = assumptions_line(state.get("defaults_used"), state["classification"].language == "hinglish")
        if line:
            answer = f"{answer.rstrip()}\n\n{line}"
    return {"answer": answer, "sources": sources, "disclaimer": DISCLAIMER.format(date=RULES_LAST_VERIFIED),
            "fallback_used": state.get("fallback_used", False), "path": state["path"] + ["finalize"]}