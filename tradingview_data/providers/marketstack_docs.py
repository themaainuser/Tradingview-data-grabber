"""Builds the Marketstack endpoint catalog from its published OpenAPI document.

``python -m tradingview_data.providers.marketstack_docs`` downloads the OpenAPI spec behind
https://docs.apilayer.com/marketstack/docs/marketstack-api-v2-v-2-0-0 and the commodity list it links
to, and rewrites ``marketstack_catalog.json`` next to this file. The catalog is committed so the app
never fetches documentation at runtime; rerun this when Marketstack adds or changes endpoints.

The spec says nothing about which subscription plan an endpoint needs, so that comes from the
plan table on https://marketstack.com/pricing and is kept in :data:`OPERATIONS` below. The API
itself is the authority: a key whose plan lacks an endpoint is refused and the app reports it as
premium. Only the standard library (and ``requests``) is used.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path
from typing import Any, Optional

import requests

SPEC_URL = "https://api.swaggerhub.com/apis/apilayer-863/MarketstackAPIv2/2.0.0/swagger.json"
DOCS_URL = "https://docs.apilayer.com/marketstack/docs/marketstack-api-v2-v-2-0-0"
COMMODITIES_URL = "https://marketstack.com/download/marketstack-commodities.xlsx"
CATALOG_PATH = Path(__file__).with_name("marketstack_catalog.json")

PLANS = ("Free", "Basic", "Professional", "Business")

# path -> (endpoint id, cheapest plan that includes it). Plans follow the pricing page: Free has
# end-of-day data, splits and dividends, tickers, exchanges, currencies and timezones; Basic adds
# intraday (US, IEX), indices, bonds and ETF holdings; Professional adds real-time prices and
# commodities; Business adds company ratings, company details and the SEC EDGAR endpoints.
OPERATIONS: dict[str, tuple[str, str]] = {
    "/v2/exchanges": ("exchanges", "Free"),
    "/v2/exchanges/{mic}": ("exchange", "Free"),
    "/v2/exchanges/{mic}/eod": ("exchange_eod", "Free"),
    "/v2/exchanges/{mic}/eod/latest": ("exchange_eod_latest", "Free"),
    "/v2/exchanges/{mic}/eod/{date}": ("exchange_eod_date", "Free"),
    "/v2/exchanges/{mic}/intraday": ("exchange_intraday", "Basic"),
    "/v2/exchanges/{mic}/intraday/latest": ("exchange_intraday_latest", "Basic"),
    "/v2/exchanges/{mic}/intraday/{date}": ("exchange_intraday_date", "Basic"),
    "/v2/exchanges/{mic}/tickers": ("exchange_tickers", "Free"),
    "/v2/tickers/{symbol}": ("ticker", "Free"),
    "/v2/tickers/{symbol}/eod": ("ticker_eod", "Free"),
    "/v2/tickers/{symbol}/eod/latest": ("ticker_eod_latest", "Free"),
    "/v2/tickers/{symbol}/eod/{date}": ("ticker_eod_date", "Free"),
    "/v2/tickers/{symbol}/intraday": ("ticker_intraday", "Basic"),
    "/v2/tickers/{symbol}/intraday/latest": ("ticker_intraday_latest", "Basic"),
    "/v2/tickers/{symbol}/intraday/{date}": ("ticker_intraday_date", "Basic"),
    "/v2/tickers/{symbol}/splits": ("ticker_splits", "Free"),
    "/v2/tickers/{symbol}/dividends": ("ticker_dividends", "Free"),
    "/v2/eod": ("eod", "Free"),
    "/v2/eod/latest": ("eod_latest", "Free"),
    "/v2/eod/{date}": ("eod_date", "Free"),
    "/v2/intraday": ("intraday", "Basic"),
    "/v2/intraday/latest": ("intraday_latest", "Basic"),
    "/v2/intraday/{date}": ("intraday_date", "Basic"),
    "/v2/timezones": ("timezones", "Free"),
    "/v2/currencies": ("currencies", "Free"),
    "/v2/splits": ("splits", "Free"),
    "/v2/dividends": ("dividends", "Free"),
    "/v2/tickerslist": ("tickerslist", "Free"),
    "/v2/tickerinfo": ("tickerinfo", "Business"),
    "/v2/companyratings": ("companyratings", "Business"),
    "/v2/indexlist": ("indexlist", "Basic"),
    "/v2/indexinfo": ("indexinfo", "Basic"),
    "/v2/bondlist": ("bondlist", "Basic"),
    "/v2/bond": ("bond", "Basic"),
    "/v2/etflist": ("etflist", "Basic"),
    "/v2/etfholdings": ("etfholdings", "Basic"),
    "/v2/stockprice": ("stockprice", "Professional"),
    "/v2/commodities": ("commodities", "Professional"),
    "/v2/commoditieshistory": ("commoditieshistory", "Professional"),
    "/v2/company_name": ("company_name", "Business"),
    "/v2/cik_code": ("cik_code", "Business"),
    "/v2/company_facts": ("company_facts", "Business"),
    "/v2/concept/accounts_payable": ("concept_accounts_payable", "Business"),
    "/v2/submissions": ("submissions", "Business"),
    "/v2/frames/accounts_payable/{unit}": ("frames_accounts_payable", "Business"),
}

INTRADAY_NOTE = "Covers US tickers listed on IEX. The bid, ask and last fields are null in the response: IEX now requires a market data agreement for them."
ETF_NOTE = "ETF endpoints count as 20 requests against your monthly quota."
RATE_NOTE = "Limited to 1 request per minute, on every plan."
HISTORY_NOTE = "How far back you can go depends on the plan: Free 1 year, Basic 10 years, Professional and Business 15+ years. Older dates need a paid plan."
INTERVAL_NOTE = "Intervals below 15min (1min, 5min, 10min) are real-time updates and need the Professional plan or higher."
_FAST_INTERVALS = ["1min", "5min", "10min"]

_PREMIUM_NOTES = {
    **{id_: [INTRADAY_NOTE] for _, (id_, plan) in OPERATIONS.items() if "intraday" in id_},
    "etflist": [ETF_NOTE],
    "etfholdings": [ETF_NOTE],
    "companyratings": [RATE_NOTE],
    "commodities": [RATE_NOTE],
    "commoditieshistory": [RATE_NOTE],
}
_REQUEST_COST = {"etflist": 20, "etfholdings": 20}

# A value that makes the form open on a request that is known to make sense; only for parameters
# whose example the documentation itself shows.
_PARAM_EXAMPLES = {
    "symbols": "AAPL",
    "symbol": "AAPL",
    "ticker": "AAPL",
    "mic": "XNAS",
    "exchange": "XNAS",
    "commodity_name": "aluminum",
    "company_name": "NVIDIA",
    "cik_code": "0001045810",
    "frame": "CY2023Q1I",
    "unit": "USD",
}
_UTILITY_TAGS = {"Reference Data"}


def clean_text(text: str) -> str:
    """Plain text for a spec description: markdown links and emphasis removed, whitespace collapsed."""

    text = re.sub(r"\[\s*([^\]]*?)\s*\]\((?:https?://[^)]*)\)\*?", r"\1", text)
    text = text.replace("`", "")
    text = re.sub(r"\*+", " ", text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+([.,;:])", r"\1", text)
    return text.strip()


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _resolve(spec: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    ref = item.get("$ref")
    if not ref:
        return item
    node: Any = spec
    for part in ref.lstrip("#/").split("/"):
        node = node[part]
    return node


def _param_type(spec_param: dict[str, Any]) -> str:
    schema = spec_param.get("schema", {})
    if schema.get("enum"):
        return "enum"
    kind = schema.get("type")
    if kind == "integer":
        return "integer"
    if kind == "number":
        return "number"
    if kind == "boolean":
        return "boolean"
    if schema.get("format") == "date" or "YYYY-MM-DD" in spec_param.get("description", ""):
        return "date"
    return "text"


def _enum(schema: dict[str, Any]) -> list[str]:
    seen: dict[str, str] = {}
    for value in schema.get("enum", []):
        seen.setdefault(str(value).upper(), str(value))
    return list(seen.values())


def commodity_names(xlsx: Path) -> list[str]:
    """Names in column A of the commodity workbook Marketstack links to (first sheet, header skipped)."""

    with zipfile.ZipFile(xlsx) as book:
        shared = [re.sub(r"<[^>]+>", "", m) for m in re.findall(r"<si>(.*?)</si>", book.read("xl/sharedStrings.xml").decode("utf-8"), re.S)]
        sheet = book.read("xl/worksheets/sheet1.xml").decode("utf-8")
    names = []
    for index in re.findall(r'<c r="A\d+"[^>]*t="s"[^>]*><v>(\d+)</v>', sheet):
        name = shared[int(index)].strip()
        if name and name != "commodity_name":
            names.append(name)
    return names


def _param(spec: dict[str, Any], raw: dict[str, Any], endpoint_id: str, commodities: list[str]) -> dict[str, Any]:
    p = _resolve(spec, raw)
    schema = p.get("schema", {})
    name = p["name"]
    description = clean_text(p.get("description", ""))
    kind = _param_type(p)
    param: dict[str, Any] = {
        "name": name,
        "in": p["in"],
        "required": bool(p.get("required")),
        "type": kind,
        "description": description,
        "enum": _enum(schema) if kind == "enum" else [],
        "enum_labels": {},
        "suggestions": [],
        "default": str(schema["default"]) if "default" in schema else None,
        "example": _PARAM_EXAMPLES.get(name),
        "multiple": False,
        "premium_note": None,
        "premium_values": [],
        "minimum": schema.get("minimum"),
        "maximum": schema.get("maximum"),
    }
    if name == "interval":
        param["premium_values"] = [v for v in _FAST_INTERVALS if v in param["enum"]]
        param["premium_note"] = INTERVAL_NOTE
    if "eod" in endpoint_id and (name == "date_from" or (name == "date" and p["in"] == "path")):
        param["premium_note"] = HISTORY_NOTE
    if name == "commodity_name":
        param["suggestions"] = commodities
    if name == "frequency":
        match = re.search(r"Accepted values include:\s*([^.]+)\.", description)
        param["suggestions"] = [v.strip() for v in match.group(1).split(",")] if match else []
    return param


def _examples(params: list[dict[str, Any]]) -> list[dict[str, Any]]:
    known = {p["name"]: p["example"] for p in params if p["required"] and p["example"]}
    if not known:
        return []
    label = ", ".join(f"{k}={v}" for k, v in known.items())
    examples = [{"caption": f"Required parameters only: {label}", "params": dict(known)}]
    if any(p["name"] == "limit" for p in params):
        examples.append({"caption": f"The same with a limit of 10 rows: {label}", "params": {**known, "limit": "10"}})
    return examples


def build_catalog(spec: dict[str, Any], commodities: Optional[list[str]] = None) -> dict[str, Any]:
    warnings: list[str] = []
    commodities = commodities or []
    tags = spec.get("tags", [])
    categories = [{"id": _slug(t["name"]), "title": t["name"], "summary": clean_text(t.get("description", ""))} for t in tags]
    by_tag = {t["name"]: _slug(t["name"]) for t in tags}
    endpoints = []
    for path, methods in spec["paths"].items():
        if path not in OPERATIONS:
            warnings.append(f"{path} is in the spec but has no entry in OPERATIONS (skipped)")
            continue
        endpoint_id, plan = OPERATIONS[path]
        op = methods["get"]
        tag = op["tags"][0]
        params = [_param(spec, p, endpoint_id, commodities) for p in op["parameters"]]
        params = [p for p in params if p["name"] != "access_key"]
        params.sort(key=lambda p: p["in"] != "path")  # stable: path parameters first, as in the URL
        endpoints.append(
            {
                "id": endpoint_id,
                "path": path,
                "title": op["summary"],
                "category": by_tag[tag],
                "description": clean_text(op["description"]),
                "plan": plan,
                "premium": plan != PLANS[0],
                "trending": False,
                "utility": tag in _UTILITY_TAGS,
                "premium_notes": _PREMIUM_NOTES.get(endpoint_id, []),
                "request_cost": _REQUEST_COST.get(endpoint_id, 1),
                "params": params,
                "examples": _examples(params),
            }
        )
    for path in OPERATIONS:
        if path not in spec["paths"]:
            warnings.append(f"{path} is in OPERATIONS but no longer in the spec")
    order = {p: i for i, p in enumerate(OPERATIONS)}
    endpoints.sort(key=lambda e: order[e["path"]])
    return {"provider": "marketstack", "source": DOCS_URL, "spec": SPEC_URL, "plans": list(PLANS), "categories": categories, "endpoints": endpoints, "warnings": warnings}


def _download(url: str, timeout: tuple[int, int] = (5, 30)) -> requests.Response:
    response = requests.get(url, timeout=timeout, headers={"User-Agent": "tradingview-data-grabber catalog builder"})
    response.raise_for_status()
    return response


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Regenerate the Marketstack endpoint catalog from its OpenAPI document.")
    parser.add_argument("--output", type=Path, default=CATALOG_PATH)
    parser.add_argument("--spec", type=Path, help="read a saved copy of the OpenAPI document instead of downloading it")
    parser.add_argument("--commodities", type=Path, help="read a saved copy of the commodity workbook instead of downloading it")
    args = parser.parse_args(argv)
    spec = json.loads(args.spec.read_text(encoding="utf-8")) if args.spec else _download(SPEC_URL).json()
    names: list[str] = []
    try:
        if args.commodities:
            names = commodity_names(args.commodities)
        else:
            workbook = args.output.with_suffix(".xlsx.tmp")
            workbook.write_bytes(_download(COMMODITIES_URL).content)
            try:
                names = commodity_names(workbook)
            finally:
                workbook.unlink(missing_ok=True)
    except (requests.RequestException, zipfile.BadZipFile, KeyError, OSError) as exc:
        print(f"warning: no commodity names ({exc})", file=sys.stderr)
    catalog = build_catalog(spec, names)
    args.output.write_text(json.dumps(catalog, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    premium = sum(1 for e in catalog["endpoints"] if e["premium"])
    print(f"{len(catalog['endpoints'])} endpoints ({premium} premium), {len(names)} commodity names -> {args.output}")
    for warning in catalog["warnings"]:
        print("warning:", warning, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
