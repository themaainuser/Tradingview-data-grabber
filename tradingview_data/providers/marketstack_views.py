"""Marketstack response shapes -> views. Everything not special-cased goes through ``views.analyze``.

Marketstack answers most endpoints as ``{"pagination": {...}, "data": ...}``; a few (company ratings,
commodity history, ETF holdings, indices) use their own wrapper. Prices, dates and flags are
normalised here (ISO timestamps to UTC, booleans to Yes/No) so the views carry only drawable values.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from . import views as V

Built = tuple[list[Optional[dict[str, Any]]], list[str]]

MAX_CHARTS = 6
_GROUPED = re.compile(r"^-?\d{1,3}(,\d{3})+(\.\d+)?$")
_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?(?:\.\d+)?)?\s*(Z|[+-]\d{2}:?\d{2})?$")
_OHLCV = ("open", "high", "low", "close", "volume")
_EOD_KEYS = ["date", "symbol", "exchange", "open", "high", "low", "close", "volume", "adj_open", "adj_high", "adj_low", "adj_close", "adj_volume", "split_factor", "dividend", "price_currency", "asset_type", "name", "exchange_code"]
_INTRADAY_KEYS = ["date", "symbol", "exchange", "open", "high", "low", "close", "volume", "mid", "last", "last_size", "bid_price", "bid_size", "ask_price", "ask_size", "marketstack_last"]
_EXCHANGE_GROUPS = [
    ("Exchange", ["name", "acronym", "mic", "operating_mic", "oprt_sgmt", "market_category_code", "exchange_status"]),
    ("Location", ["country", "country_code", "city", "website"]),
    ("Legal", ["legal_entity_name", "exchange_lei"]),
    ("Dates", ["date_creation", "date_last_update", "date_last_validation", "date_expiry", "comments"]),
]


# --- small helpers --------------------------------------------------------------------------------


def moment(value: Any) -> Optional[tuple[int, bool]]:
    """``(UTC epoch seconds, has a time of day)`` of an ISO timestamp such as ``2026-09-29T15:30:00+0000``."""

    match = _ISO.match(str(value).strip()) if value is not None else None
    if not match:
        return None
    y, mo, d, h, mi, s, offset = match.groups()
    try:
        when = datetime(int(y), int(mo), int(d), int(h or 0), int(mi or 0), int(s or 0), tzinfo=timezone.utc)
    except ValueError:
        return None
    if offset and offset != "Z":
        sign = 1 if offset[0] == "+" else -1
        digits = offset[1:].replace(":", "")
        when -= sign * timedelta(hours=int(digits[:2]), minutes=int(digits[2:]))
    return int(when.timestamp()), bool(h) and (int(h), int(mi or 0), int(s or 0)) != (0, 0, 0)


def stamp(value: Any, with_time: bool) -> Optional[str]:
    """``2026-09-29`` or, with a time of day, ``2026-09-29 15:30:00`` (UTC)."""

    parsed = moment(value)
    if parsed is None:
        return None if value in (None, "") else str(value)
    when = datetime.fromtimestamp(parsed[0], tz=timezone.utc)
    return when.strftime("%Y-%m-%d %H:%M:%S" if with_time else "%Y-%m-%d")


def num(value: Any) -> Optional[float]:
    """A number from ``1,234.5`` or ``-0.52%`` style text as well as from numbers."""

    if isinstance(value, str):
        value = value.strip().replace(",", "").rstrip("%")
    return V.to_number(value)


def scalar(value: Any) -> Any:
    """Booleans as Yes/No, ``1,234.5`` as ``1234.5``, ``{"date": ...}`` objects as their date, short lists joined, other objects dropped."""

    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, str) and _GROUPED.match(value.strip()):
        return value.strip().replace(",", "")
    if isinstance(value, dict):
        return value.get("date") if isinstance(value.get("date"), str) else None
    if isinstance(value, list):
        return ", ".join(str(v) for v in value if not isinstance(v, (dict, list)))[:300] or None
    return value


def flat(record: dict[str, Any], keys: Optional[list[str]] = None, renames: Optional[dict[str, str]] = None) -> dict[str, Any]:
    out = {}
    for key in keys or list(record):
        out[(renames or {}).get(key, key)] = scalar(record.get(key))
    return out


def dicts(value: Any) -> list[dict[str, Any]]:
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def body(payload: Any) -> Any:
    """The ``data`` of a wrapped response, or the payload itself."""

    return payload.get("data", payload) if isinstance(payload, dict) else payload


def rows_of(data: Any, key: str) -> list[dict[str, Any]]:
    """The record list of a response whose rows may sit directly in ``data`` or under ``data[key]``."""

    if isinstance(data, list):
        return dicts(data)
    if isinstance(data, dict):
        if isinstance(data.get(key), list):
            return dicts(data[key])
        if "date" in data or "symbol" in data:
            return [data]
    return []


def meta_of(data: Any) -> dict[str, Any]:
    return {k: v for k, v in data.items() if not isinstance(v, list)} if isinstance(data, dict) else {}


def facts(view_id: str, title: str, source: Any, groups: list[tuple[Optional[str], list[str]]], subtitle: Optional[str] = None, labels: Optional[dict[str, str]] = None) -> Optional[dict[str, Any]]:
    """A facts view of the named keys of a mapping; missing or empty values are left out."""

    if not isinstance(source, dict):
        return None
    built = []
    for name, keys in groups:
        items = []
        for key in keys:
            value = scalar(source.get(key))
            if value is None or (isinstance(value, str) and not value.strip()):
                continue
            item = V.smart_fact(key, value)
            if labels and key in labels:
                item["label"] = labels[key]
            items.append(item)
        built.append((name, items))
    return V.facts_view(view_id, title, built, subtitle=subtitle)


def table(view_id: str, title: str, records: list[dict[str, Any]], keys: Optional[list[str]] = None, subtitle: Optional[str] = None) -> Optional[dict[str, Any]]:
    if keys:
        present = [k for k in keys if any(r.get(k) not in (None, "") for r in records)]
        keys = present or None
    return V.table_view(view_id, title, records, keys=keys, subtitle=subtitle)


# --- price bars ---------------------------------------------------------------------------------


def bar_views(prefix: str, label: str, rows: list[dict[str, Any]], intraday: bool) -> Built:
    """A chart per symbol (candles when open/high/low/close are present) and one table of every row."""

    if not rows:
        return [], []
    clock = intraday or any((moment(r.get("date")) or (0, False))[1] for r in rows[:500])
    records = [{**flat(r), "date": stamp(r.get("date"), clock)} for r in rows]
    groups: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        groups.setdefault(str(r.get("symbol") or "?"), []).append(r)
    keys = _INTRADAY_KEYS if intraday else _EOD_KEYS
    views: list[Optional[dict[str, Any]]] = []
    notes: list[str] = []
    for symbol, group in list(groups.items())[:MAX_CHARTS]:
        pairs = [(moment(r.get("date")), r) for r in group]
        pairs = [(m[0], r) for m, r in pairs if m]
        wanted = [k for k in keys if k not in ("date", "symbol", "exchange") and k in {*_OHLCV, "adj_close", "mid", "last"}]
        columns = []
        for key in wanted:
            values = [V.to_number(r.get(key)) for _, r in pairs]
            if any(v is not None for v in values):
                columns.append({"key": key, "label": V.humanize(key), "values": values, "role": key if key in _OHLCV else "value", "unit": None})
        first = group[0]
        subtitle = " · ".join(str(x) for x in (first.get("name"), first.get("exchange") or first.get("exchange_code"), first.get("price_currency")) if x) or None
        title = f"{symbol} {'intraday' if intraday else 'end of day'}"
        views.append(V.series_view(f"{prefix}-{V.slug(symbol)}-chart", title, [t for t, _ in pairs], columns, subtitle=subtitle, intraday=clock))
    if len(groups) > MAX_CHARTS:
        notes.append(f"Charts are drawn for the first {MAX_CHARTS} of {len(groups)} symbols; the table has every row.")
    if len(rows) == 1:
        views.append(facts(f"{prefix}-latest", f"{rows[0].get('symbol') or label} latest", records[0], [(None, [k for k in keys if k != "name"] + ["name"])]))
    if clock and all(r.get("bid_price") is None and r.get("ask_price") is None and r.get("last") is None for r in rows):
        notes.append("Bid, ask and last are null for every row: IEX requires a market data agreement for them, so Marketstack leaves them empty.")
    views.append(table(f"{prefix}-table", label, records, keys))
    return views, notes


def _bars_handler(key: str, intraday: bool, sub: str) -> Callable[[Any], Built]:
    def build(payload: Any) -> Built:
        data = body(payload)
        rows = rows_of(data, key)
        built, notes = bar_views(sub, "Rows", rows, intraday)
        if not rows:
            return [], notes
        meta = meta_of(data) if isinstance(data, dict) and key in data else {}
        if meta:
            built.insert(0, exchange_facts(f"{sub}-exchange", meta) if "mic" in meta else facts(f"{sub}-ticker", str(meta.get("name") or meta.get("symbol") or "Ticker"), meta, [(None, ["name", "symbol", "country", "has_eod", "has_intraday"])]))
        return built, notes

    return build


# --- reference data --------------------------------------------------------------------------------


def exchange_facts(view_id: str, exchange: dict[str, Any]) -> Optional[dict[str, Any]]:
    return facts(view_id, str(exchange.get("name") or "Exchange"), exchange, _EXCHANGE_GROUPS, subtitle=exchange.get("mic"))


def _exchanges(payload: Any) -> Built:
    data = body(payload)
    if isinstance(data, dict):
        return [exchange_facts("exchange", data)], []
    rows = dicts(data)
    if len(rows) == 1:
        return [exchange_facts("exchange", rows[0])], []
    keys = ["name", "acronym", "mic", "country", "country_code", "city", "website", "operating_mic", "exchange_status"]
    return [table("exchanges", "Stock exchanges", [flat(r) for r in rows], keys)], []


def _exchange_tickers(payload: Any) -> Built:
    data = body(payload)
    meta = meta_of(data)
    tickers = [flat(r) for r in dicts(data.get("tickers") if isinstance(data, dict) else data)]
    return [exchange_facts("exchange", meta) if meta.get("mic") else None, table("tickers", "Tickers", tickers, ["name", "symbol", "has_eod", "has_intraday"])], []


def _ticker(payload: Any) -> Built:
    data = body(payload)
    if isinstance(data, list):
        data = data[0] if data else {}
    exchange = data.get("stock_exchange") if isinstance(data, dict) else None
    views = [
        facts("ticker", str(data.get("name") or data.get("symbol") or "Ticker"), data, [("Identity", ["name", "symbol", "item_type", "cik", "isin", "cusip", "lei", "ein_employer_id", "series_id"]), ("Classification", ["sector", "industry", "sic_code", "sic_name"])], subtitle=data.get("symbol")),
    ]
    if isinstance(exchange, dict):
        views.append(exchange_facts("ticker-exchange", exchange))
    return views, []


def _tickers_list(payload: Any) -> Built:
    records = []
    for r in dicts(body(payload)):
        exchange = r.get("stock_exchange") if isinstance(r.get("stock_exchange"), dict) else {}
        records.append({**flat(r, ["name", "ticker", "has_eod", "has_intraday"]), "exchange": exchange.get("name"), "mic": exchange.get("mic"), "country": exchange.get("country"), "city": exchange.get("city")})
    return [table("tickers", "Tickers", records, ["name", "ticker", "has_eod", "has_intraday", "exchange", "mic", "country", "city"])], []


def _ticker_info(payload: Any) -> Built:
    data = body(payload)
    if isinstance(data, list):
        data = data[0] if data else {}
    if not isinstance(data, dict):
        return [], []
    views = [
        facts("company", str(data.get("name") or "Company"), data, [("Company", ["name", "ticker", "item_type", "sector", "industry", "exchange_code", "full_time_employees", "ipo_date", "date_founded", "incorporation", "incorporation_description", "start_fiscal", "end_fiscal", "reporting_currency", "phone", "website"]), ("About", ["about", "mission", "vision"])], subtitle=data.get("ticker")),
    ]
    for key, title in (("address", "Address"), ("post_address", "Postal address")):
        if isinstance(data.get(key), dict):
            views.append(facts(f"company-{key}", title, data[key], [(None, ["street1", "street2", "city", "postal_code", "stateOrCountry", "state_or_country_description"])]))
    execs = [flat(e) for e in dicts(data.get("key_executives"))]
    views.append(table("executives", "Key executives", execs, ["name", "function", "salary", "exercised", "birth_year"]))
    listings = [flat(e) for e in dicts(data.get("stock_exchanges"))]
    views.append(table("listings", "Listings", listings, ["exchange_name", "acronym1", "exchange_mic", "country", "city", "website"]))
    names = data.get("previous_names")
    if isinstance(names, list) and names:
        views.append(table("previous-names", "Previous names", [{"name": n} for n in names if isinstance(n, str)]))
    return views, []


def _table_of(view_id: str, title: str, keys: Optional[list[str]] = None) -> Callable[[Any], Built]:
    return lambda payload: ([table(view_id, title, [flat(r) for r in dicts(body(payload))], keys)], [])


# --- corporate actions -------------------------------------------------------------------------------


def _actions(view_id: str, title: str, value_key: str, label: str, keys: list[str]) -> Callable[[Any], Built]:
    def build(payload: Any) -> Built:
        rows = dicts(body(payload))
        views: list[Optional[dict[str, Any]]] = []
        groups: dict[str, list[dict[str, Any]]] = {}
        for r in rows:
            groups.setdefault(str(r.get("symbol") or "?"), []).append(r)
        for symbol, group in list(groups.items())[:MAX_CHARTS]:
            pairs = [(moment(r.get("date")), V.to_number(r.get(value_key))) for r in group]
            pairs = [(m[0], v) for m, v in pairs if m and v is not None]
            if pairs:
                columns = [{"key": value_key, "label": label, "values": [v for _, v in pairs], "role": "value", "unit": None}]
                views.append(V.series_view(f"{view_id}-{V.slug(symbol)}-chart", f"{symbol} {title.lower()}", [t for t, _ in pairs], columns))
        records = [{**flat(r, keys), "date": stamp(r.get("date"), False)} for r in rows]
        views.append(table(f"{view_id}-table", title, records, keys))
        return views, []

    return build


# --- indices, bonds, ETFs, prices, commodities ------------------------------------------------------------


_CHANGES = [("percentage_day", "Day"), ("percentage_week", "Week"), ("percentage_month", "Month"), ("percentage_year", "Year")]


def _change_bars(view_id: str, title: str, record: dict[str, Any]) -> Optional[dict[str, Any]]:
    pairs = [(label, num(record.get(key))) for key, label in _CHANGES if key in record]
    return V.bars_view(view_id, title, [p[0] for p in pairs], [p[1] for p in pairs], fmt="percent", sign_colors=True, value_label="Change")


def _records(payload: Any) -> list[dict[str, Any]]:
    data = body(payload)
    return dicts(data) if isinstance(data, list) else [data] if isinstance(data, dict) else []


def _index_info(payload: Any) -> Built:
    rows = _records(payload)
    if not rows:
        return [], []
    head = rows[0]
    views = [
        facts("index", str(head.get("benchmark") or "Index"), head, [(None, ["benchmark", "region", "country", "price", "price_change_day", "percentage_day", "percentage_week", "percentage_month", "percentage_year", "date"])]),
        _change_bars("index-changes", f"{head.get('benchmark') or 'Index'} change", head),
    ]
    if len(rows) > 1:
        views.append(table("index-table", "Indices", [flat(r) for r in rows]))
    return views, []


def _bond(payload: Any) -> Built:
    rows = _records(payload)
    if not rows:
        return [], []
    head = rows[0]
    title = f"{head.get('country') or 'Bond'} {head.get('type') or ''}".strip()
    views = [
        facts("bond", title, head, [(None, ["country", "region", "type", "yield", "price_change_day", "percentage_week", "percentage_month", "percentage_year", "date"])]),
        _change_bars("bond-changes", f"{title} change", head),
    ]
    if len(rows) > 1:
        views.append(table("bond-table", "Bonds", [flat(r) for r in rows]))
    return views, []


def _etf_holdings(payload: Any) -> Built:
    data = body(payload)
    if not isinstance(data, dict):
        return [], []
    basics = data.get("basics") if isinstance(data.get("basics"), dict) else {}
    output = data.get("output") if isinstance(data.get("output"), dict) else {}
    attributes = output.get("attributes") if isinstance(output.get("attributes"), dict) else {}
    signature = output.get("signature") if isinstance(output.get("signature"), dict) else {}
    holdings = [flat(h["investment_security"]) for h in dicts(output.get("holdings")) if isinstance(h.get("investment_security"), dict)]
    top = sorted((h for h in holdings if num(h.get("percent_value")) is not None), key=lambda h: -(num(h.get("percent_value")) or 0))[:20]
    views = [
        facts("fund", str(basics.get("fund_name") or "ETF"), {**basics, **attributes}, [("Fund", ["fund_name", "ticker", "series_name", "series_id", "series_lei", "isin", "cik", "reg_lei", "file_number"]), ("Reporting", ["date_report_period", "end_report_period", "final_filing"])], subtitle=attributes.get("ticker")),
        facts("signature", "Filing signature", signature, [(None, ["date_signed", "name_of_applicant", "signer_name", "title", "signature"])]),
        V.bars_view("top-holdings", "Largest holdings", [str(h.get("name") or h.get("title") or "?") for h in top], [num(h.get("percent_value")) for h in top], fmt="percent", value_label="Share of fund"),
        table("holdings", "Holdings", holdings, ["name", "title", "asset_category", "balance", "units", "currency", "value_usd", "percent_value", "invested_country", "issuer_category", "isin", "cusip", "lei"]),
    ]
    return views, []


def _stock_price(payload: Any) -> Built:
    rows = _records(payload)
    views = [table("prices", "Real-time price", [flat(r) for r in rows], ["ticker", "exchange_code", "exchange_name", "country", "price", "currency", "trade_last"])]
    if len(rows) == 1:
        views.insert(0, facts("price", str(rows[0].get("ticker") or "Price"), rows[0], [(None, ["ticker", "price", "currency", "trade_last", "exchange_name", "exchange_code", "country"])]))
    return views, []


def _commodities(payload: Any) -> Built:
    rows = _records(payload)
    views: list[Optional[dict[str, Any]]] = []
    quarters = ["quarter1_25", "quarter2_25", "quarter3_25", "quarter4_25"]
    for i, r in enumerate(rows[:3]):
        name = str(r.get("commodity_name") or "Commodity")
        views.append(facts(f"commodity-{i}", name, r, [("Price", ["commodity_price", "commodity_unit", "price_change_day", "datetime"]), ("Change", [k for k, _ in _CHANGES]), ("Quarterly", quarters)]))
        views.append(_change_bars(f"commodity-{i}-changes", f"{name} change", r))
    views.append(table("commodities", "Commodities", [flat(r) for r in rows], ["commodity_name", "commodity_unit", "commodity_price", "price_change_day", "percentage_day", "percentage_week", "percentage_month", "percentage_year", "datetime"]))
    return views, []


def _commodity_history(payload: Any) -> Built:
    result = payload.get("result") if isinstance(payload, dict) else None
    result = result if isinstance(result, dict) else {}
    frequency = (result.get("basics") or {}).get("frequency") if isinstance(result.get("basics"), dict) else None
    views: list[Optional[dict[str, Any]]] = []
    records: list[dict[str, Any]] = []
    for i, item in enumerate(dicts(result.get("data"))):
        name = str(item.get("commodity_name") or "Commodity")
        unit = item.get("commodity_unit")
        prices = dicts(item.get("commodity_prices"))
        pairs = [(moment(p.get("date")), num(p.get("commodity_price"))) for p in prices]
        pairs = [(m[0], v) for m, v in pairs if m and v is not None]
        columns = [{"key": "price", "label": "Price", "values": [v for _, v in pairs], "role": "value", "unit": unit}]
        if i < MAX_CHARTS:
            views.append(V.series_view(f"history-{V.slug(name)}", f"{name} price", [t for t, _ in pairs], columns, subtitle=" · ".join(str(x) for x in (unit, frequency) if x) or None))
        records += [{"commodity": name, "unit": unit, "date": stamp(p.get("date"), False), "price": p.get("commodity_price")} for p in prices]
    views.append(table("history-table", "Prices", records, ["commodity", "unit", "date", "price"]))
    return views, []


# --- company data and SEC EDGAR --------------------------------------------------------------------------


def _ratings(payload: Any) -> Built:
    result = payload.get("result") if isinstance(payload, dict) else None
    result = result if isinstance(result, dict) else {}
    basics = result.get("basics") if isinstance(result.get("basics"), dict) else {}
    output = result.get("output") if isinstance(result.get("output"), dict) else {}
    consensus = output.get("analyst_consensus") if isinstance(output.get("analyst_consensus"), dict) else {}
    name = str(basics.get("company_name") or basics.get("ticker") or "Analyst ratings")
    counts = [("Buy", num(consensus.get("buy"))), ("Hold", num(consensus.get("hold"))), ("Sell", num(consensus.get("sell")))]
    analysts = []
    for a in dicts(output.get("analysts")):
        rating = a.get("rating") if isinstance(a.get("rating"), dict) else {}
        analysts.append({**flat(a, ["analyst_name", "analyst_firm", "analyst_role"]), **flat(rating, ["date_rating", "rated", "conclusion", "price_target", "target_date"])})
    views = [
        facts("consensus", f"{name} consensus", consensus, [("Consensus", ["consensus_conclusion", "consensus_date", "analysts_number"]), ("Price targets", ["stock_price", "analyst_average", "analyst_highest", "analyst_lowest"])], subtitle=basics.get("ticker")),
        V.bars_view("ratings", "Analyst ratings", [c[0] for c in counts], [c[1] for c in counts], fmt="number", value_label="Analysts"),
        table("analysts", "Analysts", analysts, ["analyst_name", "analyst_firm", "analyst_role", "date_rating", "rated", "conclusion", "price_target", "target_date"]),
    ]
    return views, []


def _cik_name(payload: Any) -> Built:
    data = body(payload)
    item = data[0] if isinstance(data, list) and data and isinstance(data[0], dict) else data
    if not isinstance(item, dict):
        return [], []
    addresses = item.get("addresses") or (payload.get("addresses") if isinstance(payload, dict) else None) or {}
    street = ["street1", "street2", "city", "state_or_country", "zip_code"]
    views = [facts("company", str(item.get("company_name") or "Company"), item, [(None, ["cik_code", "company_name", "ein", "sic", "sic_description", "phone", "incorporation_state"])])]
    for kind in ("mailing", "business"):
        if isinstance(addresses.get(kind), dict):
            views.append(facts(f"address-{kind}", f"{kind.title()} address", {**addresses[kind], "zip_code": addresses[kind].get("zip_code") or addresses[kind].get("zipCode")}, [(None, street)]))
    return views, []


def _company_facts(payload: Any) -> Built:
    data = body(payload)
    if not isinstance(data, dict):
        return [], []
    records = []
    for taxonomy, concepts in (data.get("facts") or {}).items():
        for concept, detail in (concepts.items() if isinstance(concepts, dict) else []):
            units = detail.get("units") if isinstance(detail, dict) else None
            for unit, observations in (units.items() if isinstance(units, dict) else []):
                obs = dicts(observations)
                latest = max(obs, key=lambda o: str(o.get("end") or ""), default={})
                records.append({"taxonomy": taxonomy, "concept": concept, "label": detail.get("label") or None, "unit": unit, "observations": len(obs), "latest_end": latest.get("end"), "latest_value": latest.get("val"), "form": latest.get("form"), "fiscal_year": latest.get("fy")})
    taxonomies = sorted({r["taxonomy"] for r in records})
    summary = {"company_name": data.get("company_name"), "cik": data.get("cik"), "taxonomies": ", ".join(taxonomies), "concepts": len({(r["taxonomy"], r["concept"]) for r in records}), "series": len(records)}
    views = [
        facts("company", str(data.get("company_name") or "Company facts"), summary, [(None, ["company_name", "cik", "taxonomies", "concepts", "series"])]),
        table("facts-table", "Reported concepts", records, ["taxonomy", "concept", "label", "unit", "observations", "latest_end", "latest_value", "form", "fiscal_year"]),
    ]
    return views, []


def _find_units(node: Any, path: tuple[str, ...] = (), depth: int = 0) -> list[tuple[tuple[str, ...], dict[str, Any], dict[str, Any]]]:
    """Every ``{"units": {unit: [observations]}}`` block in a concept response, with where it was found."""

    if depth > 5 or not isinstance(node, dict):
        return []
    if isinstance(node.get("units"), dict):
        return [(path, node, node["units"])]
    found = []
    for key, child in node.items():
        found += _find_units(child, (*path, str(key)), depth + 1)
    return found


def _concept(payload: Any) -> Built:
    data = body(payload)
    if not isinstance(data, dict):
        return [], []
    views: list[Optional[dict[str, Any]]] = [facts("company", str(data.get("company_name") or data.get("entityName") or "Concept"), data, [(None, ["company_name", "entityName", "cik"])])]
    records = []
    for path, block, units in _find_units(data):
        concept = path[-1] if path else str(block.get("tag") or "concept")
        for unit, observations in units.items():
            obs = dicts(observations)
            pairs = [(moment(o.get("end")), V.to_number(o.get("val"))) for o in obs]
            pairs = [(m[0], v) for m, v in pairs if m and v is not None]
            if len(views) <= MAX_CHARTS:
                columns = [{"key": "value", "label": str(block.get("label") or concept), "values": [v for _, v in pairs], "role": "value", "unit": unit}]
                views.append(V.series_view(f"concept-{V.slug(concept)}-{V.slug(unit)}", f"{concept} ({unit})", [t for t, _ in pairs], columns, subtitle=block.get("label") or None))
            records += [{"concept": concept, "unit": unit, **flat(o, ["end", "val", "fy", "fp", "form", "filed", "frame", "accn"])} for o in obs]
    views.append(table("concept-table", "Reported values", records, ["concept", "unit", "end", "val", "fy", "fp", "form", "filed", "frame", "accn"]))
    return views, []


def _submission(item: dict[str, Any], suffix: str) -> list[Optional[dict[str, Any]]]:
    addresses = item.get("addresses") if isinstance(item.get("addresses"), dict) else {}
    street = ["street1", "street2", "city", "state_or_country_desc", "zip_code"]
    profile = [("Company", ["company_name", "cik_code", "entity_type", "ein", "sic", "sic_description", "owner_org", "category_filer", "fiscal_year_end", "tickers", "exchanges"]), ("Registration", ["incorporation_state_or_country_desc", "phone", "website", "investor_website", "description"])]
    views = [facts(f"company{suffix}", str(item.get("company_name") or "Company"), item, profile, subtitle=scalar(item.get("tickers")))]
    for kind in ("mailing", "business"):
        if isinstance(addresses.get(kind), dict):
            views.append(facts(f"address-{kind}{suffix}", f"{kind.title()} address", addresses[kind], [(None, street)]))
    filings = item.get("filings") if isinstance(item.get("filings"), dict) else {}
    recent = filings.get("recent") if isinstance(filings.get("recent"), dict) else {}
    columns = {k: v for k, v in recent.items() if isinstance(v, list)}
    count = max((len(v) for v in columns.values()), default=0)
    rows = [{k: (v[i] if i < len(v) else None) for k, v in columns.items()} for i in range(count)]
    views.append(table(f"filings{suffix}", "Recent filings", rows, ["filing_date", "report_date", "form", "primary_doc_description", "primary_document", "accession_number", "size", "act", "file_number", "acceptance_date_time"]))
    views.append(table(f"filing-files{suffix}", "Older filing archives", [flat(f) for f in dicts(filings.get("files"))], ["name", "filing_count", "filing_from", "filing_to"]))
    views.append(table(f"former-names{suffix}", "Former names", [flat(f) for f in dicts(item.get("former_names"))], ["name", "from", "to"]))
    return views


def _submissions(payload: Any) -> Built:
    data = body(payload)
    items = dicts(data) if isinstance(data, list) else [data] if isinstance(data, dict) else []
    views: list[Optional[dict[str, Any]]] = []
    for i, item in enumerate(items[:5]):
        views += _submission(item, "" if i == 0 else f"-{i + 1}")
    return views, ([f"Showing the first 5 of {len(items)} companies."] if len(items) > 5 else [])


def _frames(payload: Any) -> Built:
    data = body(payload)
    if not isinstance(data, dict):
        return [], []
    entries = dicts(data.get("frame_data"))
    top = sorted((e for e in entries if num(e.get("val")) is not None), key=lambda e: -(num(e.get("val")) or 0))[:20]
    summary = {**data, "entries": len(entries)}
    views = [
        facts("frame", str(data.get("label") or data.get("tag") or "Frame"), summary, [(None, ["label", "taxonomy", "tag", "ccp", "uom", "entries", "description"])]),
        V.bars_view("largest", "Largest values", [str(e.get("entityName") or e.get("cik") or "?") for e in top], [num(e.get("val")) for e in top], fmt="number", value_label=str(data.get("uom") or "Value")),
        table("frame-table", "Reporting entities", [flat(e) for e in entries], ["entityName", "cik", "end", "val", "accn"]),
    ]
    return views, []


_BASIC_ACTION_KEYS = ["date", "symbol", "stock_split", "split_factor"]
_DIVIDEND_KEYS = ["date", "symbol", "dividend", "distr_freq", "payment_date", "record_date", "declaration_date"]

_HANDLERS: dict[str, Callable[[Any], Built]] = {
    "exchanges": _exchanges,
    "exchange": _exchanges,
    "exchange_tickers": _exchange_tickers,
    "ticker": _ticker,
    "tickerslist": _tickers_list,
    "tickerinfo": _ticker_info,
    "splits": _actions("splits", "Stock splits", "split_factor", "Split factor", _BASIC_ACTION_KEYS),
    "ticker_splits": _actions("splits", "Stock splits", "split_factor", "Split factor", _BASIC_ACTION_KEYS),
    "dividends": _actions("dividends", "Dividends", "dividend", "Dividend", _DIVIDEND_KEYS),
    "ticker_dividends": _actions("dividends", "Dividends", "dividend", "Dividend", _DIVIDEND_KEYS),
    "timezones": _table_of("timezones", "Timezones", ["timezone", "abbr", "abbr_dst"]),
    "currencies": _table_of("currencies", "Currencies", ["code", "name", "symbol", "symbol_native"]),
    "indexlist": _table_of("indices", "Market indices", ["benchmark"]),
    "indexinfo": _index_info,
    "bondlist": _table_of("bonds", "Bonds", ["country"]),
    "bond": _bond,
    "etflist": _table_of("etfs", "ETFs", ["ticker"]),
    "etfholdings": _etf_holdings,
    "stockprice": _stock_price,
    "commodities": _commodities,
    "commoditieshistory": _commodity_history,
    "companyratings": _ratings,
    "company_name": _cik_name,
    "cik_code": _table_of("companies", "Companies", ["cik_code", "company_name", "ein", "sic", "sic_description"]),
    "company_facts": _company_facts,
    "concept_accounts_payable": _concept,
    "submissions": _submissions,
    "frames_accounts_payable": _frames,
}


def _handler(endpoint_id: str) -> Optional[Callable[[Any], Built]]:
    if endpoint_id in _HANDLERS:
        return _HANDLERS[endpoint_id]
    if "intraday" in endpoint_id:
        return _bars_handler("intraday", True, "intraday")
    if endpoint_id == "eod" or "eod" in endpoint_id:
        return _bars_handler("eod", False, "eod")
    return None


def _paging_note(payload: Any) -> list[str]:
    page = payload.get("pagination") if isinstance(payload, dict) else None
    if not isinstance(page, dict):
        return []
    count, total, offset = (num(page.get(k)) for k in ("count", "total", "offset"))
    if count is None or total is None or total <= (offset or 0) + count:
        return []
    return [f"Showing {int(count):,} of {int(total):,} rows from offset {int(offset or 0):,}. Raise offset to read the next page; each page is one request."]


def build_views(endpoint_id: str, payload: Any, label: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Views and notes for one Marketstack response. ``label`` is the endpoint title."""

    notes: list[str] = []
    built: list[Optional[dict[str, Any]]]
    handler = _handler(endpoint_id)
    try:
        built, notes = handler(payload) if handler else (V.analyze(payload, label, V.slug(endpoint_id)), [])
    except Exception:  # a shape surprise must cost views, never the whole response
        built, notes = V.analyze(payload, label, V.slug(endpoint_id)), []
    kept, notes = V.finalize(built, [*notes, *_paging_note(payload)])
    return kept, notes
