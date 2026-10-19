"""Agent node 1: classify the question (LLM call 1).

Returns structured data (Pydantic), never free text:
  intent, language, an English search query, and any ticket details / TDR situation.
It only EXTRACTS what the user said. It never guesses missing details and never does math
beyond converting days to hours.
LLM calls: 1
"""
import os
from typing import Literal

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

from src.tools.refund_calculator import Quota, TicketStatus, TrainType, TravelClass
from src.tools.tdr_eligibility import BookingType, Situation

load_dotenv()

Intent = Literal["rule_question", "refund_calc", "tdr", "out_of_scope"]


class TicketDetails(BaseModel):
    """Only fields the user actually gave. Everything else stays null."""
    train_type: TrainType | None = Field(None, description="'vb_sleeper_amrit_bharat_2' ONLY if the user says Vande Bharat Sleeper or Amrit Bharat")
    travel_class: TravelClass | None = Field(None, description="1A, EC, 2A, FC, 3A, 3E, CC, SL or 2S. 'sleeper'->SL, '3AC'/'third AC'->3A, 'chair car'->CC")
    quota: Quota | None = Field(None, description="'tatkal' only if the user says Tatkal")
    ticket_status: TicketStatus | None = Field(None, description="confirmed / rac / waitlisted / partially_confirmed. 'WL 38' or 'waiting' -> waitlisted")
    fare_per_passenger: float | None = Field(None, description="Rupees per passenger. If only a total for several passengers is given, divide by passengers")
    passengers: int | None = None
    hours_before_departure: float | None = Field(None, description="Only if given as a duration ('20 hours', '2 days' = 48). If the user gives clock times or dates, leave null")
    train_cancelled: bool | None = Field(None, description="true only if Railways cancelled the train")


class Classification(BaseModel):
    intent: Intent = Field(description=(
        "refund_calc: user wants to know how much money they get back / lose, or whether to cancel. "
        "tdr: something went wrong on the railway side (train late, AC failure, diverted, lower class, "
        "missed connection) or user asks about TDR. "
        "rule_question: any other Indian Railways passenger rule (Tatkal, boarding change, upgrade, "
        "charting, luggage, ID proof, booking period, waitlist/RAC rules). "
        "out_of_scope: anything else, including live PNR status, train timings, booking a ticket."))
    language: Literal["en", "hinglish"] = Field(description="hinglish if the user writes Hindi in Roman letters")
    search_query: str = Field(description="A short, standalone ENGLISH search query for the rules, using words from official rules (e.g. 'RAC ticket cancellation clerkage refund')")
    ticket: TicketDetails = Field(default_factory=TicketDetails)
    tdr_situation: Situation | None = Field(None, description="Only for intent=tdr, if the situation is clear")
    booking_type: BookingType | None = Field(None, description="e_ticket if booked online/IRCTC/app, counter_ticket if bought at station")


SYSTEM_PROMPT = """You classify questions for RailSaathi, an assistant for Indian Railways passenger rules.
Read the conversation (earlier turns give context, e.g. a fare mentioned before) and the latest question.
Extract ONLY what the user actually said. Never invent a fare, class, time or status.
Return the structured result."""


def get_llm() -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(model=os.environ["GEMINI_MODEL"])


def classify(question: str, history: list[dict] | None = None) -> Classification:
    """history: last few turns as [{"role": "user"|"assistant", "content": "..."}]."""
    convo = "\n".join(f"{t['role'].upper()}: {t['content']}" for t in (history or [])[-4:])
    prompt = f"CONVERSATION SO FAR:\n{convo or '(none)'}\n\nLATEST QUESTION: {question}"
    llm = get_llm().with_structured_output(Classification)
    return llm.invoke([SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=prompt)])