"""FastAPI backend for RailSaathi.

Endpoints
  POST /chat    question + last <=4 turns  ->  answer, sources, disclaimer, metadata
  GET  /health  liveness + basic info (no LLM call)

Protection for the Gemini free tier (500 requests/day):
  - per-IP rate limit (slowapi), default 5/minute and 40/day
  - global daily cap on answered questions (DAILY_QUESTION_CAP, default 200)
Privacy: questions are NOT logged; only intent, latency, LLM calls and fallback flag.
Run:  uvicorn src.api.main:app --reload
"""
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import date
from threading import Lock
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from src.agent.answer import RULES_LAST_VERIFIED
from src.agent.graph import run
from src.retrieval.search import get_bm25, load_chunks

load_dotenv()
log = logging.getLogger("railsaathi")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

RATE_LIMIT = os.getenv("RATE_LIMIT", "5/minute;40/day")
DAILY_QUESTION_CAP = int(os.getenv("DAILY_QUESTION_CAP", "200"))


# ----------------------------------------------------------------- schemas
class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=2000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=500)
    history: list[Turn] = Field(default_factory=list, max_length=4)


class Source(BaseModel):
    title: str
    section: str
    pages: list[int]
    effective_from: str
    source_url: str
    status: str
    note: str = ""


class ChatResponse(BaseModel):
    answer: str
    sources: list[Source]
    disclaimer: str
    intent: str
    language: str
    fallback_used: bool
    llm_calls: int
    latency_ms: int


# ----------------------------------------------------------------- daily cap
class DailyCap:
    """Counts answered questions per day across all users (in memory, one instance)."""
    def __init__(self, limit: int):
        self.limit, self.day, self.count, self.lock = limit, date.today(), 0, Lock()

    def take(self) -> bool:
        with self.lock:
            if date.today() != self.day:
                self.day, self.count = date.today(), 0
            if self.count >= self.limit:
                return False
            self.count += 1
            return True


daily_cap = DailyCap(DAILY_QUESTION_CAP)


# ----------------------------------------------------------------- app
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Warm up: load chunks, BM25 and the embedding model once, so the first user is not slow.
    load_chunks()
    get_bm25()
    from src.embeddings import get_model
    get_model()
    log.info("warm-up done: %d chunks loaded", len(load_chunks()))
    yield


limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="RailSaathi API", version="0.1.0", lifespan=lifespan)
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
def rate_limited(request: Request, exc: RateLimitExceeded):
    return JSONResponse(status_code=429, content={
        "detail": "Too many questions from you right now. Please wait a minute and try again."})


@app.get("/", include_in_schema=False)
def ui():
    return FileResponse("ui/index.html")


@app.get("/health")
def health():
    return {"status": "ok", "chunks": len(load_chunks()), "rules_last_verified": RULES_LAST_VERIFIED,
            "model": os.getenv("GEMINI_MODEL")}


@app.post("/chat", response_model=ChatResponse)
@limiter.limit(RATE_LIMIT)
def chat(request: Request, body: ChatRequest):
    if not daily_cap.take():
        raise HTTPException(status_code=503, detail=(
            "RailSaathi has reached its free daily limit. Please try again tomorrow."))
    t0 = time.perf_counter()
    try:
        state = run(body.message, [t.model_dump() for t in body.history])
    except Exception as e:                       # e.g. Gemini quota (429) or network error
        quota = "429" in str(e) or "quota" in str(e).lower() or "exhausted" in str(e).lower()
        log.error("chat failed: %s", type(e).__name__)
        raise HTTPException(status_code=503 if quota else 500, detail=(
            "The AI service is busy (free-tier limit). Please try again in a minute."
            if quota else "Something went wrong. Please try again."))
    latency_ms = int((time.perf_counter() - t0) * 1000)
    c = state["classification"]
    # Privacy: log only metadata, never the question text.
    log.info("chat intent=%s lang=%s llm_calls=%d fallback=%s latency_ms=%d",
             c.intent, c.language, state["llm_calls"], state.get("fallback_used", False), latency_ms)
    return ChatResponse(
        answer=state["answer"], sources=state.get("sources", []), disclaimer=state["disclaimer"],
        intent=c.intent, language=c.language, fallback_used=state.get("fallback_used", False),
        llm_calls=state["llm_calls"], latency_ms=latency_ms)