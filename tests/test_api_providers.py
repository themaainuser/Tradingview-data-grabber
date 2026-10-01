"""The /api/providers routes, with a second fake provider proving the framework is generic."""

from __future__ import annotations

import json
from typing import Any

import pytest
import requests
from fastapi.testclient import TestClient

from tradingview_data.api import create_app
from tradingview_data.providers.alphavantage import AlphaVantage
from tradingview_data.providers.marketstack import Marketstack
from tradingview_data.providers.base import Provider, ProviderInfo, ProviderRegistry

from marketstack_support import SAMPLES, error
from providers_support import DAILY, KEY, PLACEHOLDER, FakeHttp, ok
from tradingview_data.providers.common import HttpResult


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("test attempted a real network request")

    monkeypatch.setattr(requests, "get", refuse)
    monkeypatch.setattr(requests.Session, "request", refuse)


class FakeProvider(Provider):
    info = ProviderInfo("fake", "Fake Data", "A test provider.", "https://fake.test/", "https://fake.test/docs", "FAKE_API_KEY", None, "No limits.")

    def __init__(self) -> None:
        self.queries: list[tuple[str, dict, bool]] = []

    def configured(self) -> bool:
        import os

        return bool(os.environ.get("FAKE_API_KEY"))

    def catalog(self) -> dict[str, Any]:
        endpoint = {"id": "THING", "title": "Thing", "category": "all", "description": "A thing.", "summary": "A thing.", "premium": True, "trending": False, "utility": False, "premium_notes": [], "doc_url": "https://fake.test/docs#thing", "params": [], "examples": []}
        return {"categories": [{"id": "all", "title": "All", "summary": "", "count": 1, "premium_count": 1}], "endpoints": [endpoint]}

    def query(self, endpoint_id: str, params: Any, refresh: bool = False) -> dict[str, Any]:
        if endpoint_id != "THING":
            raise KeyError(endpoint_id)
        self.queries.append((endpoint_id, dict(params), refresh))
        return {"provider": "fake", "endpoint": "THING", "title": "Thing", "status": "ok", "message": None, "cached": False, "fetched_at": 1, "elapsed_ms": 0, "bytes": 0, "params": dict(params), "views": [], "raw": None, "raw_omitted": None, "notes": []}


def client(tmp_path, *providers: Provider) -> TestClient:
    registry = ProviderRegistry()
    for p in providers:
        registry.register(p)
    return TestClient(create_app(tmp_path, providers=registry))


@pytest.fixture
def keyed(monkeypatch):
    monkeypatch.setenv("ALPHAVANTAGE_API_KEY", KEY)


def test_creating_the_app_never_touches_the_network(tmp_path):
    create_app(tmp_path)  # the autouse guard fails the test if anything fetched


def test_the_provider_list_reports_counts_and_whether_a_key_is_set_but_never_the_key(tmp_path, monkeypatch, keyed):
    api = client(tmp_path, AlphaVantage(http_get=FakeHttp()))
    (provider,) = api.get("/api/providers").json()["providers"]
    assert provider["id"] == "alphavantage" and provider["endpoint_count"] == 128 and provider["premium_count"] == 11
    assert provider["configured"] is True and provider["key_env"] == "ALPHAVANTAGE_API_KEY" and provider["requests_this_session"] == 0
    assert KEY not in api.get("/api/providers").text
    monkeypatch.delenv("ALPHAVANTAGE_API_KEY")
    assert api.get("/api/providers").json()["providers"][0]["configured"] is False


def test_the_default_registry_serves_alpha_vantage_then_marketstack(tmp_path):
    listed = TestClient(create_app(tmp_path)).get("/api/providers").json()["providers"]
    assert [p["id"] for p in listed] == ["alphavantage", "marketstack"]
    assert [p["key_env"] for p in listed] == ["ALPHAVANTAGE_API_KEY", "MARKETSTACK_API_KEY"]
    assert [p["plans"] for p in listed][0] == [] and [x["name"] for x in listed[1]["plans"]] == ["Free", "Basic", "Professional", "Business"]


def test_two_providers_are_listed_in_order_each_with_its_own_catalog_and_key(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_API_KEY", "abc")
    monkeypatch.delenv("ALPHAVANTAGE_API_KEY", raising=False)
    api = client(tmp_path, AlphaVantage(http_get=FakeHttp()), FakeProvider())
    listed = api.get("/api/providers").json()["providers"]
    assert [(p["id"], p["configured"], p["key_env"]) for p in listed] == [("alphavantage", False, "ALPHAVANTAGE_API_KEY"), ("fake", True, "FAKE_API_KEY")]
    fake = api.get("/api/providers/fake/catalog").json()
    assert [e["id"] for e in fake["endpoints"]] == ["THING"] and fake["provider"]["id"] == "fake"
    assert len(api.get("/api/providers/alphavantage/catalog").json()["endpoints"]) == 128


def test_querying_one_provider_never_touches_the_other(tmp_path, keyed):
    http, fake = FakeHttp(ok(DAILY)), FakeProvider()
    api = client(tmp_path, AlphaVantage(http_get=http), fake)
    api.post("/api/providers/fake/query", json={"endpoint": "THING", "params": {"a": "1"}})
    assert http.calls == [] and fake.queries == [("THING", {"a": "1"}, False)]
    api.post("/api/providers/alphavantage/query", json={"endpoint": "TIME_SERIES_DAILY", "params": {"symbol": "IBM"}})
    assert len(http.calls) == 1 and len(fake.queries) == 1


def test_the_catalog_has_the_contract_shape(tmp_path):
    body = client(tmp_path, AlphaVantage(http_get=FakeHttp())).get("/api/providers/alphavantage/catalog").json()
    assert set(body) == {"provider", "categories", "endpoints"}
    endpoint = next(e for e in body["endpoints"] if e["id"] == "TIME_SERIES_INTRADAY")
    assert set(endpoint) == {"id", "title", "category", "description", "summary", "premium", "trending", "utility", "premium_notes", "plan", "request_cost", "doc_url", "params", "examples"}
    assert endpoint["premium"] is True and endpoint["plan"] is None and endpoint["request_cost"] == 1
    assert set(endpoint["params"][0]) == {"name", "required", "type", "description", "enum", "enum_labels", "suggestions", "default", "example", "multiple", "premium_note", "minimum", "maximum", "premium_values", "managed"}


def test_a_query_returns_the_contract_response(tmp_path, keyed):
    api = client(tmp_path, AlphaVantage(http_get=FakeHttp(ok(DAILY))))
    body = api.post("/api/providers/alphavantage/query", json={"endpoint": "TIME_SERIES_DAILY", "params": {"symbol": "IBM"}}).json()
    assert set(body) == {"provider", "endpoint", "title", "status", "message", "cached", "fetched_at", "elapsed_ms", "bytes", "params", "views", "raw", "raw_omitted", "notes"}
    assert body["status"] == "ok" and [v["kind"] for v in body["views"]] == ["facts", "series", "table"] and KEY not in json.dumps(body)


def test_provider_side_problems_are_http_200_with_a_status(tmp_path, keyed):
    for payload, status in ((PLACEHOLDER, "premium_required"), ({"Information": "Our standard API rate limit is 25 requests per day."}, "rate_limited")):
        response = client(tmp_path, AlphaVantage(http_get=FakeHttp(ok(payload)))).post("/api/providers/alphavantage/query", json={"endpoint": "TIME_SERIES_DAILY", "params": {"symbol": "IBM"}})
        assert response.status_code == 200 and response.json()["status"] == status and response.json()["views"] == []


def test_the_refresh_flag_is_passed_through(tmp_path):
    fake = FakeProvider()
    client(tmp_path, fake).post("/api/providers/fake/query", json={"endpoint": "THING", "refresh": True})
    assert fake.queries == [("THING", {}, True)]


@pytest.mark.parametrize(
    ("method", "path", "body", "status"),
    [
        ("get", "/api/providers/nope/catalog", None, 404),
        ("post", "/api/providers/nope/query", {"endpoint": "X"}, 404),
        ("post", "/api/providers/alphavantage/query", {"endpoint": "NOT_A_FUNCTION"}, 404),
        ("post", "/api/providers/alphavantage/query", {"endpoint": "TIME_SERIES_DAILY", "params": {}}, 422),
        ("post", "/api/providers/alphavantage/query", {"endpoint": "TIME_SERIES_DAILY", "params": {"symbol": "IBM", "apikey": "x"}}, 422),
        ("post", "/api/providers/alphavantage/query", {"endpoint": "TIME_SERIES_DAILY", "params": {"symbol": 5}}, 422),
        ("post", "/api/providers/alphavantage/query", {"params": {}}, 422),
        ("post", "/api/providers/alphavantage/query", {"endpoint": ""}, 422),
        ("get", "/api/providers/..%2F..%2Fetc/catalog", None, 404),
    ],
)
def test_errors(tmp_path, method, path, body, status):
    api = client(tmp_path, AlphaVantage(http_get=FakeHttp()))
    response = getattr(api, method)(path, **({"json": body} if body is not None else {}))
    assert response.status_code == status


def test_a_validation_failure_explains_itself_in_plain_text(tmp_path):
    api = client(tmp_path, AlphaVantage(http_get=FakeHttp()))
    detail = api.post("/api/providers/alphavantage/query", json={"endpoint": "TIME_SERIES_DAILY", "params": {"symbol": "IBM", "outputsize": "huge"}}).json()["detail"]
    assert isinstance(detail, str) and "outputsize must be one of" in detail


def test_no_key_means_not_configured_over_http_without_any_request(tmp_path, monkeypatch):
    monkeypatch.delenv("ALPHAVANTAGE_API_KEY", raising=False)
    http = FakeHttp(ok(DAILY))
    body = client(tmp_path, AlphaVantage(http_get=http)).post("/api/providers/alphavantage/query", json={"endpoint": "TIME_SERIES_DAILY", "params": {"symbol": "IBM"}}).json()
    assert body["status"] == "not_configured" and http.calls == [] and body["views"] == []


def test_the_openapi_schema_lists_the_provider_routes(tmp_path):
    paths = client(tmp_path, FakeProvider()).get("/api/openapi.json").json()["paths"]
    assert {"/api/providers", "/api/providers/{provider_id}/catalog", "/api/providers/{provider_id}/query"} <= set(paths)


def test_registering_the_same_provider_twice_is_an_error():
    registry = ProviderRegistry()
    registry.register(FakeProvider())
    with pytest.raises(ValueError, match="already registered"):
        registry.register(FakeProvider())


# --- Marketstack ---------------------------------------------------------------------------------------


@pytest.fixture
def ms_keyed(monkeypatch):
    monkeypatch.setenv("MARKETSTACK_API_KEY", KEY)


def test_marketstack_serves_its_catalog_with_plans_and_premium_endpoints(tmp_path, ms_keyed):
    body = client(tmp_path, Marketstack(http_get=FakeHttp())).get("/api/providers/marketstack/catalog").json()
    assert set(body) == {"provider", "categories", "endpoints"}
    assert body["provider"]["endpoint_count"] == 46 and body["provider"]["premium_count"] == 26 and body["provider"]["configured"] is True
    assert [p["name"] for p in body["provider"]["plans"]] == ["Free", "Basic", "Professional", "Business"]
    endpoints = {e["id"]: e for e in body["endpoints"]}
    assert (endpoints["eod"]["plan"], endpoints["eod"]["premium"]) == ("Free", False)
    assert (endpoints["intraday"]["plan"], endpoints["intraday"]["premium"]) == ("Basic", True)
    assert (endpoints["commodities"]["plan"], endpoints["companyratings"]["plan"]) == ("Professional", "Business")
    assert KEY not in json.dumps(body)


def test_a_marketstack_query_returns_the_contract_response_and_never_the_key(tmp_path, ms_keyed):
    http = FakeHttp(ok(SAMPLES["ticker_eod"]))
    api = client(tmp_path, Marketstack(http_get=http))
    body = api.post("/api/providers/marketstack/query", json={"endpoint": "ticker_eod", "params": {"symbol": "AAPL", "limit": "3"}}).json()
    assert set(body) == {"provider", "endpoint", "title", "status", "message", "cached", "fetched_at", "elapsed_ms", "bytes", "params", "views", "raw", "raw_omitted", "notes"}
    assert body["status"] == "ok" and "series" in [v["kind"] for v in body["views"]] and KEY not in json.dumps(body)
    assert http.calls[0][0] == "https://api.marketstack.com/v2/tickers/AAPL/eod"


def test_marketstack_provider_side_problems_are_http_200_with_a_status(tmp_path, ms_keyed):
    refusal = HttpResult(403, json.dumps(error("function_access_restricted", 105, "Your plan does not support this API Function.")).encode(), "application/json")
    response = client(tmp_path, Marketstack(http_get=FakeHttp(refusal))).post("/api/providers/marketstack/query", json={"endpoint": "commodities", "params": {"commodity_name": "gold"}})
    assert response.status_code == 200 and response.json()["status"] == "premium_required" and response.json()["views"] == []


@pytest.mark.parametrize(
    ("body", "status"),
    [
        ({"endpoint": "nope"}, 404),
        ({"endpoint": "eod", "params": {}}, 422),
        ({"endpoint": "eod", "params": {"symbols": "AAPL", "access_key": "x"}}, 422),
        ({"endpoint": "eod", "params": {"symbols": "AAPL", "limit": "5000"}}, 422),
        ({"endpoint": "exchange_tickers", "params": {"mic": "../etc"}}, 422),
    ],
)
def test_marketstack_errors(tmp_path, body, status):
    api = client(tmp_path, Marketstack(http_get=FakeHttp()))
    assert api.post("/api/providers/marketstack/query", json=body).status_code == status
