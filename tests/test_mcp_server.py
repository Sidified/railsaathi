"""MCP server: the tools are registered and return the same results as the plain functions.
No LLM calls, no network."""
import asyncio
import json

import pytest

from src.mcp_server import mcp


def call(name: str, args: dict):
    result = asyncio.run(mcp.call_tool(name, args))
    assert not result.is_error, result
    return json.loads(result.content[0].text)


def test_tools_are_listed():
    names = {t.name for t in asyncio.run(mcp.list_tools())}
    assert names == {"calculate_refund_tool", "check_tdr", "search_rules"}


def test_refund_tool_matches_calculator():
    out = call("calculate_refund_tool", {"travel_class": "3A", "fare_per_passenger": 1850,
                                         "hours_before_departure": 20})
    assert out["refund_total"] == "925.00" and out["rule_id"] == "R7"


def test_tdr_tool():
    out = call("check_tdr", {"situation": "ac_failure"})
    assert out["rule_id"] == "T3" and out["tdr_needed"] == "yes"


def test_bad_input_is_rejected():
    with pytest.raises(Exception):      # an invalid class never reaches the calculator
        asyncio.run(mcp.call_tool("calculate_refund_tool", {"travel_class": "XYZ",
                                  "fare_per_passenger": 100, "hours_before_departure": 5}))