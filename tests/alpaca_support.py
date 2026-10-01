"""Shared fakes for the Alpaca tests: a scripted HTTP layer that records headers, and payloads in the documented shapes."""

from __future__ import annotations

import json
import threading
from typing import Any

from tradingview_data.providers.common import HttpResult

KEY_ID = "PKTESTKEYID0123456789"
SECRET = "s3cr3t-0123456789-abcdefghijklmnopqrstuvwxyz"


def ok(payload: Any) -> HttpResult:
    return HttpResult(200, json.dumps(payload).encode(), "application/json")


def failure(status: int, body: Any) -> HttpResult:
    return HttpResult(status, json.dumps(body).encode(), "application/json")


def html(status: int) -> HttpResult:
    return HttpResult(status, f"<html><head><title>{status} Authorization Required</title></head></html>".encode(), "text/html")


class FakeHttp:
    """Returns scripted results (or raises scripted exceptions) and records every call, headers included."""

    def __init__(self, *script: Any, gate: "threading.Event | None" = None) -> None:
        self.script = list(script)
        self.calls: list[tuple[str, list[tuple[str, str]], dict[str, str]]] = []
        self.gate = gate
        self._lock = threading.Lock()

    def __call__(self, url: str, params: list[tuple[str, str]], headers: "dict[str, str] | None" = None) -> HttpResult:
        with self._lock:
            self.calls.append((url, params, dict(headers or {})))
            item = self.script[min(len(self.calls), len(self.script)) - 1]
        if self.gate is not None:
            self.gate.wait(2)
        if isinstance(item, Exception):
            raise item
        return item


def bar(t: str, close: float, **extra: Any) -> dict[str, Any]:
    return {"t": t, "o": close - 1, "h": close + 1, "l": close - 2, "c": close, "v": 1000 + close, "n": 10, "vw": close - 0.5, **extra}


def quote(t: str, bid: float, **extra: Any) -> dict[str, Any]:
    return {"t": t, "bp": bid, "bs": 2, "bx": "Q", "ap": bid + 0.1, "as": 3, "ax": "P", "c": ["R"], "z": "C", **extra}


def trade(t: str, price: float, **extra: Any) -> dict[str, Any]:
    return {"t": t, "p": price, "s": 100, "x": "V", "c": ["@", "T"], "i": 1234, "z": "C", **extra}


DAILY = {
    "AAPL": [bar("2026-09-25T04:00:00Z", 218.0), bar("2026-09-28T04:00:00Z", 220.0), bar("2026-09-29T04:00:00Z", 221.0)],
    "TSLA": [bar("2026-09-25T04:00:00Z", 400.0), bar("2026-09-28T04:00:00Z", 405.0)],
}
QUOTES = [quote("2026-09-29T13:30:00.123456789Z", 221.0), quote("2026-09-29T13:30:00.987Z", 221.1), quote("2026-09-29T13:30:02Z", 221.2)]
TRADES = [trade("2026-09-29T13:30:00.100Z", 221.0), trade("2026-09-29T13:30:01.200Z", 221.5, s=50), trade("2026-09-29T13:30:02Z", 221.4)]

CONTRACT_CALL = "AAPL260116C00250000"
CONTRACT_PUT = "AAPL260116P00240000"
LATER_CALL = "AAPL260220C00250000"


def snapshot(price: float, previous: float) -> dict[str, Any]:
    return {
        "latestTrade": trade("2026-09-29T19:59:59.500Z", price),
        "latestQuote": quote("2026-09-29T19:59:59Z", price - 0.05),
        "minuteBar": bar("2026-09-29T19:59:00Z", price),
        "dailyBar": bar("2026-09-29T04:00:00Z", price),
        "prevDailyBar": bar("2026-09-28T04:00:00Z", previous),
    }


def contract(bid: float, iv: float, last: float = 4.1) -> dict[str, Any]:
    return {
        "latestQuote": quote("2026-09-29T19:59:59Z", bid),
        "latestTrade": {"t": "2026-09-29T19:57:32.589554432Z", "p": last, "s": 1, "x": "A", "c": "I"},
        "impliedVolatility": iv,
        "greeks": {"delta": 0.5, "gamma": 0.06, "theta": -0.28, "vega": 0.05, "rho": 0.01},
    }


PAYLOADS: dict[str, Any] = {
    "stock_bars": {"bars": DAILY, "next_page_token": "PAGE2"},
    "stock_bars_single": {"bars": DAILY["AAPL"], "symbol": "AAPL", "next_page_token": None},
    "stock_latest_bars": {"bars": {"AAPL": bar("2026-09-29T19:59:00Z", 221.0), "TSLA": bar("2026-09-29T19:58:00Z", 405.0)}},
    "stock_latest_bar_single": {"bar": bar("2026-09-29T19:59:00Z", 221.0), "symbol": "AAPL"},
    "stock_quotes": {"quotes": {"AAPL": QUOTES}, "next_page_token": None},
    "stock_quotes_single": {"quotes": QUOTES, "symbol": "AAPL", "next_page_token": None},
    "stock_latest_quotes": {"quotes": {"AAPL": QUOTES[0], "TSLA": quote("2026-09-29T13:30:00Z", 405.0)}},
    "stock_latest_quote_single": {"quote": QUOTES[0], "symbol": "AAPL"},
    "stock_trades": {"trades": {"AAPL": TRADES}},
    "stock_trades_single": {"trades": TRADES, "symbol": "AAPL"},
    "stock_latest_trades": {"trades": {"AAPL": TRADES[0], "TSLA": trade("2026-09-29T13:30:00Z", 405.0)}},
    "stock_latest_trade_single": {"trade": TRADES[0], "symbol": "AAPL"},
    "stock_snapshots": {"AAPL": snapshot(221.0, 220.0), "TSLA": snapshot(396.0, 400.0)},
    "stock_snapshot_single": {**snapshot(221.0, 220.0), "symbol": "AAPL"},
    "stock_auctions": {"auctions": {"AAPL": [{"d": "2026-09-28", "o": [{"c": "Q", "p": 218.5, "t": "2026-09-28T13:30:00.188Z", "x": "P"}], "c": [{"c": "6", "p": 220.0, "t": "2026-09-28T20:00:00.120Z", "x": "P"}, {"c": "M", "p": 220.0, "t": "2026-09-28T20:00:00.125Z", "x": "Q"}]}]}},
    "stock_auctions_single": {"auctions": [{"d": "2026-09-28", "o": [{"c": "Q", "p": 218.5, "t": "2026-09-28T13:30:00.188Z", "x": "P"}], "c": []}], "symbol": "AAPL"},
    "stock_conditions": {"@": "Regular Sale", "A": "Acquisition", "B": "Bunched Trade"},
    "stock_exchanges": {"N": "New York Stock Exchange", "V": "IEX"},
    "option_bars": {"bars": {CONTRACT_CALL: [bar("2026-09-25T04:00:00Z", 4.0), bar("2026-09-28T04:00:00Z", 4.4)]}},
    "option_trades": {"trades": {CONTRACT_CALL: [{"t": "2026-09-29T14:00:00Z", "p": 4.1, "s": 2, "x": "A", "c": "I"}, {"t": "2026-09-29T15:00:00Z", "p": 4.3, "s": 5, "x": "B", "c": "e"}]}},
    "option_latest_quotes": {"quotes": {CONTRACT_CALL: quote("2026-09-29T19:59:59Z", 4.15, c="A")}},
    "option_latest_trades": {"trades": {CONTRACT_CALL: {"t": "2026-09-29T19:57:32Z", "p": 4.1, "s": 1, "x": "A", "c": "I"}}},
    "option_snapshots": {"snapshots": {CONTRACT_CALL: contract(4.15, 0.337)}},
    "option_chain": {
        "snapshots": {
            CONTRACT_CALL: contract(4.15, 0.337),
            CONTRACT_PUT: contract(2.15, 0.31),
            LATER_CALL: contract(6.15, 0.35),
            "AAPL260116C00260000": contract(2.0, 0.32),
        },
        "next_page_token": "CHAIN2",
    },
    "option_conditions": {"a": "SLAN - Single Leg Auction Non ISO", "e": "SLFT - Single Leg Floor Trade"},
    "option_exchanges": {"A": "NYSE American Options", "Q": "Nasdaq Options"},
    "crypto_bars": {"bars": {"BTC/USD": [bar("2026-09-20T00:00:00Z", 81164.3), bar("2026-09-21T00:00:00Z", 86596.5)]}, "next_page_token": None},
    "crypto_quotes": {"quotes": {"BTC/USD": [{"t": "2026-09-29T11:47:18.443Z", "bp": 29058, "bs": 0.35, "ap": 29059, "as": 3.25}, {"t": "2026-09-29T11:47:19.5Z", "bp": 29057, "bs": 0.4, "ap": 29060, "as": 1.0}]}},
    "crypto_trades": {"trades": {"BTC/USD": [{"t": "2026-09-29T12:01:00.537Z", "p": 29791, "s": 0.0016, "i": 5941898911247126155, "tks": "S"}, {"t": "2026-09-29T12:02:00.1Z", "p": 29795, "s": 0.01, "i": 5941898911247126156, "tks": "B"}]}},
    "crypto_latest_bars": {"bars": {"BTC/USD": bar("2026-09-29T12:00:00Z", 29003.0)}},
    "crypto_latest_quotes": {"quotes": {"BTC/USD": {"t": "2026-09-29T11:47:18.443Z", "bp": 29058, "bs": 0.35, "ap": 29059, "as": 3.25}}},
    "crypto_latest_trades": {"trades": {"BTC/USD": {"t": "2026-09-29T12:01:00.537Z", "p": 29791, "s": 0.0016, "i": 31455289, "tks": "S"}}},
    "crypto_orderbooks": {"orderbooks": {"BTC/USD": {"t": "2026-09-29T08:00:14.137Z", "a": [{"p": 20902, "s": 0.0097}, {"p": 20910, "s": 1.5}, {"p": 21444, "s": 0}], "b": [{"p": 20846, "s": 0.19}, {"p": 20840, "s": 2.0}, {"p": 20350, "s": 0}]}}},
    "crypto_snapshots": {"snapshots": {"BTC/USD": snapshot(31744.0, 31000.0), "ETH/USD": snapshot(1800.0, 1850.0)}},
    "forex_latest_rates": {"rates": {"USDJPY": {"ap": 128.112, "bp": 127.752, "mp": 127.779, "t": "2026-09-29T05:38:41.311Z"}}},
    "forex_rates": {"rates": {"USDJPY": [{"ap": 115.18, "bp": 114.19, "mp": 115.14, "t": "2026-09-29T00:01:00Z"}, {"ap": 115.19, "bp": 114.2, "mp": 115.13, "t": "2026-09-29T00:02:00Z"}]}},
    "fixed_income_prices": {"prices": {"US912797KJ59": {"p": 99.6459, "t": "2026-09-29T20:58:00.648Z", "ytm": 4.249, "ytw": 4.249}, "US912797KS58": {"p": 99.3193, "t": "2026-09-29T20:58:00.648Z", "ytm": 4.2245, "ytw": 4.2245}}},
    "fixed_income_quotes": {"quotes": {"US912797SX61": {"ams": 1000, "ap": 99.9, "as": 1000000, "aytm": 2.2, "aytw": 2.2, "bms": 1000, "bp": 99.8, "bs": 1000000, "bytm": 5.2, "bytw": 5.2, "t": "2026-09-29T06:56:01.882Z"}}},
    "most_actives": {"most_actives": [{"symbol": "AAPL", "volume": 5_000_000, "trade_count": 90_000}, {"symbol": "TSLA", "volume": 4_000_000, "trade_count": 120_000}], "last_updated": "2026-09-29T19:59:30.088Z"},
    "movers": {"gainers": [{"change": 2.46, "percent_change": 145.56, "price": 4.15, "symbol": "AGRI"}], "losers": [{"change": -0.26, "percent_change": -63.07, "price": 0.15, "symbol": "MTACW"}], "last_updated": "2026-09-29T17:53:30Z", "market_type": "stocks"},
    "news": {
        "news": [
            {"id": 1, "headline": "Apple leads phone sales", "author": "Charles Gross", "source": "benzinga", "created_at": "2026-09-29T11:08:42Z", "updated_at": "2026-09-29T11:08:43Z", "summary": "A short summary.", "content": "<p>Body</p>", "url": "https://example.com/a", "images": [], "symbols": ["AAPL"]},
            {"id": 2, "headline": "Chips rally", "author": "", "source": "benzinga", "created_at": "2026-09-29T09:00:00Z", "summary": "", "content": "<p>Chips <b>rallied</b> today.</p>", "url": "javascript:alert(1)", "symbols": ["NVDA", "AAPL"]},
        ],
        "next_page_token": "NEWS2",
    },
    "corporate_actions": {
        "corporate_actions": {
            "cash_dividends": [{"id": "d1", "symbol": "AAPL", "rate": 0.25, "ex_date": "2026-08-09", "record_date": "2026-08-10", "payable_date": "2026-08-16", "cusip": "037833100"}],
            "forward_splits": [{"id": "s1", "symbol": "NVDA", "new_rate": 10, "old_rate": 1, "ex_date": "2026-06-10"}],
            "name_changes": [],
        },
        "next_page_token": None,
    },
}
