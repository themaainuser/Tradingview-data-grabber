"""Live quote parsing and streaming."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .bars import backoff_delay, parse_symbols
from .protocol import (
    ANONYMOUS_TOKEN,
    DEFAULT_ENDPOINT,
    DEFAULT_ORIGIN,
    generate_quote_session,
    is_heartbeat,
    iter_frames,
    send_message,
)

QUOTE_FIELDS = (
    "ch",
    "chp",
    "current_session",
    "description",
    "local_description",
    "language",
    "exchange",
    "fractional",
    "is_tradable",
    "lp",
    "lp_time",
    "minmov",
    "minmove2",
    "original_name",
    "pricescale",
    "pro_name",
    "short_name",
    "type",
    "update_mode",
    "volume",
    "currency_code",
    "rchp",
    "rtc",
    "bid",
    "ask",
    "bid_size",
    "ask_size",
)


@dataclass(frozen=True)
class QuoteUpdate:
    """A normalized quote update, including its local receipt timestamp."""

    symbol: str
    values: Mapping[str, Any]
    received_at: datetime

    def as_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "received_at": self.received_at.isoformat(),
            **dict(self.values),
        }


def _decode_symbol_name(value: object) -> str | None:
    """Normalize TradingView's plain or encoded quote record name."""

    if not isinstance(value, str) or not value:
        return None
    payload = value[1:] if value.startswith("=") else value
    if not payload.startswith("{"):
        return value
    try:
        decoded = json.loads(payload)
    except (TypeError, ValueError):
        return value
    symbol = decoded.get("symbol") if isinstance(decoded, dict) else None
    return symbol if isinstance(symbol, str) and symbol else value


def _iter_quote_records(value: object, symbol_hint: str | None = None) -> Iterator[tuple[str, dict[str, Any]]]:
    if not isinstance(value, dict):
        return
    fields = value.get("v")
    symbol = _decode_symbol_name(value.get("n") or value.get("symbol") or symbol_hint)
    if isinstance(symbol, str) and isinstance(fields, dict):
        yield symbol, fields
    for key, nested in value.items():
        if key in {"v", "n", "symbol", "s"}:
            continue
        if isinstance(nested, dict):
            nested_hint = key if isinstance(key, str) and ":" in key else symbol_hint
            yield from _iter_quote_records(nested, nested_hint)


def iter_quote_updates(value: str | bytes) -> Iterator[QuoteUpdate]:
    """Yield quote updates from ``qsd`` frames, ignoring protocol noise."""

    received_at = datetime.now(timezone.utc)
    for frame in iter_frames(value):
        if frame.get("m") != "qsd":
            continue
        payload = frame.get("p")
        if not isinstance(payload, list):
            continue
        for item in payload[1:]:
            for symbol, fields in _iter_quote_records(item):
                yield QuoteUpdate(symbol, fields, received_at)


def format_quote(update: QuoteUpdate, output_format: str = "text", *, price_only: bool = False) -> str:
    """Render a quote as compact text or one JSON record."""

    if price_only:
        return str(update.values.get("lp", ""))
    if output_format == "json":
        return json.dumps(update.as_dict(), sort_keys=True, default=str)
    if output_format != "text":
        raise ValueError("output_format must be 'text' or 'json'")
    fields = [f"{key}={value}" for key, value in update.values.items()]
    return f"{update.symbol} " + " ".join(fields)


@dataclass(frozen=True)
class QuoteStreamConfig:
    """Connection settings for one or more live quote subscriptions."""

    symbols: tuple[str, ...]
    fields: tuple[str, ...] = QUOTE_FIELDS
    auth_token: str | None = None
    timeout: int = 30
    max_retries: int = 5
    silent: bool = False
    once: bool = False
    require_price_for_once: bool = False
    raw_output: Path | None = None

    def __post_init__(self) -> None:
        if not self.symbols:
            raise ValueError("provide at least one symbol")
        if any(not symbol.strip() for symbol in self.symbols):
            raise ValueError("symbols cannot be blank")
        if len(set(self.symbols)) != len(self.symbols):
            raise ValueError("symbols must be unique; use parse_symbols for CSV input")
        if not self.fields:
            raise ValueError("provide at least one quote field")
        if self.timeout <= 0:
            raise ValueError("timeout must be positive")
        if self.max_retries < 0:
            raise ValueError("max_retries cannot be negative")


class QuoteStreamer:
    """Maintain a quote session and emit merged updates for each symbol."""

    def __init__(
        self,
        config: QuoteStreamConfig,
        *,
        connect: Callable[[], Any] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        emit: Callable[[str], None] = print,
        on_update: Callable[[QuoteUpdate], None] | None = None,
    ) -> None:
        self.config = config
        self._connect = connect or self._default_connect
        self._sleep = sleep
        self._emit = emit
        self._on_update = on_update
        self._state: dict[str, dict[str, Any]] = {}

    def _default_connect(self) -> Any:
        from websocket import create_connection

        return create_connection(
            DEFAULT_ENDPOINT,
            timeout=self.config.timeout,
            origin=DEFAULT_ORIGIN,
        )

    def subscribe(self, websocket: Any) -> str:
        """Set up and return a quote session identifier."""

        session = generate_quote_session()
        token = self.config.auth_token or os.getenv("TV_AUTH_TOKEN") or ANONYMOUS_TOKEN
        send_message(websocket, "set_auth_token", [token])
        send_message(websocket, "quote_create_session", [session])
        send_message(websocket, "quote_set_fields", [session, *self.config.fields])
        for symbol in self.config.symbols:
            send_message(websocket, "quote_add_symbols", [session, symbol])
            send_message(websocket, "quote_fast_symbols", [session, symbol])
        return session

    def _merge(self, update: QuoteUpdate) -> QuoteUpdate:
        values = self._state.setdefault(update.symbol, {})
        values.update(update.values)
        return QuoteUpdate(update.symbol, dict(values), update.received_at)

    def run(self) -> None:
        """Connect, emit parsed updates, and reconnect on transient failures."""

        raw_file = None
        if self.config.raw_output is not None:
            self.config.raw_output.parent.mkdir(parents=True, exist_ok=True)
            raw_file = self.config.raw_output.open("a", encoding="utf-8")

        failures = 0
        seen_symbols: set[str] = set()
        try:
            while True:
                websocket: Any | None = None
                received_update = False
                try:
                    websocket = self._connect()
                    self.subscribe(websocket)
                    while True:
                        message = websocket.recv()
                        if is_heartbeat(message):
                            websocket.send(message)
                            continue
                        if raw_file is not None:
                            raw_file.write(str(message) + "\n")
                            raw_file.flush()
                        if not self.config.silent:
                            self._emit(str(message))
                        for update in iter_quote_updates(message):
                            merged = self._merge(update)
                            received_update = True
                            if not self.config.require_price_for_once or "lp" in merged.values:
                                seen_symbols.add(merged.symbol)
                            if self._on_update is not None:
                                self._on_update(merged)
                        if self.config.once and seen_symbols.issuperset(self.config.symbols):
                            return
                except KeyboardInterrupt:
                    self._emit("interrupted")
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
                if received_update:
                    failures = 0
        finally:
            if raw_file is not None:
                raw_file.close()


def quote_config_from_symbols(symbols: str | Sequence[str], **kwargs: Any) -> QuoteStreamConfig:
    """Convenience constructor for applications that accept CSV symbols."""

    return QuoteStreamConfig(symbols=parse_symbols(symbols), **kwargs)
