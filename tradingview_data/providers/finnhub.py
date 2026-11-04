"""Finnhub: the endpoint catalog (generated from its OpenAPI document by ``finnhub_docs``) and a guarded query path.

The API key is read from ``FINNHUB_API_KEY`` at call time and goes only into the upstream request, in the
``X-Finnhub-Token`` header (Finnhub accepts it there as well as in the ``token`` query parameter), so it appears in no
URL we build, log or report. It is never stored, logged, cached or returned: every message and the final response are
scrubbed. Nothing is fetched until ``query`` is called, a missing key makes ``query`` answer ``not_configured`` without
touching the network, and only successful responses are cached.

Finnhub reports problems as ``{"error": "..."}``, usually with an HTTP error status. Its status is not reliable on its
own: a plan refusal comes as HTTP 403 or 401 (non-US exchanges on a free key) and sometimes as HTTP 200 (``Market data
subscription required for CFD indices.``), so the message decides. Some endpoints answer a symbol they do not know with
data-shaped zeros rather than an error (an all-zero quote); those are reported as ``empty``.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import urlsplit

import requests

from .base import Params, Plan, Provider, ProviderInfo
from .common import HttpGet, HttpResult, ResponseCache, default_http_get, first_sentence, key_fingerprint, request_target, scrub, validate_params as _validate
from .finnhub_docs import fill_dates
from .finnhub_views import build_views

BASE_URL = "https://finnhub.io/api/v1"
CATALOG_PATH = Path(__file__).with_name("finnhub_catalog.json")
RAW_LIMIT_BYTES = 400 * 1024
CACHE_TTL_SECONDS = 30.0
CACHE_ENTRIES = 32
_FORBIDDEN = {"token"}
_PUBLIC_PARAM_KEYS = ("name", "required", "type", "description", "enum", "enum_labels", "suggestions", "default", "example", "multiple", "premium_note", "minimum", "maximum", "premium_values")

# Checked in this order against Finnhub's message, then the HTTP status decides.
_KEY_PROBLEM = re.compile(r"invalid api ?key|use an api ?key|api ?key.{0,20}(invalid|missing|required)", re.I)
_RATE_LIMIT = re.compile(r"limit reached|rate limit|too many requests", re.I)
_PREMIUM = re.compile(r"(don't|do not) have access|subscription required|premium|upgrade", re.I)
_NO_ACCESS = re.compile(r"(don't|do not) have access to this resource", re.I)
_HTTP_STATUSES = {400: "invalid_request", 401: "invalid_key", 402: "premium_required", 403: "premium_required", 404: "invalid_request", 422: "invalid_request", 429: "rate_limited"}
# Fields that only echo the request: a response holding nothing else has no data.
_ECHO_FIELDS = {"symbol", "ticker", "cik", "exchange", "timezone", "metricType", "count", "s"}
_QUOTE_FIELDS = {"c", "d", "dp", "h", "l", "o", "pc", "t"}
_REDIRECTS = {301, 302, 303, 307, 308}

INFO = ProviderInfo(
    id="finnhub",
    name="Finnhub",
    description="Real-time US quotes, company news, basic financials, recommendation trends, EPS surprises, earnings and IPO calendars, insider trades and sentiment, SEC filings and as-reported statements, plus alternative data (lobbying, government spending, H-1B visas, patents) and, on paid plans, candles, estimates, ETFs, funds, bonds and economic data.",
    website="https://finnhub.io/",
    docs_url="https://finnhub.io/docs/api/",
    key_env="FINNHUB_API_KEY",
    key_url="https://finnhub.io/register",
    limits_note="Free keys allow 60 requests per minute (and at most 30 per second) and open 29 endpoints, for US-listed symbols and US exchanges only: a symbol listed elsewhere is refused. Company news reaches about a year back and the earnings calendar 30 days; candles (price history) need a paid plan. Results are cached for 30 seconds because quotes are real time.",
    plans=(
        Plan("Free", "60 requests a minute. Real-time US quotes, company profiles, market and company news (1 year), basic financials, recommendation trends, EPS surprises (last 4 quarters), the earnings (1 month back) and IPO calendars, insider transactions and sentiment, SEC filings and financials as reported, peers, symbol lists and some alternative data."),
        Plan("All-in-One", "$3,500 a month, billed annually: 900 market-data and 300 fundamental requests a minute and global coverage. Adds candles and tick data, standardised statements, dividends, ownership, estimates, price targets, ETFs, indices, mutual funds, bonds, ESG, social sentiment and economic data. Earnings call transcripts are not included. Finnhub also sells narrower packages (for example Fundamental data)."),
    ),
)


def build_catalog(raw: dict[str, Any], today: date) -> dict[str, Any]:
    """The contract's catalog from the generated JSON, with date placeholders filled in for ``today``; request paths
    stay server-side."""

    endpoints = []
    for item in raw["endpoints"]:
        params = [{**{k: p.get(k) for k in _PUBLIC_PARAM_KEYS}, "managed": False} for p in fill_dates(item["params"], today)]
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
                "doc_url": item["doc_url"],
                "params": params,
                "examples": fill_dates(item["examples"], today),
            }
        )
    categories = [
        {**c, "count": sum(1 for e in endpoints if e["category"] == c["id"]), "premium_count": sum(1 for e in endpoints if e["category"] == c["id"] and e["premium"])}
        for c in raw["categories"]
    ]
    return {"categories": categories, "endpoints": endpoints}


def _message_of(http_status: int, body: bytes, payload: Any) -> str:
    """Finnhub's own words: the ``error`` of a JSON body, else the body text (an HTML page is no message)."""

    text = payload.get("error") if isinstance(payload, dict) else payload if isinstance(payload, str) else None
    if text is None and payload is None:
        text = body.decode("utf-8", errors="replace")
    text = " ".join(str(text or "").split())
    return text if text and not text.startswith("<") else f"Finnhub answered with HTTP {http_status}."


def explain(message: str, plan: Optional[str]) -> str:
    """What a plan refusal means for this endpoint, then Finnhub's own message in brackets."""

    if not _NO_ACCESS.search(message):
        return message  # a specific message ("Market data subscription required for CFD indices.") says it already
    if plan == "Free":
        plain = "This endpoint is on Finnhub's free plan, but not for these parameters: a free key covers US-listed symbols and US exchanges only, and international data needs a paid plan."
    elif plan:
        plain = f"Your Finnhub plan does not include this endpoint. It is part of the {plan} plan."
    else:
        plain = "Your Finnhub plan does not include this endpoint, and no plan in Finnhub's pricing table does: it is sold separately."
    return f"{plain} (Finnhub: {message})"


def classify_error(http_status: int, body: bytes, payload: Any, plan: Optional[str] = None) -> Optional[tuple[str, str]]:
    """``(status, message)`` when the response is a Finnhub error, ``None`` when it is data."""

    failed = http_status != 200 or (isinstance(payload, dict) and isinstance(payload.get("error"), str))
    if not failed:
        return None
    message = _message_of(http_status, body, payload)
    for pattern, status in ((_KEY_PROBLEM, "invalid_key"), (_RATE_LIMIT, "rate_limited"), (_PREMIUM, "premium_required")):
        if pattern.search(message):
            return status, explain(message, plan) if status == "premium_required" else message
    return _HTTP_STATUSES.get(http_status) or ("upstream_error" if http_status >= 500 else "invalid_request"), message


def is_finnhub_file(url: str) -> bool:
    """True for an HTTPS address on Finnhub's own hosts (``static2.finnhub.io``)."""

    parts = urlsplit(url or "")
    host = (parts.hostname or "").lower()
    return parts.scheme == "https" and (host == "finnhub.io" or host.endswith(".finnhub.io"))


def is_blank_quote(payload: Any) -> bool:
    """Finnhub answers a symbol it does not cover with ``{"c": 0, ..., "t": 0}`` instead of an error."""

    return isinstance(payload, dict) and bool(payload) and set(payload) <= _QUOTE_FIELDS and not payload.get("t") and not payload.get("c")


def has_data(payload: Any) -> bool:
    """False for an empty answer: ``[]``, ``{}``, ``{"s": "no_data"}``, an all-zero quote, or an object that holds
    nothing but an echo of the request (``{"data": [], "symbol": "NVDA"}``)."""

    if isinstance(payload, dict):
        if payload.get("s") == "no_data" or is_blank_quote(payload):
            return False
        return any(_present(v) for k, v in payload.items() if k not in _ECHO_FIELDS)
    return _present(payload)


def _present(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_present(v) for v in value.values())
    if isinstance(value, list):
        return bool(value)
    return value not in (None, "")


class Finnhub(Provider):
    info = INFO

    def __init__(self, http_get: Optional[HttpGet] = None, clock: Callable[[], float] = time.time, ttl_seconds: float = CACHE_TTL_SECONDS, catalog_path: Path = CATALOG_PATH) -> None:
        self._http_get = http_get or default_http_get
        self._clock = clock
        self._catalog_path = catalog_path
        self._raw: Optional[dict[str, Any]] = None
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

    def _load(self) -> dict[str, Any]:
        if self._raw is None:
            self._raw = json.loads(self._catalog_path.read_text(encoding="utf-8"))
        return self._raw

    def catalog(self) -> dict[str, Any]:
        """Rebuilt when the UTC day changes, so a server that stays up for weeks still offers recent dates."""

        today = datetime.fromtimestamp(self._clock(), timezone.utc).date()
        if self._catalog is None or self._catalog_day != today:
            self._catalog, self._catalog_day = build_catalog(self._load(), today), today
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
        clean = _validate(endpoint, params, forbidden=_FORBIDDEN)
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
            result = self._http_get(BASE_URL + path, query, headers={"X-Finnhub-Token": key})
            if result.status in _REDIRECTS and is_finnhub_file(result.location):
                # Finnhub serves its largest lists (all US symbols) as a file on its static host. The address is
                # complete on its own, so it is fetched without the key, which never leaves for another host.
                result = self._http_get(result.location, [])
        except requests.Timeout:
            return self._response(endpoint, sent, "upstream_error", "Finnhub did not respond in time.", key=key)
        except ValueError:
            return self._response(endpoint, sent, "upstream_error", "Finnhub returned an unexpectedly large response.", key=key)
        except requests.RequestException:
            return self._response(endpoint, sent, "upstream_error", "Could not reach Finnhub (network error).", key=key)
        elapsed = int((time.perf_counter() - started) * 1000)
        return self._interpret(endpoint, sent, key, result, elapsed)

    def _interpret(self, endpoint: dict[str, Any], sent: dict[str, Any], key: str, result: HttpResult, elapsed: int) -> dict[str, Any]:
        size = len(result.body)
        if result.status in _REDIRECTS:
            return self._response(endpoint, sent, "upstream_error", "Finnhub answered with a redirect to an address outside finnhub.io, which was not followed.", key=key, elapsed=elapsed, size=size)
        try:
            payload: Any = json.loads(result.body.decode("utf-8", errors="replace"))
        except ValueError:
            payload = None
            if result.status == 200:
                return self._response(endpoint, sent, "upstream_error", "Finnhub returned a response that could not be read.", key=key, elapsed=elapsed, size=size)
        failure = classify_error(result.status, result.body, payload, endpoint["plan"])
        if failure:
            return self._response(endpoint, sent, failure[0], failure[1], key=key, elapsed=elapsed, size=size)
        if is_blank_quote(payload):
            return self._response(endpoint, sent, "empty", "Finnhub answered with an all-zero quote, which is how it answers a symbol it does not cover. Check the symbol (it is case sensitive, for example AAPL).", key=key, elapsed=elapsed, size=size)
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
