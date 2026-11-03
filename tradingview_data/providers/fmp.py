"""Financial Modeling Prep (FMP): the endpoint catalog (``fmp_catalog.py``) and a guarded query path.

The API key is read from ``FMP_API_KEY`` at call time and goes only into the upstream request, in the
``apikey`` header (FMP accepts the key there as well as in the query string), so it appears in no URL
we build, log or report. It is never stored, logged, cached or returned: every message and the final
response are scrubbed. Nothing is fetched until ``query`` is called, a missing key makes ``query``
answer ``not_configured`` without touching the network, and only successful responses are cached
(free keys allow 250 requests a day).

FMP reports problems with an HTTP error status and a plain-text or ``{"Error Message": ...}`` body.
A plan that lacks an endpoint, or a symbol or parameter value, gets HTTP 402 and is reported as
``premium_required``.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from datetime import date, datetime, timezone
from typing import Any, Callable, Optional

import requests

from .base import Params, Plan, Provider, ProviderInfo
from .common import HttpGet, HttpResult, ResponseCache, default_http_get, first_sentence, key_fingerprint, request_target, scrub, validate_params as _validate
from .fmp_catalog import CATEGORIES, DOCS_ROOT, ENDPOINTS, PAID_PLANS, fill_dates, plan_of
from .fmp_views import build_views

BASE_URL = "https://financialmodelingprep.com/stable"
RAW_LIMIT_BYTES = 400 * 1024
CACHE_TTL_SECONDS = 300.0
CACHE_ENTRIES = 32
_FORBIDDEN = {"apikey"}
_LONG_TEXT = {"symbols"}
_PUBLIC_PARAM_KEYS = ("name", "required", "type", "description", "enum", "enum_labels", "suggestions", "default", "example", "multiple", "premium_note", "minimum", "maximum", "premium_values")

# What FMP's message says, checked in this order: a limit message also tells you to upgrade, and an
# invalid-key message also mentions the plan, so the narrower patterns go first.
_KEY_PROBLEM = re.compile(r"invalid api ?key|missing api ?key|api ?key.{0,20}(invalid|missing|required)", re.I)
_RATE_LIMIT = re.compile(r"limit reach|rate limit|too many requests|requests? per (day|minute)|bandwidth", re.I)
_PREMIUM = re.compile(r"restricted endpoint|premium|subscription|upgrade|exclusive|special (endpoint|parameter)", re.I)
# FMP's "Premium Query Parameter" refusals name the parameter: the value is outside what the plan allows.
_REFUSED_VALUE = re.compile(r"value set for '(\w+)'", re.I)
_REFUSED_RANGE = re.compile(r"values for '(\w+)' must be between (\d+) and (\d+)", re.I)
_BOILERPLATE = re.compile(r"[\s.]*please visit our subscription page.*$", re.I)
_VALUE_HELP = {
    "symbol": "Your plan can query only a fixed list of symbols, and this one is not on it (a free Basic key has a short list of well-known ones).",
    "from": "Your plan can only start this far back: a free Basic key allows 30 days on calendars and latest SEC filings, and a year on SEC filings of one company. Use a later start date.",
    "date": "Your plan can only use a recent date here: a free Basic key allows the last 30 days.",
}
_HTTP_STATUSES = {400: "invalid_request", 401: "invalid_key", 402: "premium_required", 403: "premium_required", 404: "invalid_request", 422: "invalid_request", 429: "rate_limited"}

INFO = ProviderInfo(
    id="fmp",
    name="Financial Modeling Prep",
    description="Prices, financial statements, ratios, analyst estimates, calendars, news, ETFs, insider trades, SEC filings and economic data for stocks, indices, forex, crypto and commodities.",
    website="https://site.financialmodelingprep.com/",
    docs_url="https://site.financialmodelingprep.com/developer/docs",
    key_env="FMP_API_KEY",
    key_url="https://site.financialmodelingprep.com/register",
    limits_note="Free (Basic) keys allow 250 requests per day and 500 MB of data over a rolling 30 days. Beyond that, many endpoints are only partly open: a fixed list of well-known symbols, a cap on the rows per request (5 on statements) and a start date no more than 30 days back on calendars and latest SEC filings. A request outside a limit is refused as premium, and the form notes each limit beside its field. Paid plans are limited per minute instead and unlock the premium endpoints.",
    plans=(
        Plan("Basic", "The free plan: 250 requests a day. End-of-day prices, quotes, profiles, statements, ratios and analyst data for a fixed list of well-known symbols, with at most 5 statement periods per request; profiles for any US-traded symbol; search and some reference data for all."),
        Plan("Starter", "300 requests a minute and up to 5 years of history for US companies, with financial market news, crypto and forex."),
        Plan("Premium", "750 requests a minute and up to 30 years of history. Adds UK and Canadian coverage, intraday charts, technical indicators and corporate calendars."),
        Plan("Ultimate", "3,000 requests a minute and full history with global coverage. Adds earnings call transcripts, ETF and mutual fund holdings, 13F institutional holdings, 1-minute intraday charts and batch delivery."),
    ),
)


def build_catalog(today: date) -> dict[str, Any]:
    """The contract's catalog from the table in ``fmp_catalog``, with date placeholders filled in for ``today``."""

    endpoints = []
    for item in ENDPOINTS:
        params = [{**{k: p.get(k) for k in _PUBLIC_PARAM_KEYS}, "managed": False} for p in fill_dates(item["params"], today)]
        endpoints.append(
            {
                "id": item["id"],
                "title": item["title"],
                "category": item["category"],
                "description": item["description"],
                "summary": first_sentence(item["description"]),
                "premium": item["id"] in PAID_PLANS,
                "trending": item["trending"],
                "utility": item["utility"],
                "premium_notes": [],
                "plan": plan_of(item["id"]),
                "request_cost": 1,
                "doc_url": DOCS_ROOT + item["slug"],
                "params": params,
                "examples": fill_dates(item["examples"], today),
            }
        )
    categories = [
        {**c, "count": sum(1 for e in endpoints if e["category"] == c["id"]), "premium_count": sum(1 for e in endpoints if e["category"] == c["id"] and e["premium"])}
        for c in CATEGORIES
    ]
    return {"categories": categories, "endpoints": endpoints}


def _message_of(http_status: int, body: bytes, payload: Any) -> str:
    """FMP's own words for what went wrong: the ``Error Message`` of a JSON body, else the body text."""

    if isinstance(payload, dict):
        text = payload.get("Error Message") or payload.get("error") or payload.get("message")
    else:
        text = payload if isinstance(payload, str) else None
    if text is None and payload is None:
        text = body.decode("utf-8", errors="replace")
    text = " ".join(str(text or "").split())
    return text if text and not text.startswith("<") else f"FMP answered with HTTP {http_status}."  # an HTML error page is no message


def explain(message: str) -> str:
    """For a refused parameter value, what that means in plain words, then FMP's own message in brackets."""

    if (match := _REFUSED_RANGE.search(message)) and "Premium Query Parameter" in message:
        plain = f"Your plan allows at most {match.group(3)} {'row' if match.group(3) == '1' else 'rows'} for '{match.group(1)}' on this endpoint."
    elif (match := _REFUSED_VALUE.search(message)) and "Premium Query Parameter" in message and match.group(1) in _VALUE_HELP:
        plain = _VALUE_HELP[match.group(1)]
    else:
        return message
    return f"{plain} (Original message: {_BOILERPLATE.sub('', message).rstrip('.')}.)"


def classify_error(http_status: int, body: bytes, payload: Any) -> Optional[tuple[str, str]]:
    """``(status, message)`` when the response is an FMP error, ``None`` when it is data."""

    failed = http_status != 200 or (isinstance(payload, dict) and "Error Message" in payload)
    if not failed:
        return None
    message = _message_of(http_status, body, payload)
    plain = explain(message)
    for pattern, status in ((_KEY_PROBLEM, "invalid_key"), (_RATE_LIMIT, "rate_limited"), (_PREMIUM, "premium_required")):
        if pattern.search(message):
            return status, plain
    return _HTTP_STATUSES.get(http_status) or ("upstream_error" if http_status >= 500 else "invalid_request"), plain


def has_data(payload: Any) -> bool:
    """False for an empty array, object or string: FMP answers ``[]`` when nothing matches."""

    if isinstance(payload, dict):
        return any(has_data(v) for v in payload.values())
    if isinstance(payload, list):
        return bool(payload)
    return payload not in (None, "")


class FinancialModelingPrep(Provider):
    info = INFO

    def __init__(self, http_get: Optional[HttpGet] = None, clock: Callable[[], float] = time.time, ttl_seconds: float = CACHE_TTL_SECONDS) -> None:
        self._http_get = http_get or default_http_get
        self._clock = clock
        self._catalog: Optional[dict[str, Any]] = None
        self._catalog_day: Optional[date] = None
        self._cache = ResponseCache(clock, ttl_seconds, CACHE_ENTRIES)
        self._guard = threading.Lock()
        self.requests_this_session = 0

    # --- key and catalog -------------------------------------------------------------------------

    def _key(self) -> str:
        return os.environ.get(self.info.key_env, "").strip()

    def configured(self) -> bool:
        return bool(self._key())

    def catalog(self) -> dict[str, Any]:
        """Rebuilt when the UTC day changes, so a server that stays up for weeks still offers recent dates."""

        today = datetime.fromtimestamp(self._clock(), timezone.utc).date()
        if self._catalog is None or self._catalog_day != today:
            self._catalog, self._catalog_day = build_catalog(today), today
        return self._catalog

    def _endpoint(self, endpoint_id: str) -> dict[str, Any]:
        """The table entry, which (unlike the public catalog) knows its request path."""

        for item in ENDPOINTS:
            if item["id"] == endpoint_id:
                return {**item, "params": [{**p, "managed": False} for p in item["params"]]}
        raise KeyError(endpoint_id)

    # --- query -------------------------------------------------------------------------------------

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
            result = self._http_get(BASE_URL + path, query, headers={"apikey": key})
        except requests.Timeout:
            return self._response(endpoint, sent, "upstream_error", "Financial Modeling Prep did not respond in time.", key=key)
        except ValueError:
            return self._response(endpoint, sent, "upstream_error", "Financial Modeling Prep returned an unexpectedly large response.", key=key)
        except requests.RequestException:
            return self._response(endpoint, sent, "upstream_error", "Could not reach Financial Modeling Prep (network error).", key=key)
        elapsed = int((time.perf_counter() - started) * 1000)
        return self._interpret(endpoint, sent, key, result, elapsed)

    def _interpret(self, endpoint: dict[str, Any], sent: dict[str, Any], key: str, result: HttpResult, elapsed: int) -> dict[str, Any]:
        size = len(result.body)
        try:
            payload: Any = json.loads(result.body.decode("utf-8", errors="replace"))
        except ValueError:
            payload = None
            if result.status == 200:
                return self._response(endpoint, sent, "upstream_error", "Financial Modeling Prep returned a response that could not be read.", key=key, elapsed=elapsed, size=size)
        failure = classify_error(result.status, result.body, payload)
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
