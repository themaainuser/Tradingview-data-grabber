"""Shared fakes for the provider tests: a scripted HTTP layer and small hand-made payloads."""

from __future__ import annotations

import json
import threading
from typing import Any

from tradingview_data.providers.alphavantage import HttpResult

KEY = "sk-live-SECRET-0123456789"


def ok(payload: Any) -> HttpResult:
    return HttpResult(200, json.dumps(payload).encode(), "application/json")


def text(body: str, status: int = 200, content_type: str = "text/plain") -> HttpResult:
    return HttpResult(status, body.encode(), content_type)


class FakeHttp:
    """Returns scripted results (or raises scripted exceptions) and records every call."""

    def __init__(self, *script: Any, gate: "threading.Event | None" = None) -> None:
        self.script = list(script)
        self.calls: list[tuple[str, list[tuple[str, str]]]] = []
        self.gate = gate
        self._lock = threading.Lock()

    def __call__(self, url: str, params: list[tuple[str, str]]) -> HttpResult:
        with self._lock:
            self.calls.append((url, params))
            item = self.script[min(len(self.calls), len(self.script)) - 1]
        if self.gate is not None:
            self.gate.wait(2)
        if isinstance(item, Exception):
            raise item
        return item


DAILY = {
    "Meta Data": {"1. Information": "Daily Prices", "2. Symbol": "IBM", "3. Last Refreshed": "2026-09-29", "5. Time Zone": "US/Eastern"},
    "Time Series (Daily)": {
        "2026-09-29": {"1. open": "220.0", "2. high": "223.0", "3. low": "219.0", "4. close": "221.0", "5. volume": "1000"},
        "2026-09-28": {"1. open": "218.0", "2. high": "221.0", "3. low": "217.0", "4. close": "220.0", "5. volume": "3000"},
        "2026-09-25": {"1. open": "215.0", "2. high": "219.0", "3. low": "214.0", "4. close": "218.0", "5. volume": "2000"},
    },
}

PLACEHOLDER = {
    "endpoint": "Realtime Options",
    "message": "This is a premium endpoint. ***THE SAMPLE DATA SCHEMA BELOW IS ARTIFICIAL AND FOR ILLUSTRATION PURPOSES ONLY***. Subscribe at https://www.alphavantage.co/premium/",
    "data": [{"contractID": "XXYYZZ999999C00020", "symbol": "XXYYZZ", "expiration": "2099-99-99", "strike": "20.00", "type": "call", "last": "100.00"}],
}
