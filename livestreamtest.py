"""Compatibility entry point for live OHLCV CSV streaming.

Prefer ``tvdata bars`` for timeframe-safe paths and richer options.
"""

from pathlib import Path
from dataclasses import replace

from tradingview_data.bars import (
    Bar,
    BarStreamConfig,
    BarStreamer,
    backoff_delay,
    collect_bars as _collect_bars,
    parse_bar as _parse_bar,
    parse_symbols,
)
from tradingview_data.cli import legacy_bars_main
from tradingview_data.protocol import generate_chart_session
from tradingview_data.storage import CsvBarStore, parse_csv_time, safe_filename


class SymbolStream(CsvBarStore):
    """Legacy per-symbol store adapter backed by ``CsvBarStore``."""

    def __init__(self, symbol, csv_path, *, timeframe=None):
        super().__init__(csv_path, symbol=symbol, timeframe=timeframe)
        self.chart_session = generate_chart_session()

    @property
    def csv_path(self):
        """Retain the original path attribute used by downstream scripts."""

        return str(self.path)

    @csv_path.setter
    def csv_path(self, value):
        self.path = Path(value)

    @property
    def last_row_pos(self):
        """Retain the original name for the forming-candle file position."""

        return self.last_row_position

    @last_row_pos.setter
    def last_row_pos(self, value):
        self.last_row_position = value


def parse_bar(bar):
    """Return the historical ``(timestamp, csv_row)`` shape for legacy callers."""

    parsed = _parse_bar(bar)
    if parsed is None:
        return None
    return parsed.timestamp, parsed.csv_row()


def collect_bars(text):
    """Yield historical ``(session, timestamp, csv_row)`` bar tuples."""

    for session, bar in _collect_bars(text):
        yield session, bar.timestamp, bar.csv_row()


def _config_from_args(args):
    return BarStreamConfig(
        symbols=parse_symbols(args.symbols),
        timeframe=args.timeframe,
        history_bars=args.bars,
        output=Path(args.output),
        layout=getattr(args, "layout", "flat"),
        max_retries=getattr(args, "max_retries", 5),
        silent=getattr(args, "silent", False),
        once=getattr(args, "once", False),
    )


def build_streams(args):
    """Build the original chart-session keyed stream mapping."""

    config = _config_from_args(args)
    config.output.mkdir(parents=True, exist_ok=True)
    streams = {}
    for symbol in config.symbols:
        path = config.output / f"{safe_filename(symbol)}.csv"
        stream = SymbolStream(symbol, path, timeframe=config.timeframe)
        streams[stream.chart_session] = stream
    return streams


def subscribe(ws, streams, args):
    """Subscribe an existing socket using the original function shape."""

    stores = {}
    symbols = []
    for stream in streams.values():
        if not isinstance(stream, CsvBarStore):
            raise TypeError("legacy streams must contain SymbolStream instances")
        session = getattr(stream, "chart_session", None)
        if not isinstance(session, str) or not session:
            raise ValueError("legacy streams must define a chart_session")
        if not isinstance(stream.symbol, str) or not stream.symbol:
            raise ValueError("legacy streams must define a symbol")
        if session in stores:
            raise ValueError(f"duplicate chart session: {session}")
        stores[session] = stream
        symbols.append(stream.symbol)
    if not stores:
        raise ValueError("provide at least one legacy stream")
    config = replace(_config_from_args(args), symbols=tuple(symbols))
    BarStreamer(config).subscribe(ws, stores)


def run(args):
    """Run a legacy namespace through the modular streamer."""

    config = _config_from_args(args)
    BarStreamer(config).run(stores=build_streams(args))


def main():
    return legacy_bars_main()

__all__ = [
    "Bar",
    "BarStreamConfig",
    "BarStreamer",
    "CsvBarStore",
    "SymbolStream",
    "backoff_delay",
    "build_streams",
    "collect_bars",
    "main",
    "parse_bar",
    "parse_csv_time",
    "run",
    "safe_filename",
    "subscribe",
]


if __name__ == "__main__":
    raise SystemExit(main())
