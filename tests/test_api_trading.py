"""The /api/trading routes: the guards that protect them, the status codes, and a whole paper session over HTTP."""

from __future__ import annotations

import json

import pytest
import requests
from fastapi.testclient import TestClient

from tradingview_data.api import create_app
from tradingview_data.trading.routes import allowed_clients, allowed_hosts, client_allowed, host_name
from tradingview_data.trading.service import TradingService

from trading_support import KEY, LIVE_HOST, PAPER_HOST, SECRET, FakeBroker, uid

WRITE = {"X-Tvdata-Trading": "1"}


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("test attempted a real network request")

    monkeypatch.setattr(requests, "get", refuse)
    monkeypatch.setattr(requests.Session, "request", refuse)


def app_with(tmp_path, env=None, broker=None, host="localhost", peer="127.0.0.1", **kwargs):
    broker = broker or FakeBroker()
    values = {"ALPACA_PAPER_API_KEY_ID": KEY, "ALPACA_PAPER_API_SECRET_KEY": SECRET} if env is None else env
    service = TradingService(http=broker, getenv=values.get, audit_path=tmp_path / "audit.jsonl")
    return TestClient(create_app(tmp_path, trading=service, **kwargs), base_url=f"http://{host}", client=(peer, 50000)), broker


def order(**changes):
    return {"symbol": "AAPL", "side": "buy", "type": "market", "time_in_force": "day", "qty": "10", **changes}


# --- the guards ------------------------------------------------------------------------------------------


def test_the_host_header_must_be_a_local_name_for_every_trading_route(tmp_path):
    api, broker = app_with(tmp_path)
    for host in ("localhost", "localhost:5173", "127.0.0.1:8000", "[::1]:8000", "LOCALHOST"):
        assert api.get("/api/trading/paper/account", headers={"Host": host}).status_code == 200, host
    for host in ("evil.example", "evil.example:8000", "localhost.evil.example", "127.0.0.1.evil.example", "192.168.1.5:8000", ""):
        blocked = api.get("/api/trading/paper/account", headers={"Host": host})
        assert blocked.status_code == 403 and "TVDATA_TRADING_ALLOWED_HOSTS" in blocked.json()["detail"], host
        assert api.get("/api/trading/environments", headers={"Host": host}).status_code == 403
        assert api.post("/api/trading/paper/orders", json=order(), headers={**WRITE, "Host": host}).status_code == 403
    assert len(broker.calls) == 5  # only the five local requests reached Alpaca


def test_a_computer_that_is_not_this_one_cannot_trade_whatever_headers_it_sends(tmp_path):
    for peer in ("203.0.113.9", "192.168.1.20", "10.0.0.5", "2001:db8::1", "testclient", ""):
        api, broker = app_with(tmp_path, peer=peer)
        for method, path, body in (("GET", "/api/trading/environments", None), ("GET", "/api/trading/paper/account", None), ("POST", "/api/trading/paper/orders", order()), ("DELETE", "/api/trading/paper/positions", None)):
            refused = api.request(method, path, json=body, headers={**WRITE, "Host": "localhost"})
            assert refused.status_code == 403 and "only served to this machine" in refused.json()["detail"] and "TVDATA_TRADING_ALLOWED_CLIENTS" in refused.json()["detail"], (peer, path)
        assert broker.calls == [], peer
    for peer in ("127.0.0.1", "127.0.0.2", "::1", "::ffff:127.0.0.1"):
        api, _ = app_with(tmp_path, peer=peer)
        assert api.get("/api/trading/paper/account").status_code == 200, peer


def test_other_computers_can_be_allowed_by_address_or_range_and_a_mistake_in_the_list_is_loud(tmp_path, monkeypatch):
    monkeypatch.setenv("TVDATA_TRADING_ALLOWED_CLIENTS", "203.0.113.0/24, 192.168.1.20 ,2001:db8::/32")
    assert [str(n) for n in allowed_clients()] == ["203.0.113.0/24", "192.168.1.20/32", "2001:db8::/32"]
    for peer in ("203.0.113.9", "192.168.1.20", "2001:db8::7"):
        api, _ = app_with(tmp_path, peer=peer)
        assert api.get("/api/trading/paper/account").status_code == 200, peer
    api, broker = app_with(tmp_path, peer="192.168.1.21")  # next to an allowed address, not on the list
    assert api.get("/api/trading/paper/account").status_code == 403 and broker.calls == []
    monkeypatch.setenv("TVDATA_TRADING_ALLOWED_CLIENTS", "my-laptop")
    with pytest.raises(ValueError):
        allowed_clients()


def test_the_client_check_treats_anything_that_is_not_an_address_as_not_allowed():
    assert [client_allowed(h) for h in ("127.0.0.1", "::1", "::ffff:127.0.0.1", "10.0.0.1", "testclient", "", None, "localhost", "999.1.1.1")] == [True, True, True, False, False, False, False, False, False]
    assert client_allowed("10.1.2.3", allowed_clients(["10.0.0.0/8"])) and not client_allowed("11.1.2.3", allowed_clients(["10.0.0.0/8"]))


def test_other_hosts_can_be_allowed_by_name_and_the_names_are_parsed_without_port_or_brackets(tmp_path, monkeypatch):
    monkeypatch.setenv("TVDATA_TRADING_ALLOWED_HOSTS", "trading.lan, Desk.Example ")
    assert {"localhost", "127.0.0.1", "::1", "trading.lan", "desk.example"} <= allowed_hosts()
    assert "extra.test" in allowed_hosts(["Extra.test"])
    assert [host_name(h) for h in ("localhost:8000", "[::1]:8000", "[::1]", "::1", "Desk.Example", " 127.0.0.1:1 ")] == ["localhost", "::1", "::1", "::1", "desk.example", "127.0.0.1"]
    api, _ = app_with(tmp_path, host="trading.lan")
    assert api.get("/api/trading/paper/account").status_code == 200


MUTATIONS = [
    ("PATCH", "/api/trading/paper/account/configurations", {"suspend_trade": True}),
    ("POST", "/api/trading/paper/orders", order()),
    ("DELETE", "/api/trading/paper/orders", None),
    ("PATCH", f"/api/trading/paper/orders/{uid(1)}", {"qty": "2"}),
    ("DELETE", f"/api/trading/paper/orders/{uid(1)}", None),
    ("POST", "/api/trading/paper/positions/AAPL260116C00250000/exercise", None),
    ("POST", "/api/trading/paper/positions/AAPL260116C00250000/do-not-exercise", None),
    ("DELETE", "/api/trading/paper/positions", None),
    ("DELETE", "/api/trading/paper/positions/AAPL", None),
    ("POST", "/api/trading/paper/watchlists", {"name": "W"}),
    ("PUT", f"/api/trading/paper/watchlists/{uid(1)}", {"name": "W"}),
    ("DELETE", f"/api/trading/paper/watchlists/{uid(1)}", None),
    ("POST", f"/api/trading/paper/watchlists/{uid(1)}/assets", {"symbol": "AAPL"}),
    ("DELETE", f"/api/trading/paper/watchlists/{uid(1)}/assets/AAPL", None),
]


@pytest.mark.parametrize("method, path, body", MUTATIONS, ids=[f"{m} {p.replace('/api/trading/paper', '')[:44]}" for m, p, _ in MUTATIONS])
def test_nothing_that_changes_something_is_done_without_the_dashboards_header(tmp_path, method, path, body):
    api, broker = app_with(tmp_path)
    without = api.request(method, path, json=body)
    assert without.status_code == 403 and "X-Tvdata-Trading" in without.json()["detail"]
    wrong = api.request(method, path, json=body, headers={"X-Tvdata-Trading": "0"})
    assert wrong.status_code == 403
    assert broker.calls == []
    allowed = api.request(method, path, json=body, headers=WRITE)
    assert allowed.status_code in (200, 422) and len(broker.calls) <= 1  # past the guard; Alpaca (the fake) decides the rest


def test_a_form_post_from_another_site_cannot_place_an_order(tmp_path):
    api, broker = app_with(tmp_path)
    forged = api.post("/api/trading/paper/orders", content=json.dumps(order()), headers={"Content-Type": "text/plain", "Origin": "https://evil.example"})
    assert forged.status_code == 403 and broker.calls == []
    assert api.post("/api/trading/paper/orders", data=order(), headers={"Origin": "https://evil.example"}).status_code == 403


def test_reading_needs_no_header_and_cors_allows_the_dashboards_header_and_verbs_only_for_listed_origins(tmp_path):
    api, _ = app_with(tmp_path, cors_origins=["http://localhost:5173"])
    assert api.get("/api/trading/paper/orders").status_code == 200
    preflight = api.options("/api/trading/paper/orders/" + uid(1), headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "PATCH", "Access-Control-Request-Headers": "x-tvdata-trading,content-type"})
    assert preflight.status_code == 200 and "PATCH" in preflight.headers["access-control-allow-methods"] and "x-tvdata-trading" in preflight.headers["access-control-allow-headers"].lower()
    foreign = api.options("/api/trading/paper/orders", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "x-tvdata-trading"})
    assert foreign.status_code == 400 and "access-control-allow-origin" not in foreign.headers


# --- environments -----------------------------------------------------------------------------------------


def test_the_environment_list_is_served_without_any_request_to_alpaca(tmp_path):
    api, broker = app_with(tmp_path)
    body = api.get("/api/trading/environments").json()
    assert body["default"] == "paper" and [(e["id"], e["configured"], e["enabled"]) for e in body["environments"]] == [("paper", True, True), ("live", False, False)]
    assert KEY not in json.dumps(body) and broker.calls == []


def test_live_is_blocked_with_a_403_that_says_how_to_turn_it_on_and_an_unknown_environment_is_a_404(tmp_path):
    api, broker = app_with(tmp_path, env={"ALPACA_LIVE_API_KEY_ID": "live-key-123456", "ALPACA_LIVE_API_SECRET_KEY": "live-secret-123456"})
    for method, path, body in (("GET", "/api/trading/live/account", None), ("POST", "/api/trading/live/orders", order()), ("DELETE", "/api/trading/live/positions", None), ("GET", "/api/trading/live/quote/AAPL", None)):
        answer = api.request(method, path, json=body, headers=WRITE)
        assert answer.status_code == 403 and "ALPACA_ENABLE_LIVE_TRADING=true" in answer.json()["detail"], path
    for path in ("/api/trading/demo/account", "/api/trading/PAPER/account", "/api/trading/live%20/account"):
        assert api.get(path).status_code == 404
    assert api.post("/api/trading/demo/orders", json=order(), headers=WRITE).status_code == 404
    assert broker.calls == []


def test_live_works_once_it_is_switched_on_and_uses_only_the_live_keys_on_the_live_host(tmp_path):
    live = FakeBroker(key="PKLIVEKEYID0123456789AB", secret="live-secret-0123456789-abcdefghijklmnop")
    seen = []

    def router(method, url, params=None, body=None, headers=None):
        seen.append((method, url, dict(headers or {})))
        return live(method, url, params, body, headers)

    env = {"ALPACA_PAPER_API_KEY_ID": KEY, "ALPACA_PAPER_API_SECRET_KEY": SECRET, "ALPACA_LIVE_API_KEY_ID": live.key, "ALPACA_LIVE_API_SECRET_KEY": live.secret, "ALPACA_ENABLE_LIVE_TRADING": "true"}
    api = TestClient(create_app(tmp_path, trading=TradingService(http=router, getenv=env.get)), base_url="http://localhost", client=("127.0.0.1", 50000))
    placed = api.post("/api/trading/live/orders", json=order(), headers=WRITE).json()
    assert placed["environment"] == "live" and placed["status"] == "ok"
    method, url, headers = seen[-1]
    assert (method, url) == ("POST", f"https://{LIVE_HOST}/v2/orders") and headers["APCA-API-KEY-ID"] == live.key and KEY not in json.dumps(seen)
    seen.clear()
    assert api.get("/api/trading/paper/account").json()["status"] == "invalid_key"  # the live broker does not know the paper keys
    assert seen[-1][1] == f"https://{PAPER_HOST}/v2/account" and seen[-1][2]["APCA-API-KEY-ID"] == KEY


def test_without_keys_a_request_answers_not_configured_and_sends_nothing(tmp_path):
    api, broker = app_with(tmp_path, env={})
    answer = api.get("/api/trading/paper/account")
    assert answer.status_code == 200 and answer.json()["status"] == "not_configured" and "ALPACA_PAPER_API_KEY_ID" in answer.json()["message"]
    assert api.post("/api/trading/paper/orders", json=order(), headers=WRITE).json()["status"] == "not_configured"
    assert broker.calls == []


# --- errors -----------------------------------------------------------------------------------------------


def test_a_request_that_is_wrong_before_it_leaves_is_a_422_with_one_plain_sentence(tmp_path):
    api, broker = app_with(tmp_path)
    cases = [
        ("POST", "/api/trading/paper/orders", order(limit_price="9"), "limit_price does not apply to a market order"),
        ("POST", "/api/trading/paper/orders", {"symbol": "AAPL"}, "side is required"),
        ("POST", "/api/trading/paper/orders", order(qty="-1"), "greater than zero"),
        ("PATCH", f"/api/trading/paper/orders/{uid(1)}", {}, "Nothing to change"),
        ("PATCH", "/api/trading/paper/orders/not-an-id", {"qty": "1"}, "UUID"),
        ("DELETE", "/api/trading/paper/orders/not-an-id", None, "UUID"),
        ("PATCH", "/api/trading/paper/account/configurations", {"max_margin_multiplier": "9"}, "1, 2 or 4"),
        ("POST", "/api/trading/paper/watchlists", {"symbols": ["AAPL"]}, "needs a name"),
        ("DELETE", "/api/trading/paper/positions/AAPL?qty=1&percentage=5", None, "either qty or percentage"),
        ("DELETE", "/api/trading/paper/positions?cancel_orders=sure", None, "true or false"),
        ("POST", f"/api/trading/paper/watchlists/{uid(1)}/assets", {"symbol": "../x"}, "symbol must be a symbol"),
        ("GET", "/api/trading/paper/orders?status=pending", None, "status must be one of"),
        ("GET", "/api/trading/paper/orders?bogus=1", None, "Unknown parameter"),
        ("GET", "/api/trading/paper/account/activities/fill", None, "capital letters"),
        ("GET", "/api/trading/paper/calendar?start=tomorrow", None, "YYYY-MM-DD"),
        ("GET", "/api/trading/paper/quote/AAPL?asset_class=bonds", None, "asset_class must be one of"),
    ]
    for method, path, body, words in cases:
        answer = api.request(method, path, json=body, headers=WRITE)
        assert answer.status_code == 422, (path, answer.text)
        assert words in answer.json()["detail"], (path, answer.json())
    assert broker.calls == []
    assert api.post("/api/trading/paper/orders", json=[1, 2], headers=WRITE).status_code == 422


def test_refusals_at_alpaca_are_a_200_with_a_status_not_an_http_error(tmp_path):
    api, _ = app_with(tmp_path)
    refused = api.post("/api/trading/paper/orders", json=order(qty="100000"), headers=WRITE)
    body = refused.json()
    assert refused.status_code == 200 and (body["status"], body["code"], body["message"], body["http_status"], body["data"]) == ("rejected", 40310000, "insufficient buying power", 403, None)
    assert api.get(f"/api/trading/paper/orders/{uid(404)}").json()["status"] == "not_found"


# --- a whole paper session ----------------------------------------------------------------------------------


def test_a_paper_session_from_the_account_to_a_closed_position_over_http(tmp_path):
    api, broker = app_with(tmp_path)
    texts = []

    def get(path):
        answer = api.get("/api/trading/paper" + path)
        texts.append(answer.text)
        return answer.json()

    def send(method, path, body=None):
        answer = api.request(method, "/api/trading/paper" + path, json=body, headers=WRITE)
        texts.append(answer.text)
        return answer.json()

    assert get("/account")["data"]["equity"] == 100000.0 and get("/clock")["data"]["is_open"] is True
    assert [a["symbol"] for a in get("/assets?search=tsl")["data"]["assets"]] == ["TSLA"]
    assert get("/quote/TSLA")["data"]["last"] == 405.0

    waiting = send("POST", "/orders", order(symbol="TSLA", type="limit", time_in_force="gtc", qty="2", limit_price="300"))
    assert waiting["data"]["status"] == "accepted" and waiting["data"]["cancelable"] is True
    assert [o["id"] for o in get("/orders")["data"]["orders"]] == [waiting["data"]["id"]]
    assert get("/orders/by-client-id/" + waiting["client_order_id"])["data"]["id"] == waiting["data"]["id"]
    replaced = send("PATCH", "/orders/" + waiting["data"]["id"], {"limit_price": "310"})
    assert replaced["data"]["limit_price"] == 310.0 and replaced["data"]["replaces"] == waiting["data"]["id"]
    assert send("DELETE", "/orders/" + replaced["data"]["id"])["status"] == "ok"

    bought = send("POST", "/orders", order(qty="4"))
    assert bought["data"]["status"] == "filled"
    assert [(p["symbol"], p["qty"]) for p in get("/positions")["data"]["positions"]] == [("AAPL", 4.0)] and get("/positions/AAPL")["data"]["market_value"] == 884.0
    partly = send("DELETE", "/positions/AAPL?qty=1")
    assert partly["data"]["side"] == "sell" and get("/positions/AAPL")["data"]["qty"] == 3.0
    assert send("DELETE", "/positions?cancel_orders=true")["data"]["results"][0]["symbol"] == "AAPL" and get("/positions")["data"]["positions"] == []

    assert send("PATCH", "/account/configurations", {"no_shorting": True})["data"]["no_shorting"] is True
    watchlist = send("POST", "/watchlists", {"name": "Core", "symbols": ["AAPL"]})["data"]
    assert send("POST", f"/watchlists/{watchlist['id']}/assets", {"symbol": "SPY"})["data"]["assets"][1]["symbol"] == "SPY"
    assert [a["symbol"] for a in send("DELETE", f"/watchlists/{watchlist['id']}/assets/AAPL")["data"]["assets"]] == ["SPY"]
    assert get("/watchlists")["data"]["watchlists"][0]["name"] == "Core" and send("DELETE", f"/watchlists/{watchlist['id']}")["status"] == "ok"
    assert get("/account/activities")["data"]["activities"][0]["activity_type"] == "FILL"
    assert get("/account/portfolio-history?period=1W&timeframe=1D")["data"]["equity"][1] == 100250.5
    assert get("/calendar?start=2026-10-01")["data"]["days"][0]["date"] == "2026-10-01"
    assert get("/options/contracts?underlying_symbols=AAPL")["data"]["contracts"][0]["symbol"] == "AAPL260116C00250000"
    assert get("/options/contracts/AAPL260116P00240000")["data"]["type"] == "put"

    everything = "".join(texts) + api.get("/api/trading/environments").text
    assert KEY not in everything and SECRET not in everything and "APCA" not in everything
    audit = (tmp_path / "audit.jsonl").read_text().splitlines()
    assert [json.loads(line)["action"] for line in audit][:3] == ["place_order", "replace_order", "cancel_order"]


def test_symbols_with_a_slash_work_in_paths_and_orders_for_crypto(tmp_path):
    api, broker = app_with(tmp_path)
    bought = api.post("/api/trading/paper/orders", json=order(symbol="BTC/USD", qty="0.5", time_in_force="gtc"), headers=WRITE).json()
    assert bought["status"] == "ok" and bought["data"]["asset_class"] == "crypto" and bought["data"]["symbol"] == "BTC/USD"
    assert api.get("/api/trading/paper/positions/BTCUSD").json()["data"]["qty"] == 0.5
    assert api.get("/api/trading/paper/quote/BTC/USD").json()["data"]["kind"] == "crypto"
    assert api.get("/api/trading/paper/assets/BTC/USD").json()["status"] == "not_found" and broker.calls[-1].url.endswith("/v2/assets/BTC%2FUSD")
    closed = api.delete("/api/trading/paper/positions/BTC/USD?percentage=100", headers=WRITE).json()
    assert closed["status"] == "ok" and closed["data"]["qty"] == 0.5 and broker.calls[-1].url.endswith("/v2/positions/BTC%2FUSD") and broker.calls[-1].query == [("percentage", "100")]


def test_a_by_client_id_lookup_is_not_taken_for_an_order_id(tmp_path):
    api, _ = app_with(tmp_path)
    placed = api.post("/api/trading/paper/orders", json=order(client_order_id="lookup-me"), headers=WRITE).json()
    assert api.get("/api/trading/paper/orders/by-client-id/lookup-me").json()["data"]["id"] == placed["data"]["id"]
    assert api.get("/api/trading/paper/orders/by-client-id/unknown").json()["status"] == "not_found"


def test_the_default_app_contacts_no_one_and_keeps_its_audit_log_out_of_the_dataset_list(tmp_path):
    api = TestClient(create_app(tmp_path), base_url="http://localhost", client=("127.0.0.1", 50000))  # the autouse guard fails the test on any real request
    assert api.get("/api/trading/environments").status_code == 200
    assert api.get("/api/datasets").json()["datasets"] == []
    assert api.get("/api/health").json()["dataset_count"] == 0


def test_the_openapi_schema_lists_every_trading_route(tmp_path):
    api, _ = app_with(tmp_path)
    paths = api.get("/api/openapi.json").json()["paths"]
    trading = {p for p in paths if p.startswith("/api/trading")}
    assert len(trading) == 24 and "/api/trading/{env}/orders/{order_id}" in trading and "/api/trading/environments" in trading
    assert "/api/trading/{env}/account/activities/{activity_type}" in trading
    verbs = {verb for p in trading for verb in paths[p]}
    assert verbs == {"get", "post", "patch", "put", "delete"}
