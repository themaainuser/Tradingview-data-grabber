"""Financial Modeling Prep provider: the catalog and its plans, request building, error classification, key safety, caching."""

from __future__ import annotations

import json
import re
import threading
from datetime import date, datetime, timezone

import pytest
import requests

from tradingview_data.providers import fmp as fmp_module
from tradingview_data.providers.common import validate_params
from tradingview_data.providers.fmp import BASE_URL, INFO, FinancialModelingPrep, classify_error, has_data
from tradingview_data.providers.fmp_catalog import CATEGORIES, ENDPOINTS, PAID_PLANS, PLAN_NAMES, fill_dates, sample_day

import fmp_support as fx
from fmp_support import FakeHttp, raw
from providers_support import KEY, ok


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("test attempted a real network request")

    monkeypatch.setattr(requests, "get", refuse)
    monkeypatch.setattr(requests.Session, "request", refuse)


@pytest.fixture
def keyed(monkeypatch):
    monkeypatch.setenv("FMP_API_KEY", KEY)


@pytest.fixture
def unkeyed(monkeypatch):
    monkeypatch.delenv("FMP_API_KEY", raising=False)


def provider(*script, **kwargs):
    http = FakeHttp(*script)
    return FinancialModelingPrep(http_get=http, **kwargs), http


def at(year, month, day):
    return lambda: datetime(year, month, day, 12, tzinfo=timezone.utc).timestamp()


QUOTE_ARGS = ("quote", {"symbol": "AAPL"})


# --- the catalog and its plans ---------------------------------------------------------------------------


def test_every_endpoint_has_a_unique_id_a_known_category_and_a_plan_consistent_with_premium():
    catalog = FinancialModelingPrep(http_get=FakeHttp()).catalog()
    endpoints = {e["id"]: e for e in catalog["endpoints"]}
    assert len(endpoints) == len(catalog["endpoints"]) == len(ENDPOINTS)
    assert [p.name for p in INFO.plans] == list(PLAN_NAMES) == ["Basic", "Starter", "Premium", "Ultimate"]
    assert {e["category"] for e in endpoints.values()} <= {c["id"] for c in CATEGORIES}
    assert set(PAID_PLANS) <= set(endpoints)
    for endpoint in endpoints.values():
        assert endpoint["premium"] == (endpoint["id"] in PAID_PLANS)
        assert endpoint["plan"] == ("Basic" if not endpoint["premium"] else PAID_PLANS[endpoint["id"]])
        assert endpoint["plan"] in (*PLAN_NAMES, None) and endpoint["request_cost"] == 1
        assert endpoint["doc_url"].startswith("https://site.financialmodelingprep.com/developer/docs/stable/")
    assert sum(c["count"] for c in catalog["categories"]) == len(endpoints)
    assert sum(c["premium_count"] for c in catalog["categories"]) == len(PAID_PLANS)


def test_the_plans_follow_what_a_free_key_is_refused_and_the_pricing_pages_feature_groups():
    plans = {e["id"]: e["plan"] for e in FinancialModelingPrep(http_get=FakeHttp()).catalog()["endpoints"]}
    assert {plans[i] for i in ("quote", "profile", "income_statement", "historical_eod", "earnings_calendar", "biggest_gainers", "treasury_rates")} == {"Basic"}
    assert (plans["stock_news_latest"], plans["intraday"], plans["technical_indicator"], plans["transcript"], plans["etf_holdings"], plans["institutional_latest"]) == ("Starter", "Premium", "Premium", "Ultimate", "Ultimate", "Ultimate")
    assert plans["stock_list"] is None and plans["company_screener"] is None  # refused on Basic, tier not stated by FMP


def test_the_catalog_never_offers_the_api_key_and_every_path_parameter_is_declared_required_and_first():
    for item in ENDPOINTS:
        names = {p["name"] for p in item["params"]}
        assert "apikey" not in {n.lower() for n in names} and item["path"].startswith("/")
        for placeholder in re.findall(r"{(\w+)}", item["path"]):
            assert next(p for p in item["params"] if p["name"] == placeholder)["required"]
        places = [p["in"] for p in item["params"]]
        assert places == sorted(places, key=lambda x: x != "path")
    public = FinancialModelingPrep(http_get=FakeHttp()).catalog()
    assert all("path" not in e and all("in" not in p for p in e["params"]) for e in public["endpoints"])


def test_the_public_catalog_has_the_contract_shape():
    endpoint = next(e for e in FinancialModelingPrep(http_get=FakeHttp()).catalog()["endpoints"] if e["id"] == "intraday")
    assert set(endpoint) == {"id", "title", "category", "description", "summary", "premium", "trending", "utility", "premium_notes", "plan", "request_cost", "doc_url", "params", "examples"}
    assert set(endpoint["params"][0]) == {"name", "required", "type", "description", "enum", "enum_labels", "suggestions", "default", "example", "multiple", "premium_note", "minimum", "maximum", "premium_values", "managed"}
    assert [p["name"] for p in endpoint["params"]] == ["interval", "symbol", "from", "to", "nonadjusted"]


def test_the_one_minute_interval_and_a_long_statement_limit_are_flagged_as_premium_options():
    endpoints = {e["id"]: e for e in FinancialModelingPrep(http_get=FakeHttp()).catalog()["endpoints"]}
    interval = next(p for p in endpoints["intraday"]["params"] if p["name"] == "interval")
    assert interval["premium_values"] == ["1min"] and "Ultimate" in interval["premium_note"] and set(interval["premium_values"]) <= set(interval["enum"])
    limit = next(p for p in endpoints["income_statement"]["params"] if p["name"] == "limit")
    assert "at most 5" in limit["premium_note"] and endpoints["income_statement"]["premium"] is False


def test_the_summary_lists_the_plans_and_counts_premium_endpoints(keyed):
    summary = FinancialModelingPrep(http_get=FakeHttp()).summary()
    assert summary["id"] == "fmp" and summary["key_env"] == "FMP_API_KEY" and summary["secret_env"] is None and summary["configured"] is True
    assert summary["endpoint_count"] == len(ENDPOINTS) and summary["premium_count"] == len(PAID_PLANS)
    assert [p["name"] for p in summary["plans"]] == ["Basic", "Starter", "Premium", "Ultimate"] and "250 requests per day" in summary["limits_note"]


def test_every_example_is_a_complete_valid_request_so_choosing_one_leaves_fetch_usable():
    for item in ENDPOINTS:
        endpoint = {**item, "params": [{**p, "managed": False} for p in item["params"]]}
        required = {p["name"] for p in item["params"] if p["required"]}
        assert item["examples"], item["id"]
        for example in fill_dates(item["examples"], date(2026, 10, 1)):
            assert required <= set(example["params"]), (item["id"], example["caption"])
            validate_params(endpoint, example["params"], forbidden={"apikey"}, long_text={"symbols"})


# --- date placeholders ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("today", "expected"), [(date(2026, 10, 1), date(2026, 9, 30)), (date(2026, 10, 5), date(2026, 10, 2)), (date(2026, 10, 4), date(2026, 10, 2))])
def test_the_sample_day_is_the_latest_weekday_before_today(today, expected):
    assert sample_day(today) == expected


def test_fill_dates_replaces_the_placeholders_at_any_depth_and_leaves_everything_else_alone():
    filled = fill_dates({"a": ["@day", {"b": "@month_ago to @day"}], "c": "AAPL", "d": 3, "e": "@week_ahead", "f": "@year_ago"}, date(2026, 10, 1))
    assert filled == {"a": ["2026-09-30", {"b": "2026-08-31 to 2026-09-30"}], "c": "AAPL", "d": 3, "e": "2026-10-08", "f": "2025-09-30"}


def test_the_served_catalog_never_leaks_a_placeholder_and_its_dates_follow_the_clock():
    now = [at(2026, 10, 1)()]
    pv = FinancialModelingPrep(http_get=FakeHttp(), clock=lambda: now[0])
    first = pv.catalog()
    assert "@" not in json.dumps(first)
    calendar = next(e for e in first["endpoints"] if e["id"] == "earnings_calendar")
    assert calendar["examples"][1] == {"caption": "With a date range: from=2026-09-30, to=2026-10-08", "params": {"from": "2026-09-30", "to": "2026-10-08"}}
    assert pv.catalog() is first
    now[0] = at(2026, 10, 12)()
    moved = next(e for e in pv.catalog()["endpoints"] if e["id"] == "earnings_calendar")
    assert moved["examples"][1]["params"] == {"from": "2026-10-09", "to": "2026-10-19"}


# --- key and configuration ---------------------------------------------------------------------------------


def test_without_a_key_nothing_is_fetched_and_the_response_says_how_to_fix_it(unkeyed):
    pv, http = provider(ok(fx.QUOTE))
    response = pv.query(*QUOTE_ARGS)
    assert response["status"] == "not_configured" and "FMP_API_KEY" in response["message"] and response["fetched_at"] is None
    assert http.calls == [] and pv.requests_this_session == 0 and pv.summary()["configured"] is False


def test_a_blank_key_is_not_configured(monkeypatch):
    monkeypatch.setenv("FMP_API_KEY", "   ")
    assert FinancialModelingPrep(http_get=FakeHttp()).configured() is False


def test_validation_runs_before_the_key_check(unkeyed):
    with pytest.raises(ValueError, match="symbol is required"):
        provider()[0].query("quote", {})


def test_an_unknown_endpoint_is_a_key_error():
    with pytest.raises(KeyError):
        provider()[0].query("nope", {})


def test_the_key_is_read_at_call_time_never_at_construction(monkeypatch):
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    pv, http = provider(ok(fx.QUOTE))
    assert pv.query(*QUOTE_ARGS)["status"] == "not_configured"
    monkeypatch.setenv("FMP_API_KEY", KEY)
    assert pv.query(*QUOTE_ARGS)["status"] == "ok" and len(http.calls) == 1


# --- building the request -----------------------------------------------------------------------------------


def test_the_key_goes_in_the_apikey_header_and_never_into_the_url_or_the_reported_parameters(keyed):
    pv, http = provider(ok(fx.QUOTE))
    response = pv.query(*QUOTE_ARGS)
    assert http.calls[0] == (f"{BASE_URL}/quote", [("symbol", "AAPL")]) and http.headers == [{"apikey": KEY}]
    assert response["params"] == {"endpoint": "/quote", "symbol": "AAPL"} and KEY not in json.dumps(response)


def test_path_parameters_go_into_the_url_and_empty_optionals_are_dropped(keyed):
    pv, http = provider(ok(fx.EOD_LIGHT), ok(fx.INTRADAY), ok(fx.RSI))
    pv.query("historical_eod", {"variant": "light", "symbol": "AAPL", "from": "2026-10-01", "to": ""})
    pv.query("intraday", {"interval": "4hour", "symbol": "AAPL"})
    pv.query("technical_indicator", {"indicator": "rsi", "symbol": "AAPL", "periodLength": "14", "timeframe": "1day"})
    assert [c[0] for c in http.calls] == [f"{BASE_URL}/historical-price-eod/light", f"{BASE_URL}/historical-chart/4hour", f"{BASE_URL}/technical-indicators/rsi"]
    assert http.calls[0][1] == [("symbol", "AAPL"), ("from", "2026-10-01")]
    assert http.calls[2][1] == [("symbol", "AAPL"), ("periodLength", "14"), ("timeframe", "1day")]


@pytest.mark.parametrize(
    ("endpoint", "params", "message"),
    [
        ("quote", {}, "symbol is required"),
        ("quote", {"symbol": "AAPL", "apikey": "x"}, "apikey is set by the server"),
        ("quote", {"symbol": "AAPL", "APIKEY": "x"}, "set by the server"),
        ("quote", {"symbol": "AAPL", "bogus": "1"}, "Unknown parameter"),
        ("quote", {"symbol": ["AAPL", "MSFT"]}, "takes a single value"),
        ("quote", {"symbol": "A" * 201}, "too long"),
        ("historical_eod", {"symbol": "AAPL"}, "variant is required"),
        ("historical_eod", {"variant": "../quote", "symbol": "AAPL"}, "variant must be one of"),
        ("historical_eod", {"variant": "full", "symbol": "AAPL", "from": "01/10/2026"}, "YYYY-MM-DD"),
        ("income_statement", {"symbol": "AAPL", "limit": "0"}, "at least 1"),
        ("income_statement", {"symbol": "AAPL", "period": "monthly"}, "period must be one of"),
        ("technical_indicator", {"indicator": "sma", "symbol": "AAPL", "periodLength": "1.5", "timeframe": "1day"}, "whole number"),
        ("intraday", {"interval": "2min", "symbol": "AAPL"}, "interval must be one of"),
        ("company_screener", {"isEtf": "yes"}, "true or false"),
    ],
)
def test_invalid_parameters_are_refused_with_a_plain_message_and_no_request(keyed, endpoint, params, message):
    pv, http = provider()
    with pytest.raises(ValueError, match=message):
        pv.query(endpoint, params)
    assert http.calls == []


def test_a_long_symbol_list_and_a_caret_symbol_are_accepted(keyed):
    pv, http = provider(ok(fx.QUOTE), ok(fx.QUOTE))
    pv.query("batch_quote", {"symbols": ",".join(["AAPL"] * 300)})
    pv.query("quote", {"symbol": "^GSPC"})
    assert len(http.calls[0][1][0][1]) == 1499 and http.calls[1][1] == [("symbol", "^GSPC")]


# --- what FMP answers ------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("result", "status"),
    [
        (fx.RESTRICTED, "premium_required"),
        (fx.PREMIUM_PARAMETER, "premium_required"),
        (fx.LIMIT_BEYOND_PLAN, "premium_required"),
        (fx.INVALID_KEY, "invalid_key"),
        (fx.MISSING_PARAMETER, "invalid_request"),
        (fx.LIMIT_REACHED, "rate_limited"),
        (raw(402, json.dumps({"Error Message": "Limit Reach . Please upgrade your plan"})), "rate_limited"),
        (raw(200, json.dumps({"Error Message": "Invalid API KEY."})), "invalid_key"),
        (raw(200, json.dumps({"Error Message": "Something else went wrong"})), "invalid_request"),
        (raw(403, ""), "premium_required"),
        (raw(404, "[]"), "invalid_request"),
        (raw(500, "Internal Server Error"), "upstream_error"),
        (raw(503, ""), "upstream_error"),
        (raw(418, "teapot"), "invalid_request"),
        (raw(502, "<html><body>Bad gateway</body></html>"), "upstream_error"),
    ],
)
def test_every_kind_of_answer_has_its_own_status_a_message_and_is_never_cached(keyed, result, status):
    pv, http = provider(result)
    response = pv.query(*QUOTE_ARGS)
    assert response["status"] == status and response["message"] and response["views"] == [] and response["raw"] is None
    assert pv.query(*QUOTE_ARGS)["cached"] is False and len(http.calls) == 2


def test_fmps_own_message_is_what_the_user_reads(keyed):
    assert provider(fx.RESTRICTED)[0].query(*QUOTE_ARGS)["message"].startswith("Restricted Endpoint: This endpoint is not available under your current subscription")
    assert "404" in provider(raw(404, "[]"))[0].query(*QUOTE_ARGS)["message"]
    assert provider(raw(502, "<html>Bad gateway</html>"))[0].query(*QUOTE_ARGS)["message"] == "FMP answered with HTTP 502."


def test_classify_error_returns_none_for_data():
    assert classify_error(200, b"[]", []) is None and classify_error(200, b"{}", {"price": 1}) is None


@pytest.mark.parametrize(("payload", "expected"), [([], False), ({}, False), (None, False), ("", False), ({"a": []}, False), ([{}], True), ([{"a": 1}], True), ({"a": [1]}, True), (0, True)])
def test_has_data(payload, expected):
    assert has_data(payload) is expected


def test_an_empty_array_is_empty_and_cached(keyed):
    pv, http = provider(ok([]))
    first = pv.query("earnings_calendar", {})
    assert first["status"] == "empty" and first["views"] == [] and first["message"]
    assert pv.query("earnings_calendar", {})["cached"] is True and len(http.calls) == 1


@pytest.mark.parametrize(("raised", "fragment"), [(requests.Timeout(), "did not respond"), (requests.ConnectionError(), "network error"), (ValueError("response too large"), "large")])
def test_transport_failures_are_upstream_errors_and_not_cached(keyed, raised, fragment):
    pv, http = provider(raised)
    response = pv.query(*QUOTE_ARGS)
    assert response["status"] == "upstream_error" and fragment in response["message"] and pv.query(*QUOTE_ARGS)["cached"] is False and len(http.calls) == 2


def test_an_unreadable_success_body_is_an_upstream_error(keyed):
    response = provider(raw(200, "<html>maintenance</html>"))[0].query(*QUOTE_ARGS)
    assert response["status"] == "upstream_error" and "could not be read" in response["message"]


def test_a_good_answer_has_views_the_raw_payload_and_the_request_that_was_sent(keyed):
    pv, _ = provider(ok(fx.INCOME))
    response = pv.query("income_statement", {"symbol": "AAPL", "limit": "3", "period": "annual"})
    assert response["status"] == "ok" and response["provider"] == "fmp" and response["endpoint"] == "income_statement" and response["title"] == "Income statement"
    assert response["raw"] == fx.INCOME and response["raw_omitted"] is None and response["bytes"] > 0 and response["cached"] is False and response["fetched_at"]
    assert response["params"] == {"endpoint": "/income-statement", "symbol": "AAPL", "limit": "3", "period": "annual"}
    assert [v["kind"] for v in response["views"]] == ["facts", "series", "table"] and pv.requests_this_session == 1


def test_a_large_response_omits_the_raw_payload_but_keeps_the_views(keyed, monkeypatch):
    monkeypatch.setattr(fmp_module, "RAW_LIMIT_BYTES", 100)
    response = provider(ok(fx.INCOME))[0].query("income_statement", {"symbol": "AAPL"})
    assert response["status"] == "ok" and response["raw"] is None and response["raw_omitted"]["bytes"] > 100 and response["views"]


def test_every_endpoint_answers_through_the_provider_with_views(keyed):
    payload = [{"symbol": "AAPL", "date": "2026-10-09", "value": 1.5, "name": "Apple"}, {"symbol": "AAPL", "date": "2026-10-08", "value": 1.4, "name": "Apple"}]
    for item in ENDPOINTS:
        pv, http = provider(ok(payload))
        example = fill_dates(item["examples"][0]["params"], date(2026, 10, 1))
        response = pv.query(item["id"], example)
        assert response["status"] == "ok" and response["views"], item["id"]
        assert http.calls[0][0].startswith(BASE_URL + "/") and "{" not in http.calls[0][0], item["id"]


# --- key safety -------------------------------------------------------------------------------------------------


def test_the_key_is_scrubbed_from_provider_messages_and_data(keyed):
    leaky = raw(401, json.dumps({"Error Message": f"Invalid API KEY {KEY}"}))
    response = provider(leaky)[0].query(*QUOTE_ARGS)
    assert KEY not in json.dumps(response) and "***" in response["message"]
    echoing = [{**fx.QUOTE[0], "name": f"x {KEY} y"}]
    assert KEY not in json.dumps(provider(ok(echoing))[0].query(*QUOTE_ARGS))


def test_a_cached_answer_is_never_served_to_a_different_key(keyed, monkeypatch):
    pv, http = provider(ok(fx.QUOTE), ok(fx.QUOTE))
    pv.query(*QUOTE_ARGS)
    monkeypatch.setenv("FMP_API_KEY", "another-key-0123456789")
    assert pv.query(*QUOTE_ARGS)["cached"] is False and len(http.calls) == 2 and http.headers[1] == {"apikey": "another-key-0123456789"}


def test_the_key_is_never_part_of_a_cache_key(keyed):
    pv, _ = provider(ok(fx.QUOTE))
    pv.query(*QUOTE_ARGS)
    assert all(KEY not in key for key in pv._cache._items)


# --- caching --------------------------------------------------------------------------------------------------------


def test_an_identical_second_call_is_served_from_cache_and_refresh_bypasses_it(keyed):
    pv, http = provider(ok(fx.QUOTE))
    assert pv.query(*QUOTE_ARGS)["cached"] is False
    assert pv.query(*QUOTE_ARGS)["cached"] is True and len(http.calls) == 1
    assert pv.query(*QUOTE_ARGS, refresh=True)["cached"] is False and len(http.calls) == 2


def test_different_parameters_and_different_endpoints_are_cached_separately(keyed):
    pv, http = provider(ok(fx.QUOTE))
    pv.query("quote", {"symbol": "AAPL"})
    pv.query("quote", {"symbol": "MSFT"})
    pv.query("quote_short", {"symbol": "AAPL"})
    assert len(http.calls) == 3


def test_the_cache_expires(keyed):
    now = [1000.0]
    pv, http = provider(ok(fx.QUOTE), clock=lambda: now[0], ttl_seconds=60)
    pv.query(*QUOTE_ARGS)
    now[0] += 59
    assert pv.query(*QUOTE_ARGS)["cached"] is True
    now[0] += 2
    assert pv.query(*QUOTE_ARGS)["cached"] is False and len(http.calls) == 2


def test_concurrent_identical_requests_make_one_upstream_call(keyed):
    gate = threading.Event()
    http = FakeHttp(ok(fx.QUOTE), gate=gate)
    pv = FinancialModelingPrep(http_get=http)
    results = []
    threads = [threading.Thread(target=lambda: results.append(pv.query(*QUOTE_ARGS))) for _ in range(4)]
    for t in threads:
        t.start()
    gate.set()
    for t in threads:
        t.join(5)
    assert len(results) == 4 and len(http.calls) == 1 and sorted(r["cached"] for r in results) == [False, True, True, True]
