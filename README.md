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
- **Quant research** — repeatable SMA-crossover and RSI mean-reversion
  permutations, next-bar signals, transaction-cost-aware returns, risk metrics,
  and later-period forward folds across multiple captures.
- **Charts** — candlesticks, volume profile with a 70% value area, liquidity
  and volatility heatmaps, return/ATR, technical panels, return distribution
  against a fitted normal with VaR, drawdown (underwater) plots, weekday/hour
  seasonality, correlations, and an offline HTML gallery. Multi-symbol runs use
  separate directories rather than overwriting earlier charts.

## Install

Python 3.9 or newer is required.

```bash
python -m pip install -r requirements.txt
# or, for an editable development install:
python -m pip install -e ".[dev]"
# or, to run the dashboard API without the test tools:
python -m pip install -e ".[api]"
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
refresh images after a new analysis run. Each dataset gets
`9_return_distribution.png`, `10_drawdown.png`, and `11_seasonality.png` in
addition to the first seven charts; a chart is skipped when the capture is too
short for it (30 returns for the distribution and weekday seasonality, 2 bars
for drawdown); the hour panel also needs intraday bars and 48 returns.
Seasonality is computed in UTC. A multi-symbol output contains one
subdirectory per source CSV and, when timestamps overlap, a correlation chart
at the output root.

### Quant research dashboard

Run a repeatable grid of long-only strategy permutations over one or more
captures and open the resulting interactive dashboard:

```bash
tvdata research data/BINANCE_BTCUSDT/5.csv data/BINANCE_ETHUSDT/5.csv \
  --fee-bps 5 --periods-per-year 252 -o research
```

The self-contained `dashboard.html` filters by market, strategy family,
minimum forward Sharpe, trade count, and parameter search; it compares each
candidate's equity curve with buy-and-hold. `research.json` contains the
underlying metrics and bounded curve data. The built-in grid includes SMA
crossovers and RSI mean-reversion entry/exit levels. Positions take effect on
the bar after a signal; fees are charged on position changes. The final 40% of
longer captures is reported in four chronological forward folds, with the
initial 60% reported separately. For short series the report uses one 30%
holdout after the initial 70%. Rules are fixed (not re-fit between folds), and
sweeping many permutations still creates multiple-testing bias. Spread,
slippage, funding, borrow, and execution constraints are not modeled. This is
a research tool, not trading advice.

Annualized risk metrics depend on bar frequency and market session. Set
`--periods-per-year` to a value appropriate for the capture; `252` is only a
reasonable default for daily bars. The configured transaction cost is in basis
points per position change (both entry and exit).

#### Optional multi-model research notes

The deterministic backtest works without AI or model packages. To add a
qualitative research note from one or more models, pass each model ID with
`--model` and point the command at an OpenAI-compatible Chat Completions API:

```bash
# Local Ollama OpenAI-compatible endpoint is the default; no API key is needed.
tvdata research data/BINANCE_BTCUSDT/5.csv \
  --model qwen3:8b --model llama3.3:70b

# Hosted endpoint; keep the key in the environment, never in a command argument.
export OPENAI_API_KEY='...'
tvdata research data/BINANCE_BTCUSDT/5.csv \
  --base-url https://api.openai.com/v1 \
  --api-key-env OPENAI_API_KEY --model gpt-4.1-mini

# Compare local and hosted models in one run, each using its own endpoint.
tvdata research data/BINANCE_BTCUSDT/5.csv \
  --model qwen3:8b --model gpt-4.1-mini \
  --model-endpoint qwen3:8b=http://localhost:11434/v1 \
  --model-endpoint gpt-4.1-mini=https://api.openai.com/v1 \
  --model-api-key-env gpt-4.1-mini=OPENAI_API_KEY
```

`TVDATA_AI_BASE_URL` and `TVDATA_AI_API_KEY` can configure the endpoint and
key-variable name without CLI flags. Any OpenAI-compatible gateway can route
model IDs to hosted frontier models or local open-weight runtimes. Only the
aggregate metrics for up to 12 candidates are sent; raw bars are not sent.
Returned notes are labeled as model output in the dashboard and do not change
the quantitative ranking. A model API call shares those summary metrics with
the configured endpoint.

## Dashboard API

`tvdata serve` exposes captured data to the web dashboard through a small
read-only FastAPI service (install the optional dependencies with
`pip install -e ".[api]"`). **There is no sample data:** the API only reports
CSV captures that exist under the data directory, so the dashboard stays empty
until `tvdata bars` (or another capture) has written files there.

```bash
tvdata serve --data-dir data --host 127.0.0.1 --port 8000
# also host a built frontend at / and allow a dev server origin via CORS:
tvdata serve --static-dir frontend/build --cors-origin http://localhost:5173
```

The server binds to loopback by default and has no authentication; only bind
another interface on a network you trust. Files are re-scanned on every
request, so new captures appear without a restart. Parsed files are cached
by path, modification time, and size.

**Data layout.** Datasets are `<data-dir>/<symbol_dir>/<timeframe>.csv` (the
default `bars` layout) or flat `<data-dir>/<name>.csv`. The
`*.csv.meta.json` sidecar written by `bars` supplies the symbol and timeframe;
without it they come from the directory and file names (flat files have no
timeframe). Hidden files, sidecars, other extensions, deeper directories, and
symlinks that leave the data directory are ignored.

| Endpoint                                                                        | Response                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| ------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `GET /api/health`                                                               | `{"status", "data_dir", "dataset_count"}`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| `GET /api/datasets`                                                             | `{"datasets": [...]}` sorted by symbol then timeframe. Each entry has `id`, `symbol`, `timeframe`, `path`, `rows`, `size_bytes`, `modified` (UTC ISO-8601), `start`/`end` (epoch seconds), `valid`, and `error`. Unreadable CSVs are listed with `valid: false` and an `error` message instead of failing the listing.                                                                                                                                                                                                                                                                                                                                                                                                   |
| `GET /api/datasets/{id}/bars?limit=&start=&end=`                                | Columnar OHLCV: `columns` holds parallel `time` (UTC epoch seconds), `open`, `high`, `low`, `close`, `volume` arrays. `limit` (1–5,000,000) keeps the most recent bars of the inclusive `start`–`end` window. `total_rows`, `dropped_rows`, `duplicate_rows_collapsed`, and `quality` describe the whole file.                                                                                                                                                                                                                                                                                                                                                                                                           |
| `GET /api/datasets/{id}/report`                                                 | The `tvdata analyze` market report.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| `GET /api/datasets/{id}/charts?bins=60&value_area=0.7&window=30&return_bins=41` | Chart data computed by the same code as the PNG charts: `volume_profile` (POC, value area), `return_distribution` (histogram, fitted-normal counts, VaR/CVaR stats), `drawdown` (decimated underwater curve, deepest drawdown, recovery), `rolling_volatility`, UTC hour × weekday `activity` grids, and `seasonality`. Also `bars`, `interval_seconds`, and `intraday`. A section that needs more data or intraday bars is `null` and explained under `unavailable` (seasonality blocks are keyed `seasonality.by_weekday` and `seasonality.by_hour`). `bins` 10–200, `value_area` 0.5–0.95, `window` 5–500, `return_bins` 10–101.                                                                                      |
| `GET /api/charts/correlation?ids=<id>&ids=<id>`                                 | Close-to-close return correlation of 2–20 unique datasets over their shared timestamps: `{labels, matrix, observations, start, end}` (labels as in research; 422 when fewer than 3 returns overlap).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| `GET /api/sentiment/fear-greed?days=`                                           | CoinMarketCap's Crypto Fear and Greed Index, read by the server with no API key: `{source, fetched_at, stale, stale_reason, bands, current, snapshots, points, total_points}`. `current` and each snapshot (`yesterday`, `week_ago`, `month_ago`, `year_high`, `year_low`) carry `score` (0–100), `label`, `band` and `time`; a day with no reading is `null`. `points` holds parallel `time`, `score`, `btc_price` and `btc_volume` columns (price and volume are `null` when CoinMarketCap omits them). `days` (1–3650) returns only the most recent history. Cached for 10 minutes; if a refresh fails the last good readings are returned with `stale: true`, and with none cached the route answers 502. See below. |
| `POST /api/research/run`                                                        | Body `{"dataset_ids": [1–20 unique ids], "fee_bps": 5, "periods_per_year": 252}`; returns the `tvdata research` JSON (`schema_version` 1). Assets are labelled `<symbol>` or `<symbol>-<timeframe>` in request order. No model endpoint is called.                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |

Dataset ids are opaque slugs that are only resolved against the scanned file
list; client input is never used as a filesystem path. Errors use FastAPI's
shape: `{"detail": "message"}` for 404 (unknown id), 422 (unreadable file,
`start` after `end`, unknown id in a research or correlation request, a
bad correlation id list, or a research `ValueError`), 502 for an unreadable
Fear & Greed source, and the standard list of field errors for request validation.
NaN and infinite values are returned as `null`. Interactive Swagger docs are
served at `/api/docs` (ReDoc at `/api/redoc`, schema at `/api/openapi.json`); the
dashboard's own documentation page lives at `/docs`.

### Fear & Greed source

CoinMarketCap's documented Fear and Greed API (`pro-api.coinmarketcap.com/v3/fear-and-greed`)
requires an API key. `tradingview_data/sentiment.py` instead reads
`https://api.coinmarketcap.com/data-api/v3/fear-greed/chart`, the public route CoinMarketCap's own
chart page calls, which needs no key. Things to know before relying on it:

- It is **not a published API**. CoinMarketCap can change, rate limit or withdraw it without notice, and
  CoinMarketCap's terms of use apply to the data.
- Nothing is invented. When the route cannot be read, `GET /api/sentiment/fear-greed` answers 502 with
  the reason (or serves the last good readings flagged `stale`), and the dashboard shows the error
  instead of a number.
- The server sends its own `User-Agent` and no credentials, asks upstream at most once per ten
  minutes however many clients connect, and waits a minute after a failure before trying again.
- Upstream reports some failures as HTTP 200 with a non-zero `status.error_code`; those are treated as
  failures. Bands follow CoinMarketCap's dial: 0–19 extreme fear, 20–39 fear, 40–59 neutral, 60–79
  greed, 80–100 extreme greed.
- The Bitcoin price column comes from the same payload.

## Web dashboard

`frontend/` is a Svelte 5 dashboard for exploring captures (candlesticks, 127
indicators, compound bar filters, forward-return studies) and screening research
runs. It shows only data from `tvdata serve` or a CSV you import; with no captures
it renders empty states. It includes its own documentation at `/docs`. See
[`frontend/README.md`](frontend/README.md).

```bash
cd frontend && pnpm install && pnpm build
tvdata serve --data-dir data --static-dir frontend/build   # http://127.0.0.1:8000
```

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
├── research.py   # strategy permutations, evaluation, model notes, dashboard
├── api.py        # read-only FastAPI service for the web dashboard
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

`tests/test_api.py` is written for pytest and skips itself when the optional
`api` dependencies are not installed.

Tests are network-free and cover the protocol, CSV persistence, quote parsing,
analytics, charts, the dashboard API, and CLI behavior. The project was originally forked from
[0xrushi/tradingview-scraper](https://github.com/0xrushi/tradingview-scraper)
by rushic24; the modular implementation builds on that initial websocket
approach.
