"""Alpha Vantage: the endpoint catalog (generated from its documentation) and a guarded query path.

The API key is read from ``ALPHAVANTAGE_API_KEY`` at call time and goes only into the upstream
request. It is never stored, logged, cached, put in a URL we report, or returned: every message and
the final response are scrubbed. Nothing is fetched until ``query`` is called, a missing key makes
``query`` answer ``not_configured`` without touching the network, and only successful responses are
cached (free keys allow 25 requests a day).
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

import requests

from . import common
from .alphavantage_views import build_views
from .base import Params, Provider, ProviderInfo
from .common import HttpGet, HttpResult, ResponseCache, default_http_get, first_sentence, scrub

QUERY_URL = "https://www.alphavantage.co/query"
CATALOG_PATH = Path(__file__).with_name("alphavantage_catalog.json")
RAW_LIMIT_BYTES = 400 * 1024
CACHE_TTL_SECONDS = 300.0
CACHE_ENTRIES = 32
_LONG_TEXT = {"SYMBOLS", "tickers", "topics", "CALCULATIONS", "keywords"}
_FORBIDDEN = {"apikey", "function"}
_PREMIUM_PLACEHOLDER = re.compile(r"premium endpoint|ARTIFICIAL", re.I)
_RATE_LIMIT = re.compile(r"rate limit|requests per (day|minute|second)|per day|per minute|call frequency|spreading out", re.I)
_KEY_PROBLEM = re.compile(r"(api ?key).*(invalid|missing|demo)|demo.*api key|invalid api ?key", re.I)

INFO = ProviderInfo(
    id="alphavantage",
    name="Alpha Vantage",
    description="Stocks, ETFs, FX, crypto, commodities, economic indicators, fundamentals, news sentiment and 50+ technical indicators.",
    website="https://www.alphavantage.co/",
    docs_url="https://www.alphavantage.co/documentation/",
    key_env="ALPHAVANTAGE_API_KEY",
    key_url="https://www.alphavantage.co/support/#api-key",
    limits_note="Free keys allow 25 requests per day (Alpha Vantage support page). Premium plans lift the daily limit and unlock the premium endpoints.",
)


def build_catalog(raw: dict[str, Any]) -> dict[str, Any]:
    """The contract's catalog from the generated JSON: summaries, doc links, managed parameters, counts."""

    endpoints = []
    for item in raw["endpoints"]:
        params = []
        for p in item["params"]:
            params.append({**{k: p.get(k) for k in ("name", "required", "type", "description", "enum", "enum_labels", "suggestions", "default", "example", "multiple", "premium_note", "minimum", "maximum")}, "premium_values": p.get("premium_values") or [], "managed": p["name"] == "datatype"})
        examples = [
            {"caption": e["caption"], "params": {k: v for k, v in e["params"].items() if k not in ("function", "datatype")}}
            for e in item["examples"]
        ]
        endpoints.append(
            {
                "id": item["function"],
                "title": item["title"],
                "category": item["category"],
                "description": item["description"],
                "summary": first_sentence(item["description"]) if item["description"] else item["title"],
                "premium": item["premium"],
                "trending": item["trending"],
                "utility": item["utility"],
                "premium_notes": item["premium_notes"],
                "plan": item.get("plan"),
                "request_cost": item.get("request_cost", 1),
                "doc_url": f"{raw['source']}#{item['anchor']}",
                "params": params,
                "examples": examples,
            }
        )
    categories = [
        {
            "id": c["id"],
            "title": c["title"],
            "summary": c["summary"],
            "count": sum(1 for e in endpoints if e["category"] == c["id"]),
            "premium_count": sum(1 for e in endpoints if e["category"] == c["id"] and e["premium"]),
        }
        for c in raw["categories"]
    ]
    return {"categories": categories, "endpoints": endpoints}


def validate_params(endpoint: dict[str, Any], params: Params) -> dict[str, Any]:
    return common.validate_params(endpoint, params, forbidden=_FORBIDDEN, long_text=_LONG_TEXT)


def classify(payload: Any) -> tuple[str, Optional[str]]:
    """``(status, message)`` for a parsed JSON body. ``ok`` means the payload is data."""

    if payload in (None, {}, []):
        return "empty", "The provider returned no data for these parameters."
    if not isinstance(payload, dict):
        return "ok", None
    text = next((str(payload[k]) for k in ("Error Message", "Information", "Note") if isinstance(payload.get(k), str)), None)
    only_notice = text is not None and len([k for k in payload if k not in ("Error Message", "Information", "Note")]) == 0
    if text and (only_notice or "Error Message" in payload):
        if "Error Message" in payload and not _KEY_PROBLEM.search(text):
            return "invalid_request", text
        if _PREMIUM_PLACEHOLDER.search(text) and "premium endpoint" in text.lower():
            return "premium_required", text
        if _RATE_LIMIT.search(text):
            return "rate_limited", text
        if _KEY_PROBLEM.search(text):
            return "invalid_key", text
        return "upstream_error", text
    message = payload.get("message")
    if isinstance(message, str) and _PREMIUM_PLACEHOLDER.search(message):
        # A not-entitled key gets an artificial sample payload back: it must never be drawn as data.
        return "premium_required", message
    meaningful = [v for k, v in payload.items() if k not in ("endpoint", "message") and v not in (None, "", [], {})]
    if not meaningful:
        return "empty", "The provider returned no data for these parameters."
    return "ok", None


def _csv_records(text: str) -> Optional[list[dict[str, Any]]]:
    lines = text.lstrip("\ufeff").splitlines()
    if not lines or "," not in lines[0] or lines[0].lstrip().startswith(("<", "{", "[")):
        return None
    rows = list(csv.DictReader(io.StringIO("\n".join(lines))))
    return [dict(r) for r in rows]


class AlphaVantage(Provider):
    info = INFO

    def __init__(self, http_get: Optional[HttpGet] = None, clock: Callable[[], float] = time.time, ttl_seconds: float = CACHE_TTL_SECONDS, catalog_path: Path = CATALOG_PATH) -> None:
        self._http_get = http_get or default_http_get
        self._clock = clock
        self._catalog_path = catalog_path
        self._catalog: Optional[dict[str, Any]] = None
        self._cache = ResponseCache(clock, ttl_seconds, CACHE_ENTRIES)
        self._guard = threading.Lock()
        self.requests_this_session = 0

    # --- key and catalog -------------------------------------------------------------------------

    def _key(self) -> str:
        return os.environ.get(self.info.key_env, "").strip()

    def configured(self) -> bool:
        return bool(self._key())

    def catalog(self) -> dict[str, Any]:
        if self._catalog is None:
            self._catalog = build_catalog(json.loads(self._catalog_path.read_text(encoding="utf-8")))
        return self._catalog

    def _endpoint(self, endpoint_id: str) -> dict[str, Any]:
        for endpoint in self.catalog()["endpoints"]:
            if endpoint["id"] == endpoint_id:
                return endpoint
        raise KeyError(endpoint_id)

    # --- query ---------------------------------------------------------------------------------------

    def query(self, endpoint_id: str, params: Params, refresh: bool = False) -> dict[str, Any]:
        endpoint = self._endpoint(endpoint_id)
        clean = validate_params(endpoint, params)
        # JSON is Alpha Vantage's default, so ``datatype`` is never sent: the public demo key only
        # answers the documented example URLs exactly, and this keeps requests identical to them.
        sent = {"function": endpoint_id, **clean}
        key = self._key()
        if not key:
            return self._response(endpoint, sent, "not_configured", f"No API key is set. Add {self.info.key_env} to the backend's environment or .env file and restart it.")
        cache_key = json.dumps([endpoint_id, sent], sort_keys=True)
        if not refresh and (hit := self._cache.get(cache_key)) is not None:
            return hit
        with self._cache.lock(cache_key):
            if not refresh and (hit := self._cache.get(cache_key)) is not None:
                return hit  # another thread fetched the same thing while this one waited
            response = self._fetch(endpoint, sent, key)
            if response["status"] in ("ok", "empty"):
                self._cache.put(cache_key, response)
            return response

    def _fetch(self, endpoint: dict[str, Any], sent: dict[str, Any], key: str) -> dict[str, Any]:
        query: list[tuple[str, str]] = []
        for name, value in sent.items():
            query.extend((name, v) for v in (value if isinstance(value, list) else [value]))
        query.append(("apikey", key))
        started = time.perf_counter()
        with self._guard:
            self.requests_this_session += 1
        try:
            result = self._http_get(QUERY_URL, query)
        except requests.Timeout:
            return self._response(endpoint, sent, "upstream_error", "Alpha Vantage did not respond in time.", key=key)
        except ValueError:
            return self._response(endpoint, sent, "upstream_error", "Alpha Vantage returned an unexpectedly large response.", key=key)
        except requests.RequestException:
            return self._response(endpoint, sent, "upstream_error", "Could not reach Alpha Vantage (network error).", key=key)
        elapsed = int((time.perf_counter() - started) * 1000)
        if result.status != 200:
            return self._response(endpoint, sent, "upstream_error", f"Alpha Vantage answered with HTTP {result.status}.", key=key, elapsed=elapsed, size=len(result.body))
        return self._interpret(endpoint, sent, key, result, elapsed)

    def _interpret(self, endpoint: dict[str, Any], sent: dict[str, Any], key: str, result: HttpResult, elapsed: int) -> dict[str, Any]:
        text = result.body.decode("utf-8", errors="replace")
        size = len(result.body)
        csv_only = False
        try:
            payload: Any = json.loads(text)
        except ValueError:
            records = _csv_records(text)
            if records is None:
                return self._response(endpoint, sent, "upstream_error", "Alpha Vantage returned a response that could not be read.", key=key, elapsed=elapsed, size=size)
            payload, csv_only = records, True
        status, message = ("empty", "The provider returned no rows for these parameters.") if csv_only and not payload else classify(payload)
        if status not in ("ok",):
            return self._response(endpoint, sent, status, message, key=key, elapsed=elapsed, size=size)
        built, notes = build_views(endpoint["id"], payload, endpoint["title"])
        if not built:
            return self._response(endpoint, sent, "empty", "The provider returned data, but nothing in it could be drawn.", key=key, elapsed=elapsed, size=size)
        raw: Any = None
        omitted: Optional[dict[str, Any]] = None
        if csv_only:
            omitted = {"bytes": size, "reason": "CSV response; its rows are shown in the table."}
        elif size <= RAW_LIMIT_BYTES:
            raw = payload
        else:
            omitted = {"bytes": size, "reason": f"The response is {size / 1024:,.0f} KB, too large to include here."}
        return self._response(endpoint, sent, "ok", None, key=key, elapsed=elapsed, size=size, views=built, raw=raw, omitted=omitted, notes=notes)

    def _response(self, endpoint: dict[str, Any], sent: dict[str, Any], status: str, message: Optional[str], *, key: str = "", elapsed: int = 0, size: int = 0, views: Optional[list[dict[str, Any]]] = None, raw: Any = None, omitted: Optional[dict[str, Any]] = None, notes: Optional[list[str]] = None) -> dict[str, Any]:
        response = {
            "provider": self.info.id,
            "endpoint": endpoint["id"],
            "title": endpoint["title"],
            "status": status,
            "message": (message or "")[:400] or None,
            "cached": False,
            "fetched_at": int(self._clock()) if status != "not_configured" else None,
            "elapsed_ms": elapsed,
            "bytes": size,
            "params": sent,
            "views": views or [],
            "raw": raw,
            "raw_omitted": omitted,
            "notes": notes or [],
        }
        return scrub(response, key)
