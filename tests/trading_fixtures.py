"""The trading API's real answers, as the dashboard's parsers must read them.

``build()`` drives the real service against the fake broker and returns one answer per shape. The result
is committed as ``frontend/src/lib/testing/trading-fixtures.json``: the frontend parses every entry with its
own parsers (``trading.spec.ts``) and ``tests/test_trading_fixtures.py`` fails when the file no longer
matches what the backend produces. Regenerate it with ``python tests/trading_fixtures.py`` and then
run ``pnpm exec prettier --write src/lib/testing/trading-fixtures.json`` in ``frontend/`` (the lint step checks it).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))

from trading_support import KEY, SECRET, FakeBroker, refusal, uid  # noqa: E402

from tradingview_data.trading.service import TradingService  # noqa: E402

TARGET = Path(__file__).resolve().parent.parent / "frontend" / "src" / "lib" / "testing" / "trading-fixtures.json"
CALL, PUT = "AAPL260116C00250000", "AAPL260116P00240000"


def order(symbol: str, client_id: str, **fields: Any) -> dict[str, Any]:
    return {"symbol": symbol, "side": "buy", "type": "market", "time_in_force": "day", "qty": "1", "client_order_id": client_id, **fields}


def build() -> dict[str, Any]:
    broker = FakeBroker()
    env = {"ALPACA_PAPER_API_KEY_ID": KEY, "ALPACA_PAPER_API_SECRET_KEY": SECRET}
    svc = TradingService(http=broker, getenv=env.get, clock=lambda: 1790000000.0)
    out: dict[str, Any] = {"environments": svc.environments()}

    def keep(name: str, answer: dict[str, Any]) -> dict[str, Any]:
        out[name] = {**answer, "elapsed_ms": 0}
        return answer

    bought = keep("order_filled", svc.place_order("paper", order("AAPL", "fixture-1", qty="10")))
    keep("order_waiting", svc.place_order("paper", order("TSLA", "fixture-2", type="limit", time_in_force="gtc", qty="2", limit_price="300")))
    keep(
        "order_bracket",
        svc.place_order("paper", order("SPY", "fixture-3", type="limit", time_in_force="gtc", qty="2", limit_price="500", order_class="bracket", take_profit={"limit_price": "560"}, stop_loss={"stop_price": "480", "limit_price": "479"})),
    )
    legs = [{"symbol": CALL, "ratio_qty": "1", "side": "buy", "position_intent": "buy_to_open"}, {"symbol": PUT, "ratio_qty": "1", "side": "sell"}]
    keep("order_multileg", svc.place_order("paper", {"order_class": "mleg", "qty": "1", "type": "limit", "limit_price": "1.00", "time_in_force": "day", "client_order_id": "fixture-4", "legs": legs}))
    keep("order_refused", svc.place_order("paper", order("AAPL", "fixture-5", qty="100000")))
    keep("account", svc.account("paper"))
    keep("config", svc.configurations("paper"))
    keep("history", svc.history("paper", {"period": "1W", "timeframe": "1D"}))
    keep("activities", svc.activities("paper", {}))
    keep("clock", svc.clock("paper"))
    keep("calendar", svc.calendar("paper", {}))
    keep("assets", svc.assets("paper", {"search": "a"}))
    keep("asset", svc.asset("paper", "AAPL"))
    keep("contracts", svc.contracts("paper", {"underlying_symbols": "AAPL"}))
    keep("quote_stock", svc.quote("paper", "AAPL", {}))
    keep("quote_option", svc.quote("paper", CALL, {}))
    keep("orders", svc.orders("paper", {"status": "all"}))
    keep("order_one", svc.order("paper", bought["data"]["id"]))
    keep("positions", svc.positions("paper"))
    keep("position", svc.position("paper", "AAPL"))
    watchlist = keep("watchlist", svc.create_watchlist("paper", {"name": "Core", "symbols": ["AAPL", "TSLA"]}))
    keep("watchlists", svc.watchlists("paper"))
    keep("bulk_cancel", svc.cancel_all_orders("paper"))
    keep("bulk_close", svc.close_all_positions("paper", {"cancel_orders": "true"}))
    keep("deleted", svc.delete_watchlist("paper", watchlist["data"]["id"]))
    keep("not_found", svc.order("paper", uid(404)))
    keep("not_configured", TradingService(http=broker, getenv={}.get, clock=lambda: 1790000000.0).account("paper"))
    broker.queue.append(refusal(401, 40110000, "request is not authorized"))
    keep("invalid_key", svc.account("paper"))
    broker.queue.append(requests.ReadTimeout())
    keep("outcome_unknown", svc.place_order("paper", order("AAPL", "fixture-6")))
    return json.loads(json.dumps(out))


if __name__ == "__main__":
    TARGET.write_text(json.dumps(build(), indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {TARGET}")
