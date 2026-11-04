"""Finnhub response shapes -> views. Shapes without a handler go through ``_generic``.

Finnhub answers with objects more often than arrays: a quote is ``{"c", "d", "dp", ...}`` with one-letter keys,
candles are parallel arrays (``{"o": [...], "t": [...], "s": "ok"}``), lists come wrapped (``{"data": [...],
"symbol": ...}``, ``{"earningsCalendar": [...]}``) and times are UNIX seconds. Quotes and profiles become facts,
candles a candlestick chart, news a feed, basic financials figures plus a table per frequency, and statements as
reported a table per statement with one column per filing. A shape that surprises a handler costs that handler's
views, never the response.
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
# UNIX-second fields, shown as UTC times.
_EPOCH_FIELDS = {"datetime", "t"}
# Codes and labels that are digits only by accident: shown as sent, never as a number (a ZIP keeps its leading zero).
_IDENTIFIERS = {
    "cik", "cusip", "isin", "figi", "figiComposite", "shareClassFIGI", "accessNumber", "codeNo", "id", "phone", "socCode", "caseNumber",
    "clientId", "registrantId", "senateId", "houseRegistrantId", "worksitePostalCode", "performanceZipCode", "postalCode", "zip",
    "applicationNumber", "patentNumber", "year", "quarter", "mic", "naicsCode",
}
# Fields that only describe the request; shown as a subtitle rather than as facts.
_CONTEXT = ("symbol", "exchange", "timezone")
_ECHO = {"symbol", "ticker", "exchange", "timezone", "count", "s", "metricType"}
_LABELS = {
    "t": "Time (UTC)", "datetime": "Published (UTC)", "finnhubIndustry": "Industry (Finnhub)", "ipo": "IPO date", "weburl": "Website",
    "marketCapitalization": "Market capitalisation (millions)", "shareOutstanding": "Shares outstanding (millions)",
    "floatingShare": "Floating shares (millions)", "currency": "Reporting currency", "estimateCurrency": "Estimate currency",
    "isOpen": "Open now", "mspr": "Monthly share purchase ratio", "change": "Change",
}
_QUOTE = (("c", "Current price"), ("d", "Change"), ("dp", "Change (%)"), ("o", "Open"), ("h", "High"), ("l", "Low"), ("pc", "Previous close"))
_PROFILE_GROUPS = [
    ("Company", ["name", "ticker", "exchange", "finnhubIndustry", "country", "ipo", "weburl", "phone", "logo"]),
    ("Market", ["marketCapitalization", "shareOutstanding", "floatingShare", "currency", "estimateCurrency"]),
]
_RECOMMENDATIONS = (("strongBuy", "Strong buy"), ("buy", "Buy"), ("hold", "Hold"), ("sell", "Sell"), ("strongSell", "Strong sell"))
_STATEMENTS = (("ic", "Income statement"), ("bs", "Balance sheet"), ("cf", "Cash flow"))
_HOURS = {"bmo": "Before market open", "amc": "After market close", "dmh": "During market hours"}
_MARGINS = (("grossMargin", "Gross margin"), ("operatingMargin", "Operating margin"), ("netMargin", "Net margin"))
# Words in Finnhub's metric names that read better as the usual abbreviation.
_ABBREVIATIONS = {
    "Pe": "P/E", "Pb": "P/B", "Ps": "P/S", "Pfcf": "P/FCF", "Pcf": "P/CF", "Ptbv": "P/TBV", "Eps": "EPS", "Roe": "ROE", "Roa": "ROA",
    "Roi": "ROI", "Roic": "ROIC", "Rotc": "ROTC", "Ebitd": "EBITD", "Ebitda": "EBITDA", "Ebit": "EBIT", "Cagr": "CAGR", "Yoy": "YoY",
    "Ttm": "TTM", "Ev": "EV", "Fcf": "FCF", "Sga": "SG&A", "Std": "std. dev.", "Ad": "AD",
}
# Column labels where Finnhub's field name says too little, from the field descriptions in its spec.
_COLUMN_LABELS = {
    "insider_transactions": {"share": "Shares held after", "change": "Shares bought (+) or sold (-)", "transactionPrice": "Average price", "transactionCode": "Transaction code (SEC Form 4)", "isDerivative": "Derivative"},
    "insider_sentiment": {"change": "Net shares bought (+) or sold (-)", "mspr": "MSPR"},
    "earnings_calendar": {"hour": "When", "epsEstimate": "EPS estimate", "epsActual": "EPS actual"},
    "company_earnings": {"actual": "Actual EPS", "estimate": "Estimated EPS", "surprisePercent": "Surprise (%)"},
    "ipo_calendar": {"price": "Price or range", "numberOfShares": "Shares offered", "totalSharesValue": "Total shares value"},
}
# Number columns Finnhub already sends as percentages (1.15 means 1.15%).
_PERCENT_COLUMNS = {"surprisePercent", "dp"}
_ENDPOINT_NOTES = {"fda_committee_meeting_calendar": "Meeting times are US Eastern time, as Finnhub sends them."}
METRIC_NOTE = (
    "Basic financials are shown as Finnhub sends them. Among the figures, volumes are in millions of shares, market capitalisation, "
    "enterprise value and per-employee amounts in millions, and margins, returns, growth rates and yields are already percentages "
    "(48.79 means 48.79%). In the annual and quarterly tables, margins and returns are fractions (0.4879 means 48.79%); the margin "
    "chart shows them as percentages."
)
REPORTED_NOTE = "Statements as reported: each value is what the company filed with the SEC, in the unit on its row. Line names are the company's own and can change between filings."


# --- small helpers -------------------------------------------------------------------------------------


def num(value: Any) -> Optional[float]:
    return None if isinstance(value, bool) else V.to_number(value)


def utc(seconds: float) -> str:
    return datetime.fromtimestamp(seconds, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def clean(text: Any, limit: int = 600) -> Optional[str]:
    out = " ".join(html.unescape(_HTML.sub(" ", str(text or ""))).split())
    return (out if len(out) <= limit else out[: limit - 1].rstrip() + "\u2026") or None


def verbatim(value: Any) -> Optional[str]:
    """A cell or fact as Finnhub sent it: flags as Yes/No, everything else as text; nothing for a missing or nested value."""

    if V.is_missing(value) or isinstance(value, (dict, list)):
        return None
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(int(value)) if isinstance(value, float) and value.is_integer() else str(value)


def tone(number: Optional[float]) -> Optional[str]:
    return None if not number else "positive" if number > 0 else "negative"


def is_epoch(key: str, value: Any) -> bool:
    return key in _EPOCH_FIELDS and isinstance(value, (int, float)) and not isinstance(value, bool) and value > 1e8


def readable(record: dict[str, Any]) -> dict[str, Any]:
    """``record`` with its UNIX-second fields as UTC times."""

    return {k: (utc(v) if is_epoch(k, v) else v) for k, v in record.items()}


def records_of(payload: Any) -> list[dict[str, Any]]:
    """The records of a response: an array of objects, or the first array of objects inside an object."""

    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        for value in payload.values():
            if isinstance(value, list) and value and all(isinstance(r, dict) for r in value):
                return value
    return []


def context_of(payload: Any) -> Optional[str]:
    if not isinstance(payload, dict):
        return None
    return " \u00b7 ".join(str(payload[k]) for k in _CONTEXT if isinstance(payload.get(k), (str, int)) and payload.get(k)) or None


def patch_table(view: Optional[dict[str, Any]], records: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Redo identifier and flag columns from the ``records`` the table was built from: the generic typing would read
    ``95014`` as a number and pass booleans on, which the frontend rejects."""

    if not view:
        return view
    for index, column in enumerate(view["columns"]):
        sources = [r.get(column["key"]) for r in records[: len(view["rows"])]]
        if column["key"] in _IDENTIFIERS or any(isinstance(s, bool) for s in sources):
            column["type"] = "text"
            for row, source in zip(view["rows"], sources):
                row[index] = verbatim(source)
    return view


def table_of(view_id: str, title: str, records: list[dict[str, Any]], keys: Optional[list[str]] = None, subtitle: Optional[str] = None) -> Optional[dict[str, Any]]:
    rows = [readable(r) for r in records]
    if keys:
        keys = [k for k in keys if any(r.get(k) not in (None, "") for r in rows)] or None
    return patch_table(V.table_view(view_id, title, rows, keys=keys, subtitle=subtitle), rows)


def rows_views(prefix: str, title: str, records: list[dict[str, Any]], subtitle: Optional[str] = None) -> list[Optional[dict[str, Any]]]:
    """A table of the records, plus a chart when they have one date column and numbers. Identifiers stay in the table
    but never become a chart line (a ZIP code or NAICS code is digits, not a quantity)."""

    rows = [readable(r) for r in records]
    charted = [{k: v for k, v in r.items() if k not in _IDENTIFIERS} for r in rows]
    return [V.series_from_records(f"{prefix}-chart", title, charted, subtitle), patch_table(V.table_view(f"{prefix}-table", title, rows, subtitle=subtitle), rows)]


def fact_of(key: str, value: Any) -> Optional[dict[str, Any]]:
    if V.is_missing(value) or isinstance(value, (dict, list)):
        return None
    label = _LABELS.get(key) or V.humanize(key)
    if key in _IDENTIFIERS:
        return V.fact(key, label, verbatim(value))
    if is_epoch(key, value):
        return V.fact(key, label if key in _LABELS else f"{label} (UTC)", utc(value))
    item = V.smart_fact(key, value)
    item["label"] = label
    return item


def facts_of(view_id: str, title: str, record: dict[str, Any], groups: Optional[list[tuple[Optional[str], list[str]]]] = None, subtitle: Optional[str] = None) -> Optional[dict[str, Any]]:
    built = [(name, [item for item in (fact_of(k, record.get(k)) for k in keys) if item]) for name, keys in (groups or [(None, list(record))])]
    return V.facts_view(view_id, title, built, subtitle=subtitle)


def string_table(view_id: str, title: str, values: list[Any], key: str = "value", label: str = "Value") -> Optional[dict[str, Any]]:
    view = V.table_view(view_id, title, [{key: verbatim(v)} for v in values])
    if view:
        view["columns"][0].update(label=label, type="text")
    return view


# --- generic ----------------------------------------------------------------------------------------------


def _generic(endpoint_id: str, label: str, payload: Any) -> Built:
    """Arrays of records become a table, flat objects facts, wrapped arrays a table under the object's context."""

    slug = V.slug(endpoint_id)
    if isinstance(payload, list):
        if payload and all(isinstance(r, dict) for r in payload):
            return ([facts_of(slug, label, payload[0], subtitle=context_of(payload[0]))] if len(payload) == 1 else rows_views(slug, label, payload)), []
        if payload and all(not isinstance(v, (dict, list)) for v in payload):
            return [string_table(slug, label, payload)], []
        return V.analyze(payload, label, slug), []
    if not isinstance(payload, dict):
        return V.analyze(payload, label, slug), []
    subtitle = context_of(payload)
    nested = {k: v for k, v in payload.items() if isinstance(v, (dict, list)) and v}
    if not nested:
        return [facts_of(slug, label, payload, subtitle=subtitle)], []
    views: list[Optional[dict[str, Any]]] = []
    shown = {k: v for k, v in payload.items() if k not in nested and k not in _ECHO}
    if shown:
        views.append(facts_of(f"{slug}-facts", label, shown, subtitle=subtitle))
    for key, value in nested.items():
        title = label if len(nested) == 1 else V.humanize(key)
        prefix = f"{slug}-{V.slug(key)}"
        if isinstance(value, list) and all(isinstance(r, dict) for r in value):
            views.extend(rows_views(prefix, title, value, subtitle))
        elif isinstance(value, list) and all(not isinstance(v, (dict, list)) for v in value):
            views.append(string_table(prefix, title, value))
        elif isinstance(value, dict) and all(not isinstance(v, (dict, list)) for v in value.values()):
            views.append(facts_of(prefix, title, value, subtitle=subtitle))
        else:
            views.extend(V.analyze(value, title, prefix))
    return views, []


# --- quotes, profiles, status -----------------------------------------------------------------------------


def _quote(endpoint_id: str, label: str, payload: Any) -> Built:
    if not isinstance(payload, dict) or num(payload.get("c")) is None:
        return _generic(endpoint_id, label, payload)
    items = []
    for key, name in _QUOTE:
        number = num(payload.get(key))
        if number is not None:
            items.append(V.fact(key, name, number, "percent" if key == "dp" else "number", tone(number) if key in ("d", "dp") else None))
    if is_epoch("t", payload.get("t")):
        items.append(V.fact("t", "Updated (UTC)", utc(payload["t"])))
    return [V.facts_view("quote", label, [(None, items)])], []


def _profile(endpoint_id: str, label: str, payload: Any) -> Built:
    if not isinstance(payload, dict) or not payload.get("name"):
        return _generic(endpoint_id, label, payload)
    return [facts_of("profile", str(payload["name"]), payload, _PROFILE_GROUPS, subtitle=payload.get("ticker"))], []


def _strings(key: str, column: str) -> Callable[[str, str, Any], Built]:
    def build(endpoint_id: str, label: str, payload: Any) -> Built:
        if not isinstance(payload, list) or not all(isinstance(v, str) for v in payload):
            return _generic(endpoint_id, label, payload)
        return [string_table(V.slug(endpoint_id), label, payload, key, column)], []

    return build


# --- news --------------------------------------------------------------------------------------------------


def _news(endpoint_id: str, label: str, payload: Any) -> Built:
    rows = [r for r in records_of(payload) if r.get("headline")]
    if not rows:
        return _generic(endpoint_id, label, payload)
    items = []
    for article in rows[: V.CAPS["feed"]]:
        link = str(article.get("url") or "")
        stamp = article.get("datetime")
        posted = int(stamp) if is_epoch("datetime", stamp) else V.epoch(str(stamp or "").strip())
        tickers = [s.strip() for s in str(article.get("related") or article.get("symbol") or "").split(",") if s.strip()]
        items.append(
            {
                "title": clean(article["headline"], 300) or "",
                "url": link if link.startswith(("http://", "https://")) else None,
                "source": str(article.get("source") or "") or None,
                "published": posted,
                "summary": clean(article.get("summary") or article.get("description")),
                "sentiment": None,
                "tags": [str(article["category"])] if article.get("category") else [],
                "tickers": [{"symbol": s, "relevance": None, "score": None, "label": None} for s in tickers][:8],
            }
        )
    stamps = [t for t in (int(r["datetime"]) if is_epoch("datetime", r.get("datetime")) else V.epoch(str(r.get("datetime") or "")) for r in rows) if t is not None]
    summary = V.facts_view("summary", "Summary", [(None, [V.fact("articles", "Articles returned", len(rows), "integer"), V.fact("newest", "Newest (UTC)", utc(max(stamps)) if stamps else None), V.fact("oldest", "Oldest (UTC)", utc(min(stamps)) if stamps else None)])])
    feed = {"kind": "feed", "id": "feed", "title": "Articles", "subtitle": "In the order Finnhub returned them", "items": items, "total_items": len(rows), "truncated": len(rows) > len(items)}
    notes = []
    if endpoint_id == "company_news" and len(rows) >= 240:
        notes.append(f"Finnhub returns at most about 250 articles per request, newest first, so this answer may stop short of the start date (the oldest article is from {utc(min(stamps)) if stamps else 'an unknown time'} UTC). Narrow the range to see earlier days.")
    return [summary, feed], notes


# --- fundamentals -------------------------------------------------------------------------------------------


def metric_label(key: str) -> str:
    words = V.humanize(key.replace("/", " / ")).split(" ")
    return " ".join(_ABBREVIATIONS.get(w, w) for w in words)


def _period_table(view_id: str, title: str, block: dict[str, Any], subtitle: Optional[str]) -> tuple[Optional[dict[str, Any]], list[str]]:
    """``{metric: [{"period", "v"}]}`` as a table with a row per metric and a column per period, most recent first."""

    values: dict[str, dict[str, Optional[float]]] = {}
    for metric, points in block.items():
        if isinstance(points, list):
            values[metric] = {str(p["period"]): num(p.get("v")) for p in points if isinstance(p, dict) and p.get("period")}
    periods = sorted({p for row in values.values() for p in row}, reverse=True)
    shown = periods[:MAX_PERIODS]
    records = [{"item": metric_label(m), **{p: row.get(p) for p in shown}} for m, row in values.items() if row]
    view = V.table_view(view_id, title, records, keys=["item", *shown], subtitle=subtitle)
    if view:
        view["columns"][0].update(label="Figure", type="text")
        for column in view["columns"][1:]:
            column["label"] = column["key"]
    notes = [f"{title}: showing the latest {len(shown)} of {len(periods)} periods; the raw response has them all."] if len(periods) > len(shown) else []
    return view, notes


def _line(block: dict[str, Any], pairs: tuple[tuple[str, str], ...], scale: float = 1.0) -> tuple[list[int], list[dict[str, Any]]]:
    """Times and chart columns for some metrics of a ``{metric: [{"period", "v"}]}`` block."""

    series = {k: {str(p["period"]): num(p.get("v")) for p in block.get(k) or [] if isinstance(p, dict) and p.get("period")} for k, _ in pairs}
    periods = sorted({p for row in series.values() for p in row})
    times = [V.epoch(p) for p in periods]
    keep = [i for i, t in enumerate(times) if t is not None]
    columns = []
    for key, name in pairs:
        if series[key]:
            raw = [series[key].get(periods[i]) for i in keep]
            columns.append({"key": key, "label": name, "values": [None if v is None else round(v * scale, 6) for v in raw], "role": "value", "unit": None})
    return [int(times[i]) for i in keep], columns  # type: ignore[arg-type]


def _basic_financials(endpoint_id: str, label: str, payload: Any) -> Built:
    if not isinstance(payload, dict) or not isinstance(payload.get("metric"), dict):
        return _generic(endpoint_id, label, payload)
    symbol = payload.get("symbol") if isinstance(payload.get("symbol"), str) else None
    items = []
    for key, value in payload["metric"].items():
        if V.is_missing(value) or isinstance(value, (dict, list, bool)):
            continue
        number = num(value)
        items.append(V.fact(key, metric_label(key), number, "number") if number is not None else V.fact(key, metric_label(key), str(value)))
    views: list[Optional[dict[str, Any]]] = [V.facts_view("metrics", "Figures", [(None, items)], subtitle=symbol)]
    notes = [METRIC_NOTE]
    series = payload.get("series") if isinstance(payload.get("series"), dict) else {}
    annual = series.get("annual") if isinstance(series.get("annual"), dict) else {}
    if annual:
        times, columns = _line(annual, (("eps", "EPS"),))
        views.append(V.series_view("eps", "Earnings per share (annual)", times, columns, subtitle=symbol))
        times, columns = _line(annual, tuple((k, f"{n} (%)") for k, n in _MARGINS), 100.0)
        views.append(V.series_view("margins", "Margins (annual, % of revenue)", times, columns, subtitle=symbol))
    for freq, title in (("annual", "Annual figures"), ("quarterly", "Quarterly figures")):
        block = series.get(freq)
        if isinstance(block, dict) and block:
            table, more = _period_table(f"{freq}-table", title, block, symbol)
            views.append(table)
            notes.extend(more)
    return views, notes


def _filing_labels(reports: list[dict[str, Any]]) -> list[str]:
    labels: list[str] = []
    for report in reports:
        year, quarter = report.get("year"), report.get("quarter")
        name = f"FY{year}" if not quarter else f"{year} Q{quarter}"
        name = f"{name} {report['form']}" if report.get("form") else name
        labels.append(f"{name} ({report.get('accessNumber')})" if name in labels else name)
    return labels


def _financials_reported(endpoint_id: str, label: str, payload: Any) -> Built:
    reports = [r for r in records_of(payload) if isinstance(r.get("report"), dict)]
    if not reports:
        return _generic(endpoint_id, label, payload)
    symbol = context_of(payload)
    shown = reports[:MAX_PERIODS]
    columns = _filing_labels(shown)
    views: list[Optional[dict[str, Any]]] = []
    for code, title in _STATEMENTS:
        lines: dict[str, dict[str, Any]] = {}
        for column, report in zip(columns, shown):
            for line in report["report"].get(code) or []:
                if not isinstance(line, dict) or not (line.get("concept") or line.get("label")):
                    continue
                row = lines.setdefault(str(line.get("concept") or line.get("label")), {"item": str(line.get("label") or line.get("concept")), "unit": verbatim(line.get("unit"))})
                row[column] = num(line.get("value"))
        if lines:
            view = V.table_view(f"{code}-table", f"{title} as reported", list(lines.values()), keys=["item", "unit", *columns], subtitle=symbol)
            if view:
                view["columns"][0].update(label="Line", type="text")
                view["columns"][1].update(label="Unit", type="text")
                for column in view["columns"][2:]:
                    column["label"] = column["key"]
            views.append(view)
    keys = ["accessNumber", "form", "year", "quarter", "startDate", "endDate", "filedDate", "acceptedDate"]
    views.append(table_of("filings", "Filings", [{k: r.get(k) for k in keys} for r in reports], keys, subtitle=symbol))
    notes = [REPORTED_NOTE]
    if len(reports) > len(shown):
        notes.append(f"The statements show the latest {len(shown)} of {len(reports)} filings; the filings table lists them all.")
    return views, notes


# --- estimates and insiders ---------------------------------------------------------------------------------


def _dated(rows: list[dict[str, Any]], when: Callable[[dict[str, Any]], Optional[str]]) -> list[tuple[int, dict[str, Any]]]:
    pairs = [(t, r) for r in rows if (text := when(r)) and (t := V.epoch(text)) is not None]
    return sorted(pairs, key=lambda p: p[0])


def _recommendations(endpoint_id: str, label: str, payload: Any) -> Built:
    rows = records_of(payload)
    pairs = _dated(rows, lambda r: str(r.get("period") or "") or None)
    if not pairs:
        return _generic(endpoint_id, label, payload)
    symbol = str(pairs[-1][1].get("symbol") or "") or None
    columns = [{"key": k, "label": n, "values": [num(r.get(k)) for _, r in pairs], "role": "value", "unit": None} for k, n in _RECOMMENDATIONS]
    latest = pairs[-1][1]
    views = [
        V.series_view("trend", "Analyst recommendations", [t for t, _ in pairs], columns, subtitle=symbol),
        V.bars_view("latest", f"Recommendations on {latest['period']}", [n for _, n in _RECOMMENDATIONS], [num(latest.get(k)) for k, _ in _RECOMMENDATIONS], value_label="Analysts", subtitle=symbol),
        table_of("recommendations", label, rows, subtitle=symbol),
    ]
    return views, []


def _surprises(endpoint_id: str, label: str, payload: Any) -> Built:
    rows = records_of(payload)
    pairs = _dated(rows, lambda r: str(r.get("period") or "") or None)
    if not pairs:
        return _generic(endpoint_id, label, payload)
    symbol = str(pairs[-1][1].get("symbol") or "") or None
    columns = [{"key": k, "label": n, "values": [num(r.get(k)) for _, r in pairs], "role": "value", "unit": None} for k, n in (("actual", "Actual EPS"), ("estimate", "Estimated EPS"))]
    views = [
        V.series_view("eps", "Earnings per share: actual and estimate", [t for t, _ in pairs], columns, subtitle=symbol),
        V.bars_view("surprise", "Surprise (% of the estimate)", [str(r["period"]) for _, r in pairs], [num(r.get("surprisePercent")) for _, r in pairs], fmt="percent", sign_colors=True, value_label="Surprise", subtitle=symbol),
        table_of("surprises", label, [r for _, r in reversed(pairs)], ["period", "year", "quarter", "actual", "estimate", "surprise", "surprisePercent", "symbol"], subtitle=symbol),
    ]
    return views, []


def _insider_sentiment(endpoint_id: str, label: str, payload: Any) -> Built:
    rows = records_of(payload)
    pairs = _dated(rows, lambda r: f"{int(r['year']):04d}-{int(r['month']):02d}-01" if num(r.get("year")) and num(r.get("month")) else None)
    if not pairs:
        return _generic(endpoint_id, label, payload)
    symbol = context_of(payload)
    times = [t for t, _ in pairs]
    views = [
        V.series_view("mspr", "Monthly share purchase ratio (MSPR)", times, [{"key": "mspr", "label": "MSPR", "values": [num(r.get("mspr")) for _, r in pairs], "role": "value", "unit": None}], subtitle=symbol),
        V.series_view("change", "Net shares bought (+) or sold (-) by insiders", times, [{"key": "change", "label": "Net change", "values": [num(r.get("change")) for _, r in pairs], "role": "value", "unit": None}], subtitle=symbol),
        table_of("sentiment", label, [r for _, r in reversed(pairs)], subtitle=symbol),
    ]
    return views, ["MSPR runs from -100 (insiders only sold) to 100 (insiders only bought)."]


def _earnings_calendar(endpoint_id: str, label: str, payload: Any) -> Built:
    rows = records_of(payload)
    if not rows:
        return _generic(endpoint_id, label, payload)
    shown = [{**r, "hour": _HOURS.get(str(r.get("hour") or "").lower(), r.get("hour"))} for r in rows]
    notes = ["Finnhub returns at most 1,500 rows per request, so this range was probably cut short. Use a shorter range."] if len(rows) >= 1500 else []
    return [table_of("calendar", label, shown, ["date", "hour", "symbol", "year", "quarter", "epsEstimate", "epsActual", "revenueEstimate", "revenueActual"])], notes


# --- prices ---------------------------------------------------------------------------------------------------


def _candles(endpoint_id: str, label: str, payload: Any) -> Built:
    """Parallel arrays ``o h l c v`` against ``t`` (UNIX seconds); any other array of the same length is an indicator."""

    stamps = payload.get("t") if isinstance(payload, dict) else None
    if not isinstance(stamps, list) or not stamps or any(num(t) is None for t in stamps):
        return _generic(endpoint_id, label, payload)
    times = [int(t) for t in stamps]
    size = len(times)
    arrays = {k: v for k, v in payload.items() if k != "t" and isinstance(v, list) and len(v) == size}
    columns = [{"key": role, "label": V.humanize(role), "values": [num(x) for x in arrays[k]], "role": role, "unit": None} for k, role in (("o", "open"), ("h", "high"), ("l", "low"), ("c", "close"), ("v", "volume")) if k in arrays]
    gaps = sorted(b - a for a, b in zip(times, times[1:]) if b > a)
    intraday = bool(gaps) and gaps[len(gaps) // 2] < 86400
    views: list[Optional[dict[str, Any]]] = [V.series_view("candles", label, times, columns, intraday=intraday, time_note="Times are UTC." if intraday else None)]
    extras = [k for k in arrays if k not in ("o", "h", "l", "c", "v")]
    for key in extras:
        views.append(V.series_view(f"indicator-{V.slug(key)}", V.humanize(key), times, [{"key": key, "label": V.humanize(key), "values": [num(x) for x in arrays[key]], "role": "value", "unit": None}], intraday=intraday))
    names = {"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"}
    records = [{"time": utc(t), **{names.get(k, k): num(arrays[k][i]) for k in arrays}} for i, t in enumerate(times)]
    views.append(V.table_view("candles-table", label, records[::-1]))
    return views, []


_HANDLERS: dict[str, Callable[[str, str, Any], Built]] = {
    "quote": _quote,
    "company_profile2": _profile,
    "company_peers": _strings("symbol", "Symbol"),
    "forex_exchanges": _strings("exchange", "Exchange"),
    "crypto_exchanges": _strings("exchange", "Exchange"),
    "market_news": _news,
    "company_news": _news,
    "press_releases": _news,
    "company_basic_financials": _basic_financials,
    "financials_reported": _financials_reported,
    "recommendation_trends": _recommendations,
    "company_earnings": _surprises,
    "insider_sentiment": _insider_sentiment,
    "earnings_calendar": _earnings_calendar,
    **{endpoint_id: _candles for endpoint_id in ("stock_candles", "forex_candles", "crypto_candles", "bond_price", "technical_indicator")},
}


def build_views(endpoint_id: str, payload: Any, label: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Views and notes for one Finnhub response. ``label`` is the endpoint title."""

    handler = _HANDLERS.get(endpoint_id, _generic)
    try:
        built, notes = handler(endpoint_id, label, payload)
    except Exception:  # a shape surprise must cost views, never the whole response
        built, notes = V.analyze(payload, label, V.slug(endpoint_id)), []
    labels = _COLUMN_LABELS.get(endpoint_id, {})
    for view in built:
        for column in (view or {}).get("columns", []) if (view or {}).get("kind") == "table" else []:
            column["label"] = labels.get(column["key"], column["label"])
            if column["key"] in _PERCENT_COLUMNS and column["type"] == "number":
                column["type"] = "percent"
    if endpoint_id in _ENDPOINT_NOTES:
        notes = [*notes, _ENDPOINT_NOTES[endpoint_id]]
    return V.finalize(built, notes)
