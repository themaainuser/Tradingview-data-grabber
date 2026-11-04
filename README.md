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
FastAPI service, read-only except for the verdict ledger described below (install the optional dependencies with
`pip install -e ".[api]"`). **There is no sample data:** the API only reports
CSV captures that exist under the data directory, so the dashboard stays empty
until `tvdata bars` (or another capture) has written files there.

```bash
tvdata serve --data-dir data --host 127.0.0.1 --port 8000
# also host a built frontend at / and allow a dev server origin via CORS:
tvdata serve --static-dir frontend/build --cors-origin http://localhost:5173
# keep the verdict ledger (and with it the sealed holdouts) somewhere other than <data-dir>/.tvdata-verdict:
tvdata serve --state-dir ~/.local/state/tvdata-verdict
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
| `GET /api/providers` | The data providers this server offers (`id`, `name`, `key_env`, `secret_env`, `configured`, `endpoint_count`, `premium_count`, `limits_note`, `plans`, `requests_this_session`). Whether a key is set is reported, never the key. |
| `GET /api/providers/{id}/catalog` | A provider's endpoints with their parameters, premium flags (and, for a provider with subscription tiers, the `plan` that first includes each endpoint and its `request_cost`), docs links and examples. 404 for an unknown provider. |
| `POST /api/providers/{id}/query` | Body `{"endpoint", "params", "refresh"}`. Fetches one endpoint and returns it as drawable views (`series`, `table`, `facts`, `bars`, `feed`, `heatmap`, `text`). Provider-side problems (`rate_limited`, `premium_required`, `invalid_key`, `not_configured`...) are a 200 with a `status`; a malformed request is a 422. |
| `POST /api/research/run`                                                        | Body `{"dataset_ids": [1–20 unique ids], "fee_bps": 5, "periods_per_year": 252}`; returns the `tvdata research` JSON (`schema_version` 1). Assets are labelled `<symbol>` or `<symbol>-<timeframe>` in request order. No model endpoint is called. When the dataset has a sealed holdout only bars before it are evaluated, and `metadata.sealed_holdouts` (`[{dataset_id, excluded_bars}]`, present only then) says so. |
| `POST /api/verdict/run`                                                         | Body `{"dataset_id", "min_trades": 30, "costs": {"fee_bps_per_side": 10, "spread_bps": 1, "slippage_k": 0.1}, "periods_per_year": null}`. Judges the 16-rule grid on the research window (sealing the default holdout first if needed), appends the run to the ledger and returns the report: one verdict label, per-rule trade gate and evidence, statistics, uncertainty and integrity checks. Never ranks rules. |
| `GET /api/verdict/{id}`                                                         | Seal, ledger counts, latest completed report, freeze, stored holdout result and the defaults (with the basis of each cost default). Never writes. |
| `POST /api/verdict/{id}/seal`                                                   | Body `{"holdout_fraction": 0.2}` (0.10-0.30, at least 100 bars). Seals the last bars as holdout; 409 when already sealed. |
| `GET /api/verdict/{id}/ledger?limit=100`                                        | Hash-chained entries of this dataset (newest `limit`, 1-500, oldest first, each with a one-line `summary`), the trial keys behind N, and `intact`. |
| `POST /api/verdict/{id}/freeze`                                                 | Body `{"run_id", "rule_ids"}`. Freezes 1-2 candidate rules of the latest completed `CANDIDATE` run; one freeze per seal (409 afterwards). |
| `POST /api/verdict/{id}/holdout/read`                                           | Body `{"freeze_id"}`. Evaluates the frozen rules on the sealed holdout. Allowed once per seal; every later attempt is 409. |
| `GET /api/verdict/{id}/forward`                                                 | Frozen rules at 1x costs on bars captured after the freeze (`waiting: true` while there are none). Not stored; `start` is the last bar at freeze time; 409 without a freeze. |

Dataset ids are opaque slugs that are only resolved against the scanned file
list; client input is never used as a filesystem path. Errors use FastAPI's
shape: `{"detail": "message"}` for 404 (unknown id), 422 (unreadable file,
`start` after `end`, unknown id in a research or correlation request, a
bad correlation id list, or a research `ValueError`), 409 for verdict state conflicts (already sealed or frozen, holdout already read, changed history, broken ledger), 500 for a failed verdict run, 502 for an unreadable
Fear & Greed source, and the standard list of field errors for request validation.
NaN and infinite values are returned as `null`. Interactive Swagger docs are
served at `/api/docs` (ReDoc at `/api/redoc`, schema at `/api/openapi.json`); the
dashboard's own documentation page lives at `/docs`.

### Verdict engine

The Research page ranks 16 fixed long-only rules by forward Sharpe. On a short capture that ranking is
noise: on the 1,000-bar hourly BTC capture no rule reaches 30 trades, the rules are highly correlated
(about 3 effective independent rules out of 13) and the Sharpe standard error is about ±3 annualised. The
verdict engine (`/api/verdict/*`) reports what such data can and cannot support and never produces a
ranked "winner" it cannot defend. Each run ends in exactly one label:

- `INSUFFICIENT_DATA`: no rule reached the trade gate. Nothing is computed beyond trade counts, and nothing is ranked.
- `INDISTINGUISHABLE_FROM_LUCK`: rules passed the gate, but none passes the bootstrap test, the deflated
  Sharpe ratio and the 1.5x cost stress; `reasons` names which check each group of rules failed.
- `CANDIDATE`: at least one rule passes the gate, the bootstrap test, DSR and the 1.5x cost stress. It is
  eligible for one holdout read, nothing more.

**Fills and costs.** A rule's 0/1 target is known at a bar's close and is entered at the next bar's open
(`position[t] = target[t-1]`, asserted on every run). The position held before the open earns the
close-to-open gap, the one held after it earns the intrabar move. Every fill costs
`fee_bps_per_side + spread_bps / 2 + slippage_k × ATR(14) / open` (ATR of the signal bar), on both sides of
every trade. Every rule is also run at 1.5x and 2x those costs, and the break-even cost per trade (the round
trip at which the mean gross trade return is used up) is reported. The fee default is Binance's spot taker
fee for the regular tier (0.10% per side, 0.075% with the BNB discount): check it against your own tier.
The spread default is a placeholder because captures hold no bid/ask, and `slippage_k` is a starting value
to calibrate against real fills. The legacy Research page fills at the signal close and charges one flat
fee, so its numbers differ from the verdict engine's.

**Trade-count gate.** A rule needs `min_trades` (default 30, 1-1000) entries before it gets any statistic.
Rules below it are `INSUFFICIENT_TRADES` (or `NEVER_TRADES` at zero) and carry no Sharpe, p-value or DSR
anywhere in the response. Rules come back in fixed grid order; there is no rank or score field.

**Trial ledger and N.** `ledger.jsonl` in the state directory is an append-only JSON-lines file. Every
seal, run, freeze and holdout read is one entry whose hash is `sha256(previous hash + canonical JSON of the
entry)`, verified whenever the file is read. A run is logged even when it fails, because it still
looked at the data. Nothing in the API edits the ledger. N is the number of distinct (dataset, rule) pairs
that appear in its run entries, including failed and discarded runs; it is computed from the file, never taken
from a request, and it does not include costs, `min_trades` or the data range, so changing costs never
changes N. The ledger is tamper-evident, not tamper-proof: editing, removing or reordering a line is
detected (`intact: false`, and every write then answers 409), but deleting the newest lines, deleting the
whole state directory or recomputing every hash is not. Back it up if the holdout matters to you.

**Sealed holdout, freeze, one read.** The first run (or `POST .../seal`) stores the last 10-30% of the
bars (default 20%, at least 100 bars in the capture) as a holdout together with a fingerprint of the research
bars. Research only ever sees bars before it; bars captured after the seal are forward data, not holdout.
A run whose fingerprint no longer matches (history rewritten, file replaced) is refused with 409. The holdout
can be read only for rules that were frozen from the latest completed `CANDIDATE` run (one or two rules,
hashed together with their costs into the ledger), by one endpoint, and **once per seal**. Allowing one read
per frozen rule set would look tempting, but a second read with a different rule set would be a second look at the same
bars, which is how a holdout turns into training data, so there is one freeze and one read per seal. The
result is stored in the ledger and shown again on later `GET`s, which is not a second read. With about 1,000
bars the holdout is a sanity check, not a verdict, and the report says so. `GET .../forward` then evaluates
the frozen rules on bars captured after the freeze, the real out-of-sample set; bars between the end of
the holdout and the freeze are never evaluated. Starting over means deleting the state files by hand.

**Statistics (only for rules that passed the gate).**

- *Effective N*: participation ratio `(Σλ)² / Σλ²` of the correlation matrix of all rules' net returns
  (gated rules were tried too), with a 90% stationary-bootstrap interval (the interval is widened to include
  the point estimate, because resampling biases the ratio downward). It is scaled by `max(1, N / grid size)`.
- *Reality check*: a Romano-Wolf stepdown test on the studentised mean excess return over holding the asset
  the same share of time, using a stationary bootstrap (2,000 replicates). The excess is used because a plain
  "mean > 0" test passes every long-only rule in a rising sample. Adjusted p-values are per rule.
- *DSR* (Bailey and Lopez de Prado): uses the effective N, the variance of Sharpe ratios across all rules,
  skewness, kurtosis and sample length; the expected-maximum Sharpe is floored at zero. `dsr_sensitivity` shows
  the DSR at both ends of the effective-N interval.
- *PBO* (CSCV over up to 16 blocks): flagged `noisy` below 2,000 bars or 4 rules, where it is a rough warning.
- *Sharpe standard errors*: Mertens' formula per rule; `uncertainty` also gives the i.i.d. standard error for
  the research and holdout lengths. Any sub-window is wider.
- All randomness uses a seed derived from the dataset path and the research fingerprint (not from costs or
  settings, and not configurable), so repeating a run gives the same numbers.

**Integrity checks.** Every report lists the mean, 99th percentile and maximum close-to-open gap in bps and a
look-ahead probe: every rule is recomputed on frames truncated at five points (including 75% of the research
bars) and its targets must match the full-window ones, otherwise the run fails with 500 and is logged as failed.

**State directory.** The ledger lives in `--state-dir` (default `<data-dir>/.tvdata-verdict`, hidden so the
dataset scan ignores it). The Explorer, Charts and report routes are descriptive and still show every bar,
holdout included; only the Research page and the verdict engine stop at the seal.

**Out of scope for v1:** combinatorial purged cross-validation, purging and embargo, intrabar stop logic,
funding, liquidation and regime analysis.

### Data providers

The Providers page fetches from external data providers through the backend. There are five:

- [Alpha Vantage](https://www.alphavantage.co/documentation/): 128 endpoints (stocks, indices, options,
  FX, crypto, commodities, economic indicators, fundamentals, news sentiment, 50+ technical
  indicators), 11 of which are **premium**.
- [Marketstack v2](https://docs.apilayer.com/marketstack/docs/marketstack-api-v2-v-2-0-0): all 46
  endpoints of its OpenAPI document (exchanges, end-of-day and intraday prices by exchange, ticker or
  globally, tickers, splits and dividends, indices, bonds, ETF holdings, real-time prices,
  commodities, analyst ratings, SEC EDGAR company data, currencies and timezones), 26 of which are
  **premium**. Marketstack has subscription tiers, so each premium endpoint names the cheapest plan
  that includes it (Basic, Professional or Business; the plan table is on
  [marketstack.com/pricing](https://marketstack.com/pricing)). Some free endpoints have premium
  *options*: intraday intervals below 15 minutes need Professional (`1min`, `5min`, `10min` are marked
  in the dropdown), and history beyond one year needs a paid plan. ETF endpoints cost 20 requests of
  the monthly quota and the form says so before you fetch. The endpoints that take a date in the path accept `YYYY-MM-DD` or a full ISO-8601
  timestamp such as `2020-05-21T00:00:00+0000`. A plan that lacks an endpoint is refused by
  Marketstack (`function_access_restricted`) and reported as `premium_required`. Its free plan allows
  100 requests a month, so repeat requests are cached for five minutes there too.
- [Alpaca Market Data](https://docs.alpaca.markets/us/docs/getting-started): the 42 request-and-answer
  endpoints of its Market Data API (US stocks and ETFs, options with the chain and greeks, crypto with the order book,
  forex, fixed income, news, the most active stocks and top movers, corporate actions). It needs a key ID **and**
  a secret from a free Alpaca account. Alpaca's plans for individuals, **Basic** (free, 200 calls a
  minute) and **Algo Trader Plus** ($99 a month, 10,000 calls a minute), differ in the feed, how recent
  the data may be and the rate limit, not in which endpoints exist, so every endpoint is labelled
  **Basic** and the tiers are attached to what each plan unlocks. Choices are labelled in the
  dropdowns (`IEX · Basic`, `SIP, all US exchanges · Algo Trader Plus`, `Indicative · Basic`, `OPRA, real
  time · Algo Trader Plus`) and the paid ones are marked; the end of a historical range carries the
  15-minute limit of Basic, and a response says what Alpaca used when you left the feed or the end
  blank. A request the plan refuses (`subscription does not permit querying recent SIP data`) is
  reported as `premium_required` with the plan that would allow it. Only market data is used: no
  orders and no account data, and the Broker API (a different login) is not supported. The logo image
  and the corporate-actions event stream are left out because they are not a request with an answer.
  Real-time data and per-minute limits mean results are cached for 30 seconds, not five minutes.
- [Financial Modeling Prep](https://site.financialmodelingprep.com/developer/docs) (FMP): 151 endpoints of
  its stable API (search and screener, profiles, quotes for stocks, indices, forex, crypto and
  commodities, income statements, balance sheets, cash flows, ratios and growth, end-of-day and
  intraday prices, technical indicators, analyst estimates and ratings, earnings, dividend and IPO
  calendars, economic data, sector and industry performance, news, transcripts, ETF and fund holdings,
  13F filings, insider trades, SEC filings, index members, market hours and DCF valuations), 67 of
  which a free key is refused outright (**premium**). Endpoints that differ only by a path segment (the four
  price-history variants, the intraday intervals, the nine technical indicators) are one endpoint with
  a dropdown. FMP's plans are **Basic** (free, 250 requests a day), **Starter**, **Premium** and
  **Ultimate**. FMP does not say which plan an endpoint needs, so every endpoint was called with a
  free key to see what it refuses (HTTP 402, reported as `premium_required` with FMP's own message),
  and a premium badge names a plan only where the
  [pricing page](https://site.financialmodelingprep.com/pricing-plans) names the feature group (news
  is Starter; intraday charts and technical indicators are Premium; transcripts, ETF and fund
  holdings, 13F and batch quotes are Ultimate); the others say **Premium** alone. The rest of the free plan is
  *limited* access, described below. The key is sent in the `apikey` header, so it appears in no URL.
  Government trading, ESG, Commitment of Traders, the as-reported statements and the statement-growth
  variants are not in the catalog, nor are the bulk CSV and partner endpoints. FMP's Market Data page
  shows that the fundraiser endpoints are open on the free plan too; they are not added yet.

  **What a free (Basic) key can and cannot do.** FMP's Market Data page marks each endpoint *Full*,
  *Limited* or *No access* on the free plan and does not say what *Limited* means. Calling the live API
  with a free key showed three limits, each refused with HTTP 402 (`premium_required`) and each noted
  beside the field it concerns in the form:

  - **Which symbols.** 39 endpoints (quotes, prices, statements, ratios, key metrics, analyst data,
    dividends, earnings, DCF and more) accept only a fixed list of 87 stocks and ETFs (`AAPL`, `MSFT`,
    `NVDA`, `TSLA`, `SPY`, `TSM`, `SHOP`... the list is what *All Shares Float* returns on a free key;
    it is `BASIC_SYMBOLS` in `fmp_catalog.py`) plus a few indices, currency pairs, cryptocurrencies and
    commodities (`^GSPC`, `EURUSD`, `BTCUSD`, `GCUSD`...). Any other symbol is refused, even a large
    US company (`ORCL`, `PLUG`, `GME`, `QQQ`). *Company profile* accepts any US-traded symbol, OTC
    included, and refuses other exchanges (`SAP.DE`, `RY.TO`). Endpoints that list many symbols at once
    do not refuse anything: the earnings, dividends and splits calendars and *All Shares Float* quietly
    return only the rows of that list, so they are a part of the market, not all of it (the endpoint
    descriptions say so). The full-access endpoints take any symbol: search by symbol, name or CIK,
    profile by CIK, stock peers, SEC company profile, financial report dates, the biggest gainers,
    losers and most active stocks, market hours and the symbol lists of forex, crypto, commodities and
    indices.
  - **How many rows.** `limit` has a cap per endpoint: 5 on statements, key metrics, ratios, growth,
    enterprise values, owner earnings, dividends, earnings, splits, employee counts and the latest
    mergers (so a statement reaches back five periods, annual or quarterly); 10 on analyst estimates
    and historical grades; 1 on historical ratings; 20 on the SEC filing searches; 100 on insider
    trades. `ROW_CAPS` has the list.
  - **How far back.** A start date (`from`, or `date` for the sector and industry snapshots) must be
    within the last 30 days on the earnings, dividends and splits calendars, the latest 8-K and
    financial filings, SEC filings by form type, and the sector and industry performance and PE
    snapshots; within a year on SEC filings by symbol or CIK. How far forward a calendar looks is not
    limited. Price history, treasury rates, sector history and economic indicators are not limited
    this way: daily prices for `AAPL` go back to 1985.

  The same plan allows 250 requests a day and 500 MB of data over a rolling 30 days. Quarterly
  periods are not restricted. The limits were measured in November 2026 and FMP does not publish them,
  so the lists are `fmp_catalog.py` data (`SYMBOL_LIMITED`, `ROW_CAPS`, `RECENT_30`, `RECENT_YEAR`) to
  update when FMP changes them; a paid key is never held to them, because the form only notes a limit
  and does not enforce it.

  **Ratios and growth** (ratios, key metrics, financial growth and their trailing-twelve-month
  versions) are fractions in FMP's data (`0.469`). The page shows each as a percentage that says what
  it is a share of or a change against, with FMP's own figure in brackets: `46.91% of revenue (0.4691)`,
  `151.91% of shareholders' equity (1.5191)`, `+6.43% vs prior period (0.0643)`. Multiples (price to
  earnings, turnover, coverage, days, per-share amounts) are not shares of anything and stay numbers.
  The bases are listed in `fmp_ratios.py`; a ratio that is not listed is shown as FMP sent it.
- [Finnhub](https://finnhub.io/docs/api/): the 113 GET endpoints of its OpenAPI document (symbol search
  and lists, market status and holidays, quotes, company profiles, market and company news, peers, basic
  financials, ownership, insider transactions and sentiment, standardised and as-reported statements, SEC
  filings, IPO and earnings calendars, recommendation trends, price targets, upgrades and downgrades,
  estimates, EPS surprises, candles and ticks, ETFs, indices, mutual funds, bonds, forex, crypto, technical
  analysis, alternative data and economic data), 84 of which are **premium**. Unlike the other specs,
  Finnhub's marks each endpoint's access itself, and calling every endpoint with a free key matched it
  exactly: the 29 free endpoints answered and every other one was refused (`You don't have access to this
  resource.`, reported as `premium_required`). Its pricing table has two columns, **Free** (60 requests a
  minute) and **All-in-One** ($3,500 a month), so premium endpoints are labelled All-in-One, except the ones
  no plan in that table includes: earnings call transcripts (the pricing page says All-in-One leaves them
  out), Enterprise data and Global Filings Search (sold separately) and International Filings (approved case
  by case). Where the spec names a narrower package (`Accessible with Fundamental 2 or All in One
  subscription.`) the endpoint says so. The three POST endpoints (AI Copilot, Global Filings Search, Search In
  Filing) and the websocket are not included. The key is sent in the `X-Finnhub-Token` header, so it appears
  in no URL. Quotes are real time, so results are cached for 30 seconds.

  **What a free key can and cannot do** (measured with a free key in November 2026; Finnhub states only
  some of it):

  - **US only.** Quotes, profiles, news, basic financials, EPS surprises, filings and the other per-symbol
    endpoints refuse a symbol listed elsewhere (`RY.TO`, `SAP.DE`, `VOD.L`); the symbol list, market status
    and holidays refuse a non-US exchange. Finnhub answers with HTTP 401 or 403 and a generic message, so the
    page explains it in plain words with Finnhub's message in brackets. Quotes also work for US ETFs and
    some crypto pairs (`BINANCE:BTCUSDT`), not for forex (`OANDA:EUR_USD`) or CFD indices (`^GSPC`).
  - **How far back, how many rows.** Company news reaches about a year back and returns at most about 250
    articles per request, newest first, so a long range shows only its last days (the answer says so). The
    earnings calendar reaches 30 days back and returns at most 1,500 rows. EPS surprises are the last 4
    quarters.
  - **No price history.** Candles (stocks, forex, crypto), tick data and technical indicators need a paid
    plan.
  - **Unknown symbols.** Finnhub answers a symbol it does not know (symbols are case sensitive) with an
    all-zero quote rather than an error. That is reported as `empty`, never drawn as a price of 0.

  Examples come from Finnhub's documentation; the ones that would age out (company news, the earnings
  calendar, and USA Spending, which answers its own 2021-2022 example with no rows) use recent dates
  instead. Finnhub serves the full US symbol list (about 31,000 rows, 7 MB) as a file on its static host:
  the backend follows that one redirect, only to an `https://*.finnhub.io` address and without the key.

  **Units.** Company profiles give market capitalisation and shares outstanding in millions, and the labels
  say so. Basic financials are shown as Finnhub sends them: among the figures, volumes are in millions of
  shares, market capitalisation and enterprise value in millions, and margins, returns, growth and yields
  are already percentages (`48.79` means 48.79%); in the annual and quarterly tables, margins and returns
  are fractions (`0.4879`), which the margin chart shows as percentages.

#### Which provider for what

The providers overlap less than it seems; on free keys each is the better source for different things:

| Need | Free source to use | Why |
| --- | --- | --- |
| Real-time US quotes, many times a day | Finnhub (60 a minute) or Alpaca (200 a minute) | Alpha Vantage allows 25 requests a day; FMP 250 a day, for a fixed list of symbols |
| Daily price history | Alpaca, FMP, Alpha Vantage or Marketstack | Finnhub's candles are premium |
| Company news | Finnhub (any US symbol, a year back), Alpaca, Alpha Vantage (with sentiment scores) | FMP's news is premium |
| Analyst recommendations, EPS surprises, earnings calendar | Finnhub | FMP's analyst data covers only its fixed list on a free key |
| Insider trades and insider sentiment | Finnhub (MSPR is its own measure) | FMP caps insider trades at 100 rows |
| Financial statements | FMP (standardised, 5 periods, fixed list) or Finnhub (as filed with the SEC, any US company, back to 2010) | |
| Ratios and key metrics | Finnhub basic financials (130+ figures with annual and quarterly history, any US symbol) or FMP | |
| SEC filings | Finnhub (any US company, back to 2014) or FMP (up to a year back) | |
| Alternative data | Finnhub: lobbying, government spending, H-1B visas, patents, FDA meetings | None of the others has these |
| Stocks listed outside the US | Marketstack (end of day, 100 requests a month) | Finnhub and FMP free keys refuse them |
| Options, crypto order books | Alpaca | |


All of them share these rules:

- **The key stays on the server.** Put `ALPHAVANTAGE_API_KEY=your_key`, `MARKETSTACK_API_KEY=your_key`,
  `FMP_API_KEY=your_key`, `FINNHUB_API_KEY=your_key` and/or `ALPACA_API_KEY_ID=your_key_id` with `ALPACA_API_SECRET_KEY=your_secret` in the backend's environment
  or in a `.env` file where you run `tvdata serve` (or pass `--env-file PATH`), then restart it.
  `.env.example` shows the format; `.env` is git-ignored. The key (for Alpaca, the key ID and the secret, sent as headers) is only ever placed in the upstream
  request: it is never returned, logged, cached or shown in a message, and any text echoing it is
  scrubbed. Without a key the catalog still browses and a query answers `not_configured` without
  contacting the provider.
- **Nothing is fetched automatically.** Only an explicit query reaches the provider. Alpha Vantage
  free keys allow 25 requests a day, so successful results are cached for five minutes per API key (repeat
  requests are free; `refresh` spends one), and errors are never cached.
- **Premium endpoints are flagged** in the catalog, and a key that is not entitled is detected even
  though Alpha Vantage answers HTTP 200 with an *artificial sample payload*: that data is never
  turned into views and the status is `premium_required`. A few free endpoints have premium-gated
  *parameters* (for example `outputsize=full`); these carry a `premium_note`.
- **The catalogs are generated from the documentation** and committed
  (`tradingview_data/providers/alphavantage_catalog.json`, `marketstack_catalog.json`,
  `alpaca_catalog.json`, `finnhub_catalog.json`). Regenerate them when a provider adds endpoints:
  `python -m tradingview_data.providers.alphavantage_docs`,
  `python -m tradingview_data.providers.marketstack_docs` (it reads Marketstack's published OpenAPI
  document and the commodity list it links to; the plan each endpoint needs is kept in `OPERATIONS`
  in that module, because the OpenAPI document does not state it) or
  `python -m tradingview_data.providers.alpaca_docs` (it reads the OpenAPI definition embedded in each
  Market Data reference page listed in Alpaca's `llms.txt`; the tier rules are in `alpaca_docs.py`,
  taken from Alpaca's "Subscription Plans" section) or `python -m tradingview_data.providers.finnhub_docs`
  (it reads Finnhub's Swagger document, https://finnhub.io/static/swagger.json, whose `premium` and
  `freeTier` fields give each endpoint's plan; the pricing-table exceptions, the measured free-plan limits
  and the example dates are kept in `finnhub_docs.py`). FMP's catalog is not generated: FMP publishes no
  machine-readable spec, so `tradingview_data/providers/fmp_catalog.py` is a hand-written table whose
  paths and plans were checked against the live API (`PAID_PLANS` lists what a free key is refused).
- **Times are UTC.** Intraday timestamps are converted from the provider's time zone (US/Eastern) and
  the response says so. The exception is FMP, whose intraday timestamps carry no time zone: they are
  shown as returned and the chart says so. Finnhub sends UNIX timestamps, shown in UTC; its FDA meeting
  calendar is in US Eastern time, as sent, and the answer says so.

To add a provider: (1) write a module with a `Provider` subclass (`tradingview_data/providers/base.py`):
`info`, `configured()`, `catalog()` and `query()`; (2) have `query` return the response shape above,
building views with `providers/views.py`; (3) classify provider-side failures into the status values
rather than raising; (4) never put the key in a response; (5) register it in
`providers/registry.py`; (6) add its tests. It then appears in the dropdown with no frontend change.

### Trading (Alpaca, paper or live)

`/api/trading` places and manages orders through the [Alpaca Trading API](https://docs.alpaca.markets/us/docs/getting-started-with-trading-api),
for a **paper** account (simulated money, the default) or a **live** one. Every route is under
`/api/trading/{env}` with `env` = `paper` or `live`; `GET /api/trading/environments` says which is ready.
Every answer has the same envelope: `{environment, status, message, code, http_status, outcome_unknown,
client_order_id, data, fetched_at, elapsed_ms}`. What Alpaca refuses (insufficient buying power, a bad key, a
rate limit) is a 200 with a `status` (`rejected`, `invalid_key`, `rate_limited`, `not_found`, ...) and Alpaca's own
words in `message`; a request that is wrong before it leaves is a 422 with one plain sentence.

| Route | What it does |
| --- | --- |
| `GET .../account`, `GET/PATCH .../account/configurations` | Equity, cash, buying power, margin and flags; the account settings (suspend trading, no shorting, fractional, margin multiplier, options level, email confirmations). |
| `GET .../account/activities[/{TYPE}]`, `GET .../account/portfolio-history` | Fills and other activity with paging; the equity curve (`period`, `timeframe`, ...). |
| `GET .../clock`, `GET .../calendar` | Whether the market is open and when it next is; market days. |
| `GET .../assets?search=`, `GET .../assets/{symbol}` | Symbol search over Alpaca's asset list (fetched once per ten minutes); one asset. |
| `GET .../options/contracts[/{symbol}]` | Option contracts filtered by underlying, type, strike and expiry. |
| `GET .../quote/{symbol}` | Bid, ask, last and the day so far, from Alpaca's market data with the same keys. |
| `GET/POST/DELETE .../orders`, `GET/PATCH/DELETE .../orders/{id}`, `GET .../orders/by-client-id/{id}` | List, place, cancel all, read, replace, cancel and look up by client ID. |
| `GET/DELETE .../positions`, `GET/DELETE .../positions/{symbol}`, `POST .../positions/{contract}/exercise`, `.../do-not-exercise` | Open positions; close one (all, `qty` or `percentage`) or all; exercise an option or leave it to expire. |
| `GET/POST .../watchlists`, `GET/PUT/DELETE .../watchlists/{id}`, `POST .../watchlists/{id}/assets`, `DELETE .../watchlists/{id}/assets/{symbol}` | Watchlists. |

- **Keys.** Paper reads `ALPACA_PAPER_API_KEY_ID` and `ALPACA_PAPER_API_SECRET_KEY`, or the market-data pair
  (`ALPACA_API_KEY_ID`, `ALPACA_API_SECRET_KEY`) if those are not set. Live reads only `ALPACA_LIVE_API_KEY_ID` and
  `ALPACA_LIVE_API_SECRET_KEY`, and is **off** until `ALPACA_ENABLE_LIVE_TRADING=true` is set: until then every live
  route answers 403 and nothing is sent. Paper keys do not work on the live host and live keys do not work on the
  paper host, so a mix-up is refused by Alpaca and cannot place a trade. Keys are sent as headers only, scrubbed
  from everything returned or logged, and never returned.
- **Orders are checked before they leave.** Every rule below is one Alpaca documents: an order type, time in
  force or order class that the kind of asset does not offer; `qty` and `notional` together or neither; a price field
  that the order type would ignore (a `limit_price` on a market order reads like a cap and is not one); fractional
  quantities with anything but `day`; bracket, oto and oco orders without the exit legs they need; multi-leg options
  without two to four option legs. Everything else is left to Alpaca. Orders support stocks and ETFs, options
  (single leg and multi-leg), and crypto, with market, limit, stop, stop-limit and trailing-stop types, all time-in-force
  values, extended hours, notional and fractional quantities, and bracket, oto and oco classes.
- **One request, once.** Nothing is retried, because a retried order could be placed twice. Every order gets a
  client order ID (yours, or `tvdata-<random>`), which Alpaca requires to be unique, so sending the same order
  twice is refused. If the connection fails, or Alpaca answers with a server error (5xx), after a request that
  changes something may have been applied, the answer has `outcome_unknown: true` and the `client_order_id` to
  look the order up by.
- **Audit log.** Every request that changes something is appended to `<data-dir>/.tvdata-trading/trading-audit.jsonl`
  (time, environment, what was sent, what came back; no keys). The directory is created owner-only (0700) and the
  file 0600, whatever the umask, because it records what you traded.
- **The server has no login, so three guards protect it.** The connecting address must be this machine (loopback;
  add addresses or ranges with `TVDATA_TRADING_ALLOWED_CLIENTS`, e.g. a Docker bridge such as `172.17.0.0/16`):
  headers can be forged by another computer, so this is what keeps a server bound to a network interface from
  trading for strangers, and every `/api/trading` route answers 403 to anyone else. The `Host` header must be
  `localhost`, `127.0.0.1` or `::1` (add names with `TVDATA_TRADING_ALLOWED_HOSTS`), which stops a web page from
  reaching the server through its own domain. And every request that changes something needs an
  `X-Tvdata-Trading: 1` header, which a browser will not send from another site without the server's agreement.
  Without a login of its own, anyone you let in can trade your account: allow only addresses you control.
  Two things widen who is let in. A web page served from an origin you pass to `--cors-origin` can place orders from
  your browser (the origin is what the browser is told to trust), so list only origins you control. And a proxy:
  uvicorn replaces the connecting address with the `X-Forwarded-For` value when the connection comes from a local
  proxy, and a proxy that passes a caller's header through (Vite's dev proxy does, so `vite dev --host` would let any
  caller claim `127.0.0.1`) would defeat the check. So **a request that carries `X-Forwarded-For`, `Forwarded` or
  `X-Real-IP` is refused with a 403**; a browser talking to the dashboard directly, including through Vite on
  `localhost`, sends none of them. If you run a reverse proxy of your own in front of `tvdata serve`, set
  `TVDATA_TRADING_TRUST_PROXY=true`, and configure the proxy to **overwrite** `X-Forwarded-For` with the address it
  saw (nginx: `proxy_set_header X-Forwarded-For $remote_addr;`, not `$proxy_add_x_forwarded_for`) and to discard
  `Forwarded` and `X-Real-IP` from callers; the resolved address is then checked against the list as usual. Setting
  it for a proxy that does not do that removes this protection.
- **Not included.** Crypto funding (wallets, withdrawals, whitelisted addresses), tokenization, short locates (not
  available in paper), the activity event stream, Elite/DMA advanced routing, the deprecated corporate-action
  announcements (use the Providers page's Alpaca *Corporate actions*), and the order-update WebSocket (read orders
  again instead). Alpaca's Broker API, a different login, is not supported.

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

The **Trading** page (`/trading`) is the screen for [Alpaca trading](#trading-alpaca-paper-or-live):
the same page for a paper and a live account, with paper as the default. A banner always says which one
you are on, red for live. It has an account overview with the equity curve, an order ticket (every order
type, time in force, bracket/oto/oco exits, options and multi-leg options, crypto, fractional and
dollar-sized orders, extended hours) that shows a review before anything is sent, the order and position
lists with cancel, replace and close (all, a quantity or a percentage), watchlists, activity, and the account
settings. With real money every order and bulk action also asks you to type `LIVE`. Paper needs
`ALPACA_PAPER_API_KEY_ID` and `ALPACA_PAPER_API_SECRET_KEY` in `.env`; live stays off until
`ALPACA_ENABLE_LIVE_TRADING=true`.

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
