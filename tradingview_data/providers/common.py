"""Pieces every provider shares: one guarded GET, parameter validation, a small TTL cache, key scrubbing.

Nothing here knows a particular provider. Providers pass their own forbidden and long-text parameter
names to :func:`validate_params`, and their own clock and TTL to :class:`ResponseCache`.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import threading
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Collection, Mapping, Optional
from urllib.parse import quote

import requests

from .. import __version__
from .base import Params

MAX_BODY_BYTES = 25 * 1024 * 1024
USER_AGENT = f"tradingview-data-grabber/{__version__} (research dashboard)"


@dataclass(frozen=True)
class HttpResult:
    status: int
    body: bytes
    content_type: str


# ``(url, query)``, plus an optional ``headers=`` keyword for providers that authenticate with headers.
HttpGet = Callable[..., HttpResult]


def default_http_get(url: str, params: list[tuple[str, str]], headers: Optional[Mapping[str, str]] = None) -> HttpResult:
    """One GET: no redirects, bounded time and size. Raises ``requests`` exceptions or ``ValueError`` (too large)."""

    sent = {"User-Agent": USER_AGENT, "Accept": "application/json, text/csv", **(headers or {})}
    with requests.get(url, params=params, headers=sent, timeout=(5, 60), allow_redirects=False, stream=True) as response:
        chunks, size = [], 0
        for chunk in response.iter_content(chunk_size=65536):
            size += len(chunk)
            if size > MAX_BODY_BYTES:
                raise ValueError("response too large")
            chunks.append(chunk)
        return HttpResult(response.status_code, b"".join(chunks), response.headers.get("content-type", ""))


def first_sentence(text: str, limit: int = 200) -> str:
    sentence = re.split(r"(?<=[.!?])\s", text.strip(), maxsplit=1)[0]
    return sentence if len(sentence) <= limit else sentence[: limit - 1].rstrip() + "\u2026"


def key_fingerprint(key: str) -> str:
    """A short digest that scopes cached responses to the key that fetched them, so a different key
    (or the same account on another plan) never reads them. The key itself is never part of a cache key."""

    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def scrub(response: dict[str, Any], key: str) -> dict[str, Any]:
    """Removes the API key from anything that could echo it. Keys under 8 characters (the public
    ``demo`` key) are not scrubbed: they would garble ordinary words and protect nothing."""

    if len(key) < 8:
        return response
    text = json.dumps(response)
    return json.loads(text.replace(key, "***")) if key in text else response


# --- parameters ------------------------------------------------------------------------------------

_PATH_VALUE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-^=]{0,63}$")
_ISO_MOMENT = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:T(\d{2}):(\d{2})(?::(\d{2})(?:\.\d{1,9})?)?(?:Z|[+-](\d{2}):?(\d{2}))?)?$")


def validate_params(endpoint: dict[str, Any], params: Params, *, forbidden: Collection[str] = (), long_text: Collection[str] = ()) -> dict[str, Any]:
    """Checks ``params`` against the endpoint's documented parameters and returns the cleaned values.

    Raises ``ValueError`` with a plain message. Empty optional values are dropped. Enums are strict
    only where the documentation states the accepted values; repeated parameters (for example a date
    range) are free text because the provider also accepts relative values such as ``6month``.
    ``forbidden`` names are set by the server. A parameter the catalog marks ``in: path`` ends up in
    the URL path, so its value is restricted to characters that cannot change the path (a
    ``datetime`` is held to the strict ISO-8601 grammar instead, which has no such characters).
    """

    known = {p["name"]: p for p in endpoint["params"]}
    clean: dict[str, Any] = {}
    for name, value in params.items():
        if name.lower() in forbidden:
            raise ValueError(f"{name} is set by the server and cannot be passed")
        spec = known.get(name)
        if spec is None or spec["managed"]:
            raise ValueError(f"Unknown parameter {name!r} for {endpoint['id']}")
        multiple = bool(spec["multiple"])
        if isinstance(value, list) and not multiple:
            raise ValueError(f"{name} takes a single value")
        values = [str(v).strip() for v in (value if isinstance(value, list) else [value])]
        values = [v for v in values if v]
        if not values:
            continue
        limit = 2000 if name in long_text else 200
        for v in values:
            if len(v) > limit:
                raise ValueError(f"{name} is too long (limit {limit} characters)")
            if not multiple:
                check_type(name, spec, v)
            if spec.get("in") == "path" and not (spec["type"] == "datetime" and not multiple) and not _PATH_VALUE.match(v):
                raise ValueError(f"{name} may contain only letters, digits and . _ - ^ =")
        clean[name] = values if multiple else values[0]
    for name, spec in known.items():
        if spec["required"] and not spec["managed"] and name not in clean:
            raise ValueError(f"{name} is required")
    return clean


def check_type(name: str, spec: dict[str, Any], value: str) -> None:
    kind = spec["type"]
    if kind == "enum" and value not in spec["enum"]:
        raise ValueError(f"{name} must be one of: {', '.join(spec['enum'])}")
    if kind == "boolean" and value not in ("true", "false"):
        raise ValueError(f"{name} must be true or false")
    if kind in ("number", "integer"):
        try:
            number = float(value)
            ok = math.isfinite(number) and (kind == "number" or number == int(number))
        except ValueError:
            ok = False
        if not ok:
            raise ValueError(f"{name} must be {'a whole number' if kind == 'integer' else 'a number'}")
        low, high = spec.get("minimum"), spec.get("maximum")
        if low is not None and number < low:
            raise ValueError(f"{name} must be at least {low:g}")
        if high is not None and number > high:
            raise ValueError(f"{name} must be at most {high:g}")
    if kind == "date":
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            raise ValueError(f"{name} must be a date in YYYY-MM-DD format") from None
    if kind == "datetime" and not valid_moment(value):
        raise ValueError(f"{name} must be a date (YYYY-MM-DD) or an ISO-8601 timestamp such as 2020-05-21T00:00:00+0000")
    if kind == "month":
        try:
            datetime.strptime(value, "%Y-%m")
        except ValueError:
            raise ValueError(f"{name} must be a month in YYYY-MM format") from None


def valid_moment(value: str) -> bool:
    """A calendar date, optionally followed by ``T`` and a time (seconds, fraction and ``Z`` or a
    ``+HH:MM`` / ``+HHMM`` offset are optional): ``2020-05-21`` or ``2020-05-21T00:00:00+0000``."""

    match = _ISO_MOMENT.match(value)
    if not match:
        return False
    try:
        datetime.strptime(match.group(1), "%Y-%m-%d")
    except ValueError:
        return False
    hour, minute, second, zone_hour, zone_minute = (int(g) if g is not None else 0 for g in match.groups()[1:])
    return hour <= 23 and minute <= 59 and second <= 59 and zone_hour <= 23 and zone_minute <= 59


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


# --- cache ---------------------------------------------------------------------------------------------


class ResponseCache:
    """A small TTL cache plus one lock per key, so concurrent identical requests make one upstream call."""

    def __init__(self, clock: Callable[[], float], ttl_seconds: float, entries: int = 32) -> None:
        self._clock = clock
        self._ttl = ttl_seconds
        self._entries = entries
        self._items: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def get(self, key: str) -> Optional[dict[str, Any]]:
        with self._guard:
            entry = self._items.get(key)
            if entry is None or self._clock() - entry[0] >= self._ttl:
                self._items.pop(key, None)
                return None
            return {**entry[1], "cached": True}

    def put(self, key: str, response: dict[str, Any]) -> None:
        with self._guard:
            self._items[key] = (self._clock(), response)
            while len(self._items) > self._entries:
                self._items.popitem(last=False)

    def lock(self, key: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(key, threading.Lock())
