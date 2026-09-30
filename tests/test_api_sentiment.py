"""``GET /api/sentiment/fear-greed``: contract, errors, staleness and the no-network guarantees."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
import requests
from fastapi.testclient import TestClient

from tradingview_data.api import create_app
from tradingview_data.sentiment import FearGreedService, SentimentUnavailable, band_for

DAY = 86_400


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("test attempted a real network request")

    monkeypatch.setattr(requests, "get", refuse)
    monkeypatch.setattr(requests.Session, "request", refuse)


def utc(year, month, day):
    return int(datetime(year, month, day, tzinfo=timezone.utc).timestamp())


def payload(scores, start=utc(2026, 1, 1)):
    rows = [
        {"score": s, "name": band_for(s).label, "timestamp": str(start + i * DAY), "btcPrice": f"{100 + i}.5", "btcVolume": "1000"}
        for i, s in enumerate(scores)
    ]
    return {"data": {"dataList": rows}, "status": {"error_code": "0", "error_message": "SUCCESS"}}


class Script:
    def __init__(self, *steps):
        self.steps, self.calls = list(steps), 0

    def __call__(self):
        item = self.steps[min(self.calls, len(self.steps) - 1)]
        self.calls += 1
        if isinstance(item, Exception):
            raise item
        return item


class Clock:
    now = 10_000.0

    def __call__(self):
        return self.now


def client(tmp_path, *steps, clock=None):
    service = FearGreedService(Script(*steps), clock=clock or Clock(), ttl_seconds=600, retry_seconds=60)
    return TestClient(create_app(tmp_path, fear_greed=service)), service


def test_returns_the_documented_contract(tmp_path):
    api, _ = client(tmp_path, payload(list(range(10, 70))))
    body = api.get("/api/sentiment/fear-greed").json()
    assert set(body) == {"source", "fetched_at", "stale", "stale_reason", "bands", "current", "snapshots", "points", "total_points"}
    assert body["current"]["score"] == 69 and body["current"]["band"] == "greed"
    assert body["stale"] is False and body["stale_reason"] is None
    assert body["total_points"] == len(body["points"]["time"]) == 60
    assert set(body["snapshots"]) == {"yesterday", "week_ago", "month_ago", "year_high", "year_low"}
    assert body["snapshots"]["yesterday"]["score"] == 68
    assert body["source"]["documented"] is False
    assert body["points"]["btc_price"][0] == 100.5


def test_days_limits_the_history_and_validates(tmp_path):
    api, _ = client(tmp_path, payload(list(range(10, 70))))
    assert len(api.get("/api/sentiment/fear-greed?days=7").json()["points"]["time"]) == 8
    assert api.get("/api/sentiment/fear-greed?days=7").json()["total_points"] == 60
    for bad in ("0", "-1", "3651", "abc", "nan"):
        response = api.get(f"/api/sentiment/fear-greed?days={bad}")
        assert response.status_code == 422, bad
        assert isinstance(response.json()["detail"], list)


def test_a_failure_with_nothing_cached_is_a_502_with_a_readable_message_and_no_data(tmp_path):
    api, _ = client(tmp_path, SentimentUnavailable("CoinMarketCap did not respond in time."))
    response = api.get("/api/sentiment/fear-greed")
    assert response.status_code == 502
    assert response.json() == {"detail": "CoinMarketCap did not respond in time."}
    assert "points" not in response.text and "score" not in response.text  # never a substitute reading


def test_upstream_error_bodies_delivered_with_http_200_become_a_502(tmp_path):
    busy = {"status": {"error_code": "500", "error_message": "The system is busy, please try again later!"}}
    response = client(tmp_path, busy)[0].get("/api/sentiment/fear-greed")
    assert response.status_code == 502
    assert "system is busy" in response.json()["detail"]


def test_a_failed_refresh_serves_the_last_good_readings_flagged_stale(tmp_path):
    clock = Clock()
    api, _ = client(tmp_path, payload([40, 50, 60]), SentimentUnavailable("Could not reach CoinMarketCap (network error)."), clock=clock)
    fresh = api.get("/api/sentiment/fear-greed").json()
    assert fresh["stale"] is False
    clock.now += 700
    stale = api.get("/api/sentiment/fear-greed")
    assert stale.status_code == 200
    body = stale.json()
    assert body["stale"] is True and "network error" in body["stale_reason"]
    assert body["current"] == fresh["current"] and body["fetched_at"] == fresh["fetched_at"]


def test_repeated_requests_reach_upstream_once_per_ttl(tmp_path):
    api, service = client(tmp_path, payload([40, 50, 60]))
    for _ in range(5):
        assert api.get("/api/sentiment/fear-greed").status_code == 200
    assert service._fetch.calls == 1


def test_creating_the_app_never_touches_the_network(tmp_path):
    # The autouse guard fails the test if the default service fetched during construction.
    create_app(tmp_path)


def test_the_default_service_reads_coinmarketcap_on_first_request_only(tmp_path, monkeypatch):
    seen = []

    class Response:
        status_code = 200
        content = b"{}"

        def json(self):
            return payload([30, 45, 55])

    def fake_get(url, **kwargs):
        seen.append((url, kwargs["headers"]["User-Agent"]))
        return Response()

    monkeypatch.setattr(requests, "get", fake_get)
    api = TestClient(create_app(tmp_path))
    assert seen == []
    assert api.get("/api/sentiment/fear-greed").json()["current"]["score"] == 55
    assert len(seen) == 1 and seen[0][0].startswith("https://api.coinmarketcap.com/")
    api.get("/api/sentiment/fear-greed")
    assert len(seen) == 1


def test_works_without_any_captures_and_does_not_disturb_other_routes(tmp_path):
    api, _ = client(tmp_path, payload([50, 50]))
    assert api.get("/api/datasets").json() == {"datasets": []}
    assert api.get("/api/sentiment/fear-greed").status_code == 200
    assert api.get("/api/health").json()["dataset_count"] == 0


def test_the_route_is_get_only_and_documented(tmp_path):
    api, _ = client(tmp_path, payload([50, 50]))
    assert api.post("/api/sentiment/fear-greed").status_code == 405
    assert "/api/sentiment/fear-greed" in api.get("/api/openapi.json").json()["paths"]
