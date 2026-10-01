"""Marketstack v2: the endpoint catalog (generated from its OpenAPI document) and a guarded query path.

The access key is read from ``MARKETSTACK_API_KEY`` at call time and goes only into the upstream
request (Marketstack takes it as the ``access_key`` query parameter). It is never stored, logged,
cached, put in a URL we report, or returned: every message and the final response are scrubbed.
Nothing is fetched until ``query`` is called, a missing key makes ``query`` answer
``not_configured`` without touching the network, and only successful responses are cached (free
keys allow 100 requests a month).

Unlike Alpha Vantage, Marketstack reports problems with an HTTP error status and an
``{"error": {"code", "type", "info"}}`` body. A plan that lacks an endpoint gets
``function_access_restricted`` (HTTP 403), which is reported as ``premium_required``.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import quote

import requests

from .base import Params, Plan, Provider, ProviderInfo
from .common import HttpGet, HttpResult, ResponseCache, default_http_get, first_sentence, key_fingerprint, scrub, validate_params as _validate
from .marketstack_views import build_views

BASE_URL = "https://api.marketstack.com"
CATALOG_PATH = Path(__file__).with_name("marketstack_catalog.json")
RAW_LIMIT_BYTES = 400 * 1024
CACHE_TTL_SECONDS = 300.0
CACHE_ENTRIES = 32
_FORBIDDEN = {"access_key"}
_LONG_TEXT = {"symbols"}

INFO = ProviderInfo(
    id="marketstack",
    name="Marketstack",
    description="End-of-day and intraday stock prices, exchanges, tickers, splits and dividends, indices, bonds, ETF holdings, commodities, analyst ratings and SEC EDGAR company data.",
    website="https://marketstack.com/",
    docs_url="https://docs.apilayer.com/marketstack/docs/marketstack-api-v2-v-2-0-0",
    key_env="MARKETSTACK_API_KEY",
    key_url="https://marketstack.com/signup/free",
    limits_note="Free keys allow 100 requests per month, end-of-day data only, with 1 year of history (Marketstack pricing page). Paid plans raise the limit and unlock the premium endpoints; ETF endpoints count as 20 requests.",
    plans=(
        Plan("Free", "100 requests a month. End-of-day data with 1 year of history, splits and dividends, tickers, exchanges, currencies and timezones."),
        Plan("Basic", "10,000 requests a month and 10 years of history. Adds US intraday data (IEX), market indices, bonds and ETF holdings."),
        Plan("Professional", "100,000 requests a month and 15+ years of history. Adds real-time updates (intraday below 15 minutes), real-time stock prices and commodities."),
        Plan("Business", "500,000 requests a month. Adds analyst ratings, company details and SEC EDGAR company data."),
    ),
)

# Marketstack's error ``type`` -> our status. Anything else is decided by the HTTP status.
_ERROR_TYPES = {
    "invalid_access_key": "invalid_key",
    "missing_access_key": "invalid_key",
    "inactive_user": "invalid_key",
    "account_on_hold": "invalid_key",
    "api_access_blocked": "invalid_key",
    "function_access_restricted": "premium_required",
    "https_access_restricted": "premium_required",
    "usage_limit_reached": "rate_limited",
    "daily_usage_limit_reached": "rate_limited",
    "fair_use_limit_reached": "rate_limited",
    "rate_limit_reached": "rate_limited",
    "invalid_api_function": "invalid_request",
    "404_not_found": "invalid_request",
    "internal_error": "upstream_error",
    "maintenance_mode": "upstream_error",
}
_ERROR_CODES = {101: "invalid_key", 102: "invalid_key", 103: "invalid_request", 104: "rate_limited", 105: "premium_required", 106: "rate_limited", 107: "invalid_key"}
_HTTP_STATUSES = {400: "invalid_request", 401: "invalid_key", 403: "premium_required", 404: "invalid_request", 422: "invalid_request", 429: "rate_limited"}


def build_catalog(raw: dict[str, Any]) -> dict[str, Any]:
    """The contract's catalog from the generated JSON; request paths stay server-side."""

    endpoints = []
    for item in raw["endpoints"]:
        params = [{**{k: p.get(k) for k in ("name", "required", "type", "description", "enum", "enum_labels", "suggestions", "default", "example", "multiple", "premium_note", "minimum", "maximum", "premium_values")}, "managed": False} for p in item["params"]]
        endpoints.append(
            {
                "id": item["id"],
                "title": item["title"],
                "category": item["category"],
                "description": item["description"],
                "summary": first_sentence(item["description"]) if item["description"] else item["title"],
                "premium": item["premium"],
                "trending": item["trending"],
                "utility": item["utility"],
                "premium_notes": item["premium_notes"],
                "plan": item["plan"],
                "request_cost": item["request_cost"],
                "doc_url": raw["source"],
                "params": params,
                "examples": item["examples"],
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


def request_target(endpoint: dict[str, Any], clean: dict[str, Any]) -> tuple[str, list[tuple[str, str]]]:
    """The URL path with its parameters filled in, and the remaining parameters as a query string."""

    path = endpoint["path"]
    query: list[tuple[str, str]] = []
    for spec in endpoint["params"]:
        value = clean.get(spec["name"])
        if value is None:
            continue
        if spec["in"] == "path":
            path = path.replace("{" + spec["name"] + "}", quote(str(value), safe=""))
        else:
            query.append((spec["name"], str(value)))
    return path, query


def _error_text(error: dict[str, Any]) -> str:
    text = str(error.get("info") or error.get("message") or error.get("type") or error.get("code") or "")
    context = error.get("context")
    if isinstance(context, dict):
        details = [str(item.get("message")) for items in context.values() for item in (items if isinstance(items, list) else []) if isinstance(item, dict) and item.get("message")]
        if details:
            text = f"{text} {' '.join(details)}".strip()
    return text


def classify_error(http_status: int, payload: Any) -> Optional[tuple[str, str]]:
    """``(status, message)`` when the response is a Marketstack error, ``None`` when it is data."""

    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict):
        code = error.get("code")
        status = _ERROR_TYPES.get(str(error.get("type"))) or (_ERROR_CODES.get(code) if isinstance(code, int) else None) or _HTTP_STATUSES.get(http_status) or ("upstream_error" if http_status >= 500 else "invalid_request")
        return status, _error_text(error) or f"Marketstack answered with HTTP {http_status}."
    if http_status != 200:
        status = _HTTP_STATUSES.get(http_status) or ("upstream_error" if http_status >= 500 else "invalid_request")
        return status, f"Marketstack answered with HTTP {http_status}."
    return None


def has_data(payload: Any) -> bool:
    """False for an empty body or one whose only content is pagination or status bookkeeping."""

    if isinstance(payload, dict):
        return any(not _blank(v) for k, v in payload.items() if k not in ("pagination", "status", "success"))
    return not _blank(payload)


def _blank(value: Any) -> bool:
    if isinstance(value, dict):
        return all(_blank(v) for v in value.values())
    return value in (None, "", [])


class Marketstack(Provider):
    info = INFO

    def __init__(self, http_get: Optional[HttpGet] = None, clock: Callable[[], float] = time.time, ttl_seconds: float = CACHE_TTL_SECONDS, catalog_path: Path = CATALOG_PATH) -> None:
        self._http_get = http_get or default_http_get
        self._clock = clock
        self._catalog_path = catalog_path
        self._raw: Optional[dict[str, Any]] = None
        self._catalog: Optional[dict[str, Any]] = None
        self._cache = ResponseCache(clock, ttl_seconds, CACHE_ENTRIES)
        self._guard = threading.Lock()
        self.requests_this_session = 0

    # --- key and catalog -------------------------------------------------------------------------

    def _key(self) -> str:
        return os.environ.get(self.info.key_env, "").strip()

    def configured(self) -> bool:
        return bool(self._key())

    def _load(self) -> dict[str, Any]:
        if self._raw is None:
            self._raw = json.loads(self._catalog_path.read_text(encoding="utf-8"))
        return self._raw

    def catalog(self) -> dict[str, Any]:
        if self._catalog is None:
            self._catalog = build_catalog(self._load())
        return self._catalog

    def _endpoint(self, endpoint_id: str) -> dict[str, Any]:
        """The generated entry, which (unlike the public catalog) knows its request path."""

        for endpoint in self._load()["endpoints"]:
            if endpoint["id"] == endpoint_id:
                return {**endpoint, "params": [{**p, "managed": False} for p in endpoint["params"]]}
        raise KeyError(endpoint_id)

    # --- query ---------------------------------------------------------------------------------------

    def query(self, endpoint_id: str, params: Params, refresh: bool = False) -> dict[str, Any]:
        endpoint = self._endpoint(endpoint_id)
        clean = _validate(endpoint, params, forbidden=_FORBIDDEN, long_text=_LONG_TEXT)
        path, query = request_target(endpoint, clean)
        sent = {"endpoint": path, **dict(query)}
        key = self._key()
        if not key:
            return self._response(endpoint, sent, "not_configured", f"No API key is set. Add {self.info.key_env} to the backend's environment or .env file and restart it.")
        cache_key = json.dumps([key_fingerprint(key), endpoint_id, sent], sort_keys=True)
        if not refresh and (hit := self._cache.get(cache_key)) is not None:
            return hit
        with self._cache.lock(cache_key):
            if not refresh and (hit := self._cache.get(cache_key)) is not None:
                return hit  # another thread fetched the same thing while this one waited
            response = self._fetch(endpoint, sent, path, query, key)
            if response["status"] in ("ok", "empty"):
                self._cache.put(cache_key, response)
            return response

    def _fetch(self, endpoint: dict[str, Any], sent: dict[str, Any], path: str, query: list[tuple[str, str]], key: str) -> dict[str, Any]:
        started = time.perf_counter()
        with self._guard:
            self.requests_this_session += 1
        try:
            result = self._http_get(BASE_URL + path, [*query, ("access_key", key)])
        except requests.Timeout:
            return self._response(endpoint, sent, "upstream_error", "Marketstack did not respond in time.", key=key)
        except ValueError:
            return self._response(endpoint, sent, "upstream_error", "Marketstack returned an unexpectedly large response.", key=key)
        except requests.RequestException:
            return self._response(endpoint, sent, "upstream_error", "Could not reach Marketstack (network error).", key=key)
        elapsed = int((time.perf_counter() - started) * 1000)
        return self._interpret(endpoint, sent, key, result, elapsed)

    def _interpret(self, endpoint: dict[str, Any], sent: dict[str, Any], key: str, result: HttpResult, elapsed: int) -> dict[str, Any]:
        size = len(result.body)
        try:
            payload: Any = json.loads(result.body.decode("utf-8", errors="replace"))
        except ValueError:
            payload = None
            if result.status == 200:
                return self._response(endpoint, sent, "upstream_error", "Marketstack returned a response that could not be read.", key=key, elapsed=elapsed, size=size)
        failure = classify_error(result.status, payload)
        if failure:
            return self._response(endpoint, sent, failure[0], failure[1], key=key, elapsed=elapsed, size=size)
        if not has_data(payload):
            return self._response(endpoint, sent, "empty", "The provider returned no data for these parameters.", key=key, elapsed=elapsed, size=size)
        built, notes = build_views(endpoint["id"], payload, endpoint["title"])
        if not built:
            return self._response(endpoint, sent, "empty", "The provider returned no rows for these parameters.", key=key, elapsed=elapsed, size=size)
        omitted: Optional[dict[str, Any]] = None
        raw: Any = None
        if size <= RAW_LIMIT_BYTES:
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
