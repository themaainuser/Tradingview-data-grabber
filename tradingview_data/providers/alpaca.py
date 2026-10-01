"""Alpaca Market Data: the endpoint catalog (generated from its documentation) and a guarded query path.

Alpaca authenticates with a key ID and a secret, sent as the ``APCA-API-KEY-ID`` and
``APCA-API-SECRET-KEY`` headers. They are read from ``ALPACA_API_KEY_ID`` and
``ALPACA_API_SECRET_KEY`` at call time and go only into the upstream request. Neither is stored,
logged, cached, put in a URL we report, or returned: every message and the final response are
scrubbed. Nothing is fetched until ``query`` is called, missing credentials make ``query`` answer
``not_configured`` without touching the network, and only successful responses are cached.

This is the Market Data API only (host ``data.alpaca.markets``). It never places orders or reads an
account. Alpaca's two plans for individuals, Basic and Algo Trader Plus, differ in the feed, how
recent the data may be and the rate limit; a request the plan does not allow is answered with a
subscription error (HTTP 403 or 422) and reported as ``premium_required``.
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

import requests

from .alpaca_docs import BASIC, PLUS, fill_samples
from .alpaca_views import build_views
from .base import Params, Plan, Provider, ProviderInfo
from .common import HttpGet, HttpResult, ResponseCache, default_http_get, first_sentence, key_fingerprint, request_target, scrub, validate_params as _validate

BASE_URL = "https://data.alpaca.markets"
KEY_HEADER = "APCA-API-KEY-ID"
SECRET_HEADER = "APCA-API-SECRET-KEY"
CATALOG_PATH = Path(__file__).with_name("alpaca_catalog.json")
RAW_LIMIT_BYTES = 400 * 1024
CACHE_TTL_SECONDS = 30.0  # the data is real time, and Alpaca limits calls per minute rather than per month
CACHE_ENTRIES = 32
_FORBIDDEN = {"apca-api-key-id", "apca-api-secret-key"}
_LONG_TEXT = {"symbols", "isins", "cusips", "ids", "currency_pairs"}
_BOOKKEEPING = {"next_page_token", "symbol", "last_updated", "market_type", "currency"}
_PUBLIC_PARAM_KEYS = ("name", "required", "type", "description", "enum", "enum_labels", "suggestions", "default", "example", "multiple", "premium_note", "minimum", "maximum", "premium_values")

INFO = ProviderInfo(
    id="alpaca",
    name="Alpaca",
    description="Market data from Alpaca: US stocks and ETFs, options with the option chain and greeks, crypto, forex, fixed income, news, the most active stocks and top movers, and corporate actions.",
    website="https://alpaca.markets/",
    docs_url="https://docs.alpaca.markets/us/docs/getting-started",
    key_env="ALPACA_API_KEY_ID",
    secret_env="ALPACA_API_SECRET_KEY",
    key_url="https://app.alpaca.markets/signup",
    limits_note="Alpaca's Market Data API (no orders, no account data) needs a key ID and a secret from a free Alpaca account, paper or live. Basic is free; Algo Trader Plus costs $99 a month. The plans differ in the feed, how recent the data may be and the rate limit. Alpaca documents no separate tier for crypto, news, the screener, corporate actions, forex or fixed income.",
    plans=(
        Plan(BASIC, "Free, with 200 API calls a minute. Stocks: real-time IEX data, and SIP data from every US exchange once it is 15 minutes old. Options: the indicative feed, where quotes are modified and trades are delayed by 15 minutes. Every endpoint on this page is available."),
        Plan(PLUS, "$99 a month, with 10,000 API calls a minute. Adds the real-time SIP feed for every US exchange, with no 15-minute limit on recent data, and the real-time OPRA options feed."),
    ),
)

_HTTP_STATUSES = {400: "invalid_request", 401: "invalid_key", 403: "invalid_key", 404: "invalid_request", 422: "invalid_request", 429: "rate_limited"}
_PLAN_HINT = f"This needs the {PLUS} plan. On {BASIC}, use the IEX feed (stocks) or the indicative feed (options), or ask for data at least 15 minutes old."
_TIER_DEFAULTS = {
    "stock_latest": f"No feed was chosen, so Alpaca used the best one your plan allows: SIP with {PLUS}, IEX on {BASIC}.",
    "option_latest": f"No feed was chosen, so Alpaca used the best one your plan allows: OPRA with {PLUS}, the indicative feed on {BASIC}.",
    "stock_history": f"No end was given, so Alpaca ended the range at the latest data your plan allows: now with {PLUS}, 15 minutes ago on {BASIC}.",
    "option_history": f"No end was given, so Alpaca ended the range at the latest data your plan allows: now with {PLUS}, 15 minutes ago on {BASIC}.",
}
_TIER_PARAM = {"stock_latest": "feed", "option_latest": "feed", "stock_history": "end", "option_history": "end"}


def build_catalog(raw: dict[str, Any], today: Any) -> dict[str, Any]:
    """The contract's catalog from the generated JSON; request paths stay server-side. ``today`` is
    the UTC date that the sample-day placeholders in the examples are resolved against."""

    endpoints = []
    for item in raw["endpoints"]:
        params = [{**{k: p.get(k) for k in _PUBLIC_PARAM_KEYS}, "managed": False} for p in item["params"]]
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
                "examples": fill_samples(item["examples"], today),
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


def _message(payload: Any) -> str:
    return str(payload.get("message") or "").strip() if isinstance(payload, dict) else ""


def classify_error(http_status: int, payload: Any) -> Optional[tuple[str, str]]:
    """``(status, message)`` when the response is an Alpaca error, ``None`` when it is data.

    Alpaca answers errors with ``{"code": 42210000, "message": "..."}``; the first three digits of the
    code repeat the HTTP status. A message that mentions the subscription is a plan limit whatever the
    status is. A refused key can also come back as an HTML page from the gateway, so the body is optional.
    """

    if http_status == 200:
        return None
    text = _message(payload)
    if "subscription" in text.lower():
        return "premium_required", f"{text.rstrip('.')}. {_PLAN_HINT}"
    status = _HTTP_STATUSES.get(http_status) or ("upstream_error" if http_status >= 500 else "invalid_request")
    if status == "invalid_key":
        detail = f": {text.rstrip('.')}" if text else ""
        return status, f"Alpaca refused the credentials (HTTP {http_status}){detail}. Check that the key ID and secret are correct and belong together."
    if status == "rate_limited":
        return status, f"Alpaca's rate limit was reached{f': {text}' if text else ''}. Basic allows 200 calls a minute and {PLUS} 10,000; wait a minute and try again."
    return status, text or f"Alpaca answered with HTTP {http_status}."


def has_data(payload: Any) -> bool:
    """False for an empty body or one whose only content is paging or labelling bookkeeping."""

    if isinstance(payload, dict):
        return any(not _blank(v) for k, v in payload.items() if k not in _BOOKKEEPING)
    return not _blank(payload)


def _blank(value: Any) -> bool:
    if isinstance(value, dict):
        return all(_blank(v) for v in value.values())
    return value in (None, "", [])


class Alpaca(Provider):
    info = INFO

    def __init__(self, http_get: Optional[HttpGet] = None, clock: Callable[[], float] = time.time, ttl_seconds: float = CACHE_TTL_SECONDS, catalog_path: Path = CATALOG_PATH) -> None:
        self._http_get = http_get or default_http_get
        self._clock = clock
        self._catalog_path = catalog_path
        self._raw: Optional[dict[str, Any]] = None
        self._catalog: Optional[dict[str, Any]] = None
        self._catalog_day: Optional[Any] = None
        self._cache = ResponseCache(clock, ttl_seconds, CACHE_ENTRIES)
        self._guard = threading.Lock()
        self.requests_this_session = 0

    # --- credentials and catalog -----------------------------------------------------------------

    def _credentials(self) -> tuple[str, str]:
        return os.environ.get(self.info.key_env, "").strip(), os.environ.get(str(self.info.secret_env), "").strip()

    def configured(self) -> bool:
        return all(self._credentials())

    def _load(self) -> dict[str, Any]:
        if self._raw is None:
            self._raw = json.loads(self._catalog_path.read_text(encoding="utf-8"))
        return self._raw

    def catalog(self) -> dict[str, Any]:
        """Rebuilt when the UTC day changes, so a server that stays up for weeks still offers a recent day."""

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
        clean = _validate(endpoint, params, forbidden=_FORBIDDEN, long_text=_LONG_TEXT)
        path, query = request_target(endpoint, clean)
        sent = {"endpoint": path, **dict(query)}
        credentials = self._credentials()
        if not all(credentials):
            missing = " and ".join(name for name, value in zip((self.info.key_env, self.info.secret_env), credentials) if not value)
            return self._response(endpoint, sent, "not_configured", f"Alpaca credentials are missing. Add {missing} to the backend's environment or .env file and restart it.")
        cache_key = json.dumps([key_fingerprint(":".join(credentials)), endpoint_id, sent], sort_keys=True)
        if not refresh and (hit := self._cache.get(cache_key)) is not None:
            return hit
        with self._cache.lock(cache_key):
            if not refresh and (hit := self._cache.get(cache_key)) is not None:
                return hit  # another thread fetched the same thing while this one waited
            response = self._fetch(endpoint, sent, path, query, credentials)
            if response["status"] in ("ok", "empty"):
                self._cache.put(cache_key, response)
            return response

    def _fetch(self, endpoint: dict[str, Any], sent: dict[str, Any], path: str, query: list[tuple[str, str]], credentials: tuple[str, str]) -> dict[str, Any]:
        started = time.perf_counter()
        with self._guard:
            self.requests_this_session += 1
        headers = {KEY_HEADER: credentials[0], SECRET_HEADER: credentials[1]}
        try:
            result = self._http_get(BASE_URL + path, query, headers=headers)
        except requests.Timeout:
            return self._response(endpoint, sent, "upstream_error", "Alpaca did not respond in time.", credentials=credentials)
        except ValueError:
            return self._response(endpoint, sent, "upstream_error", "Alpaca returned an unexpectedly large response.", credentials=credentials)
        except requests.RequestException:
            return self._response(endpoint, sent, "upstream_error", "Could not reach Alpaca (network error).", credentials=credentials)
        elapsed = int((time.perf_counter() - started) * 1000)
        return self._interpret(endpoint, sent, credentials, result, elapsed)

    def _interpret(self, endpoint: dict[str, Any], sent: dict[str, Any], credentials: tuple[str, str], result: HttpResult, elapsed: int) -> dict[str, Any]:
        size = len(result.body)
        try:
            payload: Any = json.loads(result.body.decode("utf-8", errors="replace"))
        except ValueError:
            payload = None
            if result.status == 200:
                return self._response(endpoint, sent, "upstream_error", "Alpaca returned a response that could not be read.", credentials=credentials, elapsed=elapsed, size=size)
        failure = classify_error(result.status, payload)
        if failure:
            return self._response(endpoint, sent, failure[0], failure[1], credentials=credentials, elapsed=elapsed, size=size)
        if not has_data(payload):
            return self._response(endpoint, sent, "empty", "The provider returned no data for these parameters.", credentials=credentials, elapsed=elapsed, size=size)
        built, notes = build_views(endpoint["id"], payload, endpoint["title"])
        if not built:
            return self._response(endpoint, sent, "empty", "The provider returned no rows for these parameters.", credentials=credentials, elapsed=elapsed, size=size)
        omitted: Optional[dict[str, Any]] = None
        raw: Any = None
        if size <= RAW_LIMIT_BYTES:
            raw = payload
        else:
            omitted = {"bytes": size, "reason": f"The response is {size / 1024:,.0f} KB, too large to include here."}
        return self._response(endpoint, sent, "ok", None, credentials=credentials, elapsed=elapsed, size=size, views=built, raw=raw, omitted=omitted, notes=[*self._tier_notes(endpoint, sent), *notes, *self._paging_notes(payload)])

    @staticmethod
    def _tier_notes(endpoint: dict[str, Any], sent: dict[str, Any]) -> list[str]:
        rule = endpoint.get("tier_rule", "")
        return [_TIER_DEFAULTS[rule]] if rule in _TIER_DEFAULTS and _TIER_PARAM[rule] not in sent else []

    @staticmethod
    def _paging_notes(payload: Any) -> list[str]:
        token = payload.get("next_page_token") if isinstance(payload, dict) else None
        return [f"More data is available. Set page_token to {token} and fetch again to read the next page."] if token else []

    def _response(self, endpoint: dict[str, Any], sent: dict[str, Any], status: str, message: Optional[str], *, credentials: tuple[str, str] = ("", ""), elapsed: int = 0, size: int = 0, views: Optional[list[dict[str, Any]]] = None, raw: Any = None, omitted: Optional[dict[str, Any]] = None, notes: Optional[list[str]] = None) -> dict[str, Any]:
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
        for secret in credentials:
            response = scrub(response, secret)
        return response
