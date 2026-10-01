"""Marketstack provider: the catalog and its plans, request building, error classification, key safety, caching."""

from __future__ import annotations

import io
import json
import re
import threading
import zipfile
from datetime import date

import pytest
import requests

from tradingview_data.providers import marketstack_docs as docs
from tradingview_data.providers.common import HttpResult, validate_params, valid_moment
from tradingview_data.providers.marketstack import INFO, Marketstack, classify_error, has_data

from marketstack_support import EOD_ROWS, SAMPLES, error
from providers_support import KEY, FakeHttp, ok, text


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("test attempted a real network request")

    monkeypatch.setattr(requests, "get", refuse)
    monkeypatch.setattr(requests.Session, "request", refuse)


@pytest.fixture
def keyed(monkeypatch):
    monkeypatch.setenv("MARKETSTACK_API_KEY", KEY)


@pytest.fixture
def unkeyed(monkeypatch):
    monkeypatch.delenv("MARKETSTACK_API_KEY", raising=False)


def provider(*script, **kwargs):
    http = FakeHttp(*script)
    return Marketstack(http_get=http, **kwargs), http


def failure(status, body):
    return HttpResult(status, json.dumps(body).encode(), "application/json")


EOD_ARGS = ("eod", {"symbols": "AAPL"})


# --- the committed catalog and its plans ---------------------------------------------------------------


def test_the_catalog_covers_every_documented_endpoint_with_a_plan_on_each():
    catalog = Marketstack(http_get=FakeHttp()).catalog()
    endpoints = {e["id"]: e for e in catalog["endpoints"]}
    assert len(endpoints) == len(catalog["endpoints"]) == 46
    plans = [p.name for p in INFO.plans]
    assert plans == ["Free", "Basic", "Professional", "Business"]
    assert {e["plan"] for e in endpoints.values()} <= set(plans)
    assert all(e["premium"] == (e["plan"] != "Free") for e in endpoints.values())
    by_plan = {name: sorted(i for i, e in endpoints.items() if e["plan"] == name) for name in plans}
    assert [len(by_plan[n]) for n in plans] == [20, 15, 3, 8]
    assert by_plan["Professional"] == ["commodities", "commoditieshistory", "stockprice"]
    assert {"companyratings", "tickerinfo", "company_facts", "submissions"} <= set(by_plan["Business"])
    assert {"indexinfo", "bond", "etfholdings", "intraday"} <= set(by_plan["Basic"])
    assert {"eod", "ticker_dividends", "exchanges", "currencies"} <= set(by_plan["Free"])
    assert sum(c["count"] for c in catalog["categories"]) == 46
    assert sum(c["premium_count"] for c in catalog["categories"]) == 26


def test_the_catalog_never_offers_the_access_key_and_every_path_parameter_is_declared():
    raw = Marketstack(http_get=FakeHttp())._load()
    for item in raw["endpoints"]:
        names = {p["name"] for p in item["params"]}
        assert "access_key" not in names
        for placeholder in re.findall(r"{(\w+)}", item["path"]):
            assert placeholder in names and next(p for p in item["params"] if p["name"] == placeholder)["required"]
        assert item["path"].startswith("/v2/")
    public = Marketstack(http_get=FakeHttp()).catalog()
    assert all("path" not in e and all("in" not in p for p in e["params"]) for e in public["endpoints"])


def test_the_public_catalog_has_the_contract_shape():
    endpoint = next(e for e in Marketstack(http_get=FakeHttp()).catalog()["endpoints"] if e["id"] == "intraday")
    assert set(endpoint) == {"id", "title", "category", "description", "summary", "premium", "trending", "utility", "premium_notes", "plan", "request_cost", "doc_url", "params", "examples"}
    assert set(endpoint["params"][0]) == {"name", "required", "type", "description", "enum", "enum_labels", "suggestions", "default", "example", "multiple", "premium_note", "minimum", "maximum", "premium_values", "managed"}
    assert endpoint["plan"] == "Basic" and endpoint["doc_url"] == INFO.docs_url


def test_fast_intervals_and_deep_history_are_flagged_as_premium_options_on_otherwise_cheaper_endpoints():
    endpoints = {e["id"]: e for e in Marketstack(http_get=FakeHttp()).catalog()["endpoints"]}
    interval = next(p for p in endpoints["intraday"]["params"] if p["name"] == "interval")
    assert interval["premium_values"] == ["1min", "5min", "10min"] and "Professional" in interval["premium_note"]
    assert interval["enum"][:4] == ["1min", "5min", "10min", "15min"] and interval["default"] == "1hour"
    date_from = next(p for p in endpoints["eod"]["params"] if p["name"] == "date_from")
    assert endpoints["eod"]["premium"] is False and "1 year" in date_from["premium_note"]
    sort = next(p for p in endpoints["eod"]["params"] if p["name"] == "sort")
    assert sort["enum"] == ["DESC", "ASC"]


def test_limits_quota_costs_and_suggestions_come_through():
    endpoints = {e["id"]: e for e in Marketstack(http_get=FakeHttp()).catalog()["endpoints"]}
    limit = next(p for p in endpoints["eod"]["params"] if p["name"] == "limit")
    assert (limit["type"], limit["minimum"], limit["maximum"], limit["default"]) == ("integer", 1, 1000, "100")
    assert endpoints["etfholdings"]["request_cost"] == endpoints["etflist"]["request_cost"] == 20 and endpoints["eod"]["request_cost"] == 1
    assert any("20 requests" in n for n in endpoints["etfholdings"]["premium_notes"])
    assert any("1 request per minute" in n for n in endpoints["companyratings"]["premium_notes"])
    names = next(p for p in endpoints["commodities"]["params"] if p["name"] == "commodity_name")["suggestions"]
    assert len(names) == 78 and "aluminum" in names and "gold" in names


def test_every_required_parameter_is_text_a_choice_or_has_an_example_and_the_path_ones_come_first():
    for e in Marketstack(http_get=FakeHttp()).catalog()["endpoints"]:
        for p in e["params"]:
            assert p["type"] in ("text", "integer", "number", "date", "datetime", "month", "boolean", "enum")
        for ex in e["examples"]:
            assert set(ex["params"]) <= {p["name"] for p in e["params"]}
    raw = Marketstack(http_get=FakeHttp())._load()
    for item in raw["endpoints"]:
        places = [p["in"] for p in item["params"]]
        assert places == sorted(places, key=lambda x: x != "path")


def test_the_summary_lists_the_plans_and_counts_premium_endpoints(keyed):
    summary = Marketstack(http_get=FakeHttp()).summary()
    assert summary["id"] == "marketstack" and summary["endpoint_count"] == 46 and summary["premium_count"] == 26
    assert [p["name"] for p in summary["plans"]] == ["Free", "Basic", "Professional", "Business"] and summary["configured"] is True
    assert KEY not in json.dumps(summary)


# --- no key, no network ------------------------------------------------------------------------------


def test_without_a_key_nothing_is_fetched_and_the_response_says_how_to_fix_it(unkeyed):
    pv, http = provider(ok(SAMPLES["eod"]))
    response = pv.query(*EOD_ARGS)
    assert http.calls == [] and pv.requests_this_session == 0
    assert response["status"] == "not_configured" and response["views"] == [] and "MARKETSTACK_API_KEY" in response["message"]
    assert pv.configured() is False


def test_a_blank_key_is_not_configured(monkeypatch):
    monkeypatch.setenv("MARKETSTACK_API_KEY", "  ")
    assert Marketstack(http_get=FakeHttp()).configured() is False


def test_validation_runs_before_the_key_check(unkeyed):
    with pytest.raises(ValueError, match="symbols is required"):
        provider()[0].query("eod", {})


def test_an_unknown_endpoint_is_a_key_error():
    with pytest.raises(KeyError):
        provider()[0].query("nope", {})


# --- the request ------------------------------------------------------------------------------------------


def test_path_parameters_go_into_the_url_and_the_key_is_the_last_query_parameter(keyed):
    pv, http = provider(ok(SAMPLES["exchange_eod_date"]))
    response = pv.query("exchange_eod_date", {"mic": "XNAS", "symbols": "AAPL,MSFT", "date": "2026-09-29", "limit": "5"})
    (url, params), = http.calls
    assert url == "https://api.marketstack.com/v2/exchanges/XNAS/eod/2026-09-29"
    assert params == [("symbols", "AAPL,MSFT"), ("limit", "5"), ("access_key", KEY)]
    assert response["params"] == {"endpoint": "/v2/exchanges/XNAS/eod/2026-09-29", "symbols": "AAPL,MSFT", "limit": "5"}
    assert KEY not in json.dumps(response)


def test_a_ticker_in_the_path_and_empty_optionals_dropped(keyed):
    pv, http = provider(ok(SAMPLES["ticker_eod"]))
    pv.query("ticker_eod", {"symbol": "BRK-B", "date_from": "", "sort": "ASC"})
    (url, params), = http.calls
    assert url == "https://api.marketstack.com/v2/tickers/BRK-B/eod" and params == [("sort", "ASC"), ("access_key", KEY)]


@pytest.mark.parametrize("value", ["../x", "a/b", "XN AS", "%2e%2e", "a?b=c", "a#b", "..", "-start", "a\\b", "x" * 65])
def test_a_path_value_that_could_change_the_path_is_refused_before_any_request(keyed, value):
    pv, http = provider(ok({}))
    with pytest.raises(ValueError, match="may contain only|too long"):
        pv.query("exchange_tickers", {"mic": value})
    assert http.calls == []


@pytest.mark.parametrize(
    ("endpoint", "params", "message"),
    [
        ("eod", {"symbols": "AAPL", "limit": "0"}, "at least 1"),
        ("eod", {"symbols": "AAPL", "limit": "1001"}, "at most 1000"),
        ("eod", {"symbols": "AAPL", "limit": "1.5"}, "whole number"),
        ("eod", {"symbols": "AAPL", "limit": "abc"}, "whole number"),
        ("eod", {"symbols": "AAPL", "offset": "-1"}, "at least 0"),
        ("eod", {"symbols": "AAPL", "date_from": "2026-13-01"}, "YYYY-MM-DD"),
        ("eod", {"symbols": "AAPL", "sort": "UP"}, "one of: DESC, ASC"),
        ("intraday", {"symbols": "AAPL", "after_hours": "yes"}, "true or false"),
        ("intraday", {"symbols": "AAPL", "interval": "2min"}, "one of: 1min"),
        ("eod", {"symbols": "AAPL", "access_key": "x"}, "set by the server"),
        ("eod", {"symbols": "AAPL", "bogus": "1"}, "Unknown parameter"),
        ("eod", {"symbols": ["AAPL", "MSFT"]}, "single value"),
        ("eod", {"symbols": "A" * 2001}, "too long"),
        ("eod_date", {"symbols": "AAPL", "date": "not-a-date"}, "YYYY-MM-DD"),
        ("companyratings", {"ticker": "AAPL", "rated": "strong"}, "one of: buy, sell, hold"),
    ],
)
def test_invalid_parameters_are_refused_with_a_plain_message_and_no_request(keyed, endpoint, params, message):
    pv, http = provider(ok({}))
    with pytest.raises(ValueError, match=message):
        pv.query(endpoint, params)
    assert http.calls == []


def test_a_long_symbol_list_and_boundary_numbers_are_accepted(keyed):
    pv, http = provider(ok(SAMPLES["eod"]))
    pv.query("eod", {"symbols": ",".join(["AAPL"] * 300), "limit": "1000", "offset": "0"})
    assert len(http.calls) == 1


# --- classifying what comes back --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("http_status", "type_", "code", "expected"),
    [
        (401, "invalid_access_key", 101, "invalid_key"),
        (401, "missing_access_key", 101, "invalid_key"),
        (401, "inactive_user", 102, "invalid_key"),
        (401, "account_on_hold", 107, "invalid_key"),
        (403, "api_access_blocked", 104, "invalid_key"),
        (403, "function_access_restricted", 105, "premium_required"),
        (403, "https_access_restricted", 105, "premium_required"),
        (429, "usage_limit_reached", 104, "rate_limited"),
        (429, "daily_usage_limit_reached", 104, "rate_limited"),
        (429, "fair_use_limit_reached", 104, "rate_limited"),
        (429, "rate_limit_reached", 106, "rate_limited"),
        (404, "404_not_found", 404, "invalid_request"),
        (404, "invalid_api_function", 103, "invalid_request"),
        (500, "internal_error", 0, "upstream_error"),
        (503, "maintenance_mode", 503, "upstream_error"),
        (403, "something_new", 105, "premium_required"),
        (429, "something_new", 104, "rate_limited"),
        (500, "something_new", "x", "upstream_error"),
        (418, "something_new", "x", "invalid_request"),
    ],
)
def test_every_documented_error_has_its_own_status_a_message_and_is_never_cached(keyed, http_status, type_, code, expected):
    body = error(type_, code, f"The provider said {type_}.")
    pv, http = provider(failure(http_status, body), ok(SAMPLES["eod"]))
    response = pv.query(*EOD_ARGS)
    assert response["status"] == expected and response["views"] == [] and response["raw"] is None
    assert type_ in response["message"]
    assert pv.query(*EOD_ARGS)["status"] == "ok" and len(http.calls) == 2  # the failure was not cached


def test_a_plan_that_lacks_the_endpoint_is_premium_required_and_nothing_is_drawn(keyed):
    body = error("function_access_restricted", 105, "Access Restricted - Your current Subscription Plan does not support this API Function.")
    response = provider(failure(403, body))[0].query("commodities", {"commodity_name": "gold"})
    assert response["status"] == "premium_required" and "Subscription Plan" in response["message"] and response["views"] == []


def test_validation_errors_carry_the_providers_context_messages(keyed):
    body = {"error": {"code": "validation_error", "message": "Request failed with validation error", "context": {"symbols": [{"key": "missing_symbols", "message": "You did not specify any symbols."}]}}}
    response = provider(failure(422, body))[0].query(*EOD_ARGS)
    assert response["status"] == "invalid_request" and "did not specify any symbols" in response["message"]


def test_a_bodyless_error_is_classified_by_its_http_status(keyed):
    for status, expected in ((502, "upstream_error"), (429, "rate_limited"), (401, "invalid_key"), (403, "premium_required")):
        response = provider(text("", status))[0].query(*EOD_ARGS)
        assert response["status"] == expected and f"HTTP {status}" in response["message"]


def test_classify_error_returns_none_for_data():
    assert classify_error(200, SAMPLES["eod"]) is None and classify_error(200, [1]) is None


@pytest.mark.parametrize(("payload", "expected"), [({}, False), ([], False), (None, False), ({"pagination": {"total": 0}, "data": []}, False), ({"status": {"code": 200}, "result": {}}, False), ({"data": {"eod": []}}, False), ({"data": [{"a": 1}]}, True), ([{"a": 1}], True), ({"data": {"name": "x", "eod": []}}, True)])
def test_has_data(payload, expected):
    assert has_data(payload) is expected


def test_an_empty_answer_is_empty_and_cached(keyed):
    pv, http = provider(ok({"pagination": {"limit": 100, "offset": 0, "count": 0, "total": 0}, "data": []}))
    first = pv.query(*EOD_ARGS)
    assert first["status"] == "empty" and first["views"] == []
    assert pv.query(*EOD_ARGS)["cached"] is True and len(http.calls) == 1


def test_a_ticker_with_metadata_but_no_rows_is_empty_not_drawn_as_a_blank_chart(keyed):
    payload = {"pagination": {"count": 0, "total": 0}, "data": {"name": "Apple Inc", "symbol": "AAPL", "eod": []}}
    response = provider(ok(payload))[0].query("ticker_eod", {"symbol": "AAPL"})
    assert response["status"] == "empty" and response["views"] == []


@pytest.mark.parametrize(
    ("raised", "fragment"),
    [(requests.Timeout(), "did not respond in time"), (requests.ConnectionError(), "network error"), (ValueError("too big"), "unexpectedly large")],
)
def test_transport_failures_are_upstream_errors_and_not_cached(keyed, raised, fragment):
    pv, http = provider(raised, ok(SAMPLES["eod"]))
    response = pv.query(*EOD_ARGS)
    assert response["status"] == "upstream_error" and fragment in response["message"]
    assert pv.query(*EOD_ARGS)["status"] == "ok" and len(http.calls) == 2


def test_an_unreadable_success_body_is_an_upstream_error(keyed):
    response = provider(text("<html>oops</html>", 200, "text/html"))[0].query(*EOD_ARGS)
    assert response["status"] == "upstream_error" and "could not be read" in response["message"]


# --- a good answer --------------------------------------------------------------------------------------------


def test_a_good_answer_has_views_the_raw_payload_and_the_request_that_was_sent(keyed):
    pv, _ = provider(ok(SAMPLES["eod"]))
    response = pv.query(*EOD_ARGS)
    assert response["status"] == "ok" and response["message"] is None and response["cached"] is False
    assert [v["kind"] for v in response["views"]][:1] == ["facts"] and "series" in [v["kind"] for v in response["views"]]
    assert response["raw"] == SAMPLES["eod"] and response["raw_omitted"] is None and response["params"] == {"endpoint": "/v2/eod", "symbols": "AAPL"}
    assert response["fetched_at"] is not None and response["bytes"] > 0 and pv.requests_this_session == 1


def test_a_large_response_omits_the_raw_payload_but_keeps_the_views(keyed, monkeypatch):
    from tradingview_data.providers import marketstack as ms

    monkeypatch.setattr(ms, "RAW_LIMIT_BYTES", 10)
    response = provider(ok(SAMPLES["eod"]))[0].query(*EOD_ARGS)
    assert response["status"] == "ok" and response["raw"] is None and response["views"]
    assert response["raw_omitted"]["bytes"] > 10 and "too large" in response["raw_omitted"]["reason"]


def test_paging_is_explained_when_more_rows_exist(keyed):
    payload = {"pagination": {"limit": 3, "offset": 0, "count": 3, "total": 250}, "data": EOD_ROWS}
    response = provider(ok(payload))[0].query("eod", {"symbols": "AAPL", "limit": "3"})
    assert any("3 of 250 rows from offset 0" in n for n in response["notes"])


def test_every_endpoint_answers_through_the_provider_with_views(keyed):
    required = {"mic": "XNAS", "symbols": "AAPL", "symbol": "AAPL", "ticker": "AAPL", "date": "2026-09-29", "commodity_name": "gold", "cik_code": "0001045810", "company_name": "NVIDIA", "index": "sp500", "country": "germany", "unit": "USD", "frame": "CY2023Q1I"}
    pv = Marketstack(http_get=FakeHttp())
    for endpoint in pv.catalog()["endpoints"]:
        params = {p["name"]: required[p["name"]] for p in endpoint["params"] if p["required"]}
        fake = FakeHttp(ok(SAMPLES[endpoint["id"]]))
        local = Marketstack(http_get=fake)
        response = local.query(endpoint["id"], params)
        assert response["status"] == "ok" and response["views"], endpoint["id"]
        json.dumps(response, allow_nan=False)
        assert fake.calls[0][0].startswith("https://api.marketstack.com/v2/") and "{" not in fake.calls[0][0]


# --- the key never leaks -----------------------------------------------------------------------------


def test_the_key_is_scrubbed_from_provider_messages_and_data(keyed):
    leaky = error("invalid_access_key", 101, f"Bad key {KEY}")
    response = provider(failure(401, leaky))[0].query(*EOD_ARGS)
    assert KEY not in json.dumps(response) and "***" in response["message"]
    echoing = {"pagination": {"count": 1, "total": 1}, "data": [{**EOD_ROWS[0], "name": f"x {KEY} y"}]}
    assert KEY not in json.dumps(provider(ok(echoing))[0].query(*EOD_ARGS))


def test_the_key_is_read_at_call_time_never_at_construction(monkeypatch):
    monkeypatch.delenv("MARKETSTACK_API_KEY", raising=False)
    pv, http = provider(ok(SAMPLES["eod"]))
    assert pv.query(*EOD_ARGS)["status"] == "not_configured"
    monkeypatch.setenv("MARKETSTACK_API_KEY", KEY)
    assert pv.query(*EOD_ARGS)["status"] == "ok" and http.calls[0][1][-1] == ("access_key", KEY)


# --- caching ----------------------------------------------------------------------------------------------------


def test_an_identical_second_call_is_served_from_cache_and_refresh_bypasses_it(keyed):
    pv, http = provider(ok(SAMPLES["eod"]))
    assert pv.query(*EOD_ARGS)["cached"] is False
    assert pv.query(*EOD_ARGS)["cached"] is True and len(http.calls) == 1
    assert pv.query(*EOD_ARGS, refresh=True)["cached"] is False and len(http.calls) == 2


def test_different_parameters_and_different_endpoints_are_cached_separately(keyed):
    pv, http = provider(ok(SAMPLES["eod"]), ok(SAMPLES["eod"]), ok(SAMPLES["eod_latest"]))
    pv.query("eod", {"symbols": "AAPL"})
    pv.query("eod", {"symbols": "MSFT"})
    pv.query("eod_latest", {"symbols": "AAPL"})
    assert len(http.calls) == 3


def test_the_cache_expires(keyed):
    now = [1000.0]
    pv, http = provider(ok(SAMPLES["eod"]), ok(SAMPLES["eod"]), clock=lambda: now[0], ttl_seconds=60)
    pv.query(*EOD_ARGS)
    now[0] += 59
    assert pv.query(*EOD_ARGS)["cached"] is True
    now[0] += 2
    assert pv.query(*EOD_ARGS)["cached"] is False and len(http.calls) == 2


def test_concurrent_identical_requests_make_one_upstream_call(keyed):
    gate = threading.Event()
    http = FakeHttp(ok(SAMPLES["eod"]), gate=gate)
    pv = Marketstack(http_get=http)
    results = []
    threads = [threading.Thread(target=lambda: results.append(pv.query(*EOD_ARGS))) for _ in range(4)]
    for t in threads:
        t.start()
    gate.set()
    for t in threads:
        t.join(5)
    assert len(results) == 4 and len(http.calls) == 1 and sorted(r["cached"] for r in results) == [False, True, True, True]


# --- the catalog generator ------------------------------------------------------------------------------


def test_the_committed_catalog_has_no_generator_warnings_and_every_operation():
    raw = Marketstack(http_get=FakeHttp())._load()
    assert raw["warnings"] == [] and {e["path"] for e in raw["endpoints"]} == set(docs.OPERATIONS)
    assert raw["source"] == INFO.docs_url and raw["plans"] == [p.name for p in INFO.plans]


def test_the_generator_assigns_plans_resolves_references_and_warns_about_surprises():
    spec = {
        "tags": [{"name": "End-of-Day Data", "description": "Daily **prices**."}],
        "paths": {
            "/v2/eod": {"get": {"tags": ["End-of-Day Data"], "summary": "End-of-Day Data", "description": "See [the list](https://x.test/a.csv) for `symbols`.", "parameters": [{"$ref": "#/components/parameters/Key"}, {"name": "symbols", "in": "query", "required": True, "schema": {"type": "string"}}, {"name": "sort", "in": "query", "schema": {"type": "string", "enum": ["DESC", "ASC", "desc", "asc"], "default": "DESC"}}, {"name": "limit", "in": "query", "schema": {"type": "integer", "minimum": 1, "maximum": 1000}}]}},
            "/v2/brand-new": {"get": {"tags": ["End-of-Day Data"], "summary": "New", "description": "", "parameters": []}},
        },
        "components": {"parameters": {"Key": {"name": "access_key", "in": "query", "required": True, "schema": {"type": "string"}}}},
    }
    catalog = docs.build_catalog(spec, ["gold"])
    (eod,) = catalog["endpoints"]
    assert eod["id"] == "eod" and eod["plan"] == "Free" and eod["premium"] is False and eod["description"] == "See the list for symbols."
    assert [p["name"] for p in eod["params"]] == ["symbols", "sort", "limit"] and eod["params"][1]["enum"] == ["DESC", "ASC"]
    assert (eod["params"][2]["type"], eod["params"][2]["maximum"]) == ("integer", 1000) and eod["examples"][0]["params"] == {"symbols": "AAPL"}
    assert catalog["categories"][0] == {"id": "end-of-day-data", "title": "End-of-Day Data", "summary": "Daily prices."}
    assert any("/v2/brand-new" in w and "skipped" in w for w in catalog["warnings"]) and any("no longer in the spec" in w for w in catalog["warnings"])


def test_commodity_names_are_read_from_the_workbook_without_the_header(tmp_path):
    sheet = '<worksheet><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row><row r="2"><c r="A2" t="s"><v>2</v></c><c r="B2" t="s"><v>3</v></c></row><row r="3"><c r="A3" t="s"><v>4</v></c></row></sheetData></worksheet>'
    strings = "<sst>" + "".join(f"<si><t>{s}</t></si>" for s in ["commodity_name", "commodity_unit", "aluminum", "usd/t", "crude oil"]) + "</sst>"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as book:
        book.writestr("xl/sharedStrings.xml", strings)
        book.writestr("xl/worksheets/sheet1.xml", sheet)
    path = tmp_path / "c.xlsx"
    path.write_bytes(buffer.getvalue())
    assert docs.commodity_names(path) == ["aluminum", "crude oil"]


# --- dates: the documented ISO-8601 form ----------------------------------------------------------------


DATED = ["exchange_eod_date", "exchange_intraday_date", "ticker_eod_date", "ticker_intraday_date", "eod_date", "intraday_date"]


def test_the_endpoints_that_document_iso_8601_take_a_datetime_in_their_path_and_say_so():
    raw = Marketstack(http_get=FakeHttp())._load()
    documented = sorted(e["id"] for e in raw["endpoints"] if "ISO-8601" in e["description"])
    assert documented == sorted(DATED)
    for e in raw["endpoints"]:
        path_dates = [p for p in e["params"] if p["name"] == "date" and p["in"] == "path"]
        assert [p["type"] for p in path_dates] == (["datetime"] if e["id"] in DATED else [])
        assert all("ISO-8601" in p["description"] for p in path_dates)
        for p in e["params"]:
            if p["name"] in ("date_from", "date_to"):
                assert p["type"] == "date"  # the spec documents only YYYY-MM-DD for these


@pytest.mark.parametrize(
    ("given", "path_tail"),
    [
        ("2026-09-29", "2026-09-29"),
        ("2020-05-21T00:00:00+0000", "2020-05-21T00%3A00%3A00%2B0000"),
        ("2020-05-21T00:00:00+00:00", "2020-05-21T00%3A00%3A00%2B00%3A00"),
        ("2020-05-21T09:30:15.123456-04:00", "2020-05-21T09%3A30%3A15.123456-04%3A00"),
        ("2020-05-21T00:00:00Z", "2020-05-21T00%3A00%3A00Z"),
        ("2020-05-21T09:30", "2020-05-21T09%3A30"),
    ],
)
def test_a_documented_iso_8601_date_reaches_marketstack_encoded_in_the_path(keyed, given, path_tail):
    pv, http = provider(ok(SAMPLES["eod_date"]))
    response = pv.query("eod_date", {"symbols": "AAPL", "date": given})
    assert response["status"] == "ok"
    assert http.calls[0][0] == "https://api.marketstack.com/v2/eod/" + path_tail and http.calls[0][1] == [("symbols", "AAPL"), ("access_key", KEY)]


@pytest.mark.parametrize(
    "given",
    ["2020-13-01", "2020-02-30", "2020-05-21T24:00:00", "2020-05-21T10:61", "2020-05-21T10:00:60", "2020-05-21T10:00:00+2500", "2020-05-21T10:00:00+0060", "2020-05-21 10:00:00", "20200521", "2020-05-21T", "2020-05-21T10:00:00 +0000", "2020-05-21/../x", "2020-05-21T10:00:00%2f", "2020-05-21?x=1", "2020-05-21#", "x"],
)
def test_a_malformed_date_or_one_that_could_change_the_path_is_refused_before_any_request(keyed, given):
    pv, http = provider(ok({}))
    with pytest.raises(ValueError, match="ISO-8601 timestamp"):
        pv.query("eod_date", {"symbols": "AAPL", "date": given})
    assert http.calls == []


def test_a_range_filter_still_takes_only_a_plain_date(keyed):
    pv, http = provider(ok({}))
    with pytest.raises(ValueError, match="date_from must be a date in YYYY-MM-DD format"):
        pv.query("eod", {"symbols": "AAPL", "date_from": "2020-05-21T00:00:00+0000"})
    assert http.calls == []


def test_valid_moment_checks_the_calendar_and_the_clock():
    assert valid_moment("2024-02-29") and not valid_moment("2023-02-29")
    assert valid_moment("2020-05-21T23:59:59") and not valid_moment("2020-05-21T23:59:60")
    assert valid_moment("2020-05-21T00:00:00-23:59") and not valid_moment("2020-05-21T00:00:00-24:00")


# --- examples are complete requests ---------------------------------------------------------------------


def test_every_example_is_a_complete_valid_request_so_choosing_one_leaves_fetch_usable():
    raw = Marketstack(http_get=FakeHttp())._load()
    for item in raw["endpoints"]:
        endpoint = {**item, "params": [{**p, "managed": False} for p in item["params"]]}
        required = [p for p in item["params"] if p["required"]]
        for example in item["examples"]:
            assert {p["name"] for p in required} <= set(example["params"]), (item["id"], example["caption"])
            validate_params(endpoint, example["params"])
        if not item["examples"] and required:
            assert any(not p["example"] for p in required), item["id"]  # no example only where the docs give no value


def test_the_dated_endpoints_have_examples_with_a_date_and_the_caption_shows_it():
    endpoints = {e["id"]: e for e in Marketstack(http_get=FakeHttp()).catalog()["endpoints"]}
    for endpoint_id in DATED:
        for example in endpoints[endpoint_id]["examples"]:
            assert "date" in example["params"] and f"date={example['params']['date']}" in example["caption"]
        assert len(endpoints[endpoint_id]["examples"]) == 2


def test_endpoints_whose_required_values_the_documentation_does_not_give_offer_no_example():
    endpoints = {e["id"]: e for e in Marketstack(http_get=FakeHttp()).catalog()["endpoints"]}
    assert endpoints["indexinfo"]["examples"] == [] and endpoints["bond"]["examples"] == []


@pytest.mark.parametrize(("today", "expected"), [(date(2026, 10, 1), "2026-09-30"), (date(2026, 10, 5), "2026-10-02"), (date(2026, 10, 4), "2026-10-02"), (date(2026, 10, 3), "2026-10-02"), (date(2026, 10, 6), "2026-10-05")])
def test_the_sample_day_is_the_latest_weekday_before_today(today, expected):
    assert docs.sample_day(today) == expected


def test_the_generator_gives_a_date_endpoint_a_datetime_and_a_sample_day_only_when_iso_is_documented():
    def spec(description):
        return {
            "tags": [{"name": "End-of-Day Data"}],
            "paths": {"/v2/eod/{date}": {"get": {"tags": ["End-of-Day Data"], "summary": "S", "description": description, "parameters": [{"name": "symbols", "in": "query", "required": True, "schema": {"type": "string"}}, {"name": "date", "in": "path", "required": True, "description": "Date in YYYY-MM-DD format.", "schema": {"type": "string"}}]}}},
        }

    iso = docs.build_catalog(spec("Given in YYYY-MM-DD or full ISO-8601 format."), today=date(2026, 10, 5))["endpoints"][0]
    plain = docs.build_catalog(spec("Given as YYYY-MM-DD."), today=date(2026, 10, 5))["endpoints"][0]
    date_param = next(p for p in iso["params"] if p["name"] == "date")
    assert (date_param["type"], date_param["example"]) == ("datetime", "2026-10-02") and docs.ISO_NOTE in date_param["description"]
    assert iso["examples"][0]["params"] == {"date": "2026-10-02", "symbols": "AAPL"}
    assert next(p for p in plain["params"] if p["name"] == "date")["type"] == "date"


# --- cached answers belong to the key that fetched them -------------------------------------------------


def test_a_cached_answer_is_never_served_to_a_different_key(keyed, monkeypatch):
    pv, http = provider(ok(SAMPLES["eod"]), ok(SAMPLES["eod"]))
    assert pv.query(*EOD_ARGS)["cached"] is False
    monkeypatch.setenv("MARKETSTACK_API_KEY", "another-key-0123456789")
    other = pv.query(*EOD_ARGS)
    assert other["cached"] is False and len(http.calls) == 2 and http.calls[1][1][-1] == ("access_key", "another-key-0123456789")
    monkeypatch.setenv("MARKETSTACK_API_KEY", KEY)
    assert pv.query(*EOD_ARGS)["cached"] is True and len(http.calls) == 2  # the first key's answer is still its own


def test_the_key_is_never_part_of_a_cache_key(keyed):
    pv, _ = provider(ok(SAMPLES["eod"]))
    pv.query(*EOD_ARGS)
    assert pv._cache._items and all(KEY not in k for k in pv._cache._items)
