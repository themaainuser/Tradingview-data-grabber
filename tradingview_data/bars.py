"""Live OHLCV candle streaming built on the shared websocket protocol."""

from __future__ import annotations

import json
import math
import os
import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .protocol import (
    ANONYMOUS_TOKEN,
    DEFAULT_ENDPOINT,
    DEFAULT_ORIGIN,
    generate_chart_session,
    generate_quote_session,
    is_heartbeat,
    iter_frames,
    send_message,
)
from .storage import CSV_TIME_FORMAT, CsvBarStore, safe_filename

IST = ZoneInfo("Asia/Kolkata")
DEFAULT_QUOTE_FIELDS = ("lp", "volume", "currency_code")


def backoff_delay(attempt: int, maximum: float = 30.0) -> float:
    """Return a capped exponential reconnect delay."""

    return min(2 ** max(attempt, 0), maximum)


def parse_symbols(symbols: str | Sequence[str]) -> tuple[str, ...]:
    """Parse a comma-separated symbol list, retaining first-seen order."""

    raw = symbols.split(",") if isinstance(symbols, str) else symbols
    unique: list[str] = []
    seen: set[str] = set()
    for value in raw:
        symbol = value.strip()
        if symbol and symbol not in seen:
            unique.append(symbol)
            seen.add(symbol)
    if not unique:
        raise ValueError("provide at least one symbol")
    return tuple(unique)


def resolve_symbol_payload(symbol: str, *, session: str = "extended") -> str:
    """Build TradingView's encoded symbol-resolution payload."""

    return "=" + json.dumps(
        {"symbol": symbol, "adjustment": "splits", "session": session},
        separators=(",", ":"),
    )


@dataclass(frozen=True)
class Bar:
    """A normalized OHLCV candle received from a chart session."""

    timestamp: int
    source_index: int | str | None
    open: float
    high: float
    low: float
    close: float
    volume: float

    def csv_row(self, timezone: ZoneInfo = IST) -> list[object]:
        timestamp = datetime.fromtimestamp(self.timestamp, timezone).strftime(CSV_TIME_FORMAT)
        return [
            f"[{self.source_index}]",
            timestamp,
            self.open,
            self.high,
            self.low,
            self.close,
            self.volume,
        ]


def parse_bar(value: object) -> Bar | None:
    """Safely normalize a TradingView bar payload; ignore malformed bars."""

    if not isinstance(value, dict):
        return None
    values = value.get("v")
    if not isinstance(values, (list, tuple)) or len(values) < 5:
        return None
    try:
        timestamp = int(float(values[0]))
        open_, high, low, close = (float(values[index]) for index in range(1, 5))
        volume = float(values[5]) if len(values) > 5 and values[5] not in (None, "") else 0.0
    except (TypeError, ValueError, OverflowError):
        return None
    if (
        timestamp <= 0
        or not all(math.isfinite(number) for number in (open_, high, low, close, volume))
        or min(open_, high, low, close) <= 0
        or volume < 0
        or high < low
        or high < max(open_, close)
        or low > min(open_, close)
    ):
        return None
    return Bar(timestamp, value.get("i"), open_, high, low, close, volume)


def collect_bars(value: str | bytes) -> Iterator[tuple[str, Bar]]:
    """Yield ``(chart_session_id, bar)`` values from a protocol message."""

    for frame in iter_frames(value):
        if frame.get("m") not in {"du", "timescale_update"}:
            continue
        payload = frame.get("p")
        if not isinstance(payload, list) or len(payload) < 2:
            continue
        session_id, series_by_name = payload[0], payload[1]
        if not isinstance(session_id, str) or not isinstance(series_by_name, dict):
            continue
        for series in series_by_name.values():
            if not isinstance(series, dict):
                continue
            bars = series.get("s")
            if not isinstance(bars, list):
                continue
            for raw_bar in bars:
                bar = parse_bar(raw_bar)
                if bar is not None:
                    yield session_id, bar


@dataclass(frozen=True)
class BarStreamConfig:
    """Connection and persistence settings for a candle stream."""

    symbols: tuple[str, ...]
    timeframe: str = "1"
    history_bars: int = 300
    output: Path = Path("data")
    layout: str = "by-timeframe"
    auth_token: str | None = None
    timeout: int = 30
    max_retries: int = 5
    silent: bool = False
    once: bool = False

    def __post_init__(self) -> None:
        if not self.symbols:
            raise ValueError("provide at least one symbol")
        if any(not symbol.strip() for symbol in self.symbols):
            raise ValueError("symbols cannot be blank")
        if len(set(self.symbols)) != len(self.symbols):
            raise ValueError("symbols must be unique; use parse_symbols for CSV input")
        if not self.timeframe.strip():
            raise ValueError("timeframe cannot be empty")
        if self.history_bars <= 0:
            raise ValueError("history_bars must be positive")
        if self.timeout <= 0:
            raise ValueError("timeout must be positive")
        if self.max_retries < 0:
            raise ValueError("max_retries cannot be negative")
        if self.layout not in {"by-timeframe", "flat"}:
            raise ValueError("layout must be 'by-timeframe' or 'flat'")


def output_path(config: BarStreamConfig, symbol: str) -> Path:
    """Choose a collision-free path for a symbol and timeframe."""

    filename = safe_filename(symbol)
    if config.layout == "flat":
        return config.output / f"{filename}.csv"
    return config.output / filename / f"{safe_filename(config.timeframe)}.csv"


class BarStreamer:
    """Stream chart-session candles to one durable CSV per symbol/timeframe."""

    def __init__(
        self,
        config: BarStreamConfig,
        *,
        connect: Callable[[], Any] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        emit: Callable[[str], None] = print,
        on_bar: Callable[[str, Bar], None] | None = None,
    ) -> None:
        self.config = config
        self._connect = connect or self._default_connect
        self._sleep = sleep
        self._emit = emit
        self._on_bar = on_bar

    def _default_connect(self) -> Any:
        from websocket import create_connection

        return create_connection(
            DEFAULT_ENDPOINT,
            timeout=self.config.timeout,
            origin=DEFAULT_ORIGIN,
        )

    def build_stores(self) -> dict[str, CsvBarStore]:
        """Create chart-session keyed stores without opening files yet."""

        stores: dict[str, CsvBarStore] = {}
        paths: dict[Path, str] = {}
        for symbol in self.config.symbols:
            session = generate_chart_session()
            path = output_path(self.config, symbol)
            collides_with = paths.get(path)
            if collides_with is not None:
                raise ValueError(
                    f"symbols {collides_with!r} and {symbol!r} map to the same output path {path}"
                )
            paths[path] = symbol
            stores[session] = CsvBarStore(
                path,
                symbol=symbol,
                timeframe=self.config.timeframe,
            )
        return stores

    def subscribe(self, websocket: Any, stores: dict[str, CsvBarStore]) -> None:
        """Subscribe one websocket to all configured chart sessions."""

        token = self.config.auth_token or os.getenv("TV_AUTH_TOKEN") or ANONYMOUS_TOKEN
        quote_session = generate_quote_session()
        send_message(websocket, "set_auth_token", [token])
        send_message(websocket, "quote_create_session", [quote_session])
        send_message(websocket, "quote_set_fields", [quote_session, *DEFAULT_QUOTE_FIELDS])
        for symbol in self.config.symbols:
            send_message(websocket, "quote_add_symbols", [quote_session, symbol])
            send_message(websocket, "quote_fast_symbols", [quote_session, symbol])
        send_message(websocket, "quote_hibernate_all", [quote_session])

        for session, store in stores.items():
            assert store.symbol is not None
            send_message(websocket, "chart_create_session", [session, ""])
            send_message(
                websocket,
                "resolve_symbol",
                [session, "symbol_1", resolve_symbol_payload(store.symbol)],
            )
            send_message(
                websocket,
                "create_series",
                [session, "s1", "s1", "symbol_1", self.config.timeframe, self.config.history_bars],
            )

    def run(self, stores: dict[str, CsvBarStore] | None = None) -> None:
        """Connect, persist bars, and reconnect after transient failures.

        ``stores`` lets compatibility adapters retain their existing
        chart-session mappings while normal callers use generated stores.
        """

        stores = self.build_stores() if stores is None else stores
        try:
            for store in stores.values():
                store.open()
            failures = 0
            sessions_with_bars: set[str] = set()
            while True:
                websocket: Any | None = None
                wrote_bar = False
                try:
                    websocket = self._connect()
                    self.subscribe(websocket, stores)
                    while True:
                        message = websocket.recv()
                        if is_heartbeat(message):
                            websocket.send(message)
                            continue
                        if not self.config.silent:
                            self._emit(str(message))
                        for session, bar in collect_bars(message):
                            store = stores.get(session)
                            if store is None:
                                continue
                            if store.write_bar(bar.timestamp, bar.csv_row()):
                                wrote_bar = True
                                sessions_with_bars.add(session)
                                if self._on_bar is not None and store.symbol is not None:
                                    self._on_bar(store.symbol, bar)
                        if self.config.once and sessions_with_bars.issuperset(stores):
                            return
                except KeyboardInterrupt:
                    self._emit(f"interrupted, CSV files saved to {self.config.output}")
                    return
                except Exception as exc:
                    failures += 1
                    if failures > self.config.max_retries:
                        self._emit(f"giving up after {self.config.max_retries} failed attempts: {exc}")
                        return
                    delay = backoff_delay(failures)
                    self._emit(f"stream error: {exc}; reconnecting in {delay:g}s")
                    self._sleep(delay)
                finally:
                    if websocket is not None:
                        try:
                            websocket.close()
                        except Exception:
                            pass
                if wrote_bar:
                    failures = 0
        finally:
            for store in stores.values():
                store.close()
