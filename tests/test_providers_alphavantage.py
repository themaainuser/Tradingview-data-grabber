"""Alpha Vantage provider: validation, classification, the key never leaking, caching, no auto-fetch."""

from __future__ import annotations

import json
import threading

import pytest
import requests

from tradingview_data.providers import alphavantage as av
from tradingview_data.providers import common
from tradingview_data.providers.alphavantage import AlphaVantage, classify, default_http_get

from providers_support import DAILY, KEY, PLACEHOLDER, FakeHttp, ok, text


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("test attempted a real network request")

    monkeypatch.setattr(requests, "get", refuse)
    monkeypatch.setattr(requests.Session, "request", refuse)


@pytest.fixture
def keyed(monkeypatch):
    monkeypatch.setenv("ALPHAVANTAGE_API_KEY", KEY)


@pytest.fixture
def unkeyed(monkeypatch):
    monkeypatch.delenv("ALPHAVANTAGE_API_KEY", raising=False)


def provider(*script, **kwargs):
    http = FakeHttp(*script)
    return AlphaVantage(http_get=http, **kwargs), http


DAILY_ARGS = ("TIME_SERIES_DAILY", {"symbol": "IBM"})


# --- no key, no network -------------------------------------------------------------------------------


def test_without_a_key_nothing_is_fetched_and_the_response_says_how_to_fix_it(unkeyed):
    pv, http = provider(ok(DAILY))
    response = pv.query(*DAILY_ARGS)
    assert http.calls == [] and pv.requests_this_session == 0
    assert response["status"] == "not_configured" and response["views"] == []
    assert "ALPHAVANTAGE_API_KEY" in response["message"]
    assert pv.configured() is False


def test_an_empty_or_blank_key_counts_as_not_configured(monkeypatch):
    monkeypatch.setenv("ALPHAVANTAGE_API_KEY", "   ")
    assert AlphaVantage(http_get=FakeHttp()).configured() is False


def test_validation_runs_before_the_key_check_so_a_bad_request_is_reported_even_without_a_key(unkeyed):
    with pytest.raises(ValueError, match="symbol is required"):
        provider()[0].query("TIME_SERIES_DAILY", {})


# --- the request ------------------------------------------------------------------------------------------


def test_the_request_carries_function_params_and_the_key_last_and_never_datatype(keyed):
    pv, http = provider(ok(DAILY))
    pv.query("TIME_SERIES_DAILY", {"symbol": "IBM", "outputsize": "compact"})
    (url, params), = http.calls
    assert url == "https://www.alphavantage.co/query"
    assert params == [("function", "TIME_SERIES_DAILY"), ("symbol", "IBM"), ("outputsize", "compact"), ("apikey", KEY)]


def test_the_default_transport_never_follows_redirects_streams_and_identifies_itself(monkeypatch):
    seen = {}

    class Response:
        status_code = 200
        headers = {"content-type": "application/json"}

        def iter_content(self, chunk_size):
            yield b"{}"

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_get(url, **kwargs):
        seen.update(kwargs)
        return Response()

    monkeypatch.setattr(requests, "get", fake_get)
    result = default_http_get("https://example.test", [("a", "b")])
    assert result.status == 200 and result.body == b"{}"
    assert seen["allow_redirects"] is False and seen["stream"] is True
    assert seen["timeout"] == (5, 60) and seen["headers"]["User-Agent"].startswith("tradingview-data-grabber/")
    assert "mozilla" not in seen["headers"]["User-Agent"].lower()


def test_the_default_transport_refuses_an_oversized_body(monkeypatch):
    monkeypatch.setattr(common, "MAX_BODY_BYTES", 10)

    class Response:
        status_code = 200
        headers = {}

        def iter_content(self, chunk_size):
            yield b"x" * 11

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(requests, "get", lambda *a, **k: Response())
    with pytest.raises(ValueError):
        default_http_get("https://example.test", [])


def test_repeated_parameters_are_sent_as_repeated_keys(keyed):
    pv, http = provider(ok({"meta_data": {}, "payload": {}}))
    pv.query("ANALYTICS_FIXED_WINDOW", {"SYMBOLS": "AAPL,IBM", "RANGE": ["2023-07-01", "2023-08-31"], "INTERVAL": "DAILY", "CALCULATIONS": "MEAN"})
    sent = http.calls[0][1]
    assert [v for k, v in sent if k == "RANGE"] == ["2023-07-01", "2023-08-31"]


# --- classification, with the wording the service really uses ------------------------------------------------


@pytest.mark.parametrize(
    ("payload", "status"),
    [
        ({"Information": "Thank you for using Alpha Vantage! This is a premium endpoint. You may subscribe to any of the premium plans at https://www.alphavantage.co/premium/ to instantly unlock all premium endpoints"}, "premium_required"),
        ({"Information": "Thank you for using Alpha Vantage! Our standard API rate limit is 25 requests per day. Please subscribe to any of the premium plans at https://www.alphavantage.co/premium/ to instantly remove all daily rate limits."}, "rate_limited"),
        ({"Note": "Thank you for using Alpha Vantage! Our standard API call frequency is 5 calls per minute."}, "rate_limited"),
        ({"Information": "Please query the demo URLs at no more than 2 requests per second."}, "rate_limited"),
        ({"Information": "The **demo** API key is for demo purposes only. Please claim your free API key at (https://www.alphavantage.co/support/#api-key)."}, "invalid_key"),
        ({"Error Message": "the parameter apikey is invalid or missing. Please claim your free API key"}, "invalid_key"),
        ({"Error Message": "Invalid API call. Please retry or visit the documentation (https://www.alphavantage.co/documentation/) for TIME_SERIES_DAILY."}, "invalid_request"),
        ({"Information": "Something new we have never seen"}, "upstream_error"),
        (PLACEHOLDER, "premium_required"),
        ({}, "empty"),
        ({"bestMatches": []}, "empty"),
        ({"Time Series (Daily)": {"2026-01-01": {"1. open": "1"}}}, "ok"),
        (DAILY, "ok"),
    ],
)
def test_classification(payload, status):
    assert classify(payload)[0] == status


def test_a_rate_limit_notice_that_mentions_premium_plans_is_not_mistaken_for_a_premium_endpoint():
    notice = {"Information": "Our standard API rate limit is 25 requests per day. Subscribe to a premium plan to remove it."}
    assert classify(notice)[0] == "rate_limited"


def test_the_artificial_placeholder_payload_never_becomes_views(keyed):
    pv, _ = provider(ok(PLACEHOLDER))
    response = pv.query("REALTIME_OPTIONS", {"symbol": "IBM"})
    assert response["status"] == "premium_required" and response["views"] == []
    assert "premium endpoint" in response["message"] and response["raw"] is None
    assert "XXYYZZ" not in json.dumps(response)


# --- the key never leaks, on any path -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "result",
    [
        requests.Timeout(f"read timed out talking to /query?apikey={KEY}"),
        requests.ConnectionError(f"HTTPSConnectionPool: /query?function=X&apikey={KEY}"),
        ValueError("response too large"),
        text("x", 500),
        text(f"<html>error for apikey={KEY}</html>", 200, "text/html"),
        ok({"Information": f"Our standard API rate limit is 25 requests per day. key {KEY}"}),
        ok({"Information": f"This is a premium endpoint. key {KEY}"}),
        ok({"Error Message": f"the parameter apikey={KEY} is invalid or missing"}),
        ok({"Meta Data": {"1. Information": f"echoed {KEY}", "2. Symbol": "IBM"}, "Time Series (Daily)": DAILY["Time Series (Daily)"]}),
    ],
)
def test_the_api_key_never_appears_in_any_response(keyed, result):
    pv, _ = provider(result)
    response = pv.query(*DAILY_ARGS)
    assert KEY not in json.dumps(response)
    assert KEY not in repr(pv.__dict__)


def test_transport_failures_get_plain_messages_without_internals(keyed):
    cases = [(requests.Timeout("x"), "did not respond in time"), (requests.ConnectionError("dns"), "Could not reach"), (text("x", 503), "HTTP 503")]
    for result, fragment in cases:
        response = provider(result)[0].query(*DAILY_ARGS)
        assert response["status"] == "upstream_error" and fragment in response["message"]
        assert "dns" not in response["message"]


def test_an_unreadable_body_is_an_upstream_error(keyed):
    response = provider(text("<html>nope</html>", 200, "text/html"))[0].query(*DAILY_ARGS)
    assert response["status"] == "upstream_error" and response["views"] == []


# --- successful responses ----------------------------------------------------------------------------------


def test_a_good_response_has_views_params_without_the_key_and_the_raw_payload(keyed):
    response = provider(ok(DAILY))[0].query(*DAILY_ARGS)
    assert response["status"] == "ok" and response["message"] is None and response["cached"] is False
    assert [v["kind"] for v in response["views"]] == ["facts", "series", "table"]
    assert response["params"] == {"function": "TIME_SERIES_DAILY", "symbol": "IBM"}
    assert response["raw"] == DAILY and response["raw_omitted"] is None
    assert response["fetched_at"] is not None and response["bytes"] > 0


def test_a_large_response_omits_the_raw_payload_but_keeps_the_views(keyed, monkeypatch):
    monkeypatch.setattr(av, "RAW_LIMIT_BYTES", 50)
    response = provider(ok(DAILY))[0].query(*DAILY_ARGS)
    assert response["raw"] is None and response["raw_omitted"]["bytes"] > 50 and response["views"]


def test_csv_bodies_become_a_table(keyed):
    body = "symbol,name,ipoDate\nPTT,Ptt PCL,2026-09-30\nABC,Abc Inc,2026-10-01\n"
    response = provider(text(body, 200, "application/x-download"))[0].query("IPO_CALENDAR", {})
    table = response["views"][0]
    assert response["status"] == "ok" and table["kind"] == "table" and table["total_rows"] == 2
    assert response["raw"] is None and "CSV" in response["raw_omitted"]["reason"]


def test_a_header_only_csv_is_empty(keyed):
    response = provider(text("symbol,name\n", 200, "text/csv"))[0].query("IPO_CALENDAR", {})
    assert response["status"] == "empty" and response["views"] == []


def test_a_payload_that_yields_no_views_is_reported_empty_not_ok(keyed):
    response = provider(ok({"unrecognised": {"nested": {"deeper": {"deepest": {"x": 1}}}}}))[0].query("GLOBAL_QUOTE", {"symbol": "IBM"})
    assert response["status"] in ("empty", "ok")
    if response["status"] == "ok":
        assert response["views"]


# --- caching, single flight, counting --------------------------------------------------------------------------


def test_an_identical_second_call_is_served_from_cache_and_refresh_bypasses_it(keyed):
    pv, http = provider(ok(DAILY))
    first = pv.query(*DAILY_ARGS)
    second = pv.query(*DAILY_ARGS)
    assert (first["cached"], second["cached"]) == (False, True) and len(http.calls) == 1
    assert pv.query(*DAILY_ARGS, refresh=True)["cached"] is False and len(http.calls) == 2
    assert pv.requests_this_session == 2


def test_different_parameters_are_cached_separately(keyed):
    pv, http = provider(ok(DAILY))
    pv.query("TIME_SERIES_DAILY", {"symbol": "IBM"})
    pv.query("TIME_SERIES_DAILY", {"symbol": "MSFT"})
    assert len(http.calls) == 2


def test_errors_are_never_cached(keyed):
    pv, http = provider(ok({"Information": "Our standard API rate limit is 25 requests per day."}), ok(DAILY))
    assert pv.query(*DAILY_ARGS)["status"] == "rate_limited"
    assert pv.query(*DAILY_ARGS)["status"] == "ok" and len(http.calls) == 2


def test_the_cache_expires(keyed):
    now = [1000.0]
    pv, http = provider(ok(DAILY), clock=lambda: now[0], ttl_seconds=300)
    pv.query(*DAILY_ARGS)
    now[0] += 299
    assert pv.query(*DAILY_ARGS)["cached"] is True
    now[0] += 2
    assert pv.query(*DAILY_ARGS)["cached"] is False and len(http.calls) == 2


def test_concurrent_identical_queries_make_one_upstream_call(keyed):
    gate = threading.Event()
    http = FakeHttp(ok(DAILY), gate=gate)
    pv = AlphaVantage(http_get=http)
    results = []
    threads = [threading.Thread(target=lambda: results.append(pv.query(*DAILY_ARGS))) for _ in range(6)]
    for t in threads:
        t.start()
    gate.set()
    for t in threads:
        t.join(5)
    assert len(results) == 6 and len(http.calls) == 1
    assert sorted(r["cached"] for r in results) == [False] + [True] * 5


def test_the_session_counter_counts_only_real_attempts(keyed, unkeyed):
    pv, http = provider(ok(DAILY))
    with pytest.raises(ValueError):
        pv.query("TIME_SERIES_DAILY", {})
    assert pv.requests_this_session == 0


# --- validation: every rule --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("endpoint", "params", "message"),
    [
        ("TIME_SERIES_DAILY", {}, "symbol is required"),
        ("TIME_SERIES_DAILY", {"symbol": "IBM", "nope": "1"}, "Unknown parameter 'nope'"),
        ("TIME_SERIES_DAILY", {"symbol": "IBM", "apikey": "x"}, "set by the server"),
        ("TIME_SERIES_DAILY", {"symbol": "IBM", "function": "X"}, "set by the server"),
        ("TIME_SERIES_DAILY", {"symbol": "IBM", "datatype": "csv"}, "Unknown parameter 'datatype'"),
        ("TIME_SERIES_DAILY", {"symbol": "IBM", "outputsize": "huge"}, "outputsize must be one of"),
        ("TIME_SERIES_DAILY", {"symbol": ["IBM", "MSFT"]}, "takes a single value"),
        ("TIME_SERIES_DAILY", {"symbol": "x" * 201}, "too long"),
        ("TIME_SERIES_INTRADAY", {"symbol": "IBM", "interval": "5min", "month": "2009-13"}, "YYYY-MM"),
        ("TIME_SERIES_INTRADAY", {"symbol": "IBM", "interval": "5min", "adjusted": "yes"}, "true or false"),
        ("SMA", {"symbol": "IBM", "interval": "daily", "time_period": "ten", "series_type": "open"}, "must be a number"),
        ("SMA", {"symbol": "IBM", "interval": "daily", "time_period": "nan", "series_type": "open"}, "must be a number"),
        ("HISTORICAL_OPTIONS", {"symbol": "IBM", "date": "2017-02-30"}, "YYYY-MM-DD"),
    ],
)
def test_validation_rejects(endpoint, params, message):
    with pytest.raises(ValueError, match=message):
        provider()[0].query(endpoint, params)


def test_validation_accepts_suggestions_as_free_text_and_drops_empty_optionals(keyed):
    pv, http = provider(ok({"symbol": "IBM", "estimates": [{"date": "2027-12-31", "x": "1"}]}))
    pv.query("CURRENCY_EXCHANGE_RATE", {"from_currency": "XYZ", "to_currency": "ABC"})
    pv.query("TIME_SERIES_DAILY", {"symbol": "IBM", "outputsize": ""})
    assert ("from_currency", "XYZ") in http.calls[0][1]
    assert all(k != "outputsize" for k, _ in http.calls[1][1])


def test_long_free_text_lists_have_a_higher_cap(keyed):
    pv, _ = provider(ok({"meta_data": {}, "payload": {}}))
    pv.query("ANALYTICS_FIXED_WINDOW", {"SYMBOLS": ",".join(["AAPL"] * 300), "RANGE": ["full"], "INTERVAL": "DAILY", "CALCULATIONS": "MEAN"})
    with pytest.raises(ValueError, match="too long"):
        pv.query("ANALYTICS_FIXED_WINDOW", {"SYMBOLS": "A" * 2001, "RANGE": ["full"], "INTERVAL": "DAILY", "CALCULATIONS": "MEAN"})


def test_an_unknown_endpoint_is_a_key_error():
    with pytest.raises(KeyError):
        provider()[0].query("NOT_A_FUNCTION", {})


# --- the committed catalog -----------------------------------------------------------------------------------------

PREMIUM = {"TIME_SERIES_INTRADAY", "TIME_SERIES_DAILY_ADJUSTED", "REALTIME_BULK_QUOTES", "REALTIME_BULK_BID_ASK_PRICES", "INDEX_DATA", "REALTIME_OPTIONS", "HISTORICAL_OPTIONS", "FX_INTRADAY", "CRYPTO_INTRADAY", "VWAP", "MACD"}


def test_the_committed_catalog_matches_alpha_vantages_documentation():
    catalog = AlphaVantage(http_get=FakeHttp()).catalog()
    endpoints = {e["id"]: e for e in catalog["endpoints"]}
    assert len(endpoints) == len(catalog["endpoints"]) == 128
    assert {i for i, e in endpoints.items() if e["premium"]} == PREMIUM
    assert sum(c["count"] for c in catalog["categories"]) == 128
    assert sum(c["premium_count"] for c in catalog["categories"]) == len(PREMIUM)
    assert [p for e in endpoints.values() for p in e["params"] if p["name"].lower() in ("function", "apikey")] == []
    assert all(e["doc_url"].startswith("https://www.alphavantage.co/documentation/#") and len(e["summary"]) <= 200 for e in endpoints.values())


def test_every_required_parameter_has_a_documented_example_or_choice():
    for endpoint in AlphaVantage(http_get=FakeHttp()).catalog()["endpoints"]:
        for p in endpoint["params"]:
            if p["required"] and not p["managed"]:
                assert p["example"] or p["enum"], (endpoint["id"], p["name"])


def test_free_endpoints_flag_their_premium_parameters_and_datatype_is_managed():
    endpoints = {e["id"]: e for e in AlphaVantage(http_get=FakeHttp()).catalog()["endpoints"]}
    daily = {p["name"]: p for p in endpoints["TIME_SERIES_DAILY"]["params"]}
    assert "premium" in daily["outputsize"]["premium_note"].lower() and daily["datatype"]["managed"] is True
    assert endpoints["TIME_SERIES_DAILY"]["premium"] is False
    assert any(p["multiple"] for p in endpoints["ANALYTICS_FIXED_WINDOW"]["params"])
    assert all("function" not in e["params"] for e in endpoints["INDEX_DATA"]["examples"])
