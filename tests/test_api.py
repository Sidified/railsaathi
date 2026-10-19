"""API tests with both LLM calls faked (no API calls)."""
import pytest
from fastapi.testclient import TestClient

from src.agent import answer as answer_module
from src.agent import classify as classify_module
from src.agent.classify import Classification, TicketDetails
from src.api import main


@pytest.fixture
def client(monkeypatch):
    result = Classification(intent="refund_calc", language="en", search_query="refund 3A",
                            ticket=TicketDetails(travel_class="3A", fare_per_passenger=1850,
                                                 hours_before_departure=20))
    monkeypatch.setattr(classify_module, "classify", lambda q, h=None: result)
    monkeypatch.setattr(answer_module, "call_llm", lambda m: "You will get Rs 925.00 back [1].")
    main.limiter.reset()
    main.daily_cap.count = 0
    with TestClient(main.app) as c:
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok" and r.json()["chunks"] == 69


def test_chat_happy_path(client):
    r = client.post("/chat", json={"message": "3A Rs 1850, 20 hours before, refund?"})
    assert r.status_code == 200
    body = r.json()
    assert "925.00" in body["answer"]
    assert body["intent"] == "refund_calc" and body["llm_calls"] == 2
    assert body["sources"] and "Unofficial" in body["disclaimer"]
    assert "chunk_id" not in body["sources"][0]          # internal ids are not exposed


@pytest.mark.parametrize("payload", [
    {"message": ""},                                     # empty
    {"message": "x" * 501},                              # too long
    {"message": "hi", "history": [{"role": "user", "content": "a"}] * 5},   # > 4 turns
    {"message": "hi", "history": [{"role": "system", "content": "a"}]},     # bad role
])
def test_invalid_requests_are_rejected(client, payload):
    assert client.post("/chat", json=payload).status_code == 422


def test_per_ip_rate_limit(client):
    codes = [client.post("/chat", json={"message": "refund?"}).status_code for _ in range(6)]
    assert codes[:5] == [200] * 5 and codes[5] == 429


def test_daily_cap(client):
    main.daily_cap.count = main.daily_cap.limit
    r = client.post("/chat", json={"message": "refund?"})
    assert r.status_code == 503 and "daily limit" in r.json()["detail"]


def test_gemini_quota_error_becomes_friendly_503(client, monkeypatch):
    def boom(q, h=None):
        raise RuntimeError("429 RESOURCE_EXHAUSTED: quota exceeded")
    monkeypatch.setattr(classify_module, "classify", boom)
    r = client.post("/chat", json={"message": "refund?"})
    assert r.status_code == 503 and "busy" in r.json()["detail"]