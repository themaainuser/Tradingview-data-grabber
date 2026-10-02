"""Alpaca's answers as the shapes the dashboard draws.

Alpaca sends almost every number as a string (``"equity": "100234.56"``). Here the numbers become
numbers, a value that is missing or not a finite number becomes ``None``, fields nobody draws are
dropped, and what the dashboard would otherwise have to work out (is this order cancelable, how much
did the account move today) is worked out once, here.
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Optional

# Order states in which an order can still change. Alpaca's order lifecycle documentation lists them.
_OPEN = {"new", "partially_filled", "accepted", "pending_new", "accepted_for_bidding", "pending_cancel", "pending_replace", "held", "calculated", "stopped", "suspended"}
_CANCELABLE = _OPEN - {"pending_cancel"}


def num(value: Any) -> Optional[float]:
    """A finite float from a number or numeric string; ``None`` for anything else."""

    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(value) else None
    if isinstance(value, str) and value.strip():
        try:
            number = float(value)
        except ValueError:
            return None
        return number if math.isfinite(number) else None
    return None


def text(value: Any) -> Optional[str]:
    return value if isinstance(value, str) and value != "" else None


def flag(value: Any) -> Optional[bool]:
    return value if isinstance(value, bool) else None


def _src(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _pick(source: dict[str, Any], numbers: Iterable[str] = (), texts: Iterable[str] = (), flags: Iterable[str] = ()) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name in texts:
        out[name] = text(source.get(name))
    for name in numbers:
        out[name] = num(source.get(name))
    for name in flags:
        out[name] = flag(source.get(name))
    return out


def _each(value: Any, view: Any) -> list[Any]:
    return [view(item) for item in value if isinstance(item, dict)] if isinstance(value, list) else []


# --- account --------------------------------------------------------------------------------------


def account_view(raw: Any) -> dict[str, Any]:
    a = _src(raw)
    out = _pick(
        a,
        numbers=(
            "cash", "equity", "last_equity", "portfolio_value", "buying_power", "regt_buying_power",
            "non_marginable_buying_power", "options_buying_power", "sma", "initial_margin", "maintenance_margin",
            "last_maintenance_margin", "multiplier", "long_market_value", "short_market_value", "accrued_fees", "pending_transfer_in",
            "pending_transfer_out", "pending_reg_taf_fees", "intraday_adjustments",
            "options_approved_level", "options_trading_level",
        ),
        texts=("id", "account_number", "status", "currency", "created_at", "balance_asof", "crypto_status"),
        flags=("trading_blocked", "account_blocked", "transfers_blocked", "trade_suspended_by_user", "shorting_enabled"),
    )
    equity, last = out["equity"], out["last_equity"]
    out["day_change"] = equity - last if equity is not None and last is not None else None
    out["day_change_percent"] = (equity - last) / last * 100 if equity is not None and last else None
    return out


def config_view(raw: Any) -> dict[str, Any]:
    c = _src(raw)
    return {
        **_pick(c, texts=("trade_confirm_email", "max_margin_multiplier"), numbers=("max_options_trading_level",),
                flags=("suspend_trade", "no_shorting", "fractional_trading", "disable_overnight_trading", "ptp_no_exception_entry")),
    }


def history_view(raw: Any) -> dict[str, Any]:
    h = _src(raw)
    stamps = [t for t in (h.get("timestamp") or []) if isinstance(t, (int, float)) and not isinstance(t, bool)]
    size = len(stamps)

    def column(name: str) -> list[Optional[float]]:
        values = h.get(name) if isinstance(h.get(name), list) else []
        return [num(values[i]) if i < len(values) else None for i in range(size)]

    return {
        "timeframe": text(h.get("timeframe")),
        "base_value": num(h.get("base_value")),
        "base_value_asof": text(h.get("base_value_asof")),
        "timestamp": [int(t) for t in stamps],
        "equity": column("equity"),
        "profit_loss": column("profit_loss"),
        "profit_loss_pct": column("profit_loss_pct"),
    }


def activity_view(raw: Any) -> dict[str, Any]:
    a = _src(raw)
    out = _pick(
        a,
        numbers=("qty", "price", "cum_qty", "leaves_qty", "net_amount", "per_share_amount"),
        texts=("id", "activity_type", "activity_sub_type", "symbol", "side", "order_id", "order_status", "type", "status", "currency", "transaction_time", "created_at", "date"),
    )
    out["time"] = out["transaction_time"] or out["created_at"] or out["date"]
    return out


# --- market -----------------------------------------------------------------------------------------


def clock_view(raw: Any) -> dict[str, Any]:
    return _pick(_src(raw), texts=("timestamp", "next_open", "next_close"), flags=("is_open",))


def calendar_view(raw: Any) -> dict[str, Any]:
    return _pick(_src(raw), texts=("date", "open", "close", "settlement_date", "session_open", "session_close"))


def asset_view(raw: Any) -> dict[str, Any]:
    a = _src(raw)
    out = _pick(
        a,
        numbers=("min_order_size", "min_trade_increment", "price_increment", "maintenance_margin_requirement", "margin_requirement_long", "margin_requirement_short"),
        texts=("id", "symbol", "name", "class", "exchange", "status", "borrow_status"),
        flags=("tradable", "marginable", "shortable", "fractionable"),
    )
    out["attributes"] = [x for x in a.get("attributes") or [] if isinstance(x, str)]
    return out


def contract_view(raw: Any) -> dict[str, Any]:
    c = _src(raw)
    out = _pick(
        c,
        numbers=("strike_price", "multiplier", "size", "open_interest", "close_price"),
        texts=("id", "symbol", "name", "underlying_symbol", "root_symbol", "type", "style", "status", "expiration_date", "open_interest_date", "close_price_date", "underlying_asset_id"),
        flags=("tradable", "ppind"),
    )
    out["deliverables"] = [
        _pick(d, numbers=("amount", "allocation_percentage"), texts=("type", "symbol", "asset_id", "settlement_type", "settlement_method"), flags=("delayed_settlement",))
        for d in c.get("deliverables") or []
        if isinstance(d, dict)
    ]
    return out


# --- orders and positions -----------------------------------------------------------------------------


def order_view(raw: Any) -> dict[str, Any]:
    o = _src(raw)
    out = _pick(
        o,
        numbers=("qty", "notional", "filled_qty", "filled_avg_price", "limit_price", "stop_price", "trail_price", "trail_percent", "hwm", "ratio_qty"),
        texts=(
            "id", "client_order_id", "symbol", "asset_id", "asset_class", "side", "order_class", "time_in_force", "status", "position_intent",
            "created_at", "submitted_at", "filled_at", "canceled_at", "expired_at", "failed_at", "replaced_at", "expires_at", "replaced_by", "replaces",
        ),
        flags=("extended_hours",),
    )
    out["type"] = text(o.get("type")) or text(o.get("order_type"))
    out["cancelable"] = out["status"] in _CANCELABLE
    out["open"] = out["status"] in _OPEN
    out["legs"] = _each(o.get("legs"), order_view)
    return out


def position_view(raw: Any) -> dict[str, Any]:
    p = _src(raw)
    return _pick(
        p,
        numbers=(
            "qty", "qty_available", "avg_entry_price", "cost_basis", "current_price", "lastday_price", "market_value", "change_today",
            "unrealized_pl", "unrealized_plpc", "unrealized_intraday_pl", "unrealized_intraday_plpc",
        ),
        texts=("asset_id", "symbol", "asset_class", "exchange", "side"),
        flags=("asset_marginable",),
    )


def watchlist_view(raw: Any) -> dict[str, Any]:
    w = _src(raw)
    out = _pick(w, texts=("id", "name", "created_at", "updated_at"))
    out["assets"] = _each(w.get("assets"), asset_view)
    return out


def bulk_view(raw: Any, key: str) -> list[dict[str, Any]]:
    """The per-item answers of cancel-all (``key="id"``) and close-all (``key="symbol"``): HTTP 207."""

    out = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        status = item.get("status") if isinstance(item.get("status"), int) else None
        body = _src(item.get("body"))
        ok = status is not None and 200 <= status < 300
        out.append(
            {
                key: text(item.get(key)),
                "status": status,
                "ok": ok,
                "message": None if ok else text(body.get("message")),
                "order": order_view(body) if ok and body else None,
            }
        )
    return out


# --- quotes ---------------------------------------------------------------------------------------------


def quote_view(symbol: str, kind: str, raw: Any) -> dict[str, Any]:
    """One symbol's snapshot as a quote: bid, ask, last and the day so far. ``raw`` is the snapshot, or for
    crypto and options the ``{"snapshots": {symbol: snapshot}}`` wrapper."""

    snap = _src(raw)
    if isinstance(snap.get("snapshots"), dict):
        snap = _src(next(iter(snap["snapshots"].values()), None))
    trade, quote, day, previous = _src(snap.get("latestTrade")), _src(snap.get("latestQuote")), _src(snap.get("dailyBar")), _src(snap.get("prevDailyBar"))
    bid, ask, last = num(quote.get("bp")), num(quote.get("ap")), num(trade.get("p"))
    close = num(day.get("c")) if num(day.get("c")) is not None else last
    before = num(previous.get("c"))
    change = close - before if close is not None and before else None
    greeks = _src(snap.get("greeks"))
    return {
        "symbol": symbol,
        "kind": kind,
        "bid": bid,
        "bid_size": num(quote.get("bs")),
        "ask": ask,
        "ask_size": num(quote.get("as")),
        "mid": (bid + ask) / 2 if bid and ask else None,
        "spread": ask - bid if bid and ask else None,
        "last": last,
        "last_size": num(trade.get("s")),
        "last_time": text(trade.get("t")),
        "quote_time": text(quote.get("t")),
        "open": num(day.get("o")),
        "high": num(day.get("h")),
        "low": num(day.get("l")),
        "close": num(day.get("c")),
        "volume": num(day.get("v")),
        "previous_close": before,
        "change": change,
        "change_percent": change / before * 100 if change is not None and before else None,
        "implied_volatility": num(snap.get("impliedVolatility")),
        "greeks": {name: num(greeks.get(name)) for name in ("delta", "gamma", "theta", "vega", "rho")} if greeks else None,
    }
