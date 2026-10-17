"""Step 3c: Basic RAG answer with citations (no agent yet).

question -> hybrid_search (top 5) -> ONE Gemini call -> answer with [n] markers
-> the "Sources" list is built in CODE from the chunk metadata (the LLM never writes URLs).

Usage:  python -m src.rag.answer "Can I change my boarding station?"
LLM calls: 1 per question
"""
import os
import re
import sys
import time

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from src.retrieval.search import hybrid_search

load_dotenv()
TOP_K = 5

SYSTEM_PROMPT = """You are RailSaathi, an UNOFFICIAL assistant that explains Indian Railways
passenger rules (cancellation, refunds, TDR, Tatkal, waitlist/RAC, charting, boarding change,
upgrades, luggage). You are not affiliated with Indian Railways or IRCTC.

Rules you must follow:
1. Use ONLY the numbered sources given. Never use outside knowledge.
2. After every factual sentence, cite its source like [1] or [2][3].
3. Some sources are marked OUTDATED IN PART with a note. Follow the note: the newer rule wins.
   Never present an old time limit (like 48/12/4 hours) as the current rule.
4. Do NOT do arithmetic or calculate refund amounts. You may quote percentages and fixed
   charges exactly as written in the sources. If the user wants an exact amount, say an exact
   calculation needs their fare, class and timing (a calculator is coming).
5. If the sources do not answer the question, say "I'm not sure based on the official rules I
   have" and suggest checking IRCTC or calling 139. Do not guess.
6. If the question is not about Indian Railways passenger rules, politely say you only help
   with railway ticket rules. Do not cite any source in that case.
7. Answer in the SAME language as the question. English question -> English answer.
   Only if the question itself is written in Hinglish (Hindi in Roman letters), answer in
   Hinglish. Use simple words. Keep it under 150 words."""


def get_llm() -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(model=os.environ["GEMINI_MODEL"])


def format_sources(chunks: list[dict]) -> str:
    blocks = []
    for i, c in enumerate(chunks, start=1):
        flags = [f"effective from {c['effective_from']}"]
        if c["applies_to"] != "all_trains":
            flags.append(f"applies only to: {c['applies_to']}")
        if c["status"] == "partly_superseded":
            flags.append(f"OUTDATED IN PART - note: {c['note']}")
        if c["authority"] == "secondary":
            flags.append("secondary source (railway training notes, not an official rule document)")
        blocks.append(f"[{i}] ({'; '.join(flags)})\n{c['text']}")
    return "\n\n".join(blocks)


def build_citations(answer: str, chunks: list[dict]) -> tuple[list[dict], list[str]]:
    """Return (cited chunks in order, invalid tags like [9] or [RailSaathi])."""
    tags = re.findall(r"\[([^\[\]]+)\]", answer)
    numbers, invalid = set(), []
    for tag in tags:
        if tag.isdigit() and 1 <= int(tag) <= len(chunks):
            numbers.add(int(tag))
        else:
            invalid.append(tag)
    return [{"n": n, **chunks[n - 1]} for n in sorted(numbers)], invalid


def answer(question: str) -> dict:
    t0 = time.perf_counter()
    chunks = hybrid_search(question, k=TOP_K)
    t_retrieval = time.perf_counter() - t0

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=f"SOURCES:\n\n{format_sources(chunks)}\n\nQUESTION: {question}"),
    ]
    t1 = time.perf_counter()
    response = get_llm().invoke(messages)
    t_llm = time.perf_counter() - t1

    text = response.text
    citations, invalid = build_citations(text, chunks)
    usage = response.usage_metadata or {}
    return {
        "question": question,
        "answer": text,
        "citations": citations,
        "invalid_citations": invalid,
        "retrieved": [c["chunk_id"] for c in chunks],
        "latency_s": {"retrieval": round(t_retrieval, 2), "llm": round(t_llm, 2)},
        "tokens": {"input": usage.get("input_tokens"), "output": usage.get("output_tokens")},
        "llm_calls": 1,
    }


def print_result(r: dict) -> None:
    print(f"\nQ: {r['question']}\n\n{r['answer']}\n\nSources:")
    for c in r["citations"]:
        pages = f", p. {c['pages'][0]}" if len(c["pages"]) == 1 else f", pp. {c['pages'][0]}-{c['pages'][-1]}"
        print(f"  [{c['n']}] {c['title']}{pages} (effective {c['effective_from']})\n       {c['source_url']}")
    if r["invalid_citations"]:
        print(f"  WARNING: answer cites sources that do not exist: {r['invalid_citations']}")
    print(f"\nretrieved: {r['retrieved']}")
    print(f"latency: {r['latency_s']} | tokens: {r['tokens']} | LLM calls: {r['llm_calls']}")


if __name__ == "__main__":
    print_result(answer(" ".join(sys.argv[1:]) or "Can I change my boarding station?"))