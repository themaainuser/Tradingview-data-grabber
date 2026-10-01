"""Alpha Vantage response shapes -> views. Everything not special-cased goes through ``views.analyze``."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from . import views as V

_STATEMENT_METRICS = {
    "INCOME_STATEMENT": ["totalRevenue", "grossProfit", "operatingIncome", "netIncome", "ebitda"],
    "BALANCE_SHEET": ["totalAssets", "totalLiabilities", "totalShareholderEquity", "cashAndCashEquivalentsAtCarryingValue", "longTermDebt"],
    "CASH_FLOW": ["operatingCashflow", "capitalExpenditures", "cashflowFromInvestment", "cashflowFromFinancing", "netIncome"],
}
_OVERVIEW_GROUPS = [
    ("Company", ["Symbol", "AssetType", "Name", "Exchange", "Currency", "Country", "Sector", "Industry", "CIK", "Address", "OfficialSite", "FiscalYearEnd", "LatestQuarter", "Description"]),
    ("Valuation", ["MarketCapitalization", "PERatio", "PEGRatio", "TrailingPE", "ForwardPE", "PriceToSalesRatioTTM", "PriceToBookRatio", "EVToRevenue", "EVToEBITDA", "BookValue"]),
    ("Financials", ["EBITDA", "RevenueTTM", "GrossProfitTTM", "RevenuePerShareTTM", "EPS", "DilutedEPSTTM", "ProfitMargin", "OperatingMarginTTM", "ReturnOnAssetsTTM", "ReturnOnEquityTTM", "QuarterlyEarningsGrowthYOY", "QuarterlyRevenueGrowthYOY"]),
    ("Dividends", ["DividendPerShare", "DividendYield", "DividendDate", "ExDividendDate"]),
    ("Analysts", ["AnalystTargetPrice", "AnalystRatingStrongBuy", "AnalystRatingBuy", "AnalystRatingHold", "AnalystRatingSell", "AnalystRatingStrongSell"]),
    ("Technicals", ["Beta", "52WeekHigh", "52WeekLow", "50DayMovingAverage", "200DayMovingAverage", "SharesOutstanding", "SharesFloat", "PercentInsiders", "PercentInstitutions"]),
]
_SENTIMENT_ORDER = ["Bearish", "Somewhat-Bearish", "Neutral", "Somewhat-Bullish", "Bullish"]

Built = tuple[list[Optional[dict[str, Any]]], list[str]]


def _meta(payload: dict[str, Any]) -> dict[str, Any]:
    meta = payload.get("Meta Data")
    return {V.strip_prefix(k): v for k, v in meta.items()} if isinstance(meta, dict) else {}


def _time_series(function: str, payload: dict[str, Any]) -> Built:
    key = next((k for k, v in payload.items() if k != "Meta Data" and V.time_keyed(v)), None)
    if key is None:
        return V.analyze(payload, V.humanize(function), "data"), []
    meta = _meta(payload)
    zone_name = next((str(v) for k, v in meta.items() if k.lower().replace(" ", "") == "timezone"), None)
    tz = V.zone(zone_name)
    notes: list[str] = []
    keyed = payload[key]
    intraday = any(len(str(k)) > 10 for k in list(keyed)[:3])
    time_note = None
    if intraday:
        if tz is None:
            notes.append(f"The time zone {zone_name!r} is not known here, so provider times are read as UTC.")
            time_note = "Provider time zone unknown; times are read as UTC."
        else:
            time_note = f"Provider times are {zone_name}; shown in UTC."
    symbol = next((str(v) for k, v in meta.items() if k.lower() in ("symbol", "digital currency code", "from symbol")), "")
    information = str(meta.get("Information", ""))
    subtitle = " · ".join(part for part in (symbol, information) if part) or None
    has_close = any(V.role_of(V.strip_prefix(f)) == "close" for f in next(iter(keyed.values()), {}))
    title = str(meta.get("Indicator") or ("Price history" if has_close else V.strip_prefix(key)))
    series, stamps, columns, is_intraday = V.time_series_from_keyed("series", title, keyed, tz=tz, subtitle=subtitle, time_note=time_note)
    records = [{"time": k, **{V.strip_prefix(f): v for f, v in row.items()}} for k, row in list(keyed.items())[: V.CAPS["table"]]]
    detail = [(None, V.facts_from_mapping(meta))]
    summary = V.facts_view("summary", "Summary", [("Latest", V.summary_facts(stamps, columns, is_intraday)), ("Details", detail[0][1])], subtitle=subtitle)
    table = V.table_view("table", f"{title} data", records, subtitle="Newest first")
    if table and len(keyed) > len(records):
        notes.append(f"The table shows the newest {len(records):,} of {len(keyed):,} rows.")
    return [summary, series, table], notes


def _statements(function: str, payload: dict[str, Any]) -> Built:
    annual = [r for r in payload.get("annualReports") or [] if isinstance(r, dict)]
    quarterly = [r for r in payload.get("quarterlyReports") or [] if isinstance(r, dict)]
    metrics = _STATEMENT_METRICS.get(function, [])
    out: list[Optional[dict[str, Any]]] = []
    currency = next((r.get("reportedCurrency") for r in annual + quarterly if r.get("reportedCurrency")), None)
    ordered = sorted(annual, key=lambda r: str(r.get("fiscalDateEnding")))
    stamps = [V.epoch(str(r.get("fiscalDateEnding"))) for r in ordered]
    columns = []
    for metric in metrics:
        values = [V.to_number(r.get(metric)) for r in ordered]
        if any(v is not None for v in values):
            columns.append({"key": metric, "label": V.humanize(metric), "values": values, "role": "value", "unit": currency})
    if all(s is not None for s in stamps):
        out.append(V.series_view("annual-chart", "Annual key figures", stamps, columns, subtitle=f"{payload.get('symbol', '')} · {currency or ''}".strip(" ·")))  # type: ignore[arg-type]
    latest, prior = (ordered[-1], ordered[-2]) if len(ordered) > 1 else (ordered[-1] if ordered else None, None)
    items = []
    if latest and metrics:
        for metric in metrics[:3]:
            now = V.to_number(latest.get(metric))
            before = V.to_number(prior.get(metric)) if prior else None
            if now is not None:
                change = (now / before - 1) * 100 if before else None
                items.append(V.fact(metric, V.humanize(metric), now, "number", "positive" if change and change > 0 else "negative" if change and change < 0 else None, f"{change:+.1f}% vs the prior year" if change is not None else None))
    head = V.facts_from_mapping({"symbol": payload.get("symbol"), "latest_fiscal_year_end": latest.get("fiscalDateEnding") if latest else None, "currency": currency, "annual_reports": len(annual), "quarterly_reports": len(quarterly)})
    out.insert(0, V.facts_view("summary", "Summary", [("Latest annual figures", items), ("Report", head)]))
    for name, reports in (("Annual", annual), ("Quarterly", quarterly)):
        out.append(_transposed(f"{name.lower()}-table", f"{name} reports", reports))
    return out, []


def _transposed(view_id: str, title: str, reports: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Metrics as rows and fiscal periods as columns (how statements are read)."""

    if not reports:
        return None
    periods = [str(r.get("fiscalDateEnding")) for r in reports]
    names = [k for k in reports[0] if k not in ("fiscalDateEnding", "reportedCurrency")]
    records = [{"Metric": V.humanize(name), **{p: r.get(name) for p, r in zip(periods, reports)}} for name in names]
    return V.table_view(view_id, title, records, keys=["Metric", *periods], subtitle="Newest period first")


def _overview(payload: dict[str, Any]) -> Built:
    groups, used = [], set()
    for title, keys in _OVERVIEW_GROUPS:
        present = [k for k in keys if k in payload]
        used.update(present)
        groups.append((title, [V.smart_fact(k, payload[k]) for k in present]))
    rest = [k for k in payload if k not in used and not isinstance(payload[k], (dict, list))]
    groups.append(("Other", [V.smart_fact(k, payload[k]) for k in rest]))
    return [V.facts_view("overview", str(payload.get("Name") or "Company overview"), groups, subtitle=str(payload.get("Symbol") or "") or None)], []


def _wrapped_facts(wrapper: str, title: str) -> Callable[[dict[str, Any]], Built]:
    def build(payload: dict[str, Any]) -> Built:
        inner = payload.get(wrapper)
        if not isinstance(inner, dict):
            return V.analyze(payload, title, "data"), []
        return [V.facts_view("facts", title, [(None, [V.smart_fact(k, v) for k, v in inner.items()])])], []

    return build


def _etf(payload: dict[str, Any]) -> Built:
    sectors = [r for r in payload.get("sectors") or [] if isinstance(r, dict)]
    holdings = [dict(r, weight=(V.to_number(r.get("weight")) or 0) * 100) for r in payload.get("holdings") or [] if isinstance(r, dict)]
    table = V.table_view("holdings", "Holdings", holdings)
    if table:
        for column in table["columns"]:
            if column["key"] == "weight":
                column.update(type="percent", label="Weight")
    bars = V.bars_view("sectors", "Sector weights", [str(r.get("sector", "")).title() for r in sectors], [(V.to_number(r.get("weight")) or 0) * 100 for r in sectors], fmt="percent", value_label="Weight")
    return [V.facts_view("profile", "ETF profile", [(None, V.facts_from_mapping(payload))]), bars, table], []


def _earnings(payload: dict[str, Any]) -> Built:
    quarterly = sorted([r for r in payload.get("quarterlyEarnings") or [] if isinstance(r, dict)], key=lambda r: str(r.get("fiscalDateEnding")))
    stamps = [V.epoch(str(r.get("fiscalDateEnding"))) for r in quarterly]
    out: list[Optional[dict[str, Any]]] = []
    if quarterly and all(s is not None for s in stamps):
        cols = [
            {"key": "reported", "label": "Reported EPS", "values": [V.to_number(r.get("reportedEPS")) for r in quarterly], "role": "value", "unit": None},
            {"key": "estimated", "label": "Estimated EPS", "values": [V.to_number(r.get("estimatedEPS")) for r in quarterly], "role": "value", "unit": None},
        ]
        out.append(V.series_view("eps", "Earnings per share by quarter", stamps, cols, subtitle=str(payload.get("symbol") or "") or None))  # type: ignore[arg-type]
        recent = quarterly[-24:]
        out.append(V.bars_view("surprise", "Earnings surprise", [str(r.get("fiscalDateEnding")) for r in recent], [V.to_number(r.get("surprisePercentage")) for r in recent], fmt="percent", sign_colors=True, value_label="Surprise"))
    out.append(V.facts_view("summary", "Summary", [(None, V.facts_from_mapping({"symbol": payload.get("symbol"), "quarters": len(quarterly), "years": len(payload.get("annualEarnings") or [])}))]))
    out.append(V.table_view("quarterly", "Quarterly earnings", list(reversed(quarterly))))
    out.append(V.table_view("annual", "Annual earnings", [r for r in payload.get("annualEarnings") or [] if isinstance(r, dict)]))
    return out, []


def _published(text: Any) -> Optional[int]:
    match = re.match(r"^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})?$", str(text))
    if not match:
        return None
    year, month, day, hour, minute, second = (int(g or 0) for g in match.groups())
    try:
        return int(datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc).timestamp())
    except ValueError:
        return None


def _news(payload: dict[str, Any]) -> Built:
    feed = [a for a in payload.get("feed") or [] if isinstance(a, dict)]
    items = []
    for article in feed[: V.CAPS["feed"]]:
        score = V.to_number(article.get("overall_sentiment_score"))
        items.append(
            {
                "title": str(article.get("title") or "Untitled"),
                "url": article.get("url") if str(article.get("url", "")).startswith(("http://", "https://")) else None,
                "source": article.get("source") or None,
                "published": _published(article.get("time_published")),
                "summary": article.get("summary") or None,
                "sentiment": {"score": score, "label": article.get("overall_sentiment_label")} if score is not None or article.get("overall_sentiment_label") else None,
                "tags": [str(t.get("topic")).replace("_", " ").title() for t in article.get("topics") or [] if isinstance(t, dict) and t.get("topic")][:6],
                "tickers": [
                    {"symbol": str(t.get("ticker")), "relevance": V.to_number(t.get("relevance_score")), "score": V.to_number(t.get("ticker_sentiment_score")), "label": t.get("ticker_sentiment_label")}
                    for t in article.get("ticker_sentiment") or []
                    if isinstance(t, dict) and t.get("ticker")
                ][:8],
            }
        )
    out: list[Optional[dict[str, Any]]] = []
    scores = [V.to_number(a.get("overall_sentiment_score")) for a in feed]
    scores = [s for s in scores if s is not None]
    counts = {label: sum(1 for a in feed if a.get("overall_sentiment_label") == label) for label in _SENTIMENT_ORDER}
    out.append(V.facts_view("summary", "Summary", [(None, [V.fact("articles", "Articles returned", len(feed), "integer"), V.fact("average", "Average sentiment", sum(scores) / len(scores) if scores else None, "sentiment", None, "From -1 (bearish) to +1 (bullish)")])]))
    if items:
        out.append({"kind": "feed", "id": "feed", "title": "Articles", "subtitle": "Newest first", "items": items, "total_items": len(feed), "truncated": len(feed) > len(items)})
    present = [label for label in _SENTIMENT_ORDER if counts[label]]
    out.append(V.bars_view("distribution", "Sentiment of the articles", present, [float(counts[label]) for label in present], value_label="Articles"))
    return out, []


def _movers(payload: dict[str, Any]) -> Built:
    lists = {k: [r for r in payload.get(k) or [] if isinstance(r, dict)] for k in ("top_gainers", "top_losers", "most_actively_traded")}
    titles = {"top_gainers": "Top gainers", "top_losers": "Top losers", "most_actively_traded": "Most actively traded"}
    moves = [(r.get("ticker"), V.percent_value(r.get("change_percentage"))) for r in lists["top_gainers"][:10] + lists["top_losers"][:10]]
    out: list[Optional[dict[str, Any]]] = [
        V.facts_view("summary", "Summary", [(None, V.facts_from_mapping({"last_updated": payload.get("last_updated"), "metadata": payload.get("metadata")}))]),
        V.bars_view("moves", "Biggest moves", [str(t) for t, _ in moves], [p for _, p in moves], fmt="percent", sign_colors=True, value_label="Change"),
    ]
    out += [V.table_view(k, titles[k], rows) for k, rows in lists.items()]
    return out, []


def _metric_title(metric: str) -> str:
    """``STDDEV(ANNUALIZED=TRUE)`` -> ``Stddev``; the provider names metrics in capitals."""

    return V.humanize(metric.split("(")[0]).title()


def _matrix(block: dict[str, Any]) -> Optional[tuple[list[str], list[list[Optional[float]]]]]:
    names = block.get("index")
    grid = next((v for k, v in block.items() if k != "index" and isinstance(v, list)), None)
    if not isinstance(names, list) or not isinstance(grid, list) or len(grid) != len(names):
        return None
    size = len(names)
    full: list[list[Optional[float]]] = [[None] * size for _ in range(size)]
    for i, row in enumerate(grid):
        for j, cell in enumerate(row[:size] if isinstance(row, list) else []):
            value = V.to_number(cell)
            full[i][j] = value
            if full[j][i] is None:
                full[j][i] = value
    return [str(n) for n in names], full


def _analytics_fixed(payload: dict[str, Any]) -> Built:
    meta = payload.get("meta_data") if isinstance(payload.get("meta_data"), dict) else {}
    out: list[Optional[dict[str, Any]]] = [V.facts_view("summary", "Calculation", [(None, V.facts_from_mapping(meta))])]
    scalar_rows: dict[str, dict[str, Any]] = {}
    for group, metrics in (payload.get("payload") or {}).items():
        for metric, block in (metrics or {}).items() if isinstance(metrics, dict) else []:
            if isinstance(block, dict) and "index" in block:
                matrix = _matrix(block)
                if matrix:
                    names, values = matrix
                    out.append(V.heatmap_view(f"{V.slug(group)}-{V.slug(metric)}", _metric_title(metric), names, names, values, domain=[-1.0, 1.0] if "CORREL" in metric.upper() else None))
            elif isinstance(block, dict):
                for symbol, value in block.items():
                    scalar_rows.setdefault(str(symbol), {"Symbol": symbol})[_metric_title(metric)] = value
    if scalar_rows:
        out.append(V.table_view("metrics", "Metrics by symbol", list(scalar_rows.values())))
    return out, []


def _analytics_sliding(payload: dict[str, Any]) -> Built:
    meta = payload.get("meta_data") if isinstance(payload.get("meta_data"), dict) else {}
    out: list[Optional[dict[str, Any]]] = [V.facts_view("summary", "Calculation", [(None, V.facts_from_mapping(meta))])]
    for group, metrics in (payload.get("payload") or {}).items():
        for metric, block in (metrics or {}).items() if isinstance(metrics, dict) else []:
            running = next((v for k, v in (block or {}).items() if k.startswith("RUNNING_") and isinstance(v, dict)), None) if isinstance(block, dict) else None
            if not running:
                continue
            stamps = sorted({V.epoch(d) for series in running.values() if isinstance(series, dict) for d in series} - {None})
            columns = [
                {"key": str(symbol), "label": str(symbol), "values": [V.to_number(series.get(datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d"))) for t in stamps], "role": "value", "unit": None}
                for symbol, series in running.items()
                if isinstance(series, dict)
            ]
            out.append(V.series_view(f"{V.slug(group)}-{V.slug(metric)}", _metric_title(metric), stamps, columns, subtitle=f"Window of {meta.get('window_size', '?')} bars"))  # type: ignore[arg-type]
    return out, []


def _transcript(payload: dict[str, Any]) -> Built:
    segments = [s for s in payload.get("transcript") or [] if isinstance(s, dict)]
    blocks, scores = [], []
    for segment in segments:
        score = V.to_number(segment.get("sentiment"))
        if score is not None:
            scores.append(score)
        blocks.append({"heading": segment.get("speaker"), "subheading": segment.get("title"), "body": str(segment.get("content") or ""), "badge": f"Sentiment {score:+.2f}" if score is not None else None})
    facts = V.facts_view("summary", "Summary", [(None, [V.fact("symbol", "Symbol", payload.get("symbol")), V.fact("quarter", "Quarter", payload.get("quarter")), V.fact("segments", "Segments", len(segments), "integer"), V.fact("sentiment", "Average sentiment", sum(scores) / len(scores) if scores else None, "sentiment")])])
    return [facts, V.text_view("transcript", "Transcript", blocks, subtitle=f"{payload.get('symbol', '')} {payload.get('quarter', '')}".strip() or None)], []


def _index_catalog(payload: dict[str, Any]) -> Built:
    return [V.table_view("catalog", "Supported indices", [{"Symbol": k, "Name": v} for k, v in payload.items()])], []


def _options(payload: dict[str, Any]) -> Built:
    rows = [r for r in payload.get("data") or [] if isinstance(r, dict)]
    calls = sum(1 for r in rows if str(r.get("type")).lower() == "call")
    strikes = [s for s in (V.to_number(r.get("strike")) for r in rows) if s is not None]
    facts = V.facts_view("summary", "Summary", [(None, [
        V.fact("contracts", "Contracts", len(rows), "integer"),
        V.fact("calls", "Calls", calls, "integer"),
        V.fact("puts", "Puts", len(rows) - calls, "integer"),
        V.fact("expirations", "Expirations", len({r.get("expiration") for r in rows}), "integer"),
        V.fact("strikes", "Strike range", f"{min(strikes):g} to {max(strikes):g}" if strikes else None),
    ])])
    return [facts, V.table_view("contracts", "Option contracts", rows)], []


_SPECIAL: dict[str, Callable[[dict[str, Any]], Built]] = {
    "OVERVIEW": _overview,
    "GLOBAL_QUOTE": _wrapped_facts("Global Quote", "Quote"),
    "CURRENCY_EXCHANGE_RATE": _wrapped_facts("Realtime Currency Exchange Rate", "Exchange rate"),
    "ETF_PROFILE": _etf,
    "EARNINGS": _earnings,
    "NEWS_SENTIMENT": _news,
    "TOP_GAINERS_LOSERS": _movers,
    "ANALYTICS_FIXED_WINDOW": _analytics_fixed,
    "ANALYTICS_SLIDING_WINDOW": _analytics_sliding,
    "EARNINGS_CALL_TRANSCRIPT": _transcript,
    "INDEX_CATALOG": _index_catalog,
    "HISTORICAL_OPTIONS": _options,
    "REALTIME_OPTIONS": _options,
}


def _name_generic(built: list[Optional[dict[str, Any]]], payload: Any) -> None:
    """Use the response's own ``name`` and ``unit`` (economic data, indices) instead of generic titles."""

    if not isinstance(payload, dict):
        return
    name = payload.get("name") if isinstance(payload.get("name"), str) else None
    unit = payload.get("unit") if isinstance(payload.get("unit"), str) else None
    for view in built:
        if not view:
            continue
        if name and view["title"] == "Data":
            view["title"] = name
        if view["kind"] == "series" and unit:
            for column in view["series"]:
                column["unit"] = unit
            view["subtitle"] = view.get("subtitle") or unit


def build_views(function: str, payload: Any, label: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Views and notes for one Alpha Vantage response. ``label`` is the endpoint title."""

    notes: list[str] = []
    built: list[Optional[dict[str, Any]]]
    try:
        if isinstance(payload, dict) and "Meta Data" in payload:
            built, notes = _time_series(function, payload)
        elif function in _STATEMENT_METRICS and isinstance(payload, dict):
            built, notes = _statements(function, payload)
        elif function in _SPECIAL and isinstance(payload, dict):
            built, notes = _SPECIAL[function](payload)
        else:
            built = V.analyze(payload, label, V.slug(function))
            _name_generic(built, payload)
    except Exception:  # a shape surprise must cost views, never the whole response
        built, notes = V.analyze(payload, label, V.slug(function)), []
    kept = V.order_views(built)
    if not any(v["kind"] == "facts" and v["id"].endswith("summary") for v in kept):
        chart = next((v for v in kept if v["kind"] == "series"), None)
        if chart:
            summary = V.facts_view("summary", "Summary", [(None, V.summary_facts(chart["time"], chart["series"], chart["intraday"]))], subtitle=chart.get("subtitle"))
            if summary:
                kept.insert(0, summary)
    facts = [v for v in kept if v["kind"] == "facts"]
    if len(facts) > 1:
        for view in facts:
            if view["id"].endswith("-facts"):
                view["title"] = "Details"
    seen: dict[str, int] = {}
    for view in kept:
        count = seen.get(view["id"], 0)
        seen[view["id"]] = count + 1
        if count:
            view["id"] = f"{view['id']}-{count + 1}"
        if view["kind"] == "series" and view.get("truncated"):
            notes.append(f"{view['title']}: showing the most recent {len(view['time']):,} of {view['total_points']:,} points.")
        if view["kind"] == "table" and view.get("truncated"):
            notes.append(f"{view['title']}: showing the first {len(view['rows']):,} of {view['total_rows']:,} rows.")
        if view["kind"] == "feed" and view.get("truncated"):
            notes.append(f"{view['title']}: showing {len(view['items'])} of {view['total_items']} articles.")
        if view["kind"] == "text" and view.get("truncated"):
            notes.append(f"{view['title']}: showing {len(view['blocks'])} of {view['total_blocks']} blocks.")
    return kept, notes
