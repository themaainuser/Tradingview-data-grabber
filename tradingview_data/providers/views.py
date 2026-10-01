"""Provider-independent view builders: turn parsed provider data into what the frontend draws.

Every function returns plain dictionaries in the shapes documented in the providers contract
(``series``, ``table``, ``facts``, ``bars``, ``feed``, ``heatmap``, ``text``). Nothing here knows
about a particular provider; ``analyze`` is the fallback that makes sense of any JSON shape and
never raises.
"""

from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from typing import Any, Iterable, Optional, Sequence

try:  # zoneinfo ships with Python 3.9+, but its tz database may be missing on minimal systems
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore[assignment,misc]

MISSING = {"", ".", "None", "none", "-", "n/a", "N/A", "null", "NaN", "nan"}
CAPS = {"table": 5000, "series": 20_000, "feed": 100, "text": 200, "columns": 40, "bars": 60}
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2})?$")
_TEXT_NAME = re.compile(r"(^|_)(id|cik|symbol|ticker|code|zip|district|quarter|year|figi|isin|cusip|contractid|bioguide)", re.I)
_PREFIX = re.compile(r"^\d+(\.\d+)?[a-z]?[.:]\s*")
_OHLCV = {"open", "high", "low", "close", "volume"}


# --- scalars ---------------------------------------------------------------------------------------


def to_number(value: Any) -> Optional[float]:
    """A finite float from a number or numeric string; ``None`` for missing or non-numeric values."""

    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(value) else None
    if isinstance(value, str):
        text = value.strip()
        if text in MISSING:
            return None
        try:
            number = float(text)
        except ValueError:
            return None
        return number if math.isfinite(number) else None
    return None


def is_missing(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() in MISSING) or (
        isinstance(value, float) and not math.isfinite(value)
    )


def strip_prefix(key: str) -> str:
    """``"1. open"`` -> ``"open"``; ``"01. symbol"`` -> ``"symbol"``; ``"6.1: Deviation"`` -> ``"Deviation"``."""

    return _PREFIX.sub("", str(key)).strip()


def humanize(key: str) -> str:
    """A readable label for a provider field name (``PERatio`` -> ``PE Ratio``)."""

    text = strip_prefix(key).replace("_", " ")
    text = re.sub(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])|(?<=\d)(?=[A-Z])", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:1].upper() + text[1:] if text else str(key)


def percent_value(text: Any) -> Optional[float]:
    if isinstance(text, str) and text.strip().endswith("%"):
        return to_number(text.strip()[:-1])
    return None


# Legacy aliases that providers still send but minimal tz databases often lack.
_ZONE_ALIASES = {
    "US/Eastern": "America/New_York",
    "US/Central": "America/Chicago",
    "US/Mountain": "America/Denver",
    "US/Pacific": "America/Los_Angeles",
    "US/Alaska": "America/Anchorage",
    "US/Hawaii": "Pacific/Honolulu",
}


def zone(name: Optional[str]) -> Any:
    """The tz for a provider's zone name (``"US/Eastern Time"`` works); ``None`` when it cannot be resolved."""

    if not name or ZoneInfo is None:
        return None
    key = name.strip().split(" ")[0]
    try:
        return ZoneInfo(_ZONE_ALIASES.get(key, key))
    except Exception:  # unknown zone, or no tz database on this system
        return None


def epoch(text: str, tz: Any = None) -> Optional[int]:
    """UTC epoch seconds of ``YYYY-MM-DD`` (00:00 UTC) or a datetime read in ``tz`` (UTC when None)."""

    try:
        if _DATE.match(text):
            moment = datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        elif _DATETIME.match(text):
            clean = text.replace("T", " ")
            moment = datetime.strptime(clean, "%Y-%m-%d %H:%M:%S" if len(clean) > 16 else "%Y-%m-%d %H:%M")
            moment = moment.replace(tzinfo=tz or timezone.utc)
        else:
            return None
        return int(moment.timestamp())
    except (ValueError, OverflowError, OSError):
        return None


# --- view constructors ---------------------------------------------------------------------------------


def fact(key: str, label: str, value: Any, fmt: str = "text", tone: Optional[str] = None, hint: Optional[str] = None) -> dict[str, Any]:
    return {"key": key, "label": label, "value": value, "format": fmt, "tone": tone, "hint": hint}


def facts_view(view_id: str, title: str, groups: Sequence[tuple[Optional[str], list[dict[str, Any]]]], subtitle: Optional[str] = None) -> Optional[dict[str, Any]]:
    kept = [{"title": name, "items": items} for name, items in groups if items]
    if not kept:
        return None
    return {"kind": "facts", "id": view_id, "title": title, "subtitle": subtitle, "groups": kept}


def series_view(
    view_id: str,
    title: str,
    times: Sequence[int],
    columns: Sequence[dict[str, Any]],
    *,
    subtitle: Optional[str] = None,
    intraday: bool = False,
    time_note: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Ascending, de-duplicated, capped (most recent kept) series. ``columns`` need key/label/values/role/unit."""

    order = sorted({t: i for i, t in enumerate(times)}.items())
    if len(order) < 2 or not columns:
        return None
    total = len(order)
    order = order[-CAPS["series"] :]
    keep = [i for _, i in order]
    return {
        "kind": "series",
        "id": view_id,
        "title": title,
        "subtitle": subtitle,
        "time": [t for t, _ in order],
        "intraday": intraday,
        "series": [
            {
                "key": c["key"],
                "label": c["label"],
                "values": [c["values"][i] for i in keep],
                "role": c.get("role", "value"),
                "unit": c.get("unit"),
            }
            for c in columns
        ],
        "time_note": time_note,
        "truncated": total > len(order),
        "total_points": total,
    }


def role_of(label: str) -> str:
    lowered = label.strip().lower()
    return lowered if lowered in _OHLCV else "value"


def _cell(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        if isinstance(value, list) and all(not isinstance(v, (dict, list)) for v in value):
            return ", ".join(str(v) for v in value)[:300]
        return json.dumps(value, separators=(",", ":"), default=str)[:300]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _column_type(name: str, values: list[Any]) -> str:
    present = [v for v in values if not is_missing(v)]
    if not present:
        return "text"
    sample = present[:400]
    strings = [v for v in sample if isinstance(v, str)]
    if strings and len(strings) >= 0.9 * len(sample):
        if all(_DATE.match(v) for v in strings):
            return "date"
        if all(_DATETIME.match(v) for v in strings):
            return "datetime"
        if all(v.startswith(("http://", "https://")) for v in strings):
            return "url"
        if all(percent_value(v) is not None for v in strings):
            return "percent"
    if _TEXT_NAME.search(name):
        return "text"
    numeric = [v for v in sample if to_number(v) is not None]
    if len(numeric) >= 0.9 * len(sample):
        return "number"
    return "text"


def table_view(
    view_id: str,
    title: str,
    records: Sequence[dict[str, Any]],
    *,
    subtitle: Optional[str] = None,
    keys: Optional[Sequence[str]] = None,
) -> Optional[dict[str, Any]]:
    """A table from a list of objects; columns are typed from their values and numbers are parsed."""

    records = [r for r in records if isinstance(r, dict)]
    if not records:
        return None
    if keys is None:
        seen: dict[str, None] = {}
        for record in records[:500]:
            for key in record:
                seen.setdefault(key, None)
        keys = list(seen)[: CAPS["columns"]]
    total = len(records)
    shown = records[: CAPS["table"]]
    columns, cells = [], []
    for key in keys:
        raw = [record.get(key) for record in shown]
        kind = _column_type(key, raw)
        if kind == "number":
            cells.append([to_number(v) for v in raw])
        elif kind == "percent":
            cells.append([percent_value(v) if isinstance(v, str) else to_number(v) for v in raw])
        else:
            cells.append([None if is_missing(v) else _cell(v) for v in raw])
        columns.append({"key": key, "label": humanize(key), "type": kind})
    rows = [[column[i] for column in cells] for i in range(len(shown))]
    return {
        "kind": "table",
        "id": view_id,
        "title": title,
        "subtitle": subtitle,
        "columns": columns,
        "rows": rows,
        "total_rows": total,
        "truncated": total > len(shown),
    }


def series_from_records(view_id: str, title: str, records: Sequence[dict[str, Any]], subtitle: Optional[str] = None) -> Optional[dict[str, Any]]:
    """A series when the records have one unique date column and at least one numeric column."""

    records = [r for r in records if isinstance(r, dict)]
    if len(records) < 2:
        return None
    keys: dict[str, None] = {}
    for record in records[:200]:
        for key in record:
            keys.setdefault(key, None)
    date_key = next(
        (k for k in keys if _column_type(k, [r.get(k) for r in records]) in ("date", "datetime")),
        None,
    )
    if date_key is None:
        return None
    stamps = [epoch(str(r.get(date_key))) if r.get(date_key) else None for r in records]
    if any(s is None for s in stamps) or len(set(stamps)) != len(stamps):
        return None
    columns = []
    for key in keys:
        if key == date_key or _TEXT_NAME.search(key):
            continue
        raw = [r.get(key) for r in records]
        if _column_type(key, raw) != "number":
            continue
        label = humanize(key)
        columns.append({"key": key, "label": label, "values": [to_number(v) for v in raw], "role": role_of(label), "unit": None})
    if not columns:
        return None
    intraday = any(_DATETIME.match(str(r.get(date_key))) for r in records[:5])
    return series_view(view_id, title, stamps, columns[:6], subtitle=subtitle, intraday=intraday)  # type: ignore[arg-type]


def bars_view(view_id: str, title: str, labels: list[str], values: list[Optional[float]], *, fmt: str = "number", sign_colors: bool = False, value_label: str = "Value", subtitle: Optional[str] = None) -> Optional[dict[str, Any]]:
    if not labels or not any(v is not None for v in values):
        return None
    return {
        "kind": "bars",
        "id": view_id,
        "title": title,
        "subtitle": subtitle,
        "labels": labels[: CAPS["bars"]],
        "values": values[: CAPS["bars"]],
        "format": fmt,
        "sign_colors": sign_colors,
        "value_label": value_label,
    }


def heatmap_view(view_id: str, title: str, rows: list[str], cols: list[str], values: list[list[Optional[float]]], *, scale: str = "diverging", domain: Optional[list[float]] = None, subtitle: Optional[str] = None) -> Optional[dict[str, Any]]:
    if not rows or not cols or len(values) != len(rows) or any(len(r) != len(cols) for r in values):
        return None
    return {"kind": "heatmap", "id": view_id, "title": title, "subtitle": subtitle, "rows": rows, "cols": cols, "values": values, "scale": scale, "domain": domain}


def text_view(view_id: str, title: str, blocks: list[dict[str, Any]], subtitle: Optional[str] = None) -> Optional[dict[str, Any]]:
    if not blocks:
        return None
    return {
        "kind": "text",
        "id": view_id,
        "title": title,
        "subtitle": subtitle,
        "blocks": blocks[: CAPS["text"]],
        "total_blocks": len(blocks),
        "truncated": len(blocks) > CAPS["text"],
    }


# --- facts from a mapping ---------------------------------------------------------------------------------

# Provider fields that are fractions (0.0124) and read better as percentages (1.24%).
FRACTION_KEYS = {
    "dividendyield", "profitmargin", "operatingmarginttm", "returnonassetsttm", "returnonequityttm",
    "quarterlyearningsgrowthyoy", "quarterlyrevenuegrowthyoy", "net_expense_ratio", "dividend_yield", "weight",
}
_TONE_KEYS = ("change", "growth", "surprise")


def _tone(key: str, number: float) -> Optional[str]:
    if number == 0 or not any(word in key for word in _TONE_KEYS):
        return None
    return "positive" if number > 0 else "negative"


def smart_fact(key: str, value: Any) -> dict[str, Any]:
    """One fact: the label, a typed value, and a positive/negative tone for change-like fields."""

    label = humanize(key)
    if is_missing(value):
        return fact(key, label, None)
    if isinstance(value, bool):
        return fact(key, label, "Yes" if value else "No")
    if isinstance(value, (dict, list)):
        return fact(key, label, _cell(value))
    lowered = strip_prefix(key).lower()
    if isinstance(value, str):
        pct = percent_value(value)
        if pct is not None:
            return fact(key, label, pct, "percent", _tone(lowered, pct))
        if _DATE.match(value) or _DATETIME.match(value):
            return fact(key, label, value, "date")
        if value.startswith(("http://", "https://")):
            return fact(key, label, value, "url")
    number = to_number(value)
    leading_zero = isinstance(value, str) and re.match(r"^0\d", value.strip())
    if number is not None and not _TEXT_NAME.search(lowered) and not leading_zero:
        if lowered in FRACTION_KEYS:
            return fact(key, label, number * 100, "percent", _tone(lowered, number))
        whole = number == int(number) and abs(number) >= 1000 and "." not in str(value)
        return fact(key, label, int(number) if whole else number, "integer" if whole else "number", _tone(lowered, number))
    return fact(key, label, str(value))


def facts_from_mapping(mapping: dict[str, Any], skip: Iterable[str] = ()) -> list[dict[str, Any]]:
    skipped = set(skip)
    return [smart_fact(k, v) for k, v in mapping.items() if k not in skipped and not isinstance(v, (dict, list))]


# --- summaries for a series ---------------------------------------------------------------------------------


def summary_facts(times: Sequence[int], columns: Sequence[dict[str, Any]], intraday: bool) -> list[dict[str, Any]]:
    """Latest value, change, high/low and span of the primary column of a series."""

    by_role = {c["role"]: c for c in columns if c["role"] != "value"}
    primary = by_role.get("close") or next((c for c in columns if c["role"] != "volume"), None)
    if primary is None or not times:
        return []
    pairs = sorted((t, v) for t, v in zip(times, primary["values"]) if v is not None)
    if not pairs:
        return []
    values = [v for _, v in pairs]
    last, first = values[-1], values[0]
    items = [fact("latest", f"Latest {primary['label'].lower()}", last, "number")]
    if len(values) > 1:
        step = last - values[-2]
        items.append(fact("change", "Change vs previous", step, "number", "positive" if step > 0 else "negative" if step < 0 else None))
        if first:
            total = (last / first - 1) * 100
            items.append(fact("period", "Change over the period", total, "percent", "positive" if total > 0 else "negative" if total < 0 else None))
    high = by_role.get("high", primary)["values"]
    low = by_role.get("low", primary)["values"]
    items.append(fact("high", "Period high", max((v for v in high if v is not None), default=None), "number"))
    items.append(fact("low", "Period low", min((v for v in low if v is not None), default=None), "number"))
    volume = by_role.get("volume")
    if volume:
        vols = [v for v in volume["values"] if v is not None]
        if vols:
            items.append(fact("avg_volume", "Average volume", sum(vols) / len(vols), "number"))
    items.append(fact("points", "Data points", len(pairs), "integer"))

    def stamp(t: int) -> str:
        return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d %H:%M" if intraday else "%Y-%m-%d")

    items.append(fact("range", "Range (UTC)", f"{stamp(pairs[0][0])} to {stamp(pairs[-1][0])}"))
    return items


# --- the generic analyzer ---------------------------------------------------------------------------------------

_RANK = {"facts": 0, "table": 2}


def order_views(views: Iterable[Optional[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Drop empty views; summary first, then charts and feeds, then tables (stable within each)."""

    kept = [v for v in views if v]
    return sorted(kept, key=lambda v: _RANK.get(v["kind"], 1))


def time_keyed(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and len(value) >= 2
        and all(isinstance(v, dict) for v in list(value.values())[:20])
        and all(_DATE.match(str(k)) or _DATETIME.match(str(k)) for k in list(value)[:20])
    )


def time_series_from_keyed(view_id: str, title: str, keyed: dict[str, dict[str, Any]], *, tz: Any = None, subtitle: Optional[str] = None, time_note: Optional[str] = None) -> tuple[Optional[dict[str, Any]], list[int], list[dict[str, Any]], bool]:
    """A series from ``{"2026-09-29": {"1. open": "220.8", ...}}`` (the shape of most time-series APIs).

    Returns ``(view, times, columns, intraday)`` so callers can derive summaries from the same columns.
    """

    stamps, rows = [], []
    for key, row in keyed.items():
        stamp = epoch(str(key), tz)
        if stamp is not None and isinstance(row, dict):
            stamps.append(stamp)
            rows.append(row)
    fields: dict[str, None] = {}
    for row in rows[:50]:
        for field in row:
            fields.setdefault(field, None)
    columns = []
    for field in list(fields)[:12]:
        values = [to_number(row.get(field)) for row in rows]
        if all(v is None for v in values):
            continue
        label = strip_prefix(field)
        columns.append({"key": re.sub(r"\W+", "_", label).strip("_").lower(), "label": label, "values": values, "role": role_of(label), "unit": None})
    intraday = any(_DATETIME.match(str(k)) for k in list(keyed)[:3])
    view = series_view(view_id, title, stamps, columns, subtitle=subtitle, intraday=intraday, time_note=time_note)
    return view, stamps, columns, intraday


def records_views(prefix: str, title: str, records: Sequence[Any], subtitle: Optional[str] = None) -> list[Optional[dict[str, Any]]]:
    objects = [r for r in records if isinstance(r, dict)]
    if not objects:
        scalars = [{"value": r} for r in records if not isinstance(r, (dict, list))]
        return [table_view(f"{prefix}-table", title, scalars, subtitle=subtitle)] if scalars else []
    return [
        series_from_records(f"{prefix}-chart", title, objects, subtitle),
        table_view(f"{prefix}-table", title, objects, subtitle=subtitle),
    ]


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", strip_prefix(text).lower()).strip("-") or "part"


def analyze(payload: Any, title: str = "Data", prefix: str = "data", depth: int = 0) -> list[Optional[dict[str, Any]]]:
    """Views for any JSON value. Time-keyed mappings become series, lists of objects become a
    table (plus a series when they have a date), flat mappings become facts, anything nested is
    walked. Never raises: an unfamiliar shape just yields fewer views."""

    try:
        return _analyze(payload, title, prefix, depth)
    except Exception:  # an unknown shape must degrade to fewer views, never to an error
        return []


def _analyze(payload: Any, title: str, prefix: str, depth: int) -> list[Optional[dict[str, Any]]]:
    if depth > 3:
        return []
    if isinstance(payload, list):
        return records_views(prefix, title, payload)
    if not isinstance(payload, dict):
        return [facts_view(prefix, title, [(None, [smart_fact("value", payload)])])]
    views: list[Optional[dict[str, Any]]] = [facts_view(f"{prefix}-facts", title, [(None, facts_from_mapping(payload))])]
    for key, value in payload.items():
        child = f"{prefix}-{slug(key)}"
        label = humanize(key)
        if time_keyed(value):
            series = time_series_from_keyed(child, label, value)[0]
            rows = [{"time": k, **{strip_prefix(f): v for f, v in row.items()}} for k, row in list(value.items())[: CAPS["table"]]]
            views.extend([series, table_view(f"{child}-table", label, rows)])
        elif isinstance(value, list) and value:
            views.extend(records_views(child, label, value))
        elif isinstance(value, dict):
            if value and all(not isinstance(v, (dict, list)) for v in value.values()):
                views.append(facts_view(child, label, [(None, facts_from_mapping(value))]))
            else:
                views.extend(_analyze(value, label, child, depth + 1))
    return views
