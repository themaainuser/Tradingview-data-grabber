"""Builds the Alpaca Market Data endpoint catalog from its published OpenAPI definitions.

Alpaca's documentation (https://docs.alpaca.markets/us/docs/getting-started) embeds the OpenAPI
definition of one operation in every reference page, and lists the pages of its Market Data API in
https://docs.alpaca.markets/us/llms.txt. ``python -m tradingview_data.providers.alpaca_docs``
downloads those pages and rewrites ``alpaca_catalog.json`` next to this file. The catalog is
committed so the app never fetches documentation at runtime; rerun this when Alpaca adds or
changes endpoints.

The definitions say nothing about subscription tiers. Those come from the "Subscription Plans"
section of https://docs.alpaca.markets/us/docs/about-market-data-api and the Market Data FAQ, and
live in :data:`OPERATIONS` and :func:`apply_tiers` below. Alpaca has two plans for individuals,
Basic (free) and Algo Trader Plus; they differ in the feed (IEX against all US exchanges, indicative
against OPRA options), in how recent the data may be and in the rate limit, not in which endpoints
exist. So every endpoint starts at Basic, and what Algo Trader Plus adds is attached to the
parameter choices it unlocks. The API itself is the authority: a request the plan does not allow is
refused and the app reports it as ``premium_required``.

Two documented operations are left out because they cannot be shown as a request and its answer:
the logo image and the corporate-actions event stream (server-sent events). Only the standard
library (and ``requests``) is used.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Optional

import requests

DOCS_URL = "https://docs.alpaca.markets/us/docs/getting-started"
INDEX_URL = "https://docs.alpaca.markets/us/llms.txt"
SECTION = "## API Reference: Market Data API"
CATALOG_PATH = Path(__file__).with_name("alpaca_catalog.json")

PLANS = ("Basic", "Algo Trader Plus")
BASIC, PLUS = PLANS

CATEGORIES = [
    {"id": "stocks", "title": "Stocks", "summary": "Bars, quotes, trades, snapshots and auctions for US stocks and ETFs, plus the exchange and condition code tables."},
    {"id": "options", "title": "Options", "summary": "Bars, trades, quotes, snapshots and the option chain with greeks and implied volatility for US options."},
    {"id": "crypto", "title": "Crypto", "summary": "Bars, quotes, trades, snapshots and the order book for crypto pairs, served by Alpaca's own exchange."},
    {"id": "forex", "title": "Forex", "summary": "Latest and historical rates for currency pairs."},
    {"id": "fixed-income", "title": "Fixed income", "summary": "Latest prices and quotes for fixed income securities, looked up by ISIN."},
    {"id": "screener", "title": "Screener", "summary": "The most active stocks and the top market movers."},
    {"id": "news", "title": "News", "summary": "News articles for stocks and crypto, from Benzinga, back to 2015."},
    {"id": "corporate-actions", "title": "Corporate actions", "summary": "Splits, dividends, mergers, spin-offs, name changes and other corporate actions."},
]

# path -> (endpoint id, title, category, tier rule). The tier rule says which of Alpaca's documented
# plan differences apply: stock_latest (real-time stock feeds), stock_history, option_latest,
# option_history, or "" for none.
OPERATIONS: dict[str, tuple[str, str, str, str]] = {
    "/v2/stocks/bars": ("stock_bars", "Stock historical bars", "stocks", "stock_history"),
    "/v2/stocks/{symbol}/bars": ("stock_bars_single", "Stock historical bars (single symbol)", "stocks", "stock_history"),
    "/v2/stocks/bars/latest": ("stock_latest_bars", "Stock latest bars", "stocks", "stock_latest"),
    "/v2/stocks/{symbol}/bars/latest": ("stock_latest_bar_single", "Stock latest bar (single symbol)", "stocks", "stock_latest"),
    "/v2/stocks/quotes": ("stock_quotes", "Stock historical quotes", "stocks", "stock_history"),
    "/v2/stocks/{symbol}/quotes": ("stock_quotes_single", "Stock historical quotes (single symbol)", "stocks", "stock_history"),
    "/v2/stocks/quotes/latest": ("stock_latest_quotes", "Stock latest quotes", "stocks", "stock_latest"),
    "/v2/stocks/{symbol}/quotes/latest": ("stock_latest_quote_single", "Stock latest quote (single symbol)", "stocks", "stock_latest"),
    "/v2/stocks/trades": ("stock_trades", "Stock historical trades", "stocks", "stock_history"),
    "/v2/stocks/{symbol}/trades": ("stock_trades_single", "Stock historical trades (single symbol)", "stocks", "stock_history"),
    "/v2/stocks/trades/latest": ("stock_latest_trades", "Stock latest trades", "stocks", "stock_latest"),
    "/v2/stocks/{symbol}/trades/latest": ("stock_latest_trade_single", "Stock latest trade (single symbol)", "stocks", "stock_latest"),
    "/v2/stocks/snapshots": ("stock_snapshots", "Stock snapshots", "stocks", "stock_latest"),
    "/v2/stocks/{symbol}/snapshot": ("stock_snapshot_single", "Stock snapshot (single symbol)", "stocks", "stock_latest"),
    "/v2/stocks/auctions": ("stock_auctions", "Stock historical auctions", "stocks", "stock_history"),
    "/v2/stocks/{symbol}/auctions": ("stock_auctions_single", "Stock historical auctions (single symbol)", "stocks", "stock_history"),
    "/v2/stocks/meta/conditions/{ticktype}": ("stock_conditions", "Stock condition codes", "stocks", ""),
    "/v2/stocks/meta/exchanges": ("stock_exchanges", "Stock exchange codes", "stocks", ""),
    "/v1beta1/options/bars": ("option_bars", "Option historical bars", "options", "option_history"),
    "/v1beta1/options/trades": ("option_trades", "Option historical trades", "options", "option_history"),
    "/v1beta1/options/quotes/latest": ("option_latest_quotes", "Option latest quotes", "options", "option_latest"),
    "/v1beta1/options/trades/latest": ("option_latest_trades", "Option latest trades", "options", "option_latest"),
    "/v1beta1/options/snapshots": ("option_snapshots", "Option snapshots", "options", "option_latest"),
    "/v1beta1/options/snapshots/{underlying_symbol}": ("option_chain", "Option chain", "options", "option_latest"),
    "/v1beta1/options/meta/conditions/{ticktype}": ("option_conditions", "Option condition codes", "options", ""),
    "/v1beta1/options/meta/exchanges": ("option_exchanges", "Option exchange codes", "options", ""),
    "/v1beta3/crypto/{loc}/bars": ("crypto_bars", "Crypto historical bars", "crypto", ""),
    "/v1beta3/crypto/{loc}/quotes": ("crypto_quotes", "Crypto historical quotes", "crypto", ""),
    "/v1beta3/crypto/{loc}/trades": ("crypto_trades", "Crypto historical trades", "crypto", ""),
    "/v1beta3/crypto/{loc}/latest/bars": ("crypto_latest_bars", "Crypto latest bars", "crypto", ""),
    "/v1beta3/crypto/{loc}/latest/quotes": ("crypto_latest_quotes", "Crypto latest quotes", "crypto", ""),
    "/v1beta3/crypto/{loc}/latest/trades": ("crypto_latest_trades", "Crypto latest trades", "crypto", ""),
    "/v1beta3/crypto/{loc}/latest/orderbooks": ("crypto_orderbooks", "Crypto latest order book", "crypto", ""),
    "/v1beta3/crypto/{loc}/snapshots": ("crypto_snapshots", "Crypto snapshots", "crypto", ""),
    "/v1beta1/forex/latest/rates": ("forex_latest_rates", "Forex latest rates", "forex", ""),
    "/v1beta1/forex/rates": ("forex_rates", "Forex historical rates", "forex", ""),
    "/v1beta1/fixed_income/latest/prices": ("fixed_income_prices", "Fixed income latest prices", "fixed-income", ""),
    "/v1beta1/fixed_income/latest/quotes": ("fixed_income_quotes", "Fixed income latest quotes", "fixed-income", ""),
    "/v1beta1/screener/stocks/most-actives": ("most_actives", "Most active stocks", "screener", ""),
    "/v1beta1/screener/{market_type}/movers": ("movers", "Top market movers", "screener", ""),
    "/v1beta1/news": ("news", "News articles", "news", ""),
    "/v1/corporate-actions": ("corporate_actions", "Corporate actions", "corporate-actions", ""),
}

SKIPPED = {
    "/v1beta1/logos/{symbol}": "It answers with a PNG image, which a request-and-view page cannot show.",
    "/v1beta1/events/corporate-actions": "It is a long-lived server-sent event stream, not a request with an answer. GET /v1/corporate-actions returns the same data.",
}

# --- what each plan allows, from the "Subscription Plans" section and the Market Data FAQ ----------

HISTORY_END_NOTE = "On Basic, SIP data must be at least 15 minutes old, so leave end blank (it then defaults to 15 minutes ago) or choose an earlier time. Algo Trader Plus has no such limit."
LATEST_FEED_NOTE = "The SIP feed (all US exchanges) on the latest endpoints and snapshots needs Algo Trader Plus; Basic gets IEX only. Leave feed blank and Alpaca uses the best feed your plan allows."
HISTORY_FEED_NOTE = "On Basic, the SIP feed only returns data at least 15 minutes old; IEX has no such limit. Algo Trader Plus can read SIP data up to the present."
OPTION_FEED_NOTE = "The real-time OPRA feed needs Algo Trader Plus. Basic gets the indicative feed, where quotes are modified and trades are delayed by 15 minutes. Leave feed blank and Alpaca uses the best feed your plan allows."
OTC_NOTE = "OTC data needs a special subscription that Alpaca offers only to Broker API partners."

_TIER_NOTES = {
    "stock_latest": [f"{BASIC} gets the IEX feed. {PLUS} adds the SIP feed with every US exchange."],
    "stock_history": [f"{BASIC} reads SIP data once it is 15 minutes old, or IEX data right away, at 200 calls a minute. {PLUS} has no 15-minute limit and 10,000 calls a minute."],
    "option_latest": [f"{BASIC} gets the indicative feed. {PLUS} adds the real-time OPRA feed."],
    "option_history": [f"{BASIC} reads data once it is 15 minutes old, at 200 calls a minute. {PLUS} has no 15-minute limit and 10,000 calls a minute."],
}

_STOCK_FEEDS = {
    "iex": f"IEX · {BASIC}",
    "sip": "SIP, all US exchanges",
    "delayed_sip": "SIP, 15 minutes delayed",
    "boats": "BOATS, Blue Ocean overnight",
    "overnight": "Overnight, derived from BOATS",
    "otc": "OTC · Broker API partners only",
}
_OPTION_FEEDS = {"opra": f"OPRA, real time · {PLUS}", "indicative": f"Indicative · {BASIC}"}

BAR_TIMEFRAMES = ["1Min", "5Min", "15Min", "30Min", "1Hour", "4Hour", "1Day", "1Week", "1Month"]
FOREX_TIMEFRAMES = ["5Sec", "1Min", "1Day"]

# Values the page opens a form with, only where the documentation shows an example (or the tier
# the example is for does not matter); everything else is left for the user.
_PARAM_EXAMPLES = {
    "symbol": "AAPL",
    "underlying_symbol": "AAPL",
    "loc": "us",
    "ticktype": "trade",
    "tape": "A",
    "market_type": "stocks",
    "timeframe": "1Day",
    "currency_pairs": "USDJPY",
}
# Contracts and bonds in the documentation's examples have expired, so an example built on them would
# only return nothing. These endpoints offer no ready-made example; the placeholder still shows the format.
_NO_PRESETS = {"option_bars", "option_trades", "option_latest_quotes", "option_latest_trades", "option_snapshots", "fixed_income_prices", "fixed_income_quotes"}
_UTILITY = {"stock_conditions", "stock_exchanges", "option_conditions", "option_exchanges"}

# The examples need a recent trading day, and a day written into the committed catalog would age out.
# The catalog holds these placeholders and the provider fills them in when it serves the catalog.
SAMPLE_DAY = "@sample_day"
SAMPLE_START = "@sample_start"


def sample_day(today: date) -> str:
    """The latest weekday before ``today``: a day the exchanges were normally open."""

    day = today - timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day.isoformat()


def sample_start(today: date) -> str:
    """A month before :func:`sample_day`: enough daily bars to draw a chart."""

    return (date.fromisoformat(sample_day(today)) - timedelta(days=30)).isoformat()


def fill_samples(value: Any, today: date) -> Any:
    """``value`` (any nesting of lists, dicts and strings) with the sample placeholders replaced."""

    if isinstance(value, str):
        return value.replace(SAMPLE_DAY, sample_day(today)).replace(SAMPLE_START, sample_start(today))
    if isinstance(value, list):
        return [fill_samples(v, today) for v in value]
    if isinstance(value, dict):
        return {k: fill_samples(v, today) for k, v in value.items()}
    return value


# --- reading the definitions --------------------------------------------------------------------


def clean_text(text: str) -> str:
    """Plain text for a description: markdown links, quotes and emphasis removed, whitespace collapsed."""

    text = re.sub(r"(?m)^\s*>\s?", "", text)
    text = re.sub(r"\[\s*([^\]]*?)\s*\]\((?:https?://[^)]*|#[^)]*)\)", r"\1", text)
    text = text.replace("`", "")
    text = re.sub(r"\*+", " ", text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+([.,;:])", r"\1", text)
    return text.strip()


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _resolve(spec: dict[str, Any], node: Any, depth: int = 0) -> Any:
    """``node`` with ``$ref`` followed and ``allOf`` merged (later entries win), shallowly."""

    if not isinstance(node, dict) or depth > 8:
        return node
    if "$ref" in node:
        target: Any = spec
        for part in node["$ref"].lstrip("#/").split("/"):
            target = target[part]
        return _resolve(spec, target, depth + 1)
    if "allOf" in node:
        merged: dict[str, Any] = {}
        for part in node["allOf"]:
            merged.update(_resolve(spec, part, depth + 1))
        merged.update({k: v for k, v in node.items() if k != "allOf"})
        return merged
    return node


def _bullet_labels(raw: str, values: list[str]) -> dict[str, str]:
    """Short labels from a description's ``- value: meaning`` bullets (the value may be in backticks), for the values the parameter accepts."""

    labels = {}
    for value, meaning in re.findall(r"(?m)^\s*-\s*`?([\w.\-]+)`?\s*:\s*(.+?)\s*$", raw):
        text = clean_text(meaning).rstrip(".")
        if value in values and 0 < len(text) <= 48:
            labels[value] = text
    return labels


def _param_type(schema: dict[str, Any]) -> str:
    if schema.get("enum"):
        return "enum"
    kind = schema.get("type")
    if kind in ("integer", "number", "boolean"):
        return kind
    if schema.get("format") == "date":
        return "date"
    if schema.get("format") == "date-time":
        return "datetime"
    return "text"


def _param(spec: dict[str, Any], raw: dict[str, Any], endpoint_id: str, tier: str) -> dict[str, Any]:
    p = _resolve(spec, raw)
    schema = _resolve(spec, p.get("schema", {}))
    name = p["name"]
    kind = _param_type(schema)
    example = p.get("example", schema.get("example"))
    raw_description = p.get("description") or schema.get("description") or ""
    description = clean_text(raw_description)
    param: dict[str, Any] = {
        "name": name,
        "in": p["in"],
        "required": bool(p.get("required")),
        "type": kind,
        "description": description,
        "enum": [str(v) for v in schema.get("enum", [])] if kind == "enum" else [],
        "enum_labels": {},
        "suggestions": [],
        "default": None if schema.get("default") is None else (str(schema["default"]).lower() if isinstance(schema["default"], bool) else str(schema["default"])),
        "example": _PARAM_EXAMPLES.get(name, example if isinstance(example, (str, int, float)) else None),
        "multiple": False,
        "premium_note": None,
        "premium_values": [],
        "minimum": schema.get("minimum"),
        "maximum": schema.get("maximum"),
    }
    if param["example"] is not None:
        param["example"] = str(param["example"])
    param["enum_labels"] = _bullet_labels(f"{raw_description}\n{schema.get('description') or ''}", param["enum"])
    if param["enum_labels"] and re.search(r"(?m)^\s*-\s", raw_description):
        param["description"] = clean_text(re.split(r"(?m)^\s*-\s", raw_description, maxsplit=1)[0])
    if name == "timeframe":
        param["suggestions"] = FOREX_TIMEFRAMES if endpoint_id == "forex_rates" else BAR_TIMEFRAMES
    if name == "types":
        param["suggestions"] = _corporate_action_types(spec)
    apply_tiers(param, tier)
    return param


def _corporate_action_types(spec: dict[str, Any]) -> list[str]:
    """The corporate action types the response schema lists (``forward_splits`` -> ``forward_split``)."""

    schema = _resolve(spec, spec.get("components", {}).get("schemas", {}).get("corporate_actions", {}))
    return [name[:-1] if name.endswith("s") else name for name in schema.get("properties", {})]


def apply_tiers(param: dict[str, Any], tier: str) -> None:
    """Label a parameter with what each plan gets, in place. ``tier`` is the endpoint's tier rule."""

    name = param["name"]
    if name == "feed" and tier in ("stock_latest", "stock_history"):
        latest = tier == "stock_latest"
        values = [v for v in _STOCK_FEEDS if v in param["enum"]] + [v for v in param["enum"] if v not in _STOCK_FEEDS] or list(_STOCK_FEEDS)
        param["type"], param["enum"] = "enum", values
        param["enum_labels"] = {v: _STOCK_FEEDS[v] for v in values if v in _STOCK_FEEDS}
        if latest and "sip" in values:
            param["enum_labels"]["sip"] = f"SIP, all US exchanges · {PLUS}"
        param["premium_values"] = [v for v in (["sip", "otc"] if latest else ["otc"]) if v in values]
        param["premium_note"] = f"{LATEST_FEED_NOTE if latest else HISTORY_FEED_NOTE} {OTC_NOTE}"
        param["description"] = "The source feed of the data. " + ("Without one, Alpaca uses SIP with Algo Trader Plus and IEX on Basic." if latest else "The default is sip.")
        param["default"] = None if latest else param["default"]
    elif name == "feed" and tier == "option_latest":
        values = param["enum"] or list(_OPTION_FEEDS)
        param["type"], param["enum"] = "enum", values
        param["enum_labels"] = {v: _OPTION_FEEDS[v] for v in values if v in _OPTION_FEEDS}
        param["premium_values"] = [v for v in ("opra",) if v in values]
        param["premium_note"] = OPTION_FEED_NOTE
        param["description"] = "The source feed of the data. Without one, Alpaca uses OPRA with Algo Trader Plus and the indicative feed on Basic."
        param["default"] = None
    elif name == "end" and tier in ("stock_history", "option_history"):
        param["premium_note"] = HISTORY_END_NOTE


def _examples(endpoint_id: str, params: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Examples are complete requests: none is offered unless every required parameter has a value."""

    required = [p for p in params if p["required"]]
    if endpoint_id in _NO_PRESETS or not required or any(not p["example"] for p in required):
        return []
    names = {p["name"] for p in params}
    known = {p["name"]: p["example"] for p in required}
    if "symbols" in known and endpoint_id.startswith(("stock", "crypto")):
        known["symbols"] = known["symbols"].split(",")[0]
    label = ", ".join(f"{k}={v}" for k, v in known.items())
    examples = [{"caption": f"Required parameters only: {label}", "params": dict(known)}]
    if "timeframe" in known and "start" in names:
        full = {**known, "start": SAMPLE_START, "end": SAMPLE_DAY}
        examples.insert(0, {"caption": f"{known['timeframe']} bars for the last month", "params": full})
    elif "limit" in names and "start" in names and endpoint_id != "forex_rates":
        examples.insert(0, {"caption": f"The first 10 rows from {SAMPLE_DAY}", "params": {**known, "start": SAMPLE_DAY, "limit": "10"}})
    elif "limit" in names:
        examples.append({"caption": f"The same with a limit of 10 rows: {label}", "params": {**known, "limit": "10"}})
    return examples


def build_catalog(pages: list[tuple[str, dict[str, Any]]]) -> dict[str, Any]:
    """The catalog from ``(reference page URL, OpenAPI definition)`` pairs, in :data:`OPERATIONS` order."""

    warnings: list[str] = []
    found: dict[str, dict[str, Any]] = {}
    for url, spec in pages:
        for path, methods in spec.get("paths", {}).items():
            op = methods.get("get")
            if path in SKIPPED or op is None:
                continue
            if path not in OPERATIONS:
                warnings.append(f"{path} is in the documentation but has no entry in OPERATIONS (skipped)")
                continue
            endpoint_id, title, category, tier = OPERATIONS[path]
            params = [_param(spec, raw, endpoint_id, tier) for raw in op.get("parameters", []) if _resolve(spec, raw).get("in") != "header"]
            params.sort(key=lambda p: p["in"] != "path")  # stable: path parameters first, as in the URL
            found[path] = {
                "id": endpoint_id,
                "path": path,
                "title": title,
                "category": category,
                "description": clean_text(op.get("description") or op.get("summary") or title),
                "plan": BASIC,
                "premium": False,
                "trending": False,
                "utility": endpoint_id in _UTILITY,
                "premium_notes": _TIER_NOTES.get(tier, []),
                "request_cost": 1,
                "tier_rule": tier,
                "doc_url": url.removesuffix(".md"),
                "params": params,
                "examples": _examples(endpoint_id, params),
            }
    for path in OPERATIONS:
        if path not in found:
            warnings.append(f"{path} is in OPERATIONS but no longer in the documentation")
    endpoints = [found[path] for path in OPERATIONS if path in found]
    return {
        "provider": "alpaca",
        "source": DOCS_URL,
        "index": INDEX_URL,
        "plans": list(PLANS),
        "categories": CATEGORIES,
        "endpoints": endpoints,
        "skipped": [{"path": path, "reason": reason} for path, reason in SKIPPED.items()],
        "warnings": warnings,
    }


# --- downloading ----------------------------------------------------------------------------------

_DEFINITION = re.compile(r"```json\s*\n(.*?)\n```", re.S)


def definition_of(markdown: str) -> Optional[dict[str, Any]]:
    """The OpenAPI definition embedded in a reference page, or ``None`` when the page has none."""

    match = _DEFINITION.search(markdown)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(1))
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) and "paths" in parsed else None


def reference_urls(index: str) -> list[str]:
    """The Market Data reference pages (``.md`` URLs) listed in ``llms.txt``."""

    urls: list[str] = []
    inside = False
    for line in index.splitlines():
        if line.startswith("## "):
            inside = line.strip() == SECTION
        elif inside:
            match = re.search(r"\((https://docs\.alpaca\.markets/us/reference/[^)\s]+\.md)\)", line)
            if match:
                urls.append(match.group(1))
    return urls


def _download(url: str, timeout: tuple[int, int] = (5, 30)) -> str:
    response = requests.get(url, timeout=timeout, headers={"User-Agent": "tradingview-data-grabber catalog builder"})
    response.raise_for_status()
    return response.text


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Regenerate the Alpaca Market Data endpoint catalog from its documentation.")
    parser.add_argument("--output", type=Path, default=CATALOG_PATH)
    parser.add_argument("--pages", type=Path, help="read saved copies of the reference pages (*.md) from this directory instead of downloading them")
    args = parser.parse_args(argv)
    pages: list[tuple[str, dict[str, Any]]] = []
    if args.pages:
        sources = [(f"https://docs.alpaca.markets/us/reference/{path.name}", path.read_text(encoding="utf-8")) for path in sorted(args.pages.glob("*.md"))]
    else:
        sources = [(url, _download(url)) for url in reference_urls(_download(INDEX_URL))]
    for url, markdown in sources:
        definition = definition_of(markdown)
        if definition is None:
            print(f"warning: no OpenAPI definition in {url}", file=sys.stderr)
        else:
            pages.append((url, definition))
    catalog = build_catalog(pages)
    args.output.write_text(json.dumps(catalog, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(catalog['endpoints'])} endpoints from {len(pages)} pages -> {args.output}")
    for warning in catalog["warnings"]:
        print("warning:", warning, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
