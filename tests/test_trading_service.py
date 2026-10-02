"""The trading client and service against a stateful fake of Alpaca: credentials, environments, errors and every operation."""

from __future__ import annotations

import json
import os
import stat

import pytest
import requests

from tradingview_data.providers.common import HttpResult
from tradingview_data.trading.client import ENVIRONMENTS, LIVE, PAPER, TradingClient, classify
from tradingview_data.trading.service import TradingBlocked, TradingService
from tradingview_data.trading.validation import TradingInputError

from trading_support import DATA_HOST, KEY, LIVE_HOST, PAPER_HOST, SECRET, FakeBroker, refusal, reply, uid

LIVE_KEY, LIVE_SECRET = "PKLIVEKEYID0123456789AB", "live-secret-0123456789-abcdefghijklmnop"


def service(broker=None, env=None, **kwargs):
    broker = broker or FakeBroker()
    values = {"ALPACA_PAPER_API_KEY_ID": KEY, "ALPACA_PAPER_API_SECRET_KEY": SECRET} if env is None else env
    return TradingService(http=broker, getenv=values.get, **kwargs), broker


def market(symbol="AAPL", qty="10", side="buy", **extra):
    return {"symbol": symbol, "side": side, "type": "market", "time_in_force": "day", "qty": qty, **extra}


def limit(symbol="AAPL", qty="5", price="200", side="buy", **extra):
    return {"symbol": symbol, "side": side, "type": "limit", "time_in_force": "gtc", "qty": qty, "limit_price": price, **extra}


# --- credentials and environments ------------------------------------------------------------------------


def client(env, **values):
    return TradingClient(env, http=FakeBroker(), getenv=values.get)


def test_paper_uses_its_own_keys_then_the_market_data_pair_and_never_mixes_two_pairs():
    own = client(PAPER, ALPACA_PAPER_API_KEY_ID="own-key", ALPACA_PAPER_API_SECRET_KEY="own-secret", ALPACA_API_KEY_ID="data-key", ALPACA_API_SECRET_KEY="data-secret")
    assert own.credentials() == ("own-key", "own-secret")
    assert client(PAPER, ALPACA_API_KEY_ID="data-key", ALPACA_API_SECRET_KEY="data-secret").credentials() == ("data-key", "data-secret")
    mixed = client(PAPER, ALPACA_PAPER_API_KEY_ID="own-key", ALPACA_API_KEY_ID="data-key", ALPACA_API_SECRET_KEY="data-secret")
    assert mixed.credentials() == ("data-key", "data-secret")  # a key is never paired with another pair's secret
    assert client(PAPER, ALPACA_PAPER_API_KEY_ID="only-a-key").credentials() == ("", "") and not client(PAPER, ALPACA_PAPER_API_KEY_ID=" ", ALPACA_PAPER_API_SECRET_KEY="x").configured()


def test_live_keys_come_only_from_live_variables_and_live_must_be_switched_on():
    from_data_pair = client(LIVE, ALPACA_API_KEY_ID="data-key", ALPACA_API_SECRET_KEY="data-secret", ALPACA_PAPER_API_KEY_ID="p", ALPACA_PAPER_API_SECRET_KEY="p")
    assert from_data_pair.credentials() == ("", "") and not from_data_pair.configured()
    keyed = client(LIVE, ALPACA_LIVE_API_KEY_ID="live-key", ALPACA_LIVE_API_SECRET_KEY="live-secret")
    assert keyed.configured() and not keyed.enabled()
    for on in ("1", "true", "TRUE", "yes", "on"):
        assert client(LIVE, ALPACA_ENABLE_LIVE_TRADING=on).enabled()
    for off in ("", "0", "false", "no", "maybe"):
        assert not client(LIVE, ALPACA_ENABLE_LIVE_TRADING=off).enabled()
    assert client(PAPER).enabled()
    assert (PAPER.real_money, LIVE.real_money) == (False, True) and set(ENVIRONMENTS) == {"paper", "live"}
    assert PAPER.base_url == f"https://{PAPER_HOST}" and LIVE.base_url == f"https://{LIVE_HOST}"


def test_the_environment_list_says_what_is_ready_and_never_shows_a_key():
    svc, broker = service(env={"ALPACA_PAPER_API_KEY_ID": KEY, "ALPACA_PAPER_API_SECRET_KEY": SECRET, "ALPACA_LIVE_API_KEY_ID": LIVE_KEY, "ALPACA_LIVE_API_SECRET_KEY": LIVE_SECRET})
    listed = svc.environments()
    paper, live = listed["environments"]
    assert listed["default"] == "paper" and (paper["id"], paper["configured"], paper["enabled"], paper["real_money"], paper["note"]) == ("paper", True, True, False, None)
    assert (live["id"], live["configured"], live["enabled"], live["real_money"]) == ("live", True, False, True)
    assert "ALPACA_ENABLE_LIVE_TRADING=true" in live["note"] and live["key_env"] == "ALPACA_LIVE_API_KEY_ID" and paper["fallback_key_env"] == "ALPACA_API_KEY_ID"
    text = json.dumps(listed)
    assert all(secret not in text for secret in (KEY, SECRET, LIVE_KEY, LIVE_SECRET)) and broker.calls == []


def test_a_switched_off_live_environment_refuses_everything_without_a_request():
    svc, broker = service(env={"ALPACA_LIVE_API_KEY_ID": LIVE_KEY, "ALPACA_LIVE_API_SECRET_KEY": LIVE_SECRET})
    for action in (lambda: svc.account("live"), lambda: svc.place_order("live", market()), lambda: svc.cancel_all_orders("live"), lambda: svc.positions("live")):
        with pytest.raises(TradingBlocked, match="ALPACA_ENABLE_LIVE_TRADING=true"):
            action()
    with pytest.raises(KeyError):
        svc.account("demo")
    assert broker.calls == []


def test_each_environment_sends_its_own_keys_to_its_own_host_and_never_the_other_pairs_keys():
    broker = FakeBroker()
    live_broker = FakeBroker(key=LIVE_KEY, secret=LIVE_SECRET)
    seen = []

    def router(method, url, params=None, body=None, headers=None):
        seen.append((url, dict(headers or {})))
        return (live_broker if f"//{LIVE_HOST}" in url else broker)(method, url, params, body, headers)

    env = {"ALPACA_PAPER_API_KEY_ID": KEY, "ALPACA_PAPER_API_SECRET_KEY": SECRET, "ALPACA_LIVE_API_KEY_ID": LIVE_KEY, "ALPACA_LIVE_API_SECRET_KEY": LIVE_SECRET, "ALPACA_ENABLE_LIVE_TRADING": "true"}
    svc = TradingService(http=router, getenv=env.get)
    assert svc.account("paper")["status"] == "ok" and svc.account("live")["status"] == "ok"
    (paper_url, paper_headers), (live_url, live_headers) = seen
    assert paper_url == f"https://{PAPER_HOST}/v2/account" and paper_headers == {"APCA-API-KEY-ID": KEY, "APCA-API-SECRET-KEY": SECRET}
    assert live_url == f"https://{LIVE_HOST}/v2/account" and live_headers == {"APCA-API-KEY-ID": LIVE_KEY, "APCA-API-SECRET-KEY": LIVE_SECRET}


def test_without_keys_nothing_is_sent_and_the_message_says_which_variables_to_set():
    svc, broker = service(env={})
    answer = svc.account("paper")
    assert answer["status"] == "not_configured" and answer["fetched_at"] is None and answer["data"] is None
    assert "ALPACA_PAPER_API_KEY_ID and ALPACA_PAPER_API_SECRET_KEY" in answer["message"] and "ALPACA_API_KEY_ID and ALPACA_API_SECRET_KEY also work" in answer["message"]
    live, _ = service(env={"ALPACA_ENABLE_LIVE_TRADING": "true"})
    message = live.account("live")["message"]
    assert "live trading keys" in message and "ALPACA_LIVE_API_KEY_ID" in message and "also work" not in message
    assert broker.calls == []


# --- what comes back --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "result, status, words",
    [
        (refusal(401, 40110000, "request is not authorized"), "invalid_key", "Alpaca refused the credentials (HTTP 401): request is not authorized"),
        (HttpResult(401, b"<html><title>401 Authorization Required</title></html>", "text/html"), "invalid_key", "belong to your paper trading account"),
        (refusal(403, 40310000, "insufficient buying power"), "rejected", "insufficient buying power"),
        (refusal(403, 40310000, "trading is suspended for this account"), "rejected", "suspended"),
        (refusal(404, 40410000, "order not found"), "not_found", "order not found"),
        (refusal(422, 42210000, "qty must be > 0"), "rejected", "qty must be > 0"),
        (refusal(400, 40010001, "invalid symbol"), "rejected", "invalid symbol"),
        (refusal(429, 42910000, "too many requests"), "rate_limited", "rate limit was reached: too many requests"),
        (refusal(500, 50010000, "internal server error"), "upstream_error", "internal server error"),
        (HttpResult(502, b"<html>Bad gateway</html>", "text/html"), "upstream_error", "HTTP 502"),
        (HttpResult(418, b"", ""), "rejected", "HTTP 418"),
    ],
)
def test_every_answer_becomes_a_status_with_alpacas_own_words(result, status, words):
    broker = FakeBroker()
    broker.queue.append(result)
    svc, _ = service(broker)
    answer = svc.account("paper")
    assert answer["status"] == status and words in answer["message"] and answer["data"] is None and answer["http_status"] == result.status


def test_the_error_code_and_the_trading_and_data_meanings_of_403_are_kept_apart():
    assert classify(403, {"code": 40310000, "message": "x"}) == ("rejected", 40310000, "x")
    assert classify(403, {"message": "forbidden."}, (401, 403))[0] == "invalid_key"
    assert classify(200, None) == ("ok", None, None) and classify(207, [])[0] == "ok"
    assert classify(400, {"code": True, "message": 5}) == ("rejected", None, None)


@pytest.mark.parametrize(
    "error, method, unknown, words",
    [
        (requests.ReadTimeout(), "POST", True, "may still have been processed"),
        (requests.ReadTimeout(), "GET", False, "did not answer in time"),
        (requests.ConnectTimeout(), "POST", False, "Nothing was sent"),
        (requests.ConnectionError("reset"), "POST", True, "may still have been processed"),
        (requests.ConnectionError("reset"), "DELETE", True, "check the orders and positions"),
        (requests.ConnectionError("dns"), "GET", False, "network error"),
        (ValueError("response too large"), "POST", True, "unexpectedly large"),
    ],
)
def test_when_a_request_that_changes_something_gets_no_answer_the_outcome_is_marked_unknown(error, method, unknown, words):
    broker = FakeBroker()
    broker.queue.append(error)
    outcome = TradingClient(PAPER, http=broker, getenv={"ALPACA_PAPER_API_KEY_ID": KEY, "ALPACA_PAPER_API_SECRET_KEY": SECRET}.get).call(method, "/v2/orders")
    assert outcome.status == "upstream_error" and outcome.outcome_unknown is unknown and words in outcome.message and outcome.http_status is None


@pytest.mark.parametrize("status, body", [(500, b'{"message": "internal server error"}'), (502, b"<html>Bad gateway</html>"), (503, b""), (504, b"<html>Gateway Time-out</html>")])
def test_a_server_error_on_a_change_may_have_been_applied_and_on_a_read_it_cannot_have_been(status, body):
    results = {"POST orders": lambda s: s.place_order("paper", market(client_order_id="uncertain-1")), "DELETE order": lambda s: s.cancel_order("paper", uid(7)), "DELETE orders": lambda s: s.cancel_all_orders("paper"), "DELETE positions": lambda s: s.close_all_positions("paper", {}), "PATCH settings": lambda s: s.update_configurations("paper", {"no_shorting": True})}
    for name, act in results.items():
        broker = FakeBroker()
        broker.queue.append(HttpResult(status, body, "application/json"))
        answer = act(service(broker)[0])
        assert (answer["status"], answer["http_status"], answer["outcome_unknown"]) == ("upstream_error", status, True), name
        assert "may still have been processed" in answer["message"], name
    broker = FakeBroker()
    broker.queue.append(HttpResult(status, body, "application/json"))
    read = service(broker)[0].orders("paper", {})
    assert (read["status"], read["outcome_unknown"]) == ("upstream_error", False) and "may still have been processed" not in read["message"]
    placed = FakeBroker()
    placed.queue.append(HttpResult(status, body, "application/json"))
    assert service(placed)[0].place_order("paper", market(client_order_id="uncertain-2"))["client_order_id"] == "uncertain-2"  # the ID to look it up by


def test_a_definite_refusal_on_a_change_is_not_marked_uncertain():
    for result in (refusal(403, 40310000, "insufficient buying power"), refusal(422, 42210000, "order is not cancelable"), refusal(404, 40410000, "order not found"), refusal(429, 42910000, "too many requests"), refusal(401, 40110000, "request is not authorized")):
        broker = FakeBroker()
        broker.queue.append(result)
        assert service(broker)[0].place_order("paper", market())["outcome_unknown"] is False, result.status


def test_an_unreadable_success_is_an_upstream_error_and_an_empty_one_is_fine():
    broker = FakeBroker()
    broker.queue.extend([HttpResult(200, b"<html>maintenance</html>", "text/html"), HttpResult(200, b"<html>maintenance</html>", "text/html"), reply(204)])
    svc, _ = service(broker)
    read = svc.account("paper")
    assert read["status"] == "upstream_error" and "could not be read" in read["message"] and read["outcome_unknown"] is False
    placed = svc.place_order("paper", market())
    assert placed["status"] == "upstream_error" and placed["outcome_unknown"] is True and "may still have been processed" in placed["message"]
    assert svc.cancel_order("paper", uid(5))["status"] == "ok"


def test_an_echoed_key_or_secret_is_scrubbed_before_anything_is_returned_or_logged(tmp_path):
    broker = FakeBroker()
    broker.queue.append(refusal(422, 42210000, f"bad request from {KEY} with {SECRET}"))
    svc, _ = service(broker, audit_path=tmp_path / "audit.jsonl")
    answer = svc.place_order("paper", market())
    assert answer["status"] == "rejected" and answer["message"] == "bad request from *** with ***"
    assert KEY not in json.dumps(answer) and SECRET not in (tmp_path / "audit.jsonl").read_text()


# --- account, market, assets ----------------------------------------------------------------------------------


def test_the_account_is_numbers_flags_and_the_change_since_yesterday():
    svc, broker = service()
    broker.cash = 98000.0
    broker.last_equity = 99000.0
    answer = svc.account("paper")
    data = answer["data"]
    assert set(answer) == {"environment", "status", "message", "code", "http_status", "outcome_unknown", "client_order_id", "data", "fetched_at", "elapsed_ms"}
    assert (answer["environment"], answer["status"], answer["http_status"]) == ("paper", "ok", 200)
    assert (data["equity"], data["cash"], data["buying_power"], data["multiplier"]) == (98000.0, 98000.0, 98000.0, 2.0)
    assert data["day_change"] == -1000.0 and data["day_change_percent"] == pytest.approx(-1000 / 99000 * 100)
    assert data["trading_blocked"] is False and data["status"] == "ACTIVE" and data["account_number"] == "PA3TESTACCT" and data["options_trading_level"] == 2.0
    assert broker.calls[0].path == "/v2/account" and broker.calls[0].method == "GET"


def test_a_number_that_is_missing_or_not_finite_is_none_not_a_crash():
    from tradingview_data.trading import views as V

    assert V.account_view({"equity": "NaN", "last_equity": "x", "cash": None, "buying_power": "5"})["day_change"] is None
    assert V.account_view({"equity": "10", "last_equity": "0"})["day_change_percent"] is None
    assert V.account_view("not an object")["equity"] is None
    assert [V.num(v) for v in (True, "1,5", "", " 2.5 ", float("inf"), 3)] == [None, None, None, 2.5, None, 3.0]
    assert V.order_view({"status": "weird"})["cancelable"] is False
    assert V.history_view({"timestamp": [1, 2, 3], "equity": ["5"], "profit_loss": None})["equity"] == [5.0, None, None]


def test_clock_calendar_history_and_activities_are_drawn_from_alpacas_answers():
    svc, broker = service()
    svc.place_order("paper", market())
    assert svc.clock("paper")["data"] == {"timestamp": "2026-09-30T14:30:00.123456Z", "is_open": True, "next_open": "2026-10-01T13:30:00Z", "next_close": "2026-09-30T20:00:00Z"}
    days = svc.calendar("paper", {"start": "2026-10-01", "end": "2026-10-02", "date_type": "settlement"})["data"]["days"]
    assert days[1] == {"date": "2026-10-02", "open": "09:30", "close": "13:00", "settlement_date": "2026-10-05", "session_open": None, "session_close": None}
    assert dict(broker.calls[-1].query) == {"start": "2026-10-01", "end": "2026-10-02", "date_type": "SETTLEMENT"}
    history = svc.history("paper", {"period": "1W", "timeframe": "1D"})["data"]
    assert history["timestamp"] == [1790640000, 1790726400, 1790812800] and history["equity"] == [100000.0, 100250.5, None] and history["base_value"] == 100000.0
    activities = svc.activities("paper", {"page_size": "10"})["data"]
    fill = activities["activities"][0]
    assert (fill["activity_type"], fill["symbol"], fill["qty"], fill["price"], fill["time"]) == ("FILL", "AAPL", 10.0, 221.0, "2026-09-30T14:30:00.123456Z")
    assert activities["next_page_token"] == fill["id"] and svc.activities("paper", {}, "DIV")["data"]["activities"] == []
    assert broker.calls[-1].path == "/v2/account/activities/DIV"
    with pytest.raises(TradingInputError, match="capital letters"):
        svc.activities("paper", {}, "fill")
    with pytest.raises(TradingInputError, match="page_size"):
        svc.activities("paper", {"page_size": "500"})
    with pytest.raises(TradingInputError, match="Unknown parameter"):
        svc.history("paper", {"bogus": "1"})


def test_asset_search_ranks_exact_then_prefix_then_name_and_the_list_is_fetched_once_per_ten_minutes():
    now = [1000.0]
    svc, broker = service(clock=lambda: now[0])
    found = svc.assets("paper", {"search": "aa"})["data"]
    assert [a["symbol"] for a in found["assets"]] == ["AA", "AAPL"] and found["total"] == 2
    assert [a["symbol"] for a in svc.assets("paper", {"search": "tesla"})["data"]["assets"]] == ["TSLA"]
    assert svc.assets("paper", {"search": "AAPL"})["data"]["assets"][0]["name"] == "Apple Inc. Common Stock"
    assert sum(1 for c in broker.calls if c.path == "/v2/assets") == 1
    assert dict(broker.calls[0].query) == {"status": "active", "asset_class": "us_equity"}
    assert [a["symbol"] for a in svc.assets("paper", {"search": "a", "tradable": "true"})["data"]["assets"]] == ["AAPL", "TSLA"]  # AA is not tradable
    assert [a["symbol"] for a in svc.assets("paper", {"exchange": "arca"})["data"]["assets"]] == ["SPY"]
    everything = svc.assets("paper", {"limit": "2"})["data"]
    assert len(everything["assets"]) == 2 and everything["total"] == 4
    now[0] += 601
    svc.assets("paper", {"search": "aapl"})
    assert sum(1 for c in broker.calls if c.path == "/v2/assets") == 2
    with pytest.raises(TradingInputError, match="limit"):
        svc.assets("paper", {"limit": "1000"})


def test_a_failed_asset_list_is_not_cached():
    broker = FakeBroker()
    broker.queue.append(refusal(500, 50010000, "boom"))
    svc, _ = service(broker)
    assert svc.assets("paper", {"search": "aapl"})["status"] == "upstream_error"
    assert svc.assets("paper", {"search": "aapl"})["status"] == "ok"


def test_one_asset_is_looked_up_by_symbol_and_crypto_pairs_keep_their_slash_as_a_url_escape():
    svc, broker = service()
    assert svc.asset("paper", "aapl")["data"]["tradable"] is True and broker.calls[-1].path == "/v2/assets/AAPL"
    assert svc.asset("paper", "BTC/USD")["status"] == "not_found"
    assert broker.calls[-1].url.endswith("/v2/assets/BTC%2FUSD")
    assert svc.asset("paper", uid(9001))["data"]["symbol"] == "AAPL"
    with pytest.raises(TradingInputError):
        svc.asset("paper", "../account")


def test_option_contracts_are_listed_with_their_filters_and_looked_up_by_symbol():
    svc, broker = service()
    listed = svc.contracts("paper", {"underlying_symbols": "AAPL", "type": "call", "strike_price_gte": "200", "expiration_date_lte": "2026-12-31", "limit": "10"})["data"]
    assert dict(broker.calls[-1].query) == {"underlying_symbols": "AAPL", "type": "call", "strike_price_gte": "200", "expiration_date_lte": "2026-12-31", "limit": "10"}
    call = listed["contracts"][0]
    assert (call["symbol"], call["strike_price"], call["multiplier"], call["open_interest"], call["type"], call["expiration_date"]) == ("AAPL260116C00250000", 250.0, 100.0, 1200.0, "call", "2026-01-16")
    assert listed["next_page_token"] is None
    assert svc.contract("paper", "AAPL260116P00240000")["data"]["type"] == "put" and svc.contract("paper", "NOPE260116P00240000")["status"] == "not_found"
    with pytest.raises(TradingInputError, match="type must be one of"):
        svc.contracts("paper", {"type": "straddle"})


def test_quotes_come_from_the_data_host_for_stocks_crypto_and_options_with_the_same_keys():
    svc, broker = service()
    stock = svc.quote("paper", "aapl", {})["data"]
    assert broker.calls[-1].host == DATA_HOST and broker.calls[-1].path == "/v2/stocks/AAPL/snapshot" and broker.calls[-1].headers["APCA-API-KEY-ID"] == KEY
    assert (stock["kind"], stock["bid"], stock["ask"], stock["last"], stock["mid"]) == ("us_equity", 220.95, 221.05, 221.0, pytest.approx(221.0))
    assert stock["spread"] == pytest.approx(0.1) and stock["change"] == 1.5 and stock["change_percent"] == pytest.approx(1.5 / 219.5 * 100) and stock["greeks"] is None
    crypto = svc.quote("paper", "BTC/USD", {})["data"]
    assert broker.calls[-1].path == "/v1beta3/crypto/us/snapshots" and dict(broker.calls[-1].query) == {"symbols": "BTC/USD"} and crypto["kind"] == "crypto" and crypto["last"] == 84000.0
    option = svc.quote("paper", "AAPL260116C00250000", {})["data"]
    assert broker.calls[-1].path == "/v1beta1/options/snapshots" and option["kind"] == "us_option" and option["implied_volatility"] == 0.32 and option["greeks"]["delta"] == 0.5
    forced = svc.quote("paper", "BTCUSD", {"asset_class": "crypto"})  # the override picks the endpoint; Alpaca has no pair spelled that way
    assert broker.calls[-1].path == "/v1beta3/crypto/us/snapshots" and (forced["status"], forced["data"]) == ("not_found", None)
    assert svc.quote("paper", "NOPE", {})["status"] == "not_found"
    with pytest.raises(TradingInputError):
        svc.quote("paper", "AAPL", {"asset_class": "bonds"})


def test_a_quote_is_the_snapshot_of_the_symbol_asked_for_never_another_and_none_is_not_found():
    svc, broker = service()
    broker.prices["ETH/USD"] = 3000.0
    broker.queue.append(reply(200, {"snapshots": {}}))
    empty = svc.quote("paper", "BTC/USD", {})
    assert (empty["status"], empty["data"], empty["http_status"], empty["message"]) == ("not_found", None, 200, "Alpaca has no quote for BTC/USD. Check the symbol.")
    other = broker._snapshot("ETH/USD")
    broker.queue.append(reply(200, {"snapshots": {"ETH/USD": other}}))
    wrong = svc.quote("paper", "BTC/USD", {})
    assert wrong["status"] == "not_found" and wrong["data"] is None  # ETH's prices are not shown as BTC's
    broker.queue.append(reply(200, {"snapshots": {"ETH/USD": other, "BTC/USD": broker._snapshot("BTC/USD")}}))
    right = svc.quote("paper", "BTC/USD", {})["data"]
    assert (right["symbol"], right["last"]) == ("BTC/USD", 84000.0)
    broker.queue.append(reply(200, {"snapshots": {}}))
    assert svc.quote("paper", "AAPL260116C00250000", {})["status"] == "not_found"
    broker.queue.append(reply(200, {"snapshots": {"AAPL260116P00240000": broker._snapshot("AAPL260116P00240000")}}))
    assert svc.quote("paper", "AAPL260116C00250000", {})["status"] == "not_found"  # the put is not the call
    for odd in (reply(200, {}), reply(200, None), reply(200, {"snapshots": None}), reply(200, {"snapshots": {"BTC/USD": None}}), reply(200, {"snapshots": {"BTC/USD": {}}})):
        broker.queue.append(odd)
        assert svc.quote("paper", "BTC/USD", {})["status"] == "not_found"
    broker.queue.append(reply(200, {}))
    assert svc.quote("paper", "AAPL", {})["status"] == "not_found"  # a stock answer with nothing in it


def test_the_data_host_answers_403_for_bad_credentials_and_that_is_an_invalid_key_there():
    svc, _ = service(FakeBroker(key="another-key-0123456789"))
    assert svc.quote("paper", "AAPL", {})["status"] == "invalid_key"
    assert svc.account("paper")["status"] == "invalid_key"


# --- orders ----------------------------------------------------------------------------------------------


def test_a_market_order_fills_and_opens_a_position_and_every_order_has_a_client_id_we_can_find_it_by():
    svc, broker = service()
    placed = svc.place_order("paper", market(qty=10))
    order = placed["data"]
    assert placed["status"] == "ok" and placed["client_order_id"].startswith("tvdata-") and order["client_order_id"] == placed["client_order_id"]
    assert (order["status"], order["filled_qty"], order["filled_avg_price"], order["symbol"], order["side"], order["type"], order["time_in_force"], order["cancelable"], order["open"]) == ("filled", 10.0, 221.0, "AAPL", "buy", "market", "day", False, False)
    sent = broker.calls[-1]
    assert (sent.method, sent.path, sent.body) == ("POST", "/v2/orders", {"symbol": "AAPL", "side": "buy", "type": "market", "time_in_force": "day", "qty": "10", "client_order_id": placed["client_order_id"]})
    position = svc.positions("paper")["data"]["positions"][0]
    assert (position["symbol"], position["qty"], position["avg_entry_price"], position["market_value"], position["side"], position["asset_class"]) == ("AAPL", 10.0, 221.0, 2210.0, "long", "us_equity")
    assert svc.account("paper")["data"]["cash"] == pytest.approx(100000 - 2210)
    by_client = svc.order_by_client_id("paper", placed["client_order_id"])["data"]
    assert by_client["id"] == order["id"] and svc.order("paper", order["id"])["data"]["id"] == order["id"]
    mine = svc.place_order("paper", market(client_order_id="my-own-id"))
    assert mine["client_order_id"] == "my-own-id" and broker.calls[-1].body["client_order_id"] == "my-own-id"


def test_alpacas_refusals_reach_the_caller_unchanged_and_a_duplicate_client_id_cannot_place_twice():
    svc, broker = service()
    too_big = svc.place_order("paper", market(qty="1000"))
    assert (too_big["status"], too_big["http_status"], too_big["code"], too_big["message"], too_big["data"]) == ("rejected", 403, 40310000, "insufficient buying power", None)
    assert svc.place_order("paper", market(client_order_id="once"))["status"] == "ok"
    again = svc.place_order("paper", market(client_order_id="once"))
    assert (again["status"], again["message"]) == ("rejected", "client_order_id must be unique")
    assert sum(1 for o in broker.orders.values() if o["client_order_id"] == "once") == 1


def test_an_invalid_order_never_reaches_alpaca():
    svc, broker = service()
    for payload in (market(qty="0"), {**market(), "limit_price": "9"}, {**market(), "type": "limit"}, {"symbol": "AAPL"}):
        with pytest.raises(TradingInputError):
            svc.place_order("paper", payload)
    assert broker.calls == []


def test_a_limit_order_waits_can_be_replaced_and_cancelled_and_only_while_it_is_open():
    svc, broker = service()
    waiting = svc.place_order("paper", limit(price="200"))["data"]
    assert (waiting["status"], waiting["cancelable"], waiting["open"], waiting["limit_price"]) == ("accepted", True, True, 200.0)
    replaced = svc.replace_order("paper", waiting["id"], {"limit_price": "205.5", "qty": "6"})
    new = replaced["data"]
    assert replaced["status"] == "ok" and new["replaces"] == waiting["id"] and new["limit_price"] == 205.5 and new["qty"] == 6.0 and new["id"] != waiting["id"]
    assert (broker.calls[-1].method, broker.calls[-1].body) == ("PATCH", {"limit_price": "205.5", "qty": "6"})
    assert svc.order("paper", waiting["id"])["data"]["status"] == "replaced"
    assert svc.replace_order("paper", waiting["id"], {"qty": "7"})["message"] == "order is not replaceable"
    cancelled = svc.cancel_order("paper", new["id"])
    assert (cancelled["status"], cancelled["data"], cancelled["http_status"]) == ("ok", None, 204)
    again = svc.cancel_order("paper", new["id"])
    assert (again["status"], again["message"]) == ("rejected", "order is not cancelable")
    assert svc.cancel_order("paper", uid(404))["status"] == "not_found"
    with pytest.raises(TradingInputError, match="UUID"):
        svc.cancel_order("paper", "../orders")
    with pytest.raises(TradingInputError, match="Nothing to change"):
        svc.replace_order("paper", new["id"], {})


def test_orders_are_listed_newest_first_by_status_and_symbol_with_exit_legs_nested():
    svc, broker = service()
    svc.place_order("paper", market("AAPL"))
    waiting = svc.place_order("paper", limit("TSLA", price="300"))["data"]
    bracket = svc.place_order("paper", {"symbol": "SPY", "side": "buy", "type": "limit", "time_in_force": "gtc", "qty": "2", "limit_price": "500", "order_class": "bracket", "take_profit": {"limit_price": "560"}, "stop_loss": {"stop_price": "480", "limit_price": "479"}})["data"]
    assert broker.calls[-1].body["stop_loss"] == {"stop_price": "480", "limit_price": "479"} and bracket["order_class"] == "bracket"
    assert [leg["type"] for leg in bracket["legs"]] == ["limit", "stop"] and [leg["status"] for leg in bracket["legs"]] == ["held", "held"]
    open_orders = svc.orders("paper", {})["data"]["orders"]
    assert [o["symbol"] for o in open_orders] == ["SPY", "TSLA"] and dict(broker.calls[-1].query) == {"nested": "true"}
    assert [o["symbol"] for o in svc.orders("paper", {"status": "all", "limit": "2"})["data"]["orders"]] == ["SPY", "TSLA"]
    assert [o["symbol"] for o in svc.orders("paper", {"status": "closed"})["data"]["orders"]] == ["AAPL"]
    assert [o["id"] for o in svc.orders("paper", {"symbols": "TSLA", "status": "all", "nested": "false"})["data"]["orders"]] == [waiting["id"]] and dict(broker.calls[-1].query)["nested"] == "false"
    for params, words in (({"status": "pending"}, "status must be one of"), ({"limit": "501"}, "limit"), ({"symbols": "A B"}, "symbols"), ({"asset_class": "bonds"}, "asset_class"), ({"after": "last week"}, "RFC-3339")):
        with pytest.raises(TradingInputError, match=words):
            svc.orders("paper", params)
    assert svc.order("paper", uid(404))["status"] == "not_found" and svc.order_by_client_id("paper", "nope")["status"] == "not_found"


def test_cancel_all_reports_every_order_it_tried():
    svc, broker = service()
    first, second = (svc.place_order("paper", limit(price=p))["data"]["id"] for p in ("190", "191"))
    results = svc.cancel_all_orders("paper")["data"]["results"]
    assert broker.calls[-1].method == "DELETE" and broker.calls[-1].path == "/v2/orders"
    assert results == [{"id": first, "status": 200, "ok": True, "message": None, "order": None}, {"id": second, "status": 200, "ok": True, "message": None, "order": None}]
    assert svc.orders("paper", {})["data"]["orders"] == []


def test_option_and_multi_leg_orders_are_sent_with_their_legs():
    svc, broker = service()
    single = svc.place_order("paper", {"symbol": "AAPL260116C00250000", "side": "buy", "type": "limit", "time_in_force": "day", "qty": "1", "limit_price": "4.2", "position_intent": "buy_to_open"})["data"]
    assert (single["asset_class"], single["position_intent"], single["status"]) == ("us_option", "buy_to_open", "filled")
    assert svc.account("paper")["data"]["cash"] == pytest.approx(100000 - 410)  # one contract is 100 shares
    spread = svc.place_order("paper", {"order_class": "mleg", "qty": "1", "type": "limit", "limit_price": "1.00", "time_in_force": "day", "legs": [{"symbol": "AAPL260116C00250000", "ratio_qty": "1", "side": "buy", "position_intent": "buy_to_open"}, {"symbol": "AAPL260116P00240000", "ratio_qty": "1", "side": "sell"}]})
    assert spread["status"] == "ok" and broker.calls[-1].body["legs"][1] == {"symbol": "AAPL260116P00240000", "ratio_qty": "1", "side": "sell"}
    assert [leg["symbol"] for leg in spread["data"]["legs"]] == ["AAPL260116C00250000", "AAPL260116P00240000"] and spread["data"]["symbol"] == "AAPL260116C00250000"


# --- positions -------------------------------------------------------------------------------------------


def test_a_position_can_be_closed_whole_by_quantity_or_by_percentage():
    svc, broker = service()
    svc.place_order("paper", market("AAPL", "10"))
    assert svc.position("paper", "aapl")["data"]["qty"] == 10.0 and svc.position("paper", "NOPE")["status"] == "not_found"
    part = svc.close_position("paper", "AAPL", {"qty": "3"})
    assert part["status"] == "ok" and (part["data"]["side"], part["data"]["qty"], part["data"]["type"]) == ("sell", 3.0, "market") and dict(broker.calls[-1].query) == {"qty": "3"}
    half = svc.close_position("paper", "AAPL", {"percentage": "50"})
    assert half["data"]["qty"] == 3.5 and svc.position("paper", "AAPL")["data"]["qty"] == 3.5
    rest = svc.close_position("paper", "AAPL", {})
    assert rest["data"]["qty"] == 3.5 and svc.positions("paper")["data"]["positions"] == []
    svc.place_order("paper", market("AAPL", "1"))
    for params, words in (({"qty": "1", "percentage": "10"}, "either qty or percentage"), ({"qty": "0"}, "greater than zero"), ({"percentage": "101"}, "at most 100"), ({"percentage": "-5"}, "greater than zero"), ({"qty": "x"}, "must be a number"), ({"lots": "1"}, "Unknown parameter")):
        with pytest.raises(TradingInputError, match=words):
            svc.close_position("paper", "AAPL", params)
    assert svc.close_position("paper", "AAPL", {"qty": "5"})["message"] == "insufficient qty available for order"


def test_close_all_can_cancel_open_orders_first_and_reports_each_position():
    svc, broker = service()
    svc.place_order("paper", market("AAPL", "2"))
    svc.place_order("paper", market("TSLA", "1"))
    waiting = svc.place_order("paper", limit("SPY", price="400"))["data"]
    answer = svc.close_all_positions("paper", {"cancel_orders": "true"})
    assert dict(broker.calls[-1].query) == {"cancel_orders": "true"}
    results = answer["data"]["results"]
    assert [(r["symbol"], r["status"], r["ok"], r["order"]["side"]) for r in results] == [("AAPL", 200, True, "sell"), ("TSLA", 200, True, "sell")]
    assert svc.positions("paper")["data"]["positions"] == [] and svc.order("paper", waiting["id"])["data"]["status"] == "canceled"
    with pytest.raises(TradingInputError, match="true or false"):
        svc.close_all_positions("paper", {"cancel_orders": "sure"})


def test_a_bulk_answer_marks_the_items_that_failed():
    from tradingview_data.trading.views import bulk_view

    assert bulk_view([{"symbol": "AAPL", "status": 200, "body": {"id": "1", "status": "accepted", "side": "sell"}}, {"symbol": "TSLA", "status": 500, "body": {"message": "Failed to liquidate"}}, "junk", {"symbol": "X"}], "symbol") == [
        {"symbol": "AAPL", "status": 200, "ok": True, "message": None, "order": bulk_view([{"symbol": "AAPL", "status": 200, "body": {"id": "1", "status": "accepted", "side": "sell"}}], "symbol")[0]["order"]},
        {"symbol": "TSLA", "status": 500, "ok": False, "message": "Failed to liquidate", "order": None},
        {"symbol": "X", "status": None, "ok": False, "message": None, "order": None},
    ]
    assert bulk_view(None, "id") == []


def test_option_positions_can_be_exercised_or_left_to_expire():
    svc, broker = service()
    contract = "AAPL260116C00250000"
    svc.place_order("paper", {"symbol": contract, "side": "buy", "type": "market", "time_in_force": "day", "qty": "1"})
    assert svc.exercise("paper", contract) == {**svc.exercise("paper", contract), "status": "ok", "data": None, "http_status": 200}
    assert (broker.calls[-1].method, broker.calls[-1].path) == ("POST", f"/v2/positions/{contract}/exercise")
    assert svc.do_not_exercise("paper", contract)["status"] == "ok" and broker.calls[-1].path.endswith("/do-not-exercise")
    nothing = svc.exercise("paper", "AAPL260116P00240000")
    assert nothing["status"] == "rejected" and "no position" in nothing["message"]


# --- account settings and watchlists ---------------------------------------------------------------------


def test_settings_can_be_read_changed_and_a_suspended_account_refuses_orders():
    svc, broker = service()
    assert svc.configurations("paper")["data"] == {"trade_confirm_email": "all", "max_margin_multiplier": "2", "max_options_trading_level": 2.0, "suspend_trade": False, "no_shorting": False, "fractional_trading": True, "disable_overnight_trading": False, "ptp_no_exception_entry": False}
    changed = svc.update_configurations("paper", {"suspend_trade": True, "max_margin_multiplier": 1})
    assert changed["data"]["suspend_trade"] is True and broker.calls[-1].method == "PATCH" and broker.calls[-1].body == {"suspend_trade": True, "max_margin_multiplier": "1"}
    blocked = svc.place_order("paper", market())
    assert blocked["status"] == "rejected" and "suspended" in blocked["message"]
    assert svc.account("paper")["data"]["trade_suspended_by_user"] is True
    with pytest.raises(TradingInputError):
        svc.update_configurations("paper", {"suspend_trade": "yes"})


def test_watchlists_are_created_filled_renamed_trimmed_and_deleted():
    svc, broker = service()
    made = svc.create_watchlist("paper", {"name": "Tech", "symbols": ["aapl", "tsla"]})
    watchlist = made["data"]
    assert [a["symbol"] for a in watchlist["assets"]] == ["AAPL", "TSLA"] and broker.calls[-1].body == {"name": "Tech", "symbols": ["AAPL", "TSLA"]}
    assert svc.create_watchlist("paper", {"name": "Tech"})["message"] == "watchlist name must be unique"
    listed = svc.watchlists("paper")["data"]["watchlists"]
    assert [(w["name"], w["assets"]) for w in listed] == [("Tech", [])]  # the list leaves the assets out
    assert [a["symbol"] for a in svc.watchlist("paper", watchlist["id"])["data"]["assets"]] == ["AAPL", "TSLA"]
    added = svc.add_watchlist_asset("paper", watchlist["id"], "spy")
    assert [a["symbol"] for a in added["data"]["assets"]] == ["AAPL", "TSLA", "SPY"] and broker.calls[-1].body == {"symbol": "SPY"}
    removed = svc.remove_watchlist_asset("paper", watchlist["id"], "tsla")
    assert [a["symbol"] for a in removed["data"]["assets"]] == ["AAPL", "SPY"] and broker.calls[-1].path == f"/v2/watchlists/{watchlist['id']}/TSLA"
    renamed = svc.update_watchlist("paper", watchlist["id"], {"name": "Mega caps", "symbols": ["AAPL"]})
    assert (renamed["data"]["name"], [a["symbol"] for a in renamed["data"]["assets"]]) == ("Mega caps", ["AAPL"])
    assert svc.add_watchlist_asset("paper", watchlist["id"], "NOPE")["status"] == "not_found"
    deleted = svc.delete_watchlist("paper", watchlist["id"])
    assert (deleted["status"], deleted["data"]) == ("ok", None) and svc.watchlist("paper", watchlist["id"])["status"] == "not_found"
    with pytest.raises(TradingInputError, match="UUID"):
        svc.watchlist("paper", "tech")
    with pytest.raises(TradingInputError, match="needs a name"):
        svc.create_watchlist("paper", {"symbols": ["AAPL"]})


# --- the audit log ---------------------------------------------------------------------------------------


def test_every_request_that_changes_something_is_logged_with_its_outcome_and_reads_are_not(tmp_path):
    log = tmp_path / "state" / "audit.jsonl"
    svc, broker = service(audit_path=log)
    svc.account("paper")
    svc.orders("paper", {})
    assert not log.exists()
    placed = svc.place_order("paper", limit(price="200", client_order_id="audit-1"))
    svc.cancel_order("paper", placed["data"]["id"])
    svc.place_order("paper", market(qty="100000"))
    svc.update_configurations("paper", {"no_shorting": True})
    svc.create_watchlist("paper", {"name": "W"})
    svc.close_all_positions("paper", {})
    lines = [json.loads(line) for line in log.read_text().splitlines()]
    assert [(e["action"], e["status"]) for e in lines] == [("place_order", "ok"), ("cancel_order", "ok"), ("place_order", "rejected"), ("update_configurations", "ok"), ("create_watchlist", "ok"), ("close_all_positions", "ok")]
    first = lines[0]
    assert first["environment"] == "paper" and first["request"]["client_order_id"] == "audit-1" and first["request"]["limit_price"] == "200" and first["result"]["id"] == placed["data"]["id"] and first["time"].endswith("+00:00")
    assert lines[2]["message"] == "insufficient buying power" and lines[2]["http_status"] == 403 and lines[2]["result"] is None
    text = log.read_text()
    assert KEY not in text and SECRET not in text and "APCA" not in text


@pytest.mark.skipif(os.name == "nt", reason="POSIX permissions")
def test_the_audit_log_and_its_directory_are_readable_only_by_their_owner_whatever_the_umask(tmp_path):
    old = os.umask(0o022)  # the common umask, which would make both world-readable
    try:
        log = tmp_path / "state" / "audit.jsonl"
        svc, _ = service(audit_path=log)
        svc.place_order("paper", market(client_order_id="private-1"))
        svc.cancel_all_orders("paper")
        assert stat.S_IMODE(log.stat().st_mode) == 0o600 and stat.S_IMODE(log.parent.stat().st_mode) == 0o700
        assert len(log.read_text().splitlines()) == 2
        log.chmod(0o644)  # a file that was loosened is tightened again by the next write
        svc.cancel_all_orders("paper")
        assert stat.S_IMODE(log.stat().st_mode) == 0o600
    finally:
        os.umask(old)


def test_an_unwritable_audit_log_never_stops_a_trade(tmp_path):
    blocked = tmp_path / "audit.jsonl"
    blocked.mkdir()  # a directory where the file should be
    svc, _ = service(audit_path=blocked)
    assert svc.place_order("paper", market())["status"] == "ok"
