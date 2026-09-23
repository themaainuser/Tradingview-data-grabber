"""Compatibility entry point for live quote streaming.

Prefer ``tvdata quote`` for structured output and multi-symbol streaming.
"""

from pathlib import Path

from tradingview_data.bars import backoff_delay, parse_symbols, resolve_symbol_payload
from tradingview_data.cli import legacy_quote_main
from tradingview_data.protocol import generate_chart_session, send_message
from tradingview_data.quotes import QUOTE_FIELDS, QuoteStreamConfig, QuoteStreamer, format_quote, iter_quote_updates


def subscribe(ws, symbol, silent=False):
    """Subscribe a provided socket using the original function signature."""

    QuoteStreamer(QuoteStreamConfig(symbols=parse_symbols(symbol), silent=silent)).subscribe(ws)
    chart_session = generate_chart_session()
    send_message(ws, "chart_create_session", [chart_session, ""])
    send_message(ws, "resolve_symbol", [chart_session, "symbol_1", resolve_symbol_payload(symbol)])
    if not silent:
        send_message(ws, "create_series", [chart_session, "s1", "s1", "symbol_1", "1", 5000])


def run(symbol, silent=False, output=None, exitoninput=False):
    """Run a single legacy quote subscription through the modular streamer."""

    def on_update(update):
        if silent:
            print(format_quote(update, price_only=True))

    config = QuoteStreamConfig(
        symbols=parse_symbols(symbol),
        silent=silent,
        once=exitoninput,
        require_price_for_once=True,
        raw_output=Path(output) if output else None,
    )
    QuoteStreamer(config, on_update=on_update).run()


def main():
    return legacy_quote_main()

__all__ = [
    "QUOTE_FIELDS",
    "QuoteStreamConfig",
    "QuoteStreamer",
    "backoff_delay",
    "iter_quote_updates",
    "main",
    "resolve_symbol_payload",
    "run",
    "subscribe",
]


if __name__ == "__main__":
    raise SystemExit(main())
