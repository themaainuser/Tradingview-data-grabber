"""A stateful stand-in for Alpaca's trading and data hosts, for the trading tests (and the browser check).

``FakeBroker`` is a drop-in for the service's ``http`` argument: it checks the key headers, keeps
orders, positions, watchlists and settings, fills marketable orders at the price in ``prices``, enforces
buying power, and answers in Alpaca's own shapes and status codes (strings for numbers, 207 for the
bulk calls, 403/422 for refusals). It records every call.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import unquote, urlparse

from tradingview_data.providers.common import HttpResult

KEY = "PKTRADINGKEYID0123456789"
SECRET = "trading-secret-0123456789-abcdefghijklmnop"
PAPER_HOST = "paper-api.alpaca.markets"
LIVE_HOST = "api.alpaca.markets"
DATA_HOST = "data.alpaca.markets"
OPEN_STATES = ("new", "partially_filled", "accepted", "pending_new", "pending_replace")


@dataclass
class Call:
    method: str
    url: str
    query: list[tuple[str, str]]
    body: Any
    headers: dict[str, str]

    @property
    def path(self) -> str:
        return urlparse(self.url).path

    @property
    def host(self) -> str:
        return urlparse(self.url).netloc


def reply(status: int, payload: Any = None) -> HttpResult:
    body = b"" if payload is None else json.dumps(payload).encode()
    return HttpResult(status, body, "application/json")


def refusal(status: int, code: int, message: str) -> HttpResult:
    return reply(status, {"code": code, "message": message})


def uid(n: int) -> str:
    return str(uuid.UUID(int=n))


def _money(value: float) -> str:
    return f"{value:.2f}"


class FakeBroker:
    def __init__(self, *, key: str = KEY, secret: str = SECRET, cash: float = 100000.0) -> None:
        self.key, self.secret = key, secret
        self.cash = cash
        self.last_equity = cash
        self.calls: list[Call] = []
        self.queue: list[Any] = []  # scripted answers (an HttpResult or an exception), used before anything else
        self.counter = 0
        self.now = datetime(2026, 9, 30, 14, 30, tzinfo=timezone.utc)
        self.prices: dict[str, float] = {"AAPL": 221.0, "TSLA": 405.0, "SPY": 520.0, "BTC/USD": 84000.0, "AAPL260116C00250000": 4.1, "AAPL260116P00240000": 2.1}
        self.assets = [
            {"id": uid(9001), "class": "us_equity", "exchange": "NASDAQ", "symbol": "AAPL", "name": "Apple Inc. Common Stock", "status": "active", "tradable": True, "marginable": True, "shortable": True, "fractionable": True, "min_order_size": "1", "min_trade_increment": "1", "price_increment": "0.01", "attributes": ["has_options"]},
            {"id": uid(9002), "class": "us_equity", "exchange": "NASDAQ", "symbol": "TSLA", "name": "Tesla, Inc. Common Stock", "status": "active", "tradable": True, "marginable": True, "shortable": True, "fractionable": True, "attributes": []},
            {"id": uid(9003), "class": "us_equity", "exchange": "ARCA", "symbol": "SPY", "name": "SPDR S&P 500 ETF Trust", "status": "active", "tradable": True, "marginable": True, "shortable": True, "fractionable": True, "attributes": []},
            {"id": uid(9004), "class": "us_equity", "exchange": "NYSE", "symbol": "AA", "name": "Alcoa Corporation", "status": "active", "tradable": False, "marginable": False, "shortable": False, "fractionable": False, "attributes": []},
        ]
        self.orders: dict[str, dict[str, Any]] = {}
        self.positions: dict[str, dict[str, Any]] = {}
        self.activities: list[dict[str, Any]] = []
        self.watchlists: dict[str, dict[str, Any]] = {}
        self.config: dict[str, Any] = {"suspend_trade": False, "no_shorting": False, "fractional_trading": True, "disable_overnight_trading": False, "ptp_no_exception_entry": False, "trade_confirm_email": "all", "max_margin_multiplier": "2", "max_options_trading_level": 2}
        self.market_open = True

    # --- the transport ----------------------------------------------------------------------------------

    def __call__(self, method: str, url: str, params: Optional[list[tuple[str, str]]] = None, body: Any = None, headers: Optional[dict[str, str]] = None) -> HttpResult:
        call = Call(method, url, list(params or []), body, dict(headers or {}))
        self.calls.append(call)
        if self.queue:
            item = self.queue.pop(0)
            if isinstance(item, Exception):
                raise item
            return item
        if call.headers.get("APCA-API-KEY-ID") != self.key or call.headers.get("APCA-API-SECRET-KEY") != self.secret:
            if call.host == DATA_HOST:
                return reply(403, {"message": "forbidden."})
            return refusal(401, 40110000, "request is not authorized")
        query = dict(call.query)
        path = unquote(call.path)
        if call.host == DATA_HOST:
            return self._data(path, query)
        return self._trading(method, path, query, body)

    def _id(self) -> str:
        self.counter += 1
        return uid(self.counter)

    def stamp(self) -> str:
        return self.now.strftime("%Y-%m-%dT%H:%M:%S.123456Z")

    # --- trading host -------------------------------------------------------------------------------------

    def _trading(self, method: str, path: str, query: dict[str, str], body: Any) -> HttpResult:
        if path == "/v2/account":
            return reply(200, self.account())
        if path == "/v2/account/configurations":
            if method == "PATCH":
                self.config.update(body)
            return reply(200, self.config)
        if path == "/v2/clock":
            close = self.now.replace(hour=20, minute=0, second=0, microsecond=0)
            opens = (self.now + timedelta(days=1)).replace(hour=13, minute=30, second=0, microsecond=0)
            return reply(200, {"timestamp": self.stamp(), "is_open": self.market_open, "next_open": opens.strftime("%Y-%m-%dT%H:%M:%SZ"), "next_close": close.strftime("%Y-%m-%dT%H:%M:%SZ")})
        if path == "/v2/calendar":
            return reply(200, [{"date": "2026-10-01", "open": "09:30", "close": "16:00", "settlement_date": "2026-10-02"}, {"date": "2026-10-02", "open": "09:30", "close": "13:00", "settlement_date": "2026-10-05"}])
        if path == "/v2/account/portfolio/history":
            return reply(200, {"timestamp": [1790640000, 1790726400, 1790812800], "equity": [100000.0, 100250.5, None], "profit_loss": [0.0, 250.5, None], "profit_loss_pct": [0.0, 0.0025, None], "base_value": 100000.0, "timeframe": query.get("timeframe", "1D")})
        if path.startswith("/v2/account/activities"):
            kinds = path.rsplit("/", 1)[1] if path.count("/") == 4 else None
            return reply(200, [a for a in reversed(self.activities) if kinds in (None, a["activity_type"])])
        if path == "/v2/assets":
            return reply(200, [a for a in self.assets if a["status"] == query.get("status", "active")] if query.get("asset_class", "us_equity") == "us_equity" else [])
        if path.startswith("/v2/assets/"):
            symbol = path.rsplit("/", 1)[1]
            found = next((a for a in self.assets if a["symbol"] == symbol or a["id"] == symbol), None)
            return reply(200, found) if found else refusal(404, 40410000, f"asset not found for {symbol}")
        if path == "/v2/options/contracts":
            return reply(200, {"option_contracts": self.contracts(), "next_page_token": None})
        if path.startswith("/v2/options/contracts/"):
            symbol = path.rsplit("/", 1)[1]
            found = next((c for c in self.contracts() if c["symbol"] == symbol), None)
            return reply(200, found) if found else refusal(404, 40410000, "contract not found")
        if path.startswith("/v2/orders"):
            return self._orders(method, path, query, body)
        if path.startswith("/v2/positions"):
            return self._positions(method, path, query)
        if path.startswith("/v2/watchlists"):
            return self._watchlists(method, path, body)
        return refusal(404, 40410000, f"not found: {path}")

    def contracts(self) -> list[dict[str, Any]]:
        return [
            {"id": uid(8001), "symbol": "AAPL260116C00250000", "name": "AAPL Jan 16 2026 250 Call", "status": "active", "tradable": True, "expiration_date": "2026-01-16", "root_symbol": "AAPL", "underlying_symbol": "AAPL", "underlying_asset_id": uid(9001), "type": "call", "style": "american", "strike_price": "250", "multiplier": "100", "size": "100", "open_interest": "1200", "open_interest_date": "2026-09-29", "close_price": "4.1", "close_price_date": "2026-09-29"},
            {"id": uid(8002), "symbol": "AAPL260116P00240000", "name": "AAPL Jan 16 2026 240 Put", "status": "active", "tradable": True, "expiration_date": "2026-01-16", "root_symbol": "AAPL", "underlying_symbol": "AAPL", "underlying_asset_id": uid(9001), "type": "put", "style": "american", "strike_price": "240", "multiplier": "100", "size": "100", "open_interest": "800", "close_price": "2.1"},
        ]

    def market_value(self) -> float:
        return sum(float(p["market_value"]) for p in self.positions.values())

    def account(self) -> dict[str, Any]:
        equity = self.cash + self.market_value()
        return {
            "id": uid(7001), "account_number": "PA3TESTACCT", "status": "ACTIVE", "currency": "USD", "created_at": "2026-01-02T00:00:00Z",
            "cash": _money(self.cash), "equity": _money(equity), "last_equity": _money(self.last_equity), "portfolio_value": _money(equity),
            "buying_power": _money(self.cash), "regt_buying_power": _money(self.cash), "non_marginable_buying_power": _money(self.cash),
            "options_buying_power": _money(self.cash), "long_market_value": _money(self.market_value()), "short_market_value": "0", "multiplier": "2",
            "initial_margin": "0", "maintenance_margin": "0", "sma": "0", "trading_blocked": False, "account_blocked": False, "transfers_blocked": False,
            "trade_suspended_by_user": bool(self.config["suspend_trade"]), "shorting_enabled": not self.config["no_shorting"],
            "crypto_status": "ACTIVE", "options_approved_level": 2, "options_trading_level": 2, "accrued_fees": "0",
        }

    # --- orders ---------------------------------------------------------------------------------------------

    def _orders(self, method: str, path: str, query: dict[str, str], body: Any) -> HttpResult:
        if path == "/v2/orders:by_client_order_id":
            found = next((o for o in self.orders.values() if o["client_order_id"] == query.get("client_order_id")), None)
            return reply(200, found) if found else refusal(404, 40410000, "order not found")
        if path == "/v2/orders" and method == "POST":
            return self._place(body)
        if path == "/v2/orders" and method == "GET":
            wanted = query.get("status", "open")
            chosen = [o for o in self.orders.values() if wanted == "all" or (wanted == "open") == (o["status"] in OPEN_STATES)]
            if query.get("symbols"):
                chosen = [o for o in chosen if o["symbol"] in query["symbols"].split(",")]
            return reply(200, sorted(chosen, key=lambda o: o["created_at"] + o["id"], reverse=True)[: int(query.get("limit", 50))])
        if path == "/v2/orders" and method == "DELETE":
            results = []
            for order in self.orders.values():
                if order["status"] in OPEN_STATES:
                    order["status"] = "canceled"
                    results.append({"id": order["id"], "status": 200})
            return reply(207, results)
        order = self.orders.get(path.rsplit("/", 1)[1])
        if order is None:
            return refusal(404, 40410000, "order not found")
        if method == "GET":
            return reply(200, order)
        if order["status"] not in OPEN_STATES:
            return refusal(422, 42210000, "order is not cancelable" if method == "DELETE" else "order is not replaceable")
        if method == "DELETE":
            order["status"] = "canceled"
            order["canceled_at"] = self.stamp()
            return reply(204)
        replacement = {**order, "id": self._id(), "replaces": order["id"], "status": "accepted", "created_at": self.stamp(), **{k: v for k, v in body.items() if k != "trail"}}
        if "trail" in body:
            replacement["trail_price" if order.get("trail_price") else "trail_percent"] = body["trail"]
        order["status"], order["replaced_by"], order["replaced_at"] = "replaced", replacement["id"], self.stamp()
        self.orders[replacement["id"]] = replacement
        self._try_fill(replacement)
        return reply(200, replacement)

    def _price(self, symbol: str) -> float:
        return self.prices.get(symbol, 100.0)

    def _place(self, body: dict[str, Any]) -> HttpResult:
        if self.config["suspend_trade"]:
            return refusal(403, 40310000, "trading is suspended for this account")
        if any(o["client_order_id"] == body.get("client_order_id") for o in self.orders.values()):
            return refusal(422, 42210000, "client_order_id must be unique")
        legs = body.get("legs")
        symbol = body.get("symbol") or legs[0]["symbol"]
        price = self._price(symbol)
        qty = float(body["qty"]) if body.get("qty") else float(body["notional"]) / price
        cost = qty * price * (100 if "legs" in body or re.search(r"\d{6}[CP]\d{8}$", symbol) else 1)
        if body.get("side", "buy") == "buy" and cost > self.cash:
            return refusal(403, 40310000, "insufficient buying power")
        if body.get("side") == "sell" and symbol not in self.positions and self.config["no_shorting"]:
            return refusal(403, 40310000, "account is not allowed to short")
        kind = "crypto" if "/" in symbol else "us_option" if (legs or re.search(r"\d{6}[CP]\d{8}$", symbol)) else "us_equity"
        order = {
            "id": self._id(), "client_order_id": body["client_order_id"], "created_at": self.stamp(), "updated_at": self.stamp(), "submitted_at": self.stamp(),
            "filled_at": None, "expired_at": None, "canceled_at": None, "failed_at": None, "replaced_at": None, "replaced_by": None, "replaces": None,
            "asset_id": uid(9001), "symbol": symbol, "asset_class": kind, "notional": body.get("notional"), "qty": body.get("qty") or (None if body.get("notional") else None),
            "filled_qty": "0", "filled_avg_price": None, "order_class": body.get("order_class", ""), "order_type": body["type"], "type": body["type"],
            "side": body.get("side"), "position_intent": body.get("position_intent"), "time_in_force": body["time_in_force"], "limit_price": body.get("limit_price"),
            "stop_price": body.get("stop_price"), "trail_price": body.get("trail_price"), "trail_percent": body.get("trail_percent"), "hwm": None,
            "extended_hours": bool(body.get("extended_hours")), "status": "accepted", "legs": None,
        }
        if legs:
            order["legs"] = [{**order, "id": self._id(), "symbol": leg["symbol"], "side": leg["side"], "ratio_qty": leg["ratio_qty"], "legs": None, "status": "accepted"} for leg in legs]
        if body.get("order_class") in ("bracket", "oto", "oco"):
            exits = []
            for kind_name, price_key in (("take_profit", "limit_price"), ("stop_loss", "stop_price")):
                if kind_name in body:
                    exits.append({**order, "id": self._id(), "side": "sell" if body["side"] == "buy" else "buy", "type": "limit" if kind_name == "take_profit" else "stop", "order_type": "limit" if kind_name == "take_profit" else "stop", price_key: body[kind_name][price_key] if price_key in body[kind_name] else None, "limit_price": body[kind_name].get("limit_price"), "client_order_id": body["client_order_id"] + "-" + kind_name, "legs": None, "status": "held"})
            order["legs"] = exits
        self.orders[order["id"]] = order
        self._try_fill(order)
        return reply(200, order)

    def _try_fill(self, order: dict[str, Any]) -> None:
        if order["status"] not in OPEN_STATES or not self.market_open:
            return
        price = self._price(order["symbol"])
        limit = float(order["limit_price"]) if order.get("limit_price") else None
        marketable = order["type"] == "market" or (order["type"] == "limit" and limit is not None and ((order["side"] == "buy" and limit >= price) or (order["side"] == "sell" and limit <= price)))
        if not marketable:
            return
        qty = float(order["qty"]) if order.get("qty") else float(order["notional"]) / price
        self._fill(order, qty, price)

    def _fill(self, order: dict[str, Any], qty: float, price: float) -> None:
        order.update(status="filled", filled_qty=f"{qty:g}", filled_avg_price=f"{price:g}", filled_at=self.stamp(), qty=order.get("qty") or f"{qty:g}")
        sign = 1 if order["side"] == "buy" else -1
        multiplier = 100 if order["asset_class"] == "us_option" else 1
        self.cash -= sign * qty * price * multiplier
        held = self.positions.get(order["symbol"])
        total = (float(held["qty"]) if held else 0.0) + sign * qty
        if abs(total) < 1e-9:
            self.positions.pop(order["symbol"], None)
        else:
            average = price if held is None else (float(held["avg_entry_price"]) * float(held["qty"]) + sign * qty * price) / total if sign > 0 and float(held["qty"]) > 0 else float(held["avg_entry_price"])
            symbol = order["symbol"].replace("/", "")
            self.positions[order["symbol"]] = {
                "asset_id": order["asset_id"], "symbol": symbol, "asset_class": order["asset_class"], "exchange": "NASDAQ", "side": "long" if total > 0 else "short",
                "qty": f"{total:g}", "qty_available": f"{total:g}", "avg_entry_price": f"{average:g}", "cost_basis": f"{average * total * multiplier:.2f}",
                "current_price": f"{price:g}", "lastday_price": f"{price:g}", "market_value": f"{total * price * multiplier:.2f}", "change_today": "0",
                "unrealized_pl": f"{(price - average) * total * multiplier:.2f}", "unrealized_plpc": f"{(price - average) / average if average else 0:.4f}",
                "unrealized_intraday_pl": "0", "unrealized_intraday_plpc": "0", "asset_marginable": True,
            }
        self.activities.append({"id": f"20260930143000000::{self._id()}", "activity_type": "FILL", "transaction_time": self.stamp(), "type": "fill", "price": f"{price:g}", "qty": f"{qty:g}", "side": order["side"], "symbol": order["symbol"], "leaves_qty": "0", "order_id": order["id"], "cum_qty": f"{qty:g}", "order_status": "filled"})

    # --- positions ----------------------------------------------------------------------------------------------

    def _positions(self, method: str, path: str, query: dict[str, str]) -> HttpResult:
        if path == "/v2/positions" and method == "GET":
            return reply(200, list(self.positions.values()))
        if path == "/v2/positions" and method == "DELETE":
            if query.get("cancel_orders") == "true":
                for order in self.orders.values():
                    if order["status"] in OPEN_STATES:
                        order["status"] = "canceled"
            results = []
            for symbol in list(self.positions):
                closing = self._close(symbol, None, None)
                results.append({"symbol": symbol.replace("/", ""), "status": 200, "body": closing})
            return reply(207, results)
        tail = path[len("/v2/positions/"):]
        if tail.endswith("/exercise") or tail.endswith("/do-not-exercise"):
            symbol = tail.rsplit("/", 1)[0]
            if symbol not in self.positions:
                return refusal(403, 40310000, "no position for that contract")
            return reply(200)
        key = next((s for s in self.positions if s == tail or s.replace("/", "") == tail.replace("/", "")), None)
        if key is None:
            return refusal(404, 40410000, "position does not exist")
        if method == "GET":
            return reply(200, self.positions[key])
        qty = float(query["qty"]) if query.get("qty") else None
        percentage = float(query["percentage"]) if query.get("percentage") else None
        if qty is not None and qty > abs(float(self.positions[key]["qty"])):
            return refusal(403, 40310000, "insufficient qty available for order")
        return reply(200, self._close(key, qty, percentage))

    def _close(self, symbol: str, qty: Optional[float], percentage: Optional[float]) -> dict[str, Any]:
        held = self.positions[symbol]
        total = float(held["qty"])
        amount = qty if qty is not None else abs(total) * (percentage or 100) / 100
        side = "sell" if total > 0 else "buy"
        order = {
            "id": self._id(), "client_order_id": f"close-{self.counter}", "created_at": self.stamp(), "updated_at": self.stamp(), "submitted_at": self.stamp(),
            "asset_id": held["asset_id"], "symbol": held["symbol"], "asset_class": held["asset_class"], "qty": f"{amount:g}", "notional": None, "filled_qty": "0",
            "filled_avg_price": None, "order_class": "", "order_type": "market", "type": "market", "side": side, "time_in_force": "day", "limit_price": None,
            "stop_price": None, "extended_hours": False, "status": "accepted", "legs": None,
        }
        order["symbol"] = symbol
        self.orders[order["id"]] = order
        self._try_fill(order)
        return order

    # --- watchlists ------------------------------------------------------------------------------------------------

    def _asset(self, symbol: str) -> Optional[dict[str, Any]]:
        return next((a for a in self.assets if a["symbol"] == symbol), None)

    def _watchlists(self, method: str, path: str, body: Any) -> HttpResult:
        parts = path[len("/v2/watchlists"):].strip("/").split("/")
        if parts == [""]:
            if method == "POST":
                if any(w["name"] == body["name"] for w in self.watchlists.values()):
                    return refusal(422, 42210000, "watchlist name must be unique")
                wid = self._id()
                self.watchlists[wid] = {"id": wid, "account_id": uid(7001), "name": body["name"], "created_at": self.stamp(), "updated_at": self.stamp(), "assets": [a for a in (self._asset(s) for s in body.get("symbols", [])) if a]}
                return reply(200, self.watchlists[wid])
            return reply(200, [{**w, "assets": None} for w in self.watchlists.values()])
        watchlist = self.watchlists.get(parts[0])
        if watchlist is None:
            return refusal(404, 40410000, "watchlist not found")
        if len(parts) == 2:
            watchlist["assets"] = [a for a in watchlist["assets"] if a["symbol"] != parts[1]]
            return reply(200, watchlist)
        if method == "GET":
            return reply(200, watchlist)
        if method == "DELETE":
            del self.watchlists[parts[0]]
            return reply(204)
        if method == "POST":
            asset = self._asset(body["symbol"])
            if asset is None:
                return refusal(404, 40410000, "asset not found")
            watchlist["assets"].append(asset)
            return reply(200, watchlist)
        if "name" in body:
            watchlist["name"] = body["name"]
        if "symbols" in body:
            watchlist["assets"] = [a for a in (self._asset(s) for s in body["symbols"]) if a]
        return reply(200, watchlist)

    # --- the data host -------------------------------------------------------------------------------------------------

    def _snapshot(self, symbol: str) -> dict[str, Any]:
        price = self._price(symbol)
        quote = {"ap": round(price + 0.05, 2), "as": 3, "bp": round(price - 0.05, 2), "bs": 2, "t": self.stamp()}
        base = {"latestTrade": {"p": price, "s": 100, "t": self.stamp()}, "latestQuote": quote, "dailyBar": {"o": price - 1, "h": price + 2, "l": price - 2, "c": price, "v": 1_000_000}, "prevDailyBar": {"c": price - 1.5}}
        if re.search(r"\d{6}[CP]\d{8}$", symbol):
            base.update(impliedVolatility=0.32, greeks={"delta": 0.5, "gamma": 0.06, "theta": -0.28, "vega": 0.05, "rho": 0.01})
        return base

    def _data(self, path: str, query: dict[str, str]) -> HttpResult:
        if path.endswith("/snapshot"):
            symbol = path.split("/")[3]
            return reply(200, self._snapshot(symbol)) if symbol in self.prices else refusal(404, 40410000, "symbol not found")
        symbols = [s for s in query.get("symbols", "").split(",") if s in self.prices]
        return reply(200, {"snapshots": {s: self._snapshot(s) for s in symbols}}) if symbols else reply(200, {"snapshots": {}})
