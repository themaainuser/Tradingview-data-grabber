"""Finnhub provider: the generated catalog and its plans, request building, error classification, key safety, caching."""

from __future__ import annotations

import json
import threading
from datetime import date, datetime, timedelta, timezone

import pytest
import requests

from tradingview_data.providers.common import HttpResult, validate_params
from tradingview_data.providers.finnhub import BASE_URL, CACHE_TTL_SECONDS, INFO, Finnhub, classify_error, has_data, is_blank_quote, is_finnhub_file
from tradingview_data.providers.finnhub_docs import PLANS

import finnhub_support as fx
from finnhub_support import FakeHttp
from providers_support import KEY, ok

# Measured with a free key in November 2026: these answered, every other endpoint was refused.
FREE = {
    "symbol_search", "stock_symbols", "market_status", "market_holiday", "company_profile2", "market_news", "company_news", "company_peers",
    "company_basic_financials", "insider_transactions", "insider_sentiment", "financials_reported", "filings", "ipo_calendar", "recommendation_trends",
    "company_earnings", "earnings_calendar", "quote", "forex_exchanges", "forex_symbols", "crypto_exchanges", "crypto_symbols", "covid_19",
    "fda_committee_meeting_calendar", "stock_uspto_patent", "stock_visa_application", "stock_lobbying", "stock_usa_spending", "country",
}


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("test attempted a real network request")

    monkeypatch.setattr(requests, "get", refuse)
    monkeypatch.setattr(requests.Session, "request", refuse)


@pytest.fixture
def keyed(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", KEY)


@pytest.fixture
def unkeyed(monkeypatch):
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)


def provider(*script, **kwargs):
    http = FakeHttp(*script)
    return Finnhub(http_get=http, **kwargs), http


def at(year, month, day):
    return lambda: datetime(year, month, day, 12, tzinfo=timezone.utc).timestamp()


def endpoints():
    return {e["id"]: e for e in Finnhub(http_get=FakeHttp()).catalog()["endpoints"]}


# --- the catalog and its plans ---------------------------------------------------------------------------


def test_every_endpoint_has_a_unique_id_a_known_category_and_a_plan_consistent_with_premium():
    pv = Finnhub(http_get=FakeHttp())
    catalog = pv.catalog()
    listed = {e["id"]: e for e in catalog["endpoints"]}
    assert len(listed) == len(catalog["endpoints"]) == 113
    assert [p.name for p in INFO.plans] == list(PLANS) == ["Free", "All-in-One"]
    assert {e["category"] for e in listed.values()} <= {c["id"] for c in catalog["categories"]}
    for endpoint in listed.values():
        assert endpoint["premium"] == (endpoint["plan"] != "Free")
        assert endpoint["plan"] in (*PLANS, None) and endpoint["request_cost"] == 1
        assert endpoint["doc_url"].startswith("https://finnhub.io/docs/api/")
    assert sum(c["count"] for c in catalog["categories"]) == len(listed)
    assert sum(c["premium_count"] for c in catalog["categories"]) == sum(e["premium"] for e in listed.values()) == 84


def test_the_free_endpoints_are_the_ones_a_free_key_was_measured_to_open():
    assert {i for i, e in endpoints().items() if not e["premium"]} == FREE


def test_endpoints_no_plan_includes_say_so_and_narrower_packages_are_noted():
    listed = endpoints()
    assert listed["transcripts"]["plan"] is None and "does not include earnings call transcripts" in listed["transcripts"]["premium_notes"][0]
    assert listed["newsroom"]["plan"] is None and listed["international_filings"]["plan"] is None
    assert listed["stock_candles"]["plan"] == "All-in-One"
    assert "Accessible with Fundamental 2 or All in One subscription." in listed["historical_market_cap"]["premium_notes"]
    assert any("US-listed symbols only" in n for n in listed["quote"]["premium_notes"])


def test_the_catalog_never_offers_the_token_and_hides_request_paths():
    for endpoint in Finnhub(http_get=FakeHttp())._load()["endpoints"]:
        assert "token" not in {p["name"].lower() for p in endpoint["params"]} and endpoint["path"].startswith("/")
    public = Finnhub(http_get=FakeHttp()).catalog()
    assert all("path" not in e and all("in" not in p for p in e["params"]) for e in public["endpoints"])


def test_every_example_fills_the_required_parameters_with_declared_names_and_valid_values():
    pv = Finnhub(http_get=FakeHttp())
    for item in pv.catalog()["endpoints"]:
        required = {p["name"] for p in item["params"] if p["required"]}
        for example in item["examples"]:
            assert required <= set(example["params"]) <= {p["name"] for p in item["params"]}, item["id"]
            validate_params(pv._endpoint(item["id"]), example["params"], forbidden={"token"})


def test_recent_examples_are_filled_in_for_the_day_and_follow_it():
    now = [at(2026, 11, 4)()]
    pv = Finnhub(http_get=FakeHttp(), clock=lambda: now[0])
    news = next(e for e in pv.catalog()["endpoints"] if e["id"] == "company_news")
    assert news["examples"][0]["params"] == {"symbol": "AAPL", "from": "2026-10-28", "to": "2026-11-04"}
    calendar = next(e for e in pv.catalog()["endpoints"] if e["id"] == "earnings_calendar")
    assert calendar["examples"][0]["params"] == {"from": "2026-11-04", "to": "2026-11-11"}
    spending = next(e for e in pv.catalog()["endpoints"] if e["id"] == "stock_usa_spending")
    assert spending["examples"][0]["params"] == {"symbol": "LMT", "from": "2025-11-04", "to": "2026-11-04"}
    assert next(p for p in calendar["params"] if p["name"] == "from")["premium_note"].startswith("Free plan: up to 30 days back")
    now[0] += 86400
    news = next(e for e in pv.catalog()["endpoints"] if e["id"] == "company_news")
    assert news["examples"][0]["params"]["to"] == "2026-11-05"


def test_choices_are_offered_where_finnhub_documents_them():
    listed = endpoints()
    resolution = next(p for p in listed["stock_candles"]["params"] if p["name"] == "resolution")
    assert resolution["enum"] == ["1", "5", "15", "30", "60", "D", "W", "M"] and resolution["enum_labels"]["D"] == "Daily"
    assert next(p for p in listed["financials_reported"]["params"] if p["name"] == "freq")["enum"] == ["annual", "quarterly"]
    assert next(p for p in listed["market_news"]["params"] if p["name"] == "category")["enum"] == ["general", "forex", "crypto", "merger"]
    assert [p["name"] for p in listed["technical_indicator"]["params"]][-1] == "timeperiod"
    assert next(p for p in listed["insider_transactions"]["params"] if p["name"] == "symbol")["required"] is False
    assert next(p for p in listed["transcripts_list"]["params"] if p["name"] == "symbol")["required"] is False
    ownership = {p["name"]: p["required"] for p in listed["institutional_ownership"]["params"]}
    assert ownership == {"symbol": False, "cusip": False, "from": True, "to": True}  # by symbol or by CUSIP


def test_the_summary_names_the_key_but_never_holds_it(keyed):
    summary = Finnhub(http_get=FakeHttp()).summary()
    assert (summary["id"], summary["key_env"], summary["secret_env"], summary["configured"]) == ("finnhub", "FINNHUB_API_KEY", None, True)
    assert [p["name"] for p in summary["plans"]] == ["Free", "All-in-One"] and (summary["endpoint_count"], summary["premium_count"]) == (113, 84)
    assert KEY not in json.dumps(summary)


# --- requests ----------------------------------------------------------------------------------------------


def test_without_a_key_nothing_is_fetched(unkeyed):
    pv, http = provider(ok(fx.QUOTE))
    response = pv.query("quote", {"symbol": "AAPL"})
    assert response["status"] == "not_configured" and "FINNHUB_API_KEY" in response["message"] and http.calls == [] and pv.configured() is False


def test_the_key_goes_only_in_the_header_and_the_request_is_built_from_the_catalog(keyed):
    pv, http = provider(ok(fx.NEWS))
    response = pv.query("company_news", {"symbol": "AAPL", "from": "2026-10-28", "to": "2026-11-04"})
    url, query = http.calls[0]
    assert url == BASE_URL + "/company-news" and query == [("symbol", "AAPL"), ("from", "2026-10-28"), ("to", "2026-11-04")]
    assert http.headers[0] == {"X-Finnhub-Token": KEY}
    assert response["params"] == {"endpoint": "/company-news", "symbol": "AAPL", "from": "2026-10-28", "to": "2026-11-04"}
    assert response["status"] == "ok" and KEY not in json.dumps(response)


@pytest.mark.parametrize(
    ("endpoint_id", "params", "message"),
    [
        ("quote", {"symbol": "AAPL", "token": "x"}, "set by the server"),
        ("quote", {"symbol": "AAPL", "apikey": "x"}, "Unknown parameter"),
        ("quote", {}, "symbol is required"),
        ("stock_candles", {"symbol": "AAPL", "resolution": "2", "from": "1", "to": "2"}, "resolution must be one of"),
        ("company_news", {"symbol": "AAPL", "from": "28/10/2026", "to": "2026-11-04"}, "YYYY-MM-DD"),
    ],
)
def test_invalid_parameters_are_refused_before_any_request(keyed, endpoint_id, params, message):
    pv, http = provider(ok(fx.QUOTE))
    with pytest.raises(ValueError, match=message):
        pv.query(endpoint_id, params)
    assert http.calls == []


def test_an_unknown_endpoint_is_a_key_error(keyed):
    with pytest.raises(KeyError):
        provider()[0].query("nope", {})


def test_a_key_echoed_by_the_provider_is_scrubbed(keyed):
    pv, _ = provider(ok([{**fx.NEWS[0], "summary": f"token={KEY}"}]))
    assert KEY not in json.dumps(pv.query("market_news", {"category": "general"}))


def test_a_list_served_as_a_file_on_finnhubs_static_host_is_fetched_without_the_key(keyed):
    file = "https://static2.finnhub.io/file/privatedatany2/exchange/USf.json?abc"
    pv, http = provider(HttpResult(302, b"", "text/html", file), ok([{"symbol": "AAPL", "description": "APPLE INC"}, {"symbol": "MSFT", "description": "MICROSOFT CORP"}]))
    response = pv.query("stock_symbols", {"exchange": "US"})
    assert response["status"] == "ok" and http.calls[1] == (file, []) and http.headers == [{"X-Finnhub-Token": KEY}, {}]
    assert pv.requests_this_session == 1


@pytest.mark.parametrize("location", ["https://evil.test/finnhub.io/x.json", "http://static2.finnhub.io/x.json", "https://finnhub.io.evil.test/x", ""])
def test_a_redirect_anywhere_else_is_not_followed(keyed, location):
    assert not is_finnhub_file(location)
    pv, http = provider(HttpResult(302, b"", "text/html", location))
    response = pv.query("stock_symbols", {"exchange": "US"})
    assert response["status"] == "upstream_error" and "not followed" in response["message"] and len(http.calls) == 1


# --- errors and empty answers ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("result", "endpoint_id", "params", "status", "words"),
    [
        (fx.INVALID_KEY, "quote", {"symbol": "AAPL"}, "invalid_key", "Invalid API key."),
        (fx.NO_KEY, "quote", {"symbol": "AAPL"}, "invalid_key", "Please use an API key."),
        (fx.NO_ACCESS, "stock_candles", {"symbol": "AAPL", "resolution": "D", "from": "1", "to": "2"}, "premium_required", "part of the All-in-One plan"),
        (fx.NO_ACCESS_401, "stock_symbols", {"exchange": "TO"}, "premium_required", "US-listed symbols and US exchanges only"),
        (fx.NO_ACCESS, "transcripts", {"id": "AAPL_1"}, "premium_required", "sold separately"),
        (fx.CFD_INDEX, "quote", {"symbol": "^GSPC"}, "premium_required", "Market data subscription required for CFD indices."),
        (fx.LIMIT_REACHED, "quote", {"symbol": "AAPL"}, "rate_limited", "API limit reached"),
        (fx.MISSING_PARAMETER, "quote", {"symbol": "AAPL"}, "invalid_request", "Missing parameter symbol"),
        (fx.SERVER_ERROR, "quote", {"symbol": "AAPL"}, "upstream_error", "Finnhub answered with HTTP 502."),
        (fx.HTML_PAGE, "quote", {"symbol": "AAPL"}, "upstream_error", "could not be read"),
    ],
)
def test_provider_side_problems_are_a_status_with_finnhubs_words(keyed, result, endpoint_id, params, status, words):
    pv, _ = provider(result)
    response = pv.query(endpoint_id, params)
    assert response["status"] == status and words in response["message"] and response["views"] == [] and response["raw"] is None


def test_a_plan_refusal_keeps_finnhubs_message_in_brackets():
    status, message = classify_error(403, b"", {"error": "You don't have access to this resource."}, "All-in-One")
    assert status == "premium_required" and message.endswith("(Finnhub: You don't have access to this resource.)")
    assert classify_error(200, b"", fx.QUOTE) is None


@pytest.mark.parametrize("exc", [requests.Timeout(), requests.ConnectionError(), ValueError("response too large")])
def test_network_failures_are_upstream_errors(keyed, exc):
    response = provider(exc)[0].query("quote", {"symbol": "AAPL"})
    assert response["status"] == "upstream_error" and "Finnhub" in response["message"]


@pytest.mark.parametrize("payload", [[], {}, fx.NO_DATA, {"data": [], "symbol": "NVDA"}, {"count": 0, "result": []}, {"metric": {}, "metricType": "all", "series": {}, "symbol": "X"}])
def test_empty_answers_are_empty(keyed, payload):
    assert has_data(payload) is False
    assert provider(ok(payload))[0].query("insider_transactions", {"symbol": "NVDA"})["status"] == "empty"


def test_an_all_zero_quote_is_an_unknown_symbol_not_a_price(keyed):
    assert is_blank_quote(fx.BLANK_QUOTE) and not is_blank_quote(fx.QUOTE) and has_data(fx.MARKET_STATUS)
    response = provider(ok(fx.BLANK_QUOTE))[0].query("quote", {"symbol": "aapl"})
    assert response["status"] == "empty" and "all-zero quote" in response["message"] and response["views"] == []


def test_a_large_raw_answer_is_left_out_but_still_drawn(keyed):
    rows = [{"description": "X" * 500, "displaySymbol": f"S{i}", "symbol": f"S{i}", "type": "Common Stock"} for i in range(1000)]
    response = provider(ok(rows))[0].query("stock_symbols", {"exchange": "US"})
    assert response["status"] == "ok" and response["raw"] is None and response["raw_omitted"]["bytes"] > 400 * 1024 and response["views"]


# --- caching -----------------------------------------------------------------------------------------------


def test_identical_requests_are_cached_for_30_seconds_and_refresh_spends_a_request(keyed):
    now = [1_000_000.0]
    pv, http = provider(ok(fx.QUOTE), clock=lambda: now[0])
    first = pv.query("quote", {"symbol": "AAPL"})
    second = pv.query("quote", {"symbol": "AAPL"})
    assert (first["cached"], second["cached"], len(http.calls)) == (False, True, 1)
    pv.query("quote", {"symbol": "AAPL"}, refresh=True)
    assert len(http.calls) == 2
    now[0] += CACHE_TTL_SECONDS
    pv.query("quote", {"symbol": "AAPL"})
    assert len(http.calls) == 3 and pv.requests_this_session == 3 and CACHE_TTL_SECONDS == 30.0


def test_errors_are_never_cached_and_another_key_never_reads_a_cached_answer(keyed, monkeypatch):
    pv, http = provider(fx.LIMIT_REACHED, ok(fx.QUOTE), ok(fx.QUOTE))
    assert pv.query("quote", {"symbol": "AAPL"})["status"] == "rate_limited"
    assert pv.query("quote", {"symbol": "AAPL"})["status"] == "ok"
    monkeypatch.setenv("FINNHUB_API_KEY", KEY + "-other")
    assert pv.query("quote", {"symbol": "AAPL"})["cached"] is False and len(http.calls) == 3


def test_concurrent_identical_requests_make_one_upstream_call(keyed):
    gate = threading.Event()
    http = FakeHttp(ok(fx.QUOTE), gate=gate)
    pv = Finnhub(http_get=http)
    results = []
    threads = [threading.Thread(target=lambda: results.append(pv.query("quote", {"symbol": "AAPL"}))) for _ in range(4)]
    for thread in threads:
        thread.start()
    gate.set()
    for thread in threads:
        thread.join(5)
    assert len(http.calls) == 1 and len(results) == 4 and sum(r["cached"] for r in results) == 3


def test_the_catalog_day_is_utc():
    late = datetime(2026, 11, 4, 23, 30, tzinfo=timezone(timedelta(hours=-5))).timestamp()  # already the 5th in UTC
    news = next(e for e in Finnhub(http_get=FakeHttp(), clock=lambda: late).catalog()["endpoints"] if e["id"] == "company_news")
    assert news["examples"][0]["params"]["to"] == date(2026, 11, 5).isoformat()
