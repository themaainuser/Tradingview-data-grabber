"""Builds the Finnhub endpoint catalog from its published OpenAPI (Swagger 2.0) document.

``python -m tradingview_data.providers.finnhub_docs`` downloads https://finnhub.io/static/swagger.json, the spec
behind https://finnhub.io/docs/api/, and rewrites ``finnhub_catalog.json`` next to this file. The catalog is committed
so the app never fetches documentation at runtime; rerun this when Finnhub adds or changes endpoints.

Unlike the other providers' specs, Finnhub's says which plan each endpoint needs: ``premium`` is empty on the free
plan's endpoints and otherwise names the subscription. Calling every GET endpoint with a free key (November 2026)
matched it exactly: the 29 endpoints without a ``premium`` mark answered, every other one was refused. The paid tier
comes from Finnhub's pricing table, which has two columns, Free and All-in-One; the exceptions are in
:data:`NOT_ALL_IN_ONE`.

Not covered: the three POST endpoints (AI Copilot, Global Filings Search and Search In Filing), because a provider
query here is one GET, and the websocket, which is not in the spec. Only the standard library (and ``requests``) is
used.
"""

from __future__ import annotations

import argparse
import html
import json
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qsl, urlsplit

import requests

SPEC_URL = "https://finnhub.io/static/swagger.json"
DOCS_URL = "https://finnhub.io/docs/api/"
CATALOG_PATH = Path(__file__).with_name("finnhub_catalog.json")
PLANS = ("Free", "All-in-One")

# Date placeholders, filled in when the catalog is served (``fill_dates``) so an example never ages out of a window.
DAY, WEEK_AGO, WEEK_AHEAD = "@day", "@week_ago", "@week_ahead"

CATEGORY_SUMMARIES = {
    "Stock Fundamentals": "Symbol search and lists, market status, company profiles, news, peers, basic financials, ownership, insider trades, statements and SEC filings.",
    "Stock Estimates": "Analyst recommendation trends, price targets, upgrades and downgrades, estimates, EPS surprises and the earnings calendar.",
    "Stock Price": "Real-time quotes, candles, tick data, bid and ask, splits and dividends.",
    "ETFs & Indices": "Index constituents and ETF profiles, holdings and exposures.",
    "Mutual Funds": "Mutual fund profiles, holdings, exposures and EU ESG templates.",
    "Bonds": "Bond profiles, prices, TRACE ticks and yield curves.",
    "Forex": "Forex exchanges, symbols, candles and rates.",
    "Crypto": "Crypto exchanges, symbols, profiles and candles.",
    "Technical Analysis": "Pattern recognition, support and resistance levels, aggregate signals and technical indicators.",
    "Alternative Data": "Transcripts, social sentiment, supply chain, ESG, patents, H-1B visas, lobbying, government spending, congressional trades and more.",
    "Enterprise data": "Revenue breakdowns with KPIs and company newsrooms, sold separately from Finnhub's plans.",
    "Global Filings Search": "Filings from around the world: international filings, search filters and document downloads.",
    "Economic": "Country metadata, the economic calendar and economic time series.",
}

# Premium endpoints that the All-in-One plan does not include, with why. The pricing table's footnote says All-in-One
# does not include earnings call transcripts; the rest are separate products.
NOT_ALL_IN_ONE = {
    "/stock/transcripts/list": "Finnhub's pricing page says the All-in-One plan does not include earnings call transcripts; they are added on request.",
    "/stock/transcripts": "Finnhub's pricing page says the All-in-One plan does not include earnings call transcripts; they are added on request.",
}
_SEPARATE_SECTIONS = {
    "Enterprise data": "Enterprise data, sold separately from Finnhub's plans.",
    "Global Filings Search": "Part of Finnhub's Filings Search API, a separate subscription.",
}

# Limits measured with a free key that the spec does not state, noted on the endpoint and beside the parameter.
FREE_NOTES: dict[str, dict[str, str]] = {
    "/company-news": {"from": "Free plan: about a year back. Finnhub returns at most about 250 articles per request, newest first, so a long range shows only its last days."},
    "/calendar/earnings": {
        "from": "Free plan: up to 30 days back. Finnhub returns at most 1,500 rows per request, so a long range is cut short.",
        "international": "International markets need a paid plan.",
    },
    "/stock/symbol": {"exchange": "Free plan: US only (other exchanges are refused)."},
    "/stock/market-status": {"exchange": "Free plan: US only."},
    "/stock/market-holiday": {"exchange": "Free plan: US only."},
}
US_ONLY_NOTE = "Free plan: US-listed symbols only; a symbol listed elsewhere (RY.TO, SAP.DE, VOD.L) is refused."
US_ONLY = {"/quote", "/stock/profile2", "/company-news", "/stock/earnings", "/stock/metric", "/stock/filings", "/stock/financials-reported", "/stock/recommendation", "/stock/peers", "/stock/insider-transactions", "/stock/insider-sentiment"}

# Free endpoints' examples whose dates would fall outside the free plan's window as they age: recent dates instead.
EXAMPLE_DATES = {
    "/company-news": {"from": WEEK_AGO, "to": DAY},
    "/calendar/earnings": {"from": DAY, "to": WEEK_AHEAD},
}

# Where the spec's ``required`` is wrong, from the parameter descriptions and live calls.
OPTIONAL = {
    ("/stock/insider-transactions", "symbol"),  # "Leave this param blank to get the latest transactions."
    ("/institutional/ownership", "cusip"),  # either symbol or CUSIP
}

_RESOLUTIONS = ("1", "5", "15", "30", "60", "D", "W", "M")
_RESOLUTION_LABELS = {"1": "1 minute", "5": "5 minutes", "15": "15 minutes", "30": "30 minutes", "60": "60 minutes", "D": "Daily", "W": "Weekly", "M": "Monthly"}
_ENUMS: dict[tuple[str, str], tuple[str, ...]] = {
    ("/news", "category"): ("general", "forex", "crypto", "merger"),
    ("/stock/peers", "grouping"): ("sector", "industry", "subIndustry"),
    ("/stock/metric", "metric"): ("all",),
    ("/stock/financials", "statement"): ("bs", "ic", "cf"),
    ("/bond/tick", "exchange"): ("trace",),
    ("/global-filings/filter", "field"): ("countries", "exchanges", "exhibits", "forms", "gics", "naics", "caps", "acts", "sort"),
}
_ENUM_LABELS = {("/stock/financials", "statement"): {"bs": "Balance sheet", "ic": "Income statement", "cf": "Cash flow"}}
_FREQUENCIES = ("annual", "quarterly", "ttm", "ytd")

TRENDING = {"quote", "company_news", "company_basic_financials", "recommendation_trends", "company_earnings", "earnings_calendar", "insider_transactions", "company_profile2"}
UTILITY = {"symbol_search", "stock_symbols", "market_status", "market_holiday", "forex_exchanges", "forex_symbols", "crypto_exchanges", "crypto_symbols", "country", "economic_code", "global_filings_search_filter"}

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def fill_dates(value: Any, today: date) -> Any:
    """``value`` (any nesting of lists, dicts and strings) with the date placeholders replaced for ``today`` (UTC)."""

    if isinstance(value, str):
        if "@" not in value:
            return value
        for token, moment in ((WEEK_AGO, today - timedelta(days=7)), (WEEK_AHEAD, today + timedelta(days=7)), (DAY, today)):
            value = value.replace(token, moment.isoformat())
        return value
    if isinstance(value, list):
        return [fill_dates(v, today) for v in value]
    if isinstance(value, dict):
        return {k: fill_dates(v, today) for k, v in value.items()}
    return value


def clean_html(text: str, limit: int = 900) -> str:
    """Plain text of a spec description: tags removed, entities decoded, whitespace collapsed, cut at a sentence."""

    text = re.sub(r"<(table|pre)\b.*?</\1>", " ", text or "", flags=re.S | re.I)  # tables of field names read as noise
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s+([.,;:)])", r"\1", text)
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = cut.rfind(". ")
    return cut[: end + 1] if end > limit // 3 else cut.rstrip() + "\u2026"


def endpoint_id(operation_id: str) -> str:
    return operation_id.replace("-", "_")


def plan_of(path: str, op: dict[str, Any]) -> Optional[str]:
    """``Free`` for an endpoint the spec does not mark premium, ``All-in-One`` for the rest, ``None`` when no plan
    in the pricing table includes it."""

    if not op.get("premium"):
        return PLANS[0]
    if path in NOT_ALL_IN_ONE or op.get("section") in _SEPARATE_SECTIONS or "case by case" in str(op["premium"]).lower():
        return None
    return PLANS[1]


def premium_notes(path: str, op: dict[str, Any]) -> list[str]:
    notes: list[str] = []
    premium = clean_html(str(op.get("premium") or ""))
    if premium and premium.rstrip(".").lower() not in ("premium", "premium access required", "premium required"):
        notes.append(premium if premium.endswith(".") else premium + ".")  # names a narrower package, or how access is granted
    if path in NOT_ALL_IN_ONE:
        notes.append(NOT_ALL_IN_ONE[path])
    elif op.get("premium") and op.get("section") in _SEPARATE_SECTIONS:
        notes.append(_SEPARATE_SECTIONS[op["section"]])
    if op.get("freeTier"):
        notes.append(f"Free plan: {clean_html(op['freeTier']).rstrip('.')}.")
    if path in US_ONLY:
        notes.append(US_ONLY_NOTE)
    return notes


def _example_query(text: str) -> dict[str, str]:
    """The query of one docs example such as ``/quote?symbol=AAPL`` (a doubled ``symbol=symbol=AAPL`` is repaired)."""

    return {k: v.rsplit("=", 1)[-1] for k, v in parse_qsl(urlsplit(text).query, keep_blank_values=False)}


def _param(path: str, raw: dict[str, Any], example: Optional[str]) -> Optional[dict[str, Any]]:
    name = raw["name"]
    if name == "indicator_fields":
        return None  # a placeholder for indicator-specific settings; ``timeperiod`` is added instead
    kind = {"integer": "integer", "number": "number", "boolean": "boolean"}.get(str(raw.get("type")), "text")
    if raw.get("format") == "date" or (kind == "text" and name in ("from", "to", "date") and example and _DATE.match(example)):
        kind = "date"
    description = clean_html(raw.get("description", ""), 400)
    enum: tuple[str, ...] = _ENUMS.get((path, name), ())
    labels = dict(_ENUM_LABELS.get((path, name), {}))
    if name == "resolution":
        enum, labels = _RESOLUTIONS, dict(_RESOLUTION_LABELS)
    elif name == "freq":
        enum = tuple(f for f in _FREQUENCIES if re.search(rf"\b{f}\b", description, re.I))
    elif name == "airline" and (match := re.search(r"Accepted values:\s*([\w,\s]+)", description)):
        enum = tuple(v.strip() for v in match.group(1).split(",") if v.strip())
    if kind == "integer" and name in ("from", "to") and "UNIX" not in description:
        description = f"{description} UNIX timestamp, in seconds.".strip()
    note = FREE_NOTES.get(path, {}).get(name)
    return {
        "name": name,
        "in": raw.get("in", "query"),
        "required": bool(raw.get("required")) and (path, name) not in OPTIONAL,
        "type": "enum" if enum else kind,
        "description": description,
        "enum": list(enum),
        "enum_labels": labels,
        "suggestions": ["US"] if name == "exchange" and path.startswith("/stock/") else [],
        "default": None,
        "example": example,
        "multiple": False,
        "premium_note": note,
        "premium_values": [],
        "minimum": 0 if kind == "integer" else None,
        "maximum": None,
    }


def _examples(path: str, op: dict[str, Any], params: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Finnhub's own examples, kept only when they fill every required parameter, so choosing one leaves Fetch usable."""

    names = {p["name"] for p in params}
    required = {p["name"] for p in params if p["required"]}
    examples, seen = [], []
    for item in op.get("examples") or []:
        values = {k: v for k, v in _example_query(str(item.get("text") or item.get("url") or "")).items() if k in names}
        values.update({k: v for k, v in EXAMPLE_DATES.get(path, {}).items() if k in names})
        if not required <= set(values) or values in seen:
            continue
        seen.append(values)
        caption = ", ".join(f"{k}={v}" for k, v in values.items())
        if path in US_ONLY and "." in values.get("symbol", ""):
            caption += " (not US-listed: a free key is refused)"
        examples.append({"caption": f"Finnhub's example: {caption}" if caption else "No parameters", "params": values})
    if not examples and not required:
        examples.append({"caption": "No parameters", "params": {}})
    return examples


def build_catalog(spec: dict[str, Any]) -> dict[str, Any]:
    warnings: list[str] = []
    order = {p: i for i, p in enumerate(spec.get("orders") or [])}
    paths = sorted(spec["paths"].items(), key=lambda item: order.get(item[0], len(order)))
    endpoints, sections = [], {}
    for path, methods in paths:
        op = methods.get("get")
        if op is None:
            warnings.append(f"{path} has no GET operation (skipped)")
            continue
        first = _example_query(str((op.get("examples") or [{}])[0].get("text") or ""))
        overrides = EXAMPLE_DATES.get(path, {})
        params = [p for p in (_param(path, raw, overrides.get(raw["name"]) or first.get(raw["name"])) for raw in op.get("parameters", [])) if p]
        if path == "/indicator":
            params.append({**_param(path, {"name": "timeperiod", "in": "query", "type": "integer", "description": "Period of the indicator, for example 14 (indicator-specific; see Finnhub's indicator list)."}, first.get("timeperiod")), "minimum": 1})  # type: ignore[dict-item]
        params.sort(key=lambda p: p["in"] != "path")
        section = op.get("section") or "Other"
        sections.setdefault(section, None)
        plan = plan_of(path, op)
        id_ = endpoint_id(op["operationId"])
        endpoints.append(
            {
                "id": id_,
                "path": path,
                "title": op.get("summary") or op.get("title") or path,
                "category": _slug(section),
                "description": clean_html(op.get("description", "")),
                "doc_url": DOCS_URL + str(op.get("urlId") or op["operationId"]),
                "plan": plan,
                "premium": plan != PLANS[0],
                "trending": id_ in TRENDING,
                "utility": id_ in UTILITY,
                "premium_notes": premium_notes(path, op),
                "request_cost": 1,
                "params": params,
                "examples": _examples(path, op, params),
            }
        )
    ids = [e["id"] for e in endpoints]
    for duplicate in sorted({i for i in ids if ids.count(i) > 1}):
        warnings.append(f"endpoint id {duplicate} is used more than once")
    for section in sections:
        if section not in CATEGORY_SUMMARIES:
            warnings.append(f"section {section!r} has no summary in CATEGORY_SUMMARIES")
    categories = [{"id": _slug(s), "title": s, "summary": CATEGORY_SUMMARIES.get(s, "")} for s in sections]
    return {"provider": "finnhub", "source": DOCS_URL, "spec": SPEC_URL, "plans": list(PLANS), "categories": categories, "endpoints": endpoints, "warnings": warnings}


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Regenerate the Finnhub endpoint catalog from its OpenAPI document.")
    parser.add_argument("--output", type=Path, default=CATALOG_PATH)
    parser.add_argument("--spec", type=Path, help="read a saved copy of the OpenAPI document instead of downloading it")
    args = parser.parse_args(argv)
    if args.spec:
        spec = json.loads(args.spec.read_text(encoding="utf-8"))
    else:
        response = requests.get(SPEC_URL, timeout=(5, 60), headers={"User-Agent": "tradingview-data-grabber catalog builder"})
        response.raise_for_status()
        spec = response.json()
    catalog = build_catalog(spec)
    args.output.write_text(json.dumps(catalog, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    premium = sum(1 for e in catalog["endpoints"] if e["premium"])
    print(f"{len(catalog['endpoints'])} endpoints ({premium} premium) -> {args.output}")
    for warning in catalog["warnings"]:
        print("warning:", warning)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
