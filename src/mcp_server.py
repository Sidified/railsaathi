"""RailSaathi MCP server (Step 9).

Exposes RailSaathi's deterministic tools to any MCP client (Claude Desktop, Cursor, an agent...).
No LLM calls happen here: the refund and TDR tools are pure code, search is BM25 + vectors.

    python -m src.mcp_server        # runs over stdio
"""
from mcp.server.mcpserver import MCPServer

from src.retrieval.search import hybrid_search
from src.tools.refund_calculator import (Quota, RefundRequest, TicketStatus, TrainType, TravelClass,
                                         calculate_refund)
from src.tools.tdr_eligibility import BookingType, Situation, TDRRequest, check_tdr_eligibility

mcp = MCPServer(
    "railsaathi",
    instructions=("Indian Railways passenger rules (unofficial). Use calculate_refund for exact refund "
                  "amounts, check_tdr for TDR eligibility and deadlines, search_rules to find official "
                  "rule text with source links. Always cite the returned sources."),
)


@mcp.tool()
def calculate_refund_tool(travel_class: TravelClass, fare_per_passenger: float, hours_before_departure: float,
                          passengers: int = 1, quota: Quota = "general", ticket_status: TicketStatus = "confirmed",
                          train_type: TrainType = "normal", train_cancelled: bool = False) -> dict:
    """Exact refund for cancelling an Indian Railways e-ticket under the current (April 2026) rules.

    travel_class: 1A, EC, 2A, FC, 3A, 3E, CC, SL or 2S. fare_per_passenger excludes the IRCTC
    convenience fee. Returns refund_total, the rule applied, assumptions and source chunk ids.
    """
    result = calculate_refund(RefundRequest(
        travel_class=travel_class, fare_per_passenger=str(fare_per_passenger),
        hours_before_departure=hours_before_departure, passengers=passengers, quota=quota,
        ticket_status=ticket_status, train_type=train_type, train_cancelled=train_cancelled))
    return result.model_dump(mode="json")


@mcp.tool()
def check_tdr(situation: Situation, booking_type: BookingType = "e_ticket") -> dict:
    """TDR (Ticket Deposit Receipt) eligibility for a situation: train late 3h+ and not travelled,
    AC failure, diverted, terminated short, lower class, partial travel, missed connection, etc.
    Returns whether a TDR is needed, the expected refund, the deadline, documents and how to file."""
    return check_tdr_eligibility(TDRRequest(situation=situation, booking_type=booking_type)).model_dump(mode="json")


@mcp.tool()
def search_rules(query: str, k: int = 5) -> list[dict]:
    """Search the official rule documents (hybrid BM25 + vector search). Returns the top-k rule
    sections with title, section, pages, effective date, status (current / partly superseded),
    source URL and text."""
    keys = ("chunk_id", "title", "section", "pages", "effective_from", "status", "source_url", "text")
    return [{key: ch.get(key) for key in keys} for ch in hybrid_search(query, k=max(1, min(k, 10)))]


if __name__ == "__main__":
    mcp.run("stdio")