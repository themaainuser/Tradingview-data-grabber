"""Composable tools for collecting and analyzing TradingView market data.

The package intentionally keeps the websocket protocol, data persistence, and
analysis layers separate so applications can use one without importing the
others.
"""

from .bars import Bar, BarStreamConfig, BarStreamer, collect_bars
from .quotes import QuoteStreamConfig, QuoteStreamer, QuoteUpdate, iter_quote_updates

__all__ = [
    "Bar",
    "BarStreamConfig",
    "BarStreamer",
    "QuoteStreamConfig",
    "QuoteStreamer",
    "QuoteUpdate",
    "collect_bars",
    "iter_quote_updates",
]

__version__ = "0.2.0"
