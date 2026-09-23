# TradingView Data Grabber

A modular Python toolkit for collecting TradingView websocket data, keeping
OHLCV captures durable, validating them, calculating technical indicators, and
generating offline charts. It supports crypto, equities, forex, indices, and
other symbols that TradingView exposes to the connected account.

> This project is an unofficial client. Use it only with data you are allowed
> to access and in accordance with TradingView's terms and exchange rules.

## What changed

The original standalone scripts are now a package with a single `tvdata`
command while preserving the old script names as compatibility entry points.

- **Reliable transport** — length-aware websocket frame parsing, heartbeat
  handling for text or bytes, secure session IDs, and retry backoff.
- **OHLCV streaming** — multiple symbols over one socket, optional historical
  snapshot mode, deduplication, forming-candle replacement, durable flushes,
  and timeframe-aware CSV paths plus metadata.
- **Quote streaming** — parsed quote updates for multiple symbols, partial
  update merging, text/JSON output, optional raw-frame capture, and first-price
  exit mode.
- **Analysis** — CSV schema checks, invalid-row filtering, duplicate collapse,
  gap detection, SMA/EMA, RSI, MACD, ATR, Bollinger bands, VWAP, support, and
  resistance summaries.
- **Charts** — candlesticks, volume profile with a 70% value area, liquidity
  and volatility heatmaps, return/ATR, technical panels, correlations, and an
  offline HTML gallery. Multi-symbol runs use separate directories rather than
  overwriting earlier charts.

## Install

Python 3.9 or newer is required.

```bash
python -m pip install -r requirements.txt
# or, for an editable development install:
python -m pip install -e ".[dev]"
```

## Unified CLI

All commands are available through either `tvdata` after installation or
`python -m tradingview_data` from a checkout.

### Stream OHLCV bars

```bash
# Stream continuously. Files are isolated by symbol and timeframe.
tvdata bars -n BINANCE:BTCUSDT,BINANCE:ETHUSDT -t 5 -b 500 -o data

# Wait until each requested symbol has a persisted server batch, then exit.
tvdata bars -n BINANCE:BTCUSDT,BINANCE:ETHUSDT -t 60 -b 1000 --once
```

The default layout is `data/<symbol>/<timeframe>.csv`, for example
`data/BINANCE_BTCUSDT/5.csv`. Each CSV retains the compatible columns
`index,time,open,high,low,close,volume`; the adjacent `.meta.json` prevents a
different symbol or timeframe from being mixed into that dataset. Use
`--layout flat` only when compatibility with the original file layout is more
important than timeframe isolation.

Useful options:

```text
--once                 exit after every requested symbol receives a persisted batch
--max-retries 5        cap failed reconnection attempts
--verbose-protocol     print raw websocket frames for troubleshooting
```

### Stream parsed quotes

```bash
# Readable ticker output for two symbols.
tvdata quote -n BINANCE:BTCUSDT,BINANCE:ETHUSDT

# One JSON object per update; stop after both symbols receive an update.
tvdata quote -n BINANCE:BTCUSDT,BINANCE:ETHUSDT \
  --format json --once -o quotes.jsonl

# Request selected fields and keep a raw capture separately.
tvdata quote -n NASDAQ:AAPL --fields lp,bid,ask,volume \
  --raw-output raw-frames.log
```

### Validate and analyze a capture

```bash
tvdata validate data/BINANCE_BTCUSDT/5.csv --format json

tvdata analyze data/BINANCE_BTCUSDT/5.csv \
  --format json \
  --output reports/btc-summary.json \
  --enriched-csv reports/btc-indicators.csv
```

`analyze` never uses future rows to calculate indicators. Warm-up values are
left empty until enough history exists (for example, 20 rows for SMA/EMA 20).
The report is descriptive market data, not trading advice.

### Generate charts and an offline gallery

```bash
tvdata chart data/BINANCE_BTCUSDT/5.csv -o charts/btc
tvdata chart data/BINANCE_BTCUSDT/5.csv data/BINANCE_ETHUSDT/5.csv -o charts/compare
```

Open `dashboard.html` from the output directory in a browser. Click a chart to
enlarge it, pin up to four charts (saved in that browser's local storage), and
refresh images after a new analysis run. A multi-symbol output contains one
subdirectory per source CSV and, when timestamps overlap, a correlation chart
at the output root.

## Python API

The modules can be used independently in another application:

```python
from pathlib import Path

from tradingview_data.analytics import load_ohlcv, market_report
from tradingview_data.bars import BarStreamConfig, BarStreamer, parse_symbols

config = BarStreamConfig(
    symbols=parse_symbols("BINANCE:BTCUSDT"),
    timeframe="5",
    history_bars=500,
    output=Path("data"),
)
# BarStreamer(config).run()

data = load_ohlcv("data/BINANCE_BTCUSDT/5.csv")
print(market_report(data)["signals"])
```

Package boundaries:

```text
tradingview_data/
├── protocol.py   # framing, sessions, heartbeats, websocket constants
├── bars.py       # chart-session subscriptions and normalized candles
├── quotes.py     # quote-session subscriptions and parsed updates
├── storage.py    # CSV persistence, deduplication, and metadata
├── analytics.py  # validation, indicators, quality, and reports
├── charts.py     # static charts and HTML gallery
├── auth.py       # token retrieval without persistence
└── cli.py        # unified command and compatibility adapters
```

## Authentication and secrets

Anonymous access uses TradingView's anonymous token. For an authenticated
session, set `TV_AUTH_TOKEN` in your shell before running `bars` or `quote`.
To validate credentials without exposing a token, use environment variables:

```bash
export TV_USERNAME='your-account-name'
export TV_PASSWORD='your-password'
tvdata auth
```

The command deliberately does **not** print or write the retrieved token. For
automated integrations, call `tradingview_data.auth.get_auth_token()` and pass
its return value directly to `BarStreamConfig` or `QuoteStreamConfig`; otherwise
provision `TV_AUTH_TOKEN` from your organization-approved secret manager. Never
commit tokens, passwords, raw authenticated captures, or notebooks containing
them. The retired experimental notebook was removed from this checkout because
it contained a credential-like value; rotate any token that was previously used
there and rewrite published history if it was exposed.

## Legacy scripts

Existing invocations remain available:

```bash
python livestreamtest.py -n BINANCE:BTCUSDT -t 1 -b 300 -o data -s
python main.py -n BINANCE:BTCUSDT -s -q
python visuals.py data/BINANCE_BTCUSDT.csv -o charts
python getAuthToken.py
```

`livestreamtest.py` retains its original flat `data/<symbol>.csv` layout.
Prefer the unified CLI for isolated timeframes, structured quote output, and
analysis commands.

## Development and tests

```bash
python -m pytest
# or without pytest discovery:
python -m unittest discover -s tests -v
```

Tests are network-free and cover the protocol, CSV persistence, quote parsing,
analytics, charts, and CLI behavior. The project was originally forked from
[0xrushi/tradingview-scraper](https://github.com/0xrushi/tradingview-scraper)
by rushic24; the modular implementation builds on that initial websocket
approach.
