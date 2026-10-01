"""Alpaca provider: the catalog and its tier labels, request building, headers, error classification, credential safety, caching."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
import requests

from tradingview_data.providers import alpaca_docs as docs
from tradingview_data.providers.alpaca import BASE_URL, INFO, Alpaca, classify_error, has_data
from tradingview_data.providers.common import default_http_get, validate_params
from tradingview_data.providers.marketstack import Marketstack

from alpaca_support import KEY_ID, PAYLOADS, SECRET, FakeHttp, failure, html, ok


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("test attempted a real network request")

    monkeypatch.setattr(requests, "get", refuse)
    monkeypatch.setattr(requests.Session, "request", refuse)


@pytest.fixture
def keyed(monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY_ID", KEY_ID)
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", SECRET)


@pytest.fixture
def unkeyed(monkeypatch):
    monkeypatch.delenv("ALPACA_API_KEY_ID", raising=False)
    monkeypatch.delenv("ALPACA_API_SECRET_KEY", raising=False)


def provider(*script, **kwargs):
    http = FakeHttp(*script)
    return Alpaca(http_get=http, **kwargs), http


def at(year, month, day):
    return lambda: datetime(year, month, day, 12, tzinfo=timezone.utc).timestamp()


BARS_ARGS = ("stock_bars", {"symbols": "AAPL", "timeframe": "1Day"})


# --- the committed catalog and its tier labels -----------------------------------------------------------------


def test_the_catalog_covers_every_market_data_endpoint_and_labels_each_with_its_plan():
    catalog = Alpaca().catalog()
    endpoints = catalog["endpoints"]
    assert len(endpoints) == len({e["id"] for e in endpoints}) == 42
    assert [p.name for p in INFO.plans] == ["Basic", "Algo Trader Plus"]
    assert {e["plan"] for e in endpoints} == {"Basic"} and not any(e["premium"] for e in endpoints)
    assert all(e["request_cost"] == 1 and e["doc_url"].startswith("https://docs.alpaca.markets/us/reference/") for e in endpoints)
    counts = {c["title"]: c["count"] for c in catalog["categories"]}
    assert counts == {"Stocks": 18, "Options": 8, "Crypto": 8, "Forex": 2, "Fixed income": 2, "Screener": 2, "News": 1, "Corporate actions": 1}
    assert sum(c["premium_count"] for c in catalog["categories"]) == 0


def test_each_plan_states_its_price_rate_limit_and_feeds():
    basic, plus = INFO.plans
    for words in ("Free", "200 API calls a minute", "IEX", "15 minutes", "indicative"):
        assert words in basic.summary
    for words in ("$99 a month", "10,000 API calls a minute", "SIP", "OPRA"):
        assert words in plus.summary
    assert INFO.key_env == "ALPACA_API_KEY_ID" and INFO.secret_env == "ALPACA_API_SECRET_KEY"


def endpoint_params(catalog, rule):
    raw = json.loads(docs.CATALOG_PATH.read_text(encoding="utf-8"))
    public = {e["id"]: e for e in catalog["endpoints"]}
    return [(public[e["id"]], e["tier_rule"]) for e in raw["endpoints"] if e["tier_rule"] == rule]


def param(endpoint, name):
    return next(p for p in endpoint["params"] if p["name"] == name)


def test_stock_feeds_name_the_plan_that_unlocks_them():
    catalog = Alpaca().catalog()
    latest = endpoint_params(catalog, "stock_latest")
    assert len(latest) == 8
    for endpoint, _ in latest:
        feed = param(endpoint, "feed")
        assert feed["premium_values"] == ["sip", "otc"] and "Algo Trader Plus" in feed["enum_labels"]["sip"] and "Basic" in feed["enum_labels"]["iex"]
        assert "Broker API partners only" in feed["enum_labels"]["otc"] and "IEX only" in feed["premium_note"] and feed["default"] is None
        assert endpoint["premium_notes"] == ["Basic gets the IEX feed. Algo Trader Plus adds the SIP feed with every US exchange."]


def test_historical_requests_explain_the_fifteen_minute_limit_on_basic():
    catalog = Alpaca().catalog()
    stock = endpoint_params(catalog, "stock_history")
    assert len(stock) == 8
    for endpoint, _ in stock:
        assert "15 minutes" in param(endpoint, "end")["premium_note"] and "Algo Trader Plus" in param(endpoint, "end")["premium_note"]
        feed = param(endpoint, "feed")
        assert feed["premium_values"] == ["otc"] and feed["default"] == "sip" and "Basic" in feed["enum_labels"]["iex"]
        assert "Basic reads SIP data once it is 15 minutes old" in endpoint["premium_notes"][0] and "10,000 calls a minute" in endpoint["premium_notes"][0]
    options = endpoint_params(catalog, "option_history")
    assert [e["id"] for e, _ in options] == ["option_bars", "option_trades"]
    assert all("15 minutes" in param(e, "end")["premium_note"] and not any(p["name"] == "feed" for p in e["params"]) for e, _ in options)


def test_option_feeds_name_the_plan_that_unlocks_opra():
    for endpoint, _ in endpoint_params(Alpaca().catalog(), "option_latest"):
        feed = param(endpoint, "feed")
        assert feed["enum"] == ["opra", "indicative"] and feed["premium_values"] == ["opra"]
        assert feed["enum_labels"] == {"opra": "OPRA, real time · Algo Trader Plus", "indicative": "Indicative · Basic"}
        assert "indicative feed" in feed["premium_note"] and "Algo Trader Plus" in feed["premium_note"]


def test_endpoints_with_no_documented_tier_carry_no_tier_text():
    catalog = Alpaca().catalog()
    plain = [e for e in catalog["endpoints"] if e["id"].startswith(("crypto", "news", "movers", "most_actives", "corporate", "forex", "fixed_income", "stock_conditions", "stock_exchanges", "option_conditions", "option_exchanges"))]
    assert len(plain) == 20
    assert all(e["premium_notes"] == [] and all(p["premium_note"] is None and p["premium_values"] == [] for p in e["params"]) for e in plain)


def test_premium_values_are_always_choices_the_parameter_offers():
    for endpoint in Alpaca().catalog()["endpoints"]:
        for p in endpoint["params"]:
            assert set(p["premium_values"]) <= set(p["enum"]) and set(p["enum_labels"]) <= set(p["enum"])
            if p["premium_values"]:
                assert p["premium_note"]


def test_dropdown_values_get_short_labels_from_the_documentation():
    crypto = next(e for e in Alpaca().catalog()["endpoints"] if e["id"] == "crypto_bars")
    assert param(crypto, "loc")["enum_labels"] == {"us": "Alpaca US", "us-1": "Kraken US", "eu-1": "Kraken EU"}
    actions = next(e for e in Alpaca().catalog()["endpoints"] if e["id"] == "corporate_actions")
    assert param(actions, "region")["enum_labels"]["non_us"] == "only non-US corporate actions"


def test_the_public_catalog_hides_paths_and_keeps_every_path_parameter_declared():
    catalog = Alpaca().catalog()
    assert all("path" not in e and "tier_rule" not in e and all("in" not in p for p in e["params"]) for e in catalog["endpoints"])
    raw = json.loads(docs.CATALOG_PATH.read_text(encoding="utf-8"))
    for endpoint in raw["endpoints"]:
        placeholders = {part[1:-1] for part in endpoint["path"].split("/") if part.startswith("{")}
        declared = {p["name"] for p in endpoint["params"] if p["in"] == "path"}
        assert placeholders == declared and all(p["required"] for p in endpoint["params"] if p["in"] == "path")
        assert not any(p["in"] == "header" for p in endpoint["params"])


def test_every_example_is_a_complete_valid_request():
    alpaca = Alpaca(clock=at(2026, 9, 30))
    for endpoint in alpaca.catalog()["endpoints"]:
        required = {p["name"] for p in endpoint["params"] if p["required"]}
        for example in endpoint["examples"]:
            assert required <= set(example["params"]), endpoint["id"]
            assert "@sample" not in json.dumps(example)
            validate_params(alpaca._endpoint(endpoint["id"]), example["params"], long_text=("symbols",))


def test_examples_use_a_recent_trading_day_and_follow_the_clock():
    def bars_example(clock):
        endpoint = next(e for e in Alpaca(clock=clock).catalog()["endpoints"] if e["id"] == "stock_bars")
        return endpoint["examples"][0]["params"]

    assert bars_example(at(2026, 9, 30)) == {"symbols": "AAPL", "timeframe": "1Day", "start": "2026-08-30", "end": "2026-09-29"}
    assert bars_example(at(2026, 9, 28))["end"] == "2026-09-25"  # the Friday before a Monday
    alpaca = Alpaca(clock=at(2026, 9, 30))
    assert alpaca.catalog() is alpaca.catalog()


def test_the_summary_names_both_credentials_and_the_plans():
    summary = Alpaca().summary()
    assert (summary["id"], summary["endpoint_count"], summary["premium_count"]) == ("alpaca", 42, 0)
    assert (summary["key_env"], summary["secret_env"]) == ("ALPACA_API_KEY_ID", "ALPACA_API_SECRET_KEY")
    assert [p["name"] for p in summary["plans"]] == ["Basic", "Algo Trader Plus"]
    assert Marketstack().summary()["secret_env"] is None


# --- credentials ---------------------------------------------------------------------------------------------------------


def test_both_credentials_are_needed_and_the_message_names_only_what_is_missing(monkeypatch, unkeyed):
    alpaca, http = provider(ok(PAYLOADS["stock_bars"]))
    assert alpaca.configured() is False
    both = alpaca.query(*BARS_ARGS)
    assert both["status"] == "not_configured" and "ALPACA_API_KEY_ID and ALPACA_API_SECRET_KEY" in both["message"] and both["fetched_at"] is None
    monkeypatch.setenv("ALPACA_API_KEY_ID", KEY_ID)
    assert alpaca.configured() is False
    only_key = alpaca.query(*BARS_ARGS)
    assert "ALPACA_API_SECRET_KEY" in only_key["message"] and "ALPACA_API_KEY_ID" not in only_key["message"]
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", SECRET)
    assert alpaca.configured() is True
    assert http.calls == []


def test_the_credentials_go_only_into_the_headers(keyed):
    alpaca, http = provider(ok(PAYLOADS["stock_bars"]))
    response = alpaca.query("stock_bars", {"symbols": "AAPL,TSLA", "timeframe": "1Day", "limit": "5"})
    ((url, query, headers),) = http.calls
    assert url == BASE_URL + "/v2/stocks/bars" and headers == {"APCA-API-KEY-ID": KEY_ID, "APCA-API-SECRET-KEY": SECRET}
    assert query == [("symbols", "AAPL,TSLA"), ("timeframe", "1Day"), ("limit", "5")]
    assert response["params"] == {"endpoint": "/v2/stocks/bars", "symbols": "AAPL,TSLA", "timeframe": "1Day", "limit": "5"}
    assert KEY_ID not in json.dumps(response) and SECRET not in json.dumps(response)


def test_a_credential_echoed_by_the_provider_is_scrubbed_everywhere(keyed):
    payload = {**PAYLOADS["stock_bars"], "debug": f"{KEY_ID}/{SECRET}"}
    alpaca, _ = provider(ok(payload), failure(403, {"message": f"bad {KEY_ID} or {SECRET}"}))
    good = alpaca.query(*BARS_ARGS, refresh=True)
    assert good["raw"]["debug"] == "***/***"
    bad = alpaca.query(*BARS_ARGS, refresh=True)
    assert bad["status"] == "invalid_key" and KEY_ID not in json.dumps(bad) and SECRET not in json.dumps(bad)


def test_the_shared_http_layer_adds_headers_to_the_defaults(monkeypatch):
    seen = {}

    class Response:
        status_code = 200
        headers = {"content-type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def iter_content(self, chunk_size):
            yield b"{}"

    def fake_get(url, **kwargs):
        seen.update(kwargs)
        return Response()

    monkeypatch.setattr(requests, "get", fake_get)
    result = default_http_get("https://data.alpaca.markets/x", [("a", "1")], {"APCA-API-KEY-ID": "k"})
    assert result.status == 200 and result.body == b"{}"
    assert seen["headers"]["APCA-API-KEY-ID"] == "k" and seen["headers"]["User-Agent"].startswith("tradingview-data-grabber/")
    assert seen["allow_redirects"] is False and seen["params"] == [("a", "1")]
    default_http_get("https://data.alpaca.markets/x", [])
    assert set(seen["headers"]) == {"User-Agent", "Accept"}


# --- parameters ----------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "endpoint_id, params, problem",
    [
        ("stock_bars", {"symbols": "AAPL"}, "timeframe is required"),
        ("stock_bars", {"timeframe": "1Day"}, "symbols is required"),
        ("stock_bars", {"symbols": "AAPL", "timeframe": "1Day", "apikey": "x"}, "Unknown parameter"),
        ("stock_bars", {"symbols": "AAPL", "timeframe": "1Day", "APCA-API-KEY-ID": "x"}, "set by the server"),
        ("stock_bars", {"symbols": "AAPL", "timeframe": "1Day", "limit": "0"}, "at least 1"),
        ("stock_bars", {"symbols": "AAPL", "timeframe": "1Day", "limit": "10001"}, "at most 10000"),
        ("stock_bars", {"symbols": "AAPL", "timeframe": "1Day", "limit": "5.5"}, "whole number"),
        ("stock_bars", {"symbols": "AAPL", "timeframe": "1Day", "start": "last week"}, "ISO-8601"),
        ("stock_bars", {"symbols": "AAPL", "timeframe": "1Day", "feed": "nasdaq"}, "must be one of"),
        ("stock_bars", {"symbols": "AAPL", "timeframe": "1Day", "sort": "up"}, "must be one of"),
        ("stock_bars", {"symbols": ["AAPL", "TSLA"], "timeframe": "1Day"}, "single value"),
        ("stock_bars", {"symbols": "A" * 2001, "timeframe": "1Day"}, "too long"),
        ("stock_bars_single", {"symbol": "AAPL/../../v2", "timeframe": "1Day"}, "may contain only"),
        ("stock_bars_single", {"symbol": "AAPL?x=1", "timeframe": "1Day"}, "may contain only"),
        ("crypto_bars", {"loc": "mars", "symbols": "BTC/USD", "timeframe": "1Day"}, "must be one of"),
        ("news", {"include_content": "yes"}, "true or false"),
        ("news", {"limit": "51"}, "at most 50"),
        ("option_chain", {"underlying_symbol": "AAPL", "strike_price_gte": "cheap"}, "a number"),
        ("option_chain", {"underlying_symbol": "AAPL", "expiration_date": "2026-13-01"}, "YYYY-MM-DD"),
        ("movers", {"market_type": "bonds"}, "must be one of"),
    ],
)
def test_invalid_requests_are_refused_before_any_request_is_made(keyed, endpoint_id, params, problem):
    alpaca, http = provider(ok({}))
    with pytest.raises(ValueError, match=problem):
        alpaca.query(endpoint_id, params)
    assert http.calls == []


def test_an_unknown_endpoint_is_a_key_error(keyed):
    with pytest.raises(KeyError):
        provider(ok({}))[0].query("no_such_endpoint", {})


@pytest.mark.parametrize("moment", ["2026-09-29", "2026-09-29T13:30:00Z", "2026-09-29T09:30:00-04:00", "2026-09-29T13:30:00.123456789Z", "2024-01-04T00:00:00.5+0000"])
def test_dates_and_rfc3339_timestamps_with_nanoseconds_are_accepted(keyed, moment):
    alpaca, http = provider(ok(PAYLOADS["stock_bars"]))
    assert alpaca.query("stock_bars", {"symbols": "AAPL", "timeframe": "1Min", "start": moment, "end": moment})["status"] == "ok"
    assert dict(http.calls[0][1])["start"] == moment


def test_path_parameters_fill_the_url_and_empty_optional_values_are_dropped(keyed):
    alpaca, http = provider(ok(PAYLOADS["stock_bars_single"]), ok(PAYLOADS["crypto_bars"]))
    alpaca.query("stock_bars_single", {"symbol": "BRK.B", "timeframe": "1Day", "limit": "  ", "start": ""})
    alpaca.query("crypto_bars", {"loc": "us-1", "symbols": "BTC/USD", "timeframe": "1Day"})
    assert http.calls[0][0] == BASE_URL + "/v2/stocks/BRK.B/bars" and http.calls[0][1] == [("timeframe", "1Day")]
    assert http.calls[1][0] == BASE_URL + "/v1beta3/crypto/us-1/bars" and ("symbols", "BTC/USD") in http.calls[1][1]


# --- answers ----------------------------------------------------------------------------------------------------------


def test_a_good_answer_has_views_raw_data_and_timing_and_nothing_secret(keyed):
    alpaca, _ = provider(ok(PAYLOADS["stock_bars"]))
    response = alpaca.query(*BARS_ARGS)
    assert response["status"] == "ok" and response["provider"] == "alpaca" and response["endpoint"] == "stock_bars" and response["title"] == "Stock historical bars"
    assert response["raw"] == PAYLOADS["stock_bars"] and response["raw_omitted"] is None and response["bytes"] > 0 and response["cached"] is False
    assert [v["kind"] for v in response["views"]] == ["facts", "series", "series", "table"]
    assert alpaca.requests_this_session == 1


@pytest.mark.parametrize(
    "result, status, words",
    [
        (html(401), "invalid_key", "refused the credentials (HTTP 401)"),
        (failure(403, {"message": "forbidden."}), "invalid_key", "refused the credentials (HTTP 403): forbidden"),
        (failure(403, {"code": 40310000, "message": "subscription does not permit querying recent SIP data"}), "premium_required", "Algo Trader Plus"),
        (failure(422, {"code": 42210000, "message": "subscription does not permit querying recent SIP data"}), "premium_required", "IEX feed"),
        (failure(400, {"code": 40010001, "message": "invalid symbol: !!"}), "invalid_request", "invalid symbol"),
        (failure(404, {"message": "not found"}), "invalid_request", "not found"),
        (failure(429, {"message": "too many requests."}), "rate_limited", "200 calls a minute"),
        (failure(500, {"message": "internal server error"}), "upstream_error", "internal server error"),
        (html(502), "upstream_error", "HTTP 502"),
        (html(418), "invalid_request", "HTTP 418"),
    ],
)
def test_every_refusal_becomes_a_status_and_a_plain_message(keyed, result, status, words):
    response = provider(result)[0].query(*BARS_ARGS)
    assert response["status"] == status and words in response["message"]
    assert response["views"] == [] and response["raw"] is None


def test_a_subscription_refusal_names_the_plan_that_would_allow_it(keyed):
    response = provider(failure(403, {"message": "subscription does not permit querying recent SIP data"}))[0].query("stock_latest_trades", {"symbols": "AAPL", "feed": "sip"})
    assert response["status"] == "premium_required"
    assert response["message"].startswith("subscription does not permit querying recent SIP data. This needs the Algo Trader Plus plan.")
    assert "use the IEX feed (stocks) or the indicative feed (options)" in response["message"]


def test_the_error_classifier_reads_data_and_failures_alike():
    assert classify_error(200, {"bars": {}}) is None
    assert classify_error(200, None) is None
    assert classify_error(403, {"message": "Subscription required"})[0] == "premium_required"
    assert classify_error(401, None)[0] == "invalid_key"
    assert classify_error(503, None)[0] == "upstream_error"
    assert classify_error(400, {"message": ""}) == ("invalid_request", "Alpaca answered with HTTP 400.")


@pytest.mark.parametrize(
    "error, words",
    [(requests.Timeout(), "did not respond in time"), (ValueError("response too large"), "unexpectedly large"), (requests.ConnectionError("dns failure"), "network error")],
)
def test_network_trouble_is_an_upstream_error_not_an_exception(keyed, error, words):
    response = provider(error)[0].query(*BARS_ARGS)
    assert response["status"] == "upstream_error" and words in response["message"]


def test_a_200_that_is_not_json_is_an_upstream_error(keyed):
    response = provider(requests_text("<html>maintenance</html>"))[0].query(*BARS_ARGS)
    assert response["status"] == "upstream_error" and "could not be read" in response["message"]


def requests_text(body):
    from tradingview_data.providers.common import HttpResult

    return HttpResult(200, body.encode(), "text/html")


@pytest.mark.parametrize("payload", [{"bars": {}, "next_page_token": None}, {"bars": [], "symbol": "AAPL", "next_page_token": None}, {"news": [], "next_page_token": None}, {"gainers": [], "losers": [], "last_updated": "x", "market_type": "stocks"}, [], None])
def test_answers_with_nothing_in_them_are_empty_not_ok(keyed, payload):
    response = provider(ok(payload))[0].query(*BARS_ARGS)
    assert response["status"] == "empty" and "no data" in response["message"] and response["views"] == []


def test_has_data_ignores_paging_and_labels():
    assert has_data({"bars": {"AAPL": [{}]}}) and has_data({"A": "Regular Sale"})
    assert not has_data({"next_page_token": "x", "symbol": "AAPL", "bars": []}) and not has_data({"bars": {"AAPL": []}})


def test_a_next_page_token_becomes_a_note_telling_the_user_what_to_do(keyed):
    response = provider(ok(PAYLOADS["stock_bars"]))[0].query("stock_bars", {"symbols": "AAPL,TSLA", "timeframe": "1Day", "feed": "iex", "end": "2026-09-29"})
    assert response["notes"] == ["More data is available. Set page_token to PAGE2 and fetch again to read the next page."]


def test_when_the_plan_decides_the_feed_or_the_end_the_answer_says_how(keyed):
    alpaca, _ = provider(ok(PAYLOADS["stock_latest_trades"]), ok(PAYLOADS["stock_latest_trades"]), ok(PAYLOADS["stock_bars"]), ok(PAYLOADS["option_latest_quotes"]))
    left_blank = alpaca.query("stock_latest_trades", {"symbols": "AAPL"})
    assert left_blank["notes"] == ["No feed was chosen, so Alpaca used the best one your plan allows: SIP with Algo Trader Plus, IEX on Basic."]
    chosen = alpaca.query("stock_latest_trades", {"symbols": "AAPL", "feed": "iex"})
    assert chosen["notes"] == []
    history = alpaca.query("stock_bars", {"symbols": "AAPL", "timeframe": "1Day"})
    assert history["notes"][0] == "No end was given, so Alpaca ended the range at the latest data your plan allows: now with Algo Trader Plus, 15 minutes ago on Basic."
    options = alpaca.query("option_latest_quotes", {"symbols": "AAPL260116C00250000"})
    assert "OPRA with Algo Trader Plus, the indicative feed on Basic" in options["notes"][0]


def test_a_huge_answer_keeps_its_views_but_not_its_raw_json(keyed):
    big = {"bars": {"AAPL": [{"t": f"2026-01-{day:02d}T00:00:00Z", "o": 1, "h": 2, "l": 0, "c": 1, "v": 1, "pad": "x" * 500} for day in range(1, 29)] * 40}}
    response = provider(ok(big))[0].query(*BARS_ARGS)
    assert response["status"] == "ok" and response["raw"] is None and response["raw_omitted"]["bytes"] > 400 * 1024 and response["views"]


# --- caching ---------------------------------------------------------------------------------------------------------


def test_identical_requests_are_answered_from_memory_until_the_entry_expires_or_is_refreshed(keyed):
    now = [1000.0]
    alpaca, http = provider(ok(PAYLOADS["stock_bars"]), ok(PAYLOADS["stock_bars"]), ok(PAYLOADS["stock_bars"]), clock=lambda: now[0])
    assert alpaca.query(*BARS_ARGS)["cached"] is False
    assert alpaca.query(*BARS_ARGS)["cached"] is True and len(http.calls) == 1
    assert alpaca.query("stock_bars", {"symbols": "AAPL", "timeframe": "1Week"})["cached"] is False
    assert alpaca.query(*BARS_ARGS, refresh=True)["cached"] is False and len(http.calls) == 3
    now[0] += 31  # real-time data: the entry only lives 30 seconds
    alpaca.query(*BARS_ARGS)
    assert len(http.calls) == 4


def test_a_changed_credential_never_reads_what_another_one_fetched(monkeypatch, keyed):
    alpaca, http = provider(ok(PAYLOADS["stock_bars"]))
    alpaca.query(*BARS_ARGS)
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", SECRET + "-rotated")
    assert alpaca.query(*BARS_ARGS)["cached"] is False and len(http.calls) == 2
    assert http.calls[1][2]["APCA-API-SECRET-KEY"].endswith("-rotated")


def test_only_successful_answers_are_remembered(keyed):
    alpaca, http = provider(failure(429, {"message": "too many requests."}), ok(PAYLOADS["stock_bars"]))
    assert alpaca.query(*BARS_ARGS)["status"] == "rate_limited"
    assert alpaca.query(*BARS_ARGS)["status"] == "ok" and len(http.calls) == 2
    empty, http2 = provider(ok({"bars": {}}))
    assert empty.query(*BARS_ARGS)["status"] == "empty" and empty.query(*BARS_ARGS)["cached"] is True and len(http2.calls) == 1
