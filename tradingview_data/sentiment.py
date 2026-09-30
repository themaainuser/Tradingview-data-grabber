"""Crypto Fear & Greed index from CoinMarketCap's public chart endpoint (no API key).

CoinMarketCap's documented API (``pro-api.coinmarketcap.com/v3/fear-and-greed``) requires a key.
The website's own chart page, however, reads the same index from an unauthenticated JSON route,
``api.coinmarketcap.com/data-api/v3/fear-greed/chart``, which this module uses. That route is not a
published, versioned API: it can change, be rate limited or be withdrawn without notice, and
CoinMarketCap's terms of use apply to the data. So this module

* never invents a value: when the route cannot be read the service raises
  :class:`SentimentUnavailable` (or serves the last good data, clearly flagged ``stale``);
* identifies itself honestly with its own User-Agent and sends no credentials;
* asks upstream at most once per ``ttl_seconds`` (single flight across threads) and backs off
  after a failure instead of retrying on every request.
"""

from __future__ import annotations

import calendar
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Callable, Mapping, Optional

import requests

from . import __version__

ENDPOINT = "https://api.coinmarketcap.com/data-api/v3/fear-greed/chart"
PAGE_URL = "https://coinmarketcap.com/charts/fear-and-greed-index/"
USER_AGENT = f"tradingview-data-grabber/{__version__} (research dashboard; no scraping of pages)"
SOURCE: dict[str, Any] = {
    "name": "CoinMarketCap",
    "index": "CMC Crypto Fear and Greed Index",
    "url": PAGE_URL,
    "endpoint": ENDPOINT,
    # The key-free route is what coinmarketcap.com itself calls; it is not a published API.
    "documented": False,
}

DAY = 86_400
MAX_RESPONSE_BYTES = 10 * 1024 * 1024


class SentimentUnavailable(Exception):
    """The index could not be fetched or understood; the message is safe to show to users."""


@dataclass(frozen=True)
class Band:
    key: str
    label: str
    start: int  # inclusive
    end: int  # exclusive, except the last band which includes 100


# Matches CoinMarketCap's own dial configuration; scores 0-19, 20-39, 40-59, 60-79, 80-100.
BANDS: tuple[Band, ...] = (
    Band("extreme_fear", "Extreme fear", 0, 20),
    Band("fear", "Fear", 20, 40),
    Band("neutral", "Neutral", 40, 60),
    Band("greed", "Greed", 60, 80),
    Band("extreme_greed", "Extreme greed", 80, 100),
)


def band_for(score: int) -> Band:
    """The band a 0-100 score falls in (lower bound inclusive; 100 is Extreme greed)."""

    if not 0 <= score <= 100:
        raise ValueError(f"score must be between 0 and 100, got {score}")
    for band in BANDS:
        if score < band.end:
            return band
    return BANDS[-1]


@dataclass(frozen=True)
class Series:
    """Parsed, validated, ascending history. Times are UTC epoch seconds."""

    time: tuple[int, ...]
    score: tuple[int, ...]
    btc_price: tuple[Optional[float], ...]
    btc_volume: tuple[Optional[float], ...]
    dropped_rows: int = 0


def _number(value: Any) -> Optional[float]:
    """A finite float from a number or numeric string; ``None`` when missing or unusable."""

    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result and result not in (float("inf"), float("-inf")) else None


def parse_chart(payload: Any) -> Series:
    """Validate a ``/fear-greed/chart`` response and return its rows in time order.

    CoinMarketCap reports failures with HTTP 200 and a non-zero ``status.error_code``, so the
    status block is checked rather than the HTTP status. Rows with an unusable timestamp or a score
    outside 0-100 are dropped and counted; a later row replaces an earlier one with the same time.
    """

    if not isinstance(payload, Mapping):
        raise SentimentUnavailable("CoinMarketCap returned an unexpected response.")
    status = payload.get("status")
    if isinstance(status, Mapping) and str(status.get("error_code", "0")) != "0":
        detail = str(status.get("error_message") or "unknown error")[:200]
        raise SentimentUnavailable(f"CoinMarketCap reported an error: {detail}")
    data = payload.get("data")
    rows = data.get("dataList") if isinstance(data, Mapping) else None
    if not isinstance(rows, list):
        raise SentimentUnavailable("CoinMarketCap returned an unexpected response (no data list).")

    parsed: dict[int, tuple[int, Optional[float], Optional[float]]] = {}
    dropped = 0
    for row in rows:
        if not isinstance(row, Mapping):
            dropped += 1
            continue
        timestamp = _number(row.get("timestamp"))
        score = _number(row.get("score"))
        if timestamp is None or timestamp <= 0 or score is None or score != int(score) or not 0 <= score <= 100:
            dropped += 1
            continue
        parsed[int(timestamp)] = (int(score), _number(row.get("btcPrice")), _number(row.get("btcVolume")))
    if not parsed:
        raise SentimentUnavailable("CoinMarketCap returned no usable Fear & Greed readings.")
    ordered = sorted(parsed)
    return Series(
        time=tuple(ordered),
        score=tuple(parsed[t][0] for t in ordered),
        btc_price=tuple(parsed[t][1] for t in ordered),
        btc_volume=tuple(parsed[t][2] for t in ordered),
        dropped_rows=dropped,
    )


def fetch_chart(*, now: Optional[float] = None, get: Optional[Callable[..., Any]] = None) -> Any:
    """Read the full history from CoinMarketCap. Raises :class:`SentimentUnavailable` on any failure."""

    end = int((time.time() if now is None else now)) + DAY  # past "now" so the live reading is included
    try:
        response = (get or requests.get)(
            ENDPOINT,
            params={"start": 1, "end": end},
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            timeout=(5, 15),
        )
    except requests.Timeout as exc:
        raise SentimentUnavailable("CoinMarketCap did not respond in time.") from exc
    except requests.RequestException as exc:
        raise SentimentUnavailable("Could not reach CoinMarketCap (network error).") from exc
    if response.status_code != 200:
        raise SentimentUnavailable(f"CoinMarketCap answered with HTTP {response.status_code}.")
    if len(response.content) > MAX_RESPONSE_BYTES:
        raise SentimentUnavailable("CoinMarketCap returned an unexpectedly large response.")
    try:
        return response.json()
    except ValueError as exc:
        raise SentimentUnavailable("CoinMarketCap returned an unreadable response.") from exc


@dataclass(frozen=True)
class Snapshot:
    series: Series
    fetched_at: float
    stale: bool = False
    stale_reason: Optional[str] = None


class FearGreedService:
    """Cached access to the index: one upstream request per ``ttl_seconds`` however many clients ask."""

    def __init__(
        self,
        fetch: Optional[Callable[[], Any]] = None,
        *,
        ttl_seconds: float = 600.0,
        retry_seconds: float = 60.0,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._fetch = fetch or (lambda: fetch_chart(now=clock()))
        self._ttl = ttl_seconds
        self._retry = retry_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._cached: Optional[tuple[Series, float]] = None
        self._failure: Optional[tuple[str, float]] = None  # (message, time of failure)

    def _serve(self, reason: Optional[str]) -> Snapshot:
        assert self._cached is not None
        series, fetched_at = self._cached
        return Snapshot(series, fetched_at, stale=reason is not None, stale_reason=reason)

    def _fresh(self) -> bool:
        return self._cached is not None and self._clock() - self._cached[1] < self._ttl

    def get(self) -> Snapshot:
        if self._fresh():
            return self._serve(None)
        with self._lock:
            if self._fresh():  # another thread refreshed while this one waited
                return self._serve(None)
            if self._failure and self._clock() - self._failure[1] < self._retry:
                message = self._failure[0]  # recently failed: do not hammer upstream
            else:
                try:
                    series = parse_chart(self._fetch())
                except SentimentUnavailable as exc:
                    message = str(exc)
                    self._failure = (message, self._clock())
                else:
                    self._cached = (series, self._clock())
                    self._failure = None
                    return self._serve(None)
            if self._cached is not None:
                return self._serve(message)
            raise SentimentUnavailable(message)


def _utc_date(seconds: int) -> date:
    return datetime.fromtimestamp(seconds, timezone.utc).date()


def _months_back(day: date, months: int) -> date:
    """Same day-of-month ``months`` earlier, clamped to the month's length (Mar 31 -> Feb 28)."""

    year, month = divmod(day.year * 12 + day.month - 1 - months, 12)
    month += 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def _point(series: Series, index: int) -> dict[str, Any]:
    score = series.score[index]
    band = band_for(score)
    return {"score": score, "label": band.label, "band": band.key, "time": series.time[index]}


def compute_snapshots(series: Series) -> dict[str, Optional[dict[str, Any]]]:
    """Comparison readings derived from the series; a date with no reading is ``None``, never estimated."""

    last = len(series.time) - 1
    today = _utc_date(series.time[last])
    by_date: dict[date, int] = {}
    for index, stamp in enumerate(series.time):
        by_date[_utc_date(stamp)] = index  # the last reading of each UTC day wins

    def on(target: date) -> Optional[dict[str, Any]]:
        index = by_date.get(target)
        return None if index is None else _point(series, index)

    window_start = series.time[last] - 365 * DAY
    in_year = [i for i, stamp in enumerate(series.time) if stamp >= window_start]
    high = max(in_year, key=lambda i: (series.score[i], series.time[i]))
    low = min(in_year, key=lambda i: (series.score[i], -series.time[i]))
    return {
        "yesterday": on(date.fromordinal(today.toordinal() - 1)),
        "week_ago": on(date.fromordinal(today.toordinal() - 7)),
        "month_ago": on(_months_back(today, 1)),
        "year_high": _point(series, high),
        "year_low": _point(series, low),
    }


def build_response(snapshot: Snapshot, days: Optional[int] = None) -> dict[str, Any]:
    """The JSON body of ``GET /api/sentiment/fear-greed`` (see the README for the contract)."""

    series = snapshot.series
    last = len(series.time) - 1
    start = 0
    if days is not None:
        cutoff = series.time[last] - days * DAY
        start = next((i for i, stamp in enumerate(series.time) if stamp >= cutoff), last)
    return {
        "source": SOURCE,
        "fetched_at": int(snapshot.fetched_at),
        "stale": snapshot.stale,
        "stale_reason": snapshot.stale_reason,
        "bands": [{"key": b.key, "label": b.label, "from": b.start, "to": b.end} for b in BANDS],
        "current": _point(series, last),
        "snapshots": compute_snapshots(series),
        "points": {
            "time": list(series.time[start:]),
            "score": list(series.score[start:]),
            "btc_price": list(series.btc_price[start:]),
            "btc_volume": list(series.btc_volume[start:]),
        },
        "total_points": len(series.time),
    }
