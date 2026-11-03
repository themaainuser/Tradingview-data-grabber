"""Financial Modeling Prep response shapes -> views. Everything not special-cased goes through ``views.analyze``.

FMP answers almost every endpoint with a JSON array of flat records (a one-element array for one
company). Statements and ratios become a table with one column per period, quotes and profiles
become facts, prices become a candlestick chart, and news becomes a feed. A shape that surprises a
handler costs that handler's views, never the response.
"""

from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from . import views as V

Built = tuple[list[Optional[dict[str, Any]]], list[str]]

MAX_PERIODS = 20
_HTML = re.compile(r"<[^>]+>")
_INLINE_TAG = re.compile(r"</?(a|b|i|u|em|strong|span|sub|sup|small)\b[^>]*>", re.I)
_EXCHANGE_PREFIX = re.compile(r"^[A-Z]+:")
_OHLCV = ("open", "high", "low", "close", "volume")
# Price-history columns that stand in for an open, high, low or close.
_PRICE_ALIASES = {"adjOpen": "open", "adjHigh": "high", "adjLow": "low", "adjClose": "close", "price": "close"}
_PERIOD_FIELDS = {"date", "symbol", "reportedCurrency", "cik", "filingDate", "acceptedDate", "fiscalYear", "calendarYear", "period", "lastUpdated"}
# Fields FMP already reports as percentages (2.5 means 2.5%), unlike the fractions the generic formatter knows.
_PERCENT_FIELDS = {"changePercentage", "changesPercentage", "1D", "5D", "1M", "3M", "6M", "ytd", "1Y", "3Y", "5Y", "10Y", "max", "averageChange"}
_LABELS = {
    "ytd": "Year to date", "1D": "1 day", "5D": "5 days", "1M": "1 month", "3M": "3 months", "6M": "6 months", "1Y": "1 year", "3Y": "3 years", "5Y": "5 years", "10Y": "10 years",
    "max": "Since listing", "changePercentage": "Change (%)", "changesPercentage": "Change (%)", "priceAvg50": "50-day average", "priceAvg200": "200-day average", "averageChange": "Average change (%)",
}
# Codes and labels that are digits only by accident: shown as sent, never as a number (0000320193 keeps its zeros, 3/A is not lost, 2025 is not 2,025).
_IDENTIFIERS = {"cik", "reportingCik", "companyCik", "targetedCik", "sicCode", "fiscalYear", "calendarYear", "yearBorn", "formType", "transactionType", "postalCode", "zip", "phone", "cusip", "isin"}
_CHART_FIELDS = {
    "income_statement": ["revenue", "grossProfit", "operatingIncome", "netIncome"],
    "balance_sheet": ["totalAssets", "totalLiabilities", "totalStockholdersEquity"],
    "cash_flow": ["operatingCashFlow", "freeCashFlow"],
    "key_metrics": ["returnOnEquity", "returnOnInvestedCapital", "returnOnCapitalEmployed"],
    "ratios": ["grossProfitMargin", "operatingProfitMargin", "netProfitMargin"],
    "financial_growth": ["revenueGrowth", "netIncomeGrowth", "epsgrowth"],
    "enterprise_values": ["marketCapitalization", "enterpriseValue"],
    "owner_earnings": ["ownersEarnings"],
}
_YIELDS = [("month1", "1M"), ("month2", "2M"), ("month3", "3M"), ("month6", "6M"), ("year1", "1Y"), ("year2", "2Y"), ("year3", "3Y"), ("year5", "5Y"), ("year7", "7Y"), ("year10", "10Y"), ("year20", "20Y"), ("year30", "30Y")]
_QUOTE_GROUPS = [
    ("Price", ["price", "change", "changePercentage", "open", "previousClose"]),
    ("Ranges", ["dayLow", "dayHigh", "yearLow", "yearHigh", "priceAvg50", "priceAvg200"]),
    ("Market", ["volume", "marketCap", "exchange", "timestamp"]),
]
_PROFILE_GROUPS = [
    ("Company", ["companyName", "symbol", "exchangeFullName", "exchange", "sector", "industry", "country", "ceo", "fullTimeEmployees", "ipoDate", "website"]),
    ("Market", ["price", "change", "changePercentage", "marketCap", "beta", "range", "volume", "averageVolume", "lastDividend", "currency"]),
    ("Identifiers", ["cik", "isin", "cusip"]),
    ("Contact", ["phone", "address", "city", "state", "zip"]),
    ("Flags", ["isEtf", "isActivelyTrading", "isAdr", "isFund"]),
]


# --- small helpers -------------------------------------------------------------------------------------


def rows_of(payload: Any) -> list[dict[str, Any]]:
    """The records of a response: an array of objects, or one object."""

    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    return [payload] if isinstance(payload, dict) else []


def num(value: Any) -> Optional[float]:
    return None if isinstance(value, bool) else V.to_number(value)


def clean(text: Any, limit: int = 600) -> Optional[str]:
    """Plain text of a field that may hold HTML, shortened for a card."""

    out = " ".join(html.unescape(_HTML.sub(" ", _INLINE_TAG.sub("", str(text or "")))).split())
    return (out if len(out) <= limit else out[: limit - 1].rstrip() + "\u2026") or None


def utc(seconds: float) -> str:
    return datetime.fromtimestamp(seconds, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def verbatim(value: Any) -> Optional[str]:
    """A cell or fact as FMP sent it: flags as Yes/No, everything else as text; nothing for a missing or nested value."""

    if V.is_missing(value) or isinstance(value, (dict, list)):
        return None
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(int(value)) if isinstance(value, float) and value.is_integer() else str(value)


def patch_table(view: Optional[dict[str, Any]], records: list[Any]) -> Optional[dict[str, Any]]:
    """Redo the cells of identifier and flag columns from the raw ``records`` the table was built from. The generic column
    typing would read ``4`` and ``0000320193`` as numbers (losing ``3/A`` and the zeros) and pass booleans on, which the
    frontend rejects."""

    if not view:
        return view
    objects = [r for r in records if isinstance(r, dict)]
    for index, column in enumerate(view["columns"]):
        sources = [r.get(column["key"]) for r in objects[: len(view["rows"])]]
        if column["key"] in _IDENTIFIERS or any(isinstance(s, bool) for s in sources):
            column["type"] = "text"
            for row, source in zip(view["rows"], sources):
                row[index] = verbatim(source)
    return view


def fact_of(key: str, value: Any) -> Optional[dict[str, Any]]:
    """One fact for a record field: percentages as such, epoch timestamps as UTC times, the rest by ``smart_fact``."""

    if V.is_missing(value) or isinstance(value, (dict, list)):
        return None
    if key in _IDENTIFIERS:
        return V.fact(key, _LABELS.get(key) or V.humanize(key), verbatim(value))
    number = num(value)
    if key in _PERCENT_FIELDS and number is not None:
        item = V.fact(key, _LABELS.get(key) or V.humanize(key), number, "percent", "positive" if number > 0 else "negative" if number < 0 else None)
    elif key == "timestamp" and number is not None and number > 1e9:
        item = V.fact(key, "Updated (UTC)", utc(number / 1000 if number > 1e11 else number))  # some endpoints send milliseconds
    else:
        item = V.smart_fact(key, value)
        if key in _LABELS:
            item["label"] = _LABELS[key]
    return item


def facts_of(view_id: str, title: str, record: dict[str, Any], groups: Optional[list[tuple[Optional[str], list[str]]]] = None, subtitle: Optional[str] = None) -> Optional[dict[str, Any]]:
    built = [(name, [item for item in (fact_of(k, record.get(k)) for k in keys) if item]) for name, keys in (groups or [(None, list(record))])]
    return V.facts_view(view_id, title, built, subtitle=subtitle)


def table_of(view_id: str, title: str, records: list[dict[str, Any]], keys: Optional[list[str]] = None, subtitle: Optional[str] = None) -> Optional[dict[str, Any]]:
    if keys:
        keys = [k for k in keys if any(r.get(k) not in (None, "") for r in records)] or None
    return patch_table(V.table_view(view_id, title, records, keys=keys, subtitle=subtitle), records)


def subtitle_of(row: dict[str, Any]) -> Optional[str]:
    return " \u00b7 ".join(str(row[k]) for k in ("symbol", "reportedCurrency") if row.get(k)) or None


# --- one record -> facts, many -> table ---------------------------------------------------------------


def _generic(endpoint_id: str, label: str, payload: Any) -> Built:
    rows = rows_of(payload) if isinstance(payload, list) else []
    if len(rows) == 1 and len(payload) == 1:
        return [facts_of(V.slug(endpoint_id), label, rows[0], subtitle=rows[0].get("symbol"))], []
    views = V.analyze(payload, label, V.slug(endpoint_id))
    for view in views:
        if view and view["kind"] == "table" and isinstance(payload, list):
            patch_table(view, payload)
    return views, []


def _quote(endpoint_id: str, label: str, payload: Any) -> Built:
    rows = rows_of(payload)
    if len(rows) != 1:
        return _generic(endpoint_id, label, payload)
    row = rows[0]
    return [facts_of("quote", str(row.get("name") or row.get("symbol") or label), row, _QUOTE_GROUPS, subtitle=row.get("symbol"))], []


def _profile(endpoint_id: str, label: str, payload: Any) -> Built:
    rows = rows_of(payload)
    if len(rows) != 1:
        return _generic(endpoint_id, label, payload)
    row = rows[0]
    about = clean(row.get("description"), 4000)
    views = [facts_of("profile", str(row.get("companyName") or row.get("symbol") or label), row, _PROFILE_GROUPS, subtitle=row.get("symbol"))]
    if about:
        views.append(V.text_view("about", "About", [{"heading": None, "subheading": None, "body": about, "badge": None}]))
    return views, []


# --- statements and ratios: periods across, fields down -------------------------------------------------


def _period_labels(rows: list[dict[str, Any]]) -> list[str]:
    labels: list[str] = []
    for row in rows:
        label = " ".join(str(row[k]) for k in ("fiscalYear", "calendarYear", "period") if row.get(k) and (k != "calendarYear" or not row.get("fiscalYear"))) or str(row.get("date") or "?")
        labels.append(f"{label} ({row['date']})" if label in labels and row.get("date") else label)
    return labels


def _pivot(view_id: str, title: str, columns: list[tuple[str, dict[str, Any]]], subtitle: Optional[str], *, names_as_sent: bool = False) -> tuple[Optional[dict[str, Any]], list[str]]:
    """A table whose rows are fields and whose columns are periods, most recent first. Field names are made readable
    unless they are data (segment names such as ``iPhone``), which stay as sent."""

    shown = columns[:MAX_PERIODS]
    fields: dict[str, None] = {}
    for _, values in shown:
        for key in values:
            fields.setdefault(key)
    records = [{"item": field if names_as_sent else V.humanize(field), **{label: values.get(field) for label, values in shown}} for field in fields]
    view = V.table_view(view_id, title, records, keys=["item", *(label for label, _ in shown)], subtitle=subtitle)
    if view:
        for column, (label, _) in zip(view["columns"][1:], shown):
            column["label"] = label
    notes = [f"{title}: showing the latest {MAX_PERIODS} of {len(columns)} periods."] if len(columns) > len(shown) else []
    return view, notes


def _periodic(endpoint_id: str, label: str, payload: Any) -> Built:
    rows = [r for r in rows_of(payload) if r.get("date") or r.get("fiscalYear")]
    if not rows:
        return [], []
    columns = [(name, {k: n for k, v in row.items() if k not in _PERIOD_FIELDS and (n := num(v)) is not None}) for name, row in zip(_period_labels(rows), rows)]
    stamped = [(t, i) for i, row in enumerate(rows) if (t := V.epoch(str(row.get("date") or ""))) is not None]
    series = [
        {"key": key, "label": V.humanize(key), "values": [columns[i][1].get(key) for _, i in stamped], "role": "value", "unit": None}
        for key in _CHART_FIELDS.get(endpoint_id, [])
        if any(key in values for _, values in columns)
    ]
    chart = V.series_view(f"{V.slug(endpoint_id)}-chart", label, [t for t, _ in stamped], series, subtitle=subtitle_of(rows[0]))
    table, notes = _pivot(f"{V.slug(endpoint_id)}-table", label, columns, subtitle_of(rows[0]))
    return [chart, table], notes


def _segments(endpoint_id: str, label: str, payload: Any) -> Built:
    """Revenue segments: each record holds ``data``, a ``{segment: revenue}`` mapping for one period."""

    rows = [r for r in rows_of(payload) if isinstance(r.get("data"), dict)]
    if not rows:
        return _generic(endpoint_id, label, payload)
    columns = [(name, {k: n for k, v in row["data"].items() if (n := num(v)) is not None}) for name, row in zip(_period_labels(rows), rows)]
    table, notes = _pivot(V.slug(endpoint_id), label, columns, subtitle_of(rows[0]), names_as_sent=True)
    return [table], notes


# --- prices -------------------------------------------------------------------------------------------------


def _bar_columns(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_role: dict[str, str] = {}
    for key in rows[0] if rows else ():
        role = key if key in _OHLCV else _PRICE_ALIASES.get(key)
        if role and role not in by_role:
            by_role[role] = key
    return [{"key": role, "label": V.humanize(role), "values": [num(r.get(by_role[role])) for r in rows], "role": role, "unit": None} for role in _OHLCV if role in by_role]


def _prices(endpoint_id: str, label: str, payload: Any) -> Built:
    rows = [r for r in rows_of(payload) if r.get("date")]
    pairs = [(t, r) for r in rows if (t := V.epoch(str(r["date"]))) is not None]
    if not pairs:
        return _generic(endpoint_id, label, payload)
    clock = any(" " in str(r["date"]) or "T" in str(r["date"]) for _, r in pairs[:5])
    note = "Times are shown as FMP returns them, in the exchange's local time." if clock else None
    first = pairs[0][1]
    symbol = str(first.get("symbol") or "")
    subtitle = symbol or None
    times = [t for t, _ in pairs]
    ordered = [r for _, r in pairs]
    views: list[Optional[dict[str, Any]]] = [V.series_view(f"{V.slug(endpoint_id)}-chart", f"{symbol} {label.lower()}".strip(), times, _bar_columns(ordered), subtitle=subtitle, intraday=clock, time_note=note)]
    if endpoint_id == "technical_indicator":
        known = {*_OHLCV, *_PRICE_ALIASES, *_PERIOD_FIELDS, "change", "changePercent", "vwap"}
        for key in first:
            if key not in known and any(num(r.get(key)) is not None for r in ordered):
                views.append(V.series_view("indicator", V.humanize(key), times, [{"key": key, "label": V.humanize(key), "values": [num(r.get(key)) for r in ordered], "role": "value", "unit": None}], subtitle=subtitle, intraday=clock, time_note=note))
    views.append(patch_table(V.table_view(f"{V.slug(endpoint_id)}-table", label, ordered, subtitle=subtitle), ordered))
    return views, []


# --- movers and snapshots -----------------------------------------------------------------------------------


def _movers(endpoint_id: str, label: str, payload: Any) -> Built:
    rows = rows_of(payload)
    keys = ["symbol", "name", "price", "change", "changesPercentage", "exchange"]
    shown = [r for r in rows if num(r.get("changesPercentage")) is not None][: V.CAPS["bars"]]
    bars = V.bars_view("change", "Change today", [str(r.get("symbol")) for r in shown], [num(r.get("changesPercentage")) for r in shown], fmt="percent", sign_colors=True, value_label="Change")
    return [bars, table_of("movers", label, rows, keys)], []


def _snapshot(group_key: str, value_key: str, value_label: str, fmt: str, sign_colors: bool) -> Callable[[str, str, Any], Built]:
    def build(endpoint_id: str, label: str, payload: Any) -> Built:
        rows = rows_of(payload)
        shown = [r for r in rows if r.get(group_key) and num(r.get(value_key)) is not None]
        bars = V.bars_view("snapshot-bars", label, [str(r[group_key]) for r in shown], [num(r[value_key]) for r in shown], fmt=fmt, sign_colors=sign_colors, value_label=value_label)
        notes = [f"Bars are drawn for the first {V.CAPS['bars']} of {len(shown)} rows; the table has every row."] if len(shown) > V.CAPS["bars"] else []
        return [bars, table_of("snapshot-table", label, rows)], notes

    return build


def _treasury(endpoint_id: str, label: str, payload: Any) -> Built:
    rows = [r for r in rows_of(payload) if r.get("date")]
    pairs = [(t, r) for r in rows if (t := V.epoch(str(r["date"]))) is not None]
    columns = [{"key": key, "label": name, "values": [num(r.get(key)) for _, r in pairs], "role": "value", "unit": None} for key, name in _YIELDS if any(num(r.get(key)) is not None for _, r in pairs)]
    views: list[Optional[dict[str, Any]]] = [V.series_view("yields", "Treasury yields", [t for t, _ in pairs], columns, subtitle="Percent per year")]
    if pairs:
        latest = max(pairs, key=lambda p: p[0])[1]
        points = [(name, num(latest.get(key))) for key, name in _YIELDS if num(latest.get(key)) is not None]
        views.append(V.bars_view("curve", f"Yield curve on {latest['date']}", [n for n, _ in points], [v for _, v in points], value_label="Yield (%)"))
    views.append(table_of("rates", label, rows))
    return views, []


# --- news, transcripts -----------------------------------------------------------------------------------------


def _news(endpoint_id: str, label: str, payload: Any) -> Built:
    rows = [r for r in rows_of(payload) if r.get("title")]
    if not rows:
        return _generic(endpoint_id, label, payload)
    items = []
    for article in rows[: V.CAPS["feed"]]:
        link = str(article.get("url") or article.get("link") or "")
        posted = V.epoch(str(article.get("publishedDate") or article.get("date") or "").strip())
        symbols = [_EXCHANGE_PREFIX.sub("", s.strip()) for s in str(article.get("symbol") or article.get("tickers") or "").split(",") if s.strip()]
        items.append(
            {
                "title": str(article["title"]),
                "url": link if link.startswith(("http://", "https://")) else None,
                "source": " \u00b7 ".join(dict.fromkeys(str(article[k]) for k in ("publisher", "author", "site") if article.get(k))) or None,
                "published": posted,
                "summary": clean(article.get("text") or article.get("content")),
                "sentiment": None,
                "tags": [],
                "tickers": [{"symbol": s, "relevance": None, "score": None, "label": None} for s in symbols][:8],
            }
        )
    stamps = [t for t in (V.epoch(str(r.get("publishedDate") or r.get("date") or "")) for r in rows) if t is not None]
    summary = V.facts_view("summary", "Summary", [(None, [V.fact("articles", "Articles returned", len(rows), "integer"), V.fact("newest", "Newest (UTC)", utc(max(stamps)) if stamps else None)])])
    feed = {"kind": "feed", "id": "feed", "title": "Articles", "subtitle": "In the order FMP returned them", "items": items, "total_items": len(rows), "truncated": len(rows) > len(items)}
    return [summary, feed], []


def _transcript(endpoint_id: str, label: str, payload: Any) -> Built:
    rows = [r for r in rows_of(payload) if r.get("content")]
    if not rows:
        return _generic(endpoint_id, label, payload)
    row = rows[0]
    blocks = [{"heading": None, "subheading": None, "body": paragraph, "badge": None} for paragraph in (p.strip() for p in str(row["content"]).splitlines()) if paragraph]
    when = " ".join(str(row[k]) for k in ("symbol", "period", "year") if row.get(k))
    return [facts_of("call", label, {k: row.get(k) for k in ("symbol", "year", "period", "date")}), V.text_view("transcript", "Transcript", blocks, subtitle=when or None)], []


_HANDLERS: dict[str, Callable[[str, str, Any], Built]] = {
    "quote": _quote,
    "profile": _profile,
    "historical_eod": _prices,
    "intraday": _prices,
    "technical_indicator": _prices,
    "revenue_product_segmentation": _segments,
    "revenue_geographic_segmentation": _segments,
    "biggest_gainers": _movers,
    "biggest_losers": _movers,
    "most_actives": _movers,
    "sector_performance": _snapshot("sector", "averageChange", "Average change", "percent", True),
    "industry_performance": _snapshot("industry", "averageChange", "Average change", "percent", True),
    "sector_pe": _snapshot("sector", "pe", "Price to earnings", "number", False),
    "industry_pe": _snapshot("industry", "pe", "Price to earnings", "number", False),
    "treasury_rates": _treasury,
    "transcript": _transcript,
    **{endpoint_id: _periodic for endpoint_id in _CHART_FIELDS},
    **{endpoint_id: _news for endpoint_id in ("fmp_articles", "general_news", "press_releases_latest", "stock_news_latest", "crypto_news_latest", "forex_news_latest", "press_releases_search", "stock_news_search", "crypto_news_search", "forex_news_search")},
}


def build_views(endpoint_id: str, payload: Any, label: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Views and notes for one FMP response. ``label`` is the endpoint title."""

    handler = _HANDLERS.get(endpoint_id)
    try:
        built, notes = handler(endpoint_id, label, payload) if handler else _generic(endpoint_id, label, payload)
    except Exception:  # a shape surprise must cost views, never the whole response
        built, notes = V.analyze(payload, label, V.slug(endpoint_id)), []
    return V.finalize(built, notes)
