"""Alpaca response shapes -> views. Anything not special-cased goes through ``views.analyze``.

Alpaca's market data comes in a few shapes: records keyed by symbol (``{"bars": {"AAPL": [...]}}``),
the same for one symbol (``{"bars": [...], "symbol": "AAPL"}``), snapshots, and a handful of
one-off responses (news, screener, corporate actions, order book). Timestamps are RFC-3339 with up
to nanoseconds and become UTC epoch seconds for charts and ``YYYY-MM-DD HH:MM:SS`` text in tables.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from . import views as V

Built = tuple[list[Optional[dict[str, Any]]], list[str]]
Handler = Callable[[Any, str], Built]

MAX_CHARTS = 6
SNAPSHOT_FACTS = 3
DEPTH_LEVELS = 20
_TIME = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.(\d+))?)?\s*(Z|[+-]\d{2}:?\d{2})?)?$")
_OCC = re.compile(r"^(.+?)(\d{2})(\d{2})(\d{2})([CP])(\d{8})$")
_SNAPSHOT_KEYS = {"latestTrade", "latestQuote", "minuteBar", "dailyBar", "prevDailyBar"}
_CORPORATE_FIRST = ["symbol", "ex_date", "record_date", "payable_date", "process_date", "effective_date"]


# --- small helpers --------------------------------------------------------------------------------


def _parse(value: Any) -> Optional[tuple[datetime, str]]:
    """``(UTC datetime, fraction digits)`` of an RFC-3339 timestamp or a date, else ``None``."""

    match = _TIME.match(str(value).strip()) if value is not None else None
    if not match:
        return None
    y, mo, d, h, mi, s, fraction, offset = match.groups()
    try:
        when = datetime(int(y), int(mo), int(d), int(h or 0), int(mi or 0), int(s or 0), tzinfo=timezone.utc)
    except ValueError:
        return None
    if offset and offset != "Z":
        sign = 1 if offset[0] == "+" else -1
        digits = offset[1:].replace(":", "")
        when -= sign * timedelta(hours=int(digits[:2]), minutes=int(digits[2:]))
    return when, fraction or ""


def moment(value: Any) -> Optional[int]:
    parsed = _parse(value)
    return int(parsed[0].timestamp()) if parsed else None


def stamp(value: Any, milliseconds: bool = False) -> Optional[str]:
    """``2026-09-29 15:30:00`` (UTC), with ``.123`` appended for ticks; a bare date stays a date."""

    parsed = _parse(value)
    if parsed is None:
        return None if value in (None, "") else str(value)
    when, fraction = parsed
    if len(str(value).strip()) == 10:
        return when.strftime("%Y-%m-%d")
    text = when.strftime("%Y-%m-%d %H:%M:%S")
    return f"{text}.{(fraction + '000')[:3]}" if milliseconds and fraction else text


def num(value: Any) -> Optional[float]:
    return V.to_number(value)


def _join(value: Any) -> Optional[str]:
    """Condition codes arrive as a list for stocks and a string for options."""

    if isinstance(value, list):
        return ",".join(str(v) for v in value if v not in (None, "")) or None
    return str(value).strip() or None if value is not None else None


def _dicts(value: Any) -> list[dict[str, Any]]:
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def by_symbol(payload: Any, plural: str, singular: Optional[str] = None) -> dict[str, Any]:
    """``{symbol: records-or-record}`` from ``{"bars": {...}}`` and from the single-symbol forms
    ``{"bars": [...], "symbol": "AAPL"}`` / ``{"bar": {...}, "symbol": "AAPL"}``."""

    if not isinstance(payload, dict):
        return {}
    data, symbol = payload.get(plural), payload.get("symbol")
    if isinstance(data, dict):
        return {str(k): v for k, v in data.items()}
    if isinstance(data, list) and symbol:
        return {str(symbol): data}
    one = payload.get(singular) if singular else None
    if isinstance(one, dict) and symbol:
        return {str(symbol): one}
    return {}


def _table(view_id: str, title: str, rows: list[dict[str, Any]], subtitle: Optional[str] = None, keys: Optional[list[str]] = None) -> Optional[dict[str, Any]]:
    """A table of the keys that have a value in at least one row (columns that are always empty are dropped)."""

    if not rows:
        return None
    wanted = keys or list(dict.fromkeys(k for row in rows for k in row))
    present = [k for k in wanted if any(row.get(k) not in (None, "") for row in rows)]
    return V.table_view(view_id, title, rows, keys=present or None, subtitle=subtitle)


def _facts(view_id: str, title: str, groups: list[tuple[Optional[str], list[Optional[dict[str, Any]]]]], subtitle: Optional[str] = None) -> Optional[dict[str, Any]]:
    return V.facts_view(view_id, title, [(name, [item for item in items if item]) for name, items in groups], subtitle=subtitle)


def _fact(key: str, label: str, value: Any, fmt: str = "number", tone: Optional[str] = None) -> Optional[dict[str, Any]]:
    if value is None or value == "":
        return None
    return V.fact(key, label, value, fmt, tone)


def _signed(value: Optional[float]) -> Optional[str]:
    return None if value is None or value == 0 else "positive" if value > 0 else "negative"


def _intraday(times: list[int]) -> bool:
    """Bars closer together than a day (daily bars across a DST change are 23 hours apart)."""

    ordered = sorted(set(times))
    return len(ordered) > 1 and min(b - a for a, b in zip(ordered, ordered[1:])) < 20 * 3600


def _slug(symbol: str) -> str:
    return V.slug(symbol) or "symbol"


def _drawn(candidates: Any, limit: int) -> tuple[list[dict[str, Any]], int]:
    """The first ``limit`` views that exist, and how many more existed beyond them. A candidate that
    is ``None`` (a symbol with too little data to chart, say) takes no slot and is not counted."""

    shown: list[dict[str, Any]] = []
    extra = 0
    for view in candidates:
        if view is None:
            continue
        if len(shown) < limit:
            shown.append(view)
        else:
            extra += 1
    return shown, extra


def _covers(table: Optional[dict[str, Any]], claim: str) -> str:
    """The end of a note that says what the table holds. A table cut at its cap does not hold
    everything, and ``views.finalize`` already reports the cut, so nothing is claimed then."""

    return "." if table is not None and table.get("truncated") else f"; the table has {claim}."


# --- rows ---------------------------------------------------------------------------------------------


def bar_row(symbol: str, bar: dict[str, Any]) -> dict[str, Any]:
    return {"symbol": symbol, "time": stamp(bar.get("t")), "open": num(bar.get("o")), "high": num(bar.get("h")), "low": num(bar.get("l")), "close": num(bar.get("c")), "volume": num(bar.get("v")), "trades": num(bar.get("n")), "vwap": num(bar.get("vw"))}


def quote_row(symbol: str, quote: dict[str, Any]) -> dict[str, Any]:
    bid, ask = num(quote.get("bp")), num(quote.get("ap"))
    spread = ask - bid if bid and ask else None
    return {
        "symbol": symbol, "time": stamp(quote.get("t"), True), "bid_price": bid, "bid_size": num(quote.get("bs")), "bid_exchange": quote.get("bx") or None,
        "ask_price": ask, "ask_size": num(quote.get("as")), "ask_exchange": quote.get("ax") or None, "spread": spread, "conditions": _join(quote.get("c")), "tape": quote.get("z") or None,
    }


def trade_row(symbol: str, trade: dict[str, Any]) -> dict[str, Any]:
    trade_id = trade.get("i")
    return {"symbol": symbol, "time": stamp(trade.get("t"), True), "price": num(trade.get("p")), "size": num(trade.get("s")), "exchange": trade.get("x") or None, "conditions": _join(trade.get("c")), "trade_id": None if trade_id is None else str(trade_id), "tape": trade.get("z") or None, "taker_side": trade.get("tks") or None}


_ROWS = {"bar": bar_row, "quote": quote_row, "trade": trade_row}


# --- bars, quotes and trades ------------------------------------------------------------------------------

_BAR_COLUMNS = (("o", "Open", "open"), ("h", "High", "high"), ("l", "Low", "low"), ("c", "Close", "close"), ("v", "Volume", "volume"), ("vw", "VWAP", "value"))


def _series(view_id: str, title: str, items: list[dict[str, Any]], columns: tuple[tuple[str, str, str], ...]) -> Optional[dict[str, Any]]:
    pairs = [(moment(item.get("t")), item) for item in items]
    pairs = [(t, item) for t, item in pairs if t is not None]
    built = []
    for key, label, role in columns:
        values = [num(item.get(key)) for _, item in pairs]
        if any(v is not None for v in values):
            built.append({"key": label.lower().replace(" ", "_"), "label": label, "values": values, "role": role, "unit": None})
    times = [t for t, _ in pairs]
    return V.series_view(view_id, title, times, built, intraday=_intraday(times))


def _history(kind: str, plural: str, columns: tuple[tuple[str, str, str], ...], noun: str) -> Handler:
    def build(payload: Any, label: str) -> Built:
        data = {s: _dicts(v) for s, v in by_symbol(payload, plural).items()}
        charts = [(items, _series(f"{kind}-{_slug(symbol)}-chart", f"{symbol} {noun}", items, columns), symbol) for symbol, items in data.items()]
        shown, extra = _drawn((chart for _, chart, _ in charts), MAX_CHARTS)
        rows = [_ROWS[kind](symbol, item) for symbol, items in data.items() for item in items]
        table = _table(f"{kind}-table", label, rows)
        whole = table is not None and not table.get("truncated")
        notes = [
            f"{symbol}: some {noun} share a second, so the chart shows the last of each second." + (f" The table lists all {len(items):,}." if whole else "")
            for items, chart, symbol in charts
            if chart in shown and chart["total_points"] < len(items)
        ]
        if extra:
            notes.append(f"Charts are drawn for the first {MAX_CHARTS} of {len(shown) + extra} symbols that have enough data to chart{_covers(table, 'every row')}")
        return [*shown, table], notes

    return build


def _latest(kind: str, plural: str, singular: str) -> Handler:
    def build(payload: Any, label: str) -> Built:
        data = {s: v for s, v in by_symbol(payload, plural, singular).items() if isinstance(v, dict)}
        rows = [_ROWS[kind](symbol, record) for symbol, record in data.items()]
        views: list[Optional[dict[str, Any]]] = []
        if len(rows) == 1:
            row = rows[0]
            keys = [k for k in row if k != "symbol"]
            views.append(_facts(f"{kind}-latest", f"{row['symbol']} latest {kind}", [(None, [_cell(k, row[k]) for k in keys])]))
        views.append(_table(f"{kind}-table", label, rows))
        return views, []

    return build


def _cell(key: str, value: Any) -> Optional[dict[str, Any]]:
    """A fact from one row cell, labelled from its key (times, codes and ids stay text)."""

    if value is None:
        return None
    item = V.smart_fact(key, value)
    if key == "time":
        item["format"] = "text"
    return item


# --- snapshots ---------------------------------------------------------------------------------------------


def snapshots_of(payload: Any) -> dict[str, dict[str, Any]]:
    """Snapshots by symbol from ``{"snapshots": {...}}``, a bare ``{"AAPL": {...}}`` or one snapshot."""

    if not isinstance(payload, dict):
        return {}
    if isinstance(payload.get("snapshots"), dict):
        found = payload["snapshots"]
    elif _SNAPSHOT_KEYS & set(payload):
        found = {payload.get("symbol") or "?": payload}
    else:
        found = payload
    return {str(k): v for k, v in found.items() if isinstance(v, dict)}


def snapshot_row(symbol: str, snap: dict[str, Any]) -> dict[str, Any]:
    trade, quote = snap.get("latestTrade") or {}, snap.get("latestQuote") or {}
    day, previous, minute = snap.get("dailyBar") or {}, snap.get("prevDailyBar") or {}, snap.get("minuteBar") or {}
    price = num(trade.get("p"))
    last = num(day.get("c")) if num(day.get("c")) is not None else price
    before = num(previous.get("c"))
    change = last - before if last is not None and before else None
    return {
        "symbol": symbol, "price": price, "time": stamp(trade.get("t"), True), "bid_price": num(quote.get("bp")), "ask_price": num(quote.get("ap")),
        "open": num(day.get("o")), "high": num(day.get("h")), "low": num(day.get("l")), "close": num(day.get("c")), "volume": num(day.get("v")),
        "previous_close": before, "change": change, "change_percent": change / before * 100 if change is not None and before else None,
        "minute_close": num(minute.get("c")),
    }


def _snapshot_facts(symbol: str, snap: dict[str, Any]) -> Optional[dict[str, Any]]:
    trade, quote = snap.get("latestTrade") or {}, snap.get("latestQuote") or {}
    row = snapshot_row(symbol, snap)
    bar_groups = [("Today", "dailyBar"), ("Previous day", "prevDailyBar"), ("Latest minute", "minuteBar")]
    groups: list[tuple[Optional[str], list[Optional[dict[str, Any]]]]] = [
        ("Latest trade", [_fact("price", "Price", num(trade.get("p"))), _fact("size", "Size", num(trade.get("s"))), _fact("time", "Time", stamp(trade.get("t"), True), "text"), _fact("exchange", "Exchange", trade.get("x"), "text")]),
        ("Latest quote", [_fact("bid", "Bid price", num(quote.get("bp"))), _fact("bid_size", "Bid size", num(quote.get("bs"))), _fact("ask", "Ask price", num(quote.get("ap"))), _fact("ask_size", "Ask size", num(quote.get("as"))), _fact("quote_time", "Time", stamp(quote.get("t"), True), "text")]),
    ]
    if row["change"] is not None:
        groups.insert(0, ("Change on the day", [_fact("change", "Change", row["change"], "number", _signed(row["change"])), _fact("change_percent", "Change", row["change_percent"], "percent", _signed(row["change_percent"]))]))
    for title, key in bar_groups:
        bar = snap.get(key) or {}
        groups.append((title, [_fact(f"{key}_{name}", label, num(bar.get(field))) for field, name, label in (("o", "open", "Open"), ("h", "high", "High"), ("l", "low", "Low"), ("c", "close", "Close"), ("v", "volume", "Volume"), ("vw", "vwap", "VWAP"), ("n", "trades", "Trades"))]))
    return _facts(f"snapshot-{_slug(symbol)}", f"{symbol} snapshot", groups)


def _snapshots(payload: Any, label: str) -> Built:
    data = snapshots_of(payload)
    rows = [snapshot_row(symbol, snap) for symbol, snap in data.items()]
    facts, extra = _drawn((_snapshot_facts(symbol, snap) for symbol, snap in data.items()), SNAPSHOT_FACTS)
    views: list[Optional[dict[str, Any]]] = [*facts]
    ranked = [(r["symbol"], r["change_percent"]) for r in rows if r["change_percent"] is not None]
    table = None
    if len(rows) > 1:
        ranked.sort(key=lambda m: -abs(m[1]))
        table = _table("snapshots-table", label, rows)
        views.append(V.bars_view("day-change", "Change on the day", [s for s, _ in ranked], [v for _, v in ranked], fmt="percent", sign_colors=True, value_label="Change"))
        views.append(table)
    notes = [f"Facts are shown for the first {SNAPSHOT_FACTS} of {len(facts) + extra} symbols{_covers(table, 'all of them')}"] if extra else []
    return views, notes


# --- options -----------------------------------------------------------------------------------------------


def occ(contract: str) -> Optional[dict[str, Any]]:
    """Root, expiration, type and strike from an OCC contract symbol such as ``AAPL240426C00162500``."""

    match = _OCC.match(contract)
    if not match:
        return None
    root, yy, mm, dd, kind, strike = match.groups()
    return {"underlying": root, "expiration": f"20{yy}-{mm}-{dd}", "type": "call" if kind == "C" else "put", "strike": int(strike) / 1000}


def contract_row(contract: str, snap: dict[str, Any]) -> dict[str, Any]:
    trade, quote, greeks = snap.get("latestTrade") or {}, snap.get("latestQuote") or {}, snap.get("greeks") or {}
    base = occ(contract) or {}
    return {
        "contract": contract, "underlying": base.get("underlying"), "expiration": base.get("expiration"), "type": base.get("type"), "strike": base.get("strike"),
        "bid_price": num(quote.get("bp")), "ask_price": num(quote.get("ap")), "last_price": num(trade.get("p")), "last_time": stamp(trade.get("t"), True),
        "implied_volatility": num(snap.get("impliedVolatility")), "delta": num(greeks.get("delta")), "gamma": num(greeks.get("gamma")), "theta": num(greeks.get("theta")), "vega": num(greeks.get("vega")), "rho": num(greeks.get("rho")),
    }


def _iv_bars(rows: list[dict[str, Any]], kind: str, expiration: str) -> Optional[dict[str, Any]]:
    picked = sorted((r for r in rows if r["type"] == kind and r["expiration"] == expiration and r["implied_volatility"] is not None and r["strike"] is not None), key=lambda r: r["strike"])
    return V.bars_view(f"iv-{kind}s", f"Implied volatility of {kind}s expiring {expiration}", [f"{r['strike']:g}" for r in picked], [r["implied_volatility"] * 100 for r in picked], fmt="percent", value_label="Implied volatility", subtitle="By strike price")


def _chain(payload: Any, label: str) -> Built:
    data = snapshots_of(payload)
    rows = [contract_row(contract, snap) for contract, snap in data.items()]
    rows.sort(key=lambda r: (r["expiration"] or "", r["strike"] or 0, r["type"] or ""))
    views: list[Optional[dict[str, Any]]] = []
    if len(rows) == 1:
        row = rows[0]
        views.append(_facts("contract", row["contract"], [(None, [_cell(k, row[k]) for k in row if k != "contract"])]))
    elif rows:
        expirations = sorted({r["expiration"] for r in rows if r["expiration"]})
        strikes = [r["strike"] for r in rows if r["strike"] is not None]
        calls = sum(1 for r in rows if r["type"] == "call")
        views.append(_facts("chain-summary", "Chain summary", [(None, [
            _fact("contracts", "Contracts", len(rows), "integer"), _fact("calls", "Calls", calls, "integer"), _fact("puts", "Puts", sum(1 for r in rows if r["type"] == "put"), "integer"),
            _fact("expirations", "Expirations", len(expirations), "integer"), _fact("first", "First expiration", expirations[0] if expirations else None, "date"), _fact("last", "Last expiration", expirations[-1] if expirations else None, "date"),
            _fact("low", "Lowest strike", min(strikes) if strikes else None), _fact("high", "Highest strike", max(strikes) if strikes else None),
        ])]))
        if expirations:
            views.extend([_iv_bars(rows, "call", expirations[0]), _iv_bars(rows, "put", expirations[0])])
    views.append(_table("chain-table", label, rows))
    return views, []


# --- the order book ----------------------------------------------------------------------------------------


def _levels(book: dict[str, Any], key: str, descending: bool) -> list[tuple[float, float]]:
    found = [(num(level.get("p")), num(level.get("s"))) for level in _dicts(book.get(key))]
    return sorted(((p, s or 0.0) for p, s in found if p is not None), reverse=descending)


def _book_facts(symbol: str, book: dict[str, Any], bids: list[tuple[float, float]], asks: list[tuple[float, float]]) -> Optional[dict[str, Any]]:
    best_bid, best_ask = (bids[0][0] if bids else None), (asks[0][0] if asks else None)
    spread = best_ask - best_bid if best_bid is not None and best_ask is not None else None
    return _facts(f"book-{_slug(symbol)}", f"{symbol} order book", [(None, [
        _fact("best_bid", "Best bid", best_bid), _fact("best_ask", "Best ask", best_ask), _fact("spread", "Spread", spread),
        _fact("spread_percent", "Spread", spread / best_ask * 100 if spread is not None and best_ask else None, "percent"),
        _fact("bid_depth", "Total bid size", sum(s for _, s in bids) if bids else None), _fact("ask_depth", "Total ask size", sum(s for _, s in asks) if asks else None),
        _fact("levels", "Price levels", len(bids) + len(asks), "integer"), _fact("time", "As of", stamp(book.get("t"), True), "text"),
    ])])


def _orderbooks(payload: Any, label: str) -> Built:
    books = {s: b for s, b in by_symbol(payload, "orderbooks").items() if isinstance(b, dict)}
    sides = {symbol: (_levels(book, "b", True), _levels(book, "a", False)) for symbol, book in books.items()}
    facts, extra = _drawn((_book_facts(symbol, books[symbol], *sides[symbol]) for symbol in books), MAX_CHARTS)
    views: list[Optional[dict[str, Any]]] = [*facts]
    if len(books) == 1:
        bids, asks = next(iter(sides.values()))
        for side, levels in (("Bid", bids), ("Ask", asks)):
            top = levels[:DEPTH_LEVELS]
            views.append(V.bars_view(f"depth-{side.lower()}", f"{side} size at the best {len(top)} prices", [f"{p:g}" for p, _ in top], [s for _, s in top], value_label="Size"))
    rows: list[dict[str, Any]] = []
    for symbol, (bids, asks) in sides.items():
        for side, levels in (("bid", bids), ("ask", asks)):
            total = 0.0
            for price, size in levels:
                total += size
                rows.append({"symbol": symbol, "side": side, "price": price, "size": size, "cumulative_size": total})
    table = _table("book-table", label, rows)
    views.append(table)
    notes = [f"Facts are shown for the first {MAX_CHARTS} of {len(facts) + extra} symbols{_covers(table, 'every price level of all of them')}"] if extra else []
    return views, notes


# --- one-off responses ----------------------------------------------------------------------------------------

_HTML = re.compile(r"<[^>]+>")


def _news(payload: Any, label: str) -> Built:
    articles = _dicts(payload.get("news")) if isinstance(payload, dict) else []
    items = []
    for article in articles[: V.CAPS["feed"]]:
        summary = str(article.get("summary") or "").strip() or _HTML.sub(" ", str(article.get("content") or "")).strip()
        url = str(article.get("url") or "")
        author = str(article.get("author") or "").strip()
        source = str(article.get("source") or "").strip()
        items.append(
            {
                "title": str(article.get("headline") or "Untitled"),
                "url": url if url.startswith(("http://", "https://")) else None,
                "source": " · ".join(x for x in (source, author) if x) or None,
                "published": moment(article.get("created_at")),
                "summary": " ".join(summary.split())[:600] or None,
                "sentiment": None,
                "tags": [],
                "tickers": [{"symbol": str(s), "relevance": None, "score": None, "label": None} for s in article.get("symbols") or [] if s][:8],
            }
        )
    counts: dict[str, int] = {}
    for article in articles:
        for symbol in article.get("symbols") or []:
            counts[str(symbol)] = counts.get(str(symbol), 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:12]
    times = [t for t in (moment(a.get("created_at")) for a in articles) if t is not None]
    out: list[Optional[dict[str, Any]]] = [
        _facts("summary", "Summary", [(None, [
            _fact("articles", "Articles returned", len(articles), "integer"), _fact("symbols", "Symbols mentioned", len(counts), "integer"),
            _fact("sources", "Sources", len({a.get("source") for a in articles if a.get("source")}), "integer"),
            _fact("newest", "Newest (UTC)", stamp(datetime.fromtimestamp(max(times), timezone.utc).isoformat()) if times else None, "text"),
            _fact("oldest", "Oldest (UTC)", stamp(datetime.fromtimestamp(min(times), timezone.utc).isoformat()) if times else None, "text"),
        ])]),
    ]
    if items:
        out.append({"kind": "feed", "id": "feed", "title": "Articles", "subtitle": "In the order Alpaca returned them", "items": items, "total_items": len(articles), "truncated": len(articles) > len(items)})
    out.append(V.bars_view("symbols", "Articles by symbol", [s for s, _ in ranked], [float(c) for _, c in ranked], value_label="Articles"))
    return out, []


def _most_actives(payload: Any, label: str) -> Built:
    rows = [{"symbol": str(r.get("symbol")), "volume": num(r.get("volume")), "trades": num(r.get("trade_count"))} for r in _dicts(payload.get("most_actives"))] if isinstance(payload, dict) else []
    updated = stamp(payload.get("last_updated")) if isinstance(payload, dict) else None
    views = [
        V.bars_view("volume", "Volume", [r["symbol"] for r in rows], [r["volume"] for r in rows], value_label="Shares", subtitle=f"Updated {updated} UTC" if updated else None),
        V.bars_view("trades", "Trade count", [r["symbol"] for r in rows], [r["trades"] for r in rows], value_label="Trades"),
        _table("actives-table", label, rows),
    ]
    return views, []


def _movers(payload: Any, label: str) -> Built:
    if not isinstance(payload, dict):
        return [], []
    updated = stamp(payload.get("last_updated"))
    subtitle = " · ".join(x for x in (str(payload.get("market_type") or "").title(), f"Updated {updated} UTC" if updated else None) if x) or None
    views: list[Optional[dict[str, Any]]] = []
    for key, title in (("gainers", "Top gainers"), ("losers", "Top losers")):
        rows = [{"symbol": str(r.get("symbol")), "price": num(r.get("price")), "change": num(r.get("change")), "percent_change": num(r.get("percent_change"))} for r in _dicts(payload.get(key))]
        views.append(V.bars_view(key, title, [r["symbol"] for r in rows], [r["percent_change"] for r in rows], fmt="percent", sign_colors=True, value_label="Change", subtitle=subtitle))
        views.append(_table(f"{key}-table", title, rows))
    return views, []


def _corporate_actions(payload: Any, label: str) -> Built:
    groups = payload.get("corporate_actions") if isinstance(payload, dict) else None
    if not isinstance(groups, dict):
        return [], []
    present = {k: _dicts(v) for k, v in groups.items() if _dicts(v)}
    views: list[Optional[dict[str, Any]]] = [_facts("summary", "Summary", [(None, [_fact(k, V.humanize(k), len(v), "integer") for k, v in present.items()])])]
    for kind, records in present.items():
        keys = list(dict.fromkeys(k for record in records for k in record))
        ordered = [k for k in _CORPORATE_FIRST if k in keys] + [k for k in keys if k not in _CORPORATE_FIRST]
        views.append(V.table_view(f"actions-{V.slug(kind)}", V.humanize(kind), records, keys=ordered[: V.CAPS["columns"]]))
    return views, []


def _rates(payload: Any, label: str) -> Built:
    data = by_symbol(payload, "rates")
    columns = (("bp", "Bid", "value"), ("mp", "Mid", "value"), ("ap", "Ask", "value"))
    items = {pair: _dicts(value) if isinstance(value, list) else [value] if isinstance(value, dict) else [] for pair, value in data.items()}
    charts = (_series(f"rates-{_slug(pair)}-chart", f"{pair} rates", items[pair], columns) if isinstance(value, list) else None for pair, value in data.items())
    shown, extra = _drawn(charts, MAX_CHARTS)
    rows = [{"pair": pair, "time": stamp(i.get("t"), True), "bid": num(i.get("bp")), "mid": num(i.get("mp")), "ask": num(i.get("ap"))} for pair, found in items.items() for i in found]
    table = _table("rates-table", label, rows)
    notes = [f"Charts are drawn for the first {MAX_CHARTS} of {len(shown) + extra} currency pairs that have enough history to chart{_covers(table, 'every row')}"] if extra else []
    return [*shown, table], notes


def _fixed_income(kind: str) -> Handler:
    def build(payload: Any, label: str) -> Built:
        data = {k: v for k, v in by_symbol(payload, kind).items() if isinstance(v, dict)}
        if kind == "prices":
            rows = [{"isin": isin, "time": stamp(r.get("t"), True), "price": num(r.get("p")), "yield_to_maturity": num(r.get("ytm")), "yield_to_worst": num(r.get("ytw"))} for isin, r in data.items()]
            views = [V.bars_view("yields", "Yield to maturity", [r["isin"] for r in rows], [r["yield_to_maturity"] for r in rows], fmt="percent", value_label="Yield") if len(rows) > 1 else None]
        else:
            rows = [
                {
                    "isin": isin, "time": stamp(r.get("t"), True), "bid_price": num(r.get("bp")), "bid_size": num(r.get("bs")), "bid_min_size": num(r.get("bms")), "bid_yield_to_maturity": num(r.get("bytm")), "bid_yield_to_worst": num(r.get("bytw")),
                    "ask_price": num(r.get("ap")), "ask_size": num(r.get("as")), "ask_min_size": num(r.get("ams")), "ask_yield_to_maturity": num(r.get("aytm")), "ask_yield_to_worst": num(r.get("aytw")),
                }
                for isin, r in data.items()
            ]
            views = []
        return [*views, _table("fixed-income-table", label, rows)], []

    return build


def _auctions(payload: Any, label: str) -> Built:
    data = by_symbol(payload, "auctions")
    rows = []
    for symbol, days in data.items():
        for day in _dicts(days):
            for key, name in (("o", "opening"), ("c", "closing")):
                for trade in _dicts(day.get(key)):
                    rows.append({"symbol": symbol, "date": day.get("d"), "auction": name, "time": stamp(trade.get("t"), True), "price": num(trade.get("p")), "exchange": trade.get("x") or None, "condition": trade.get("c") or None})
    summary = _facts("summary", "Summary", [(None, [_fact("prints", "Auction prints", len(rows), "integer"), _fact("symbols", "Symbols", len(data), "integer"), _fact("days", "Days", len({(r["symbol"], r["date"]) for r in rows}), "integer")])]) if rows else None
    return [summary, _table("auctions-table", label, rows)], []


def _codes(payload: Any, label: str) -> Built:
    rows = [{"code": str(k), "name": str(v)} for k, v in sorted(payload.items())] if isinstance(payload, dict) else []
    return [_table("codes-table", label, rows)], []


_BARS = _history("bar", "bars", _BAR_COLUMNS, "bars")
_QUOTES = _history("quote", "quotes", (("bp", "Bid price", "value"), ("ap", "Ask price", "value")), "quotes")
_TRADES = _history("trade", "trades", (("p", "Price", "value"), ("s", "Size", "volume")), "trades")

_HANDLERS: dict[str, Handler] = {
    "stock_bars": _BARS, "stock_bars_single": _BARS, "option_bars": _BARS, "crypto_bars": _BARS,
    "stock_quotes": _QUOTES, "stock_quotes_single": _QUOTES, "crypto_quotes": _QUOTES,
    "stock_trades": _TRADES, "stock_trades_single": _TRADES, "option_trades": _TRADES, "crypto_trades": _TRADES,
    "stock_latest_bars": _latest("bar", "bars", "bar"), "stock_latest_bar_single": _latest("bar", "bars", "bar"), "crypto_latest_bars": _latest("bar", "bars", "bar"),
    "stock_latest_quotes": _latest("quote", "quotes", "quote"), "stock_latest_quote_single": _latest("quote", "quotes", "quote"), "crypto_latest_quotes": _latest("quote", "quotes", "quote"), "option_latest_quotes": _latest("quote", "quotes", "quote"),
    "stock_latest_trades": _latest("trade", "trades", "trade"), "stock_latest_trade_single": _latest("trade", "trades", "trade"), "crypto_latest_trades": _latest("trade", "trades", "trade"), "option_latest_trades": _latest("trade", "trades", "trade"),
    "stock_snapshots": _snapshots, "stock_snapshot_single": _snapshots, "crypto_snapshots": _snapshots,
    "option_snapshots": _chain, "option_chain": _chain,
    "crypto_orderbooks": _orderbooks,
    "stock_auctions": _auctions, "stock_auctions_single": _auctions,
    "stock_conditions": _codes, "stock_exchanges": _codes, "option_conditions": _codes, "option_exchanges": _codes,
    "forex_latest_rates": _rates, "forex_rates": _rates,
    "fixed_income_prices": _fixed_income("prices"), "fixed_income_quotes": _fixed_income("quotes"),
    "most_actives": _most_actives, "movers": _movers, "news": _news, "corporate_actions": _corporate_actions,
}


def build_views(endpoint_id: str, payload: Any, label: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Views and notes for one Alpaca response. ``label`` is the endpoint title."""

    handler = _HANDLERS.get(endpoint_id)
    built: list[Optional[dict[str, Any]]] = []
    notes: list[str] = []
    try:
        if handler:
            built, notes = handler(payload, label)
    except Exception:  # a shape surprise must cost views, never the whole response
        built, notes = [], []
    if not any(built):
        built = V.analyze(payload, label, V.slug(endpoint_id))
    return V.finalize(built, notes)
