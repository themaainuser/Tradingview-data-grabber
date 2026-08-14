# tradingview-scraper

Real-time TradingView websocket scraper for crypto and stocks, with charting/visualization tooling.

## Install

```
pip install -r requirements.txt
```

## Tools

### 1. Live OHLCV streaming to CSV — `livestreamtest.py`

Streams live candlestick data (open/high/low/close/volume) from TradingView's websocket into a CSV.
Reconnects with backoff, writes incrementally (no data loss on crash), dedupes bars, and updates the
forming candle in place.

```
python livestreamtest.py -n BINANCE:BTCUSDT -t 1 -b 300 -o data -s
```

| Flag              | Meaning                                                   | Default           |
| ----------------- | --------------------------------------------------------- | ----------------- |
| `-n, --symbol`    | symbol (e.g. `BINANCE:BTCUSDT`, `NSE:RELIANCE`)           | `BINANCE:BTCUSDT` |
| `-t, --timeframe` | bar timeframe in minutes                                  | `1`               |
| `-b, --bars`      | bars requested on connect (TradingView caps ~5000 for 1m) | `300`             |
| `-o, --output`    | output data folder, one CSV per symbol inside             | `data`            |
| `-s, --silent`    | don't print raw websocket messages                        | off               |

CSV columns: `index, time, open, high, low, close, volume` — `time` is IST
(`Fri Aug 14 2026 07:36:00 GMT+0530` format). `[index]` counts up from `[0]` as bars stream in.

Multiple symbols share one websocket (one chart session each):

```
python livestreamtest.py -n BINANCE:BTCUSDT,ETHUSDT,NSE:RELIANCE -s
```

Output layout: `data/<symbol>.csv` per symbol, e.g. `data/BINANCE_BTCUSDT.csv`.

### 2. Live quote streaming — `main.py`

Streams quote data (last price, bid/ask, volume, etc.) and prints the current price.

```
python main.py -n BINANCE:BTCUSDT
```

| Flag           | Meaning                                   |
| -------------- | ----------------------------------------- |
| `-n, --symbol` | symbol (required)                         |
| `-s, --silent` | only print the current price (`lp` field) |
| `-o, --output` | append raw frames to a file               |
| `-q, --quit`   | exit after the first price update         |

### 3. Charts & heatmaps — `visuals.py`

Turns captured CSVs into charts and an HTML dashboard:

```
python visuals.py captured_btc.csv                # single symbol
python visuals.py btc.csv eth.csv sol.csv         # adds a correlation heatmap
python visuals.py captured_btc.csv -o charts      # custom output dir
```

Generated charts (`charts/` by default):

| File                               | What it shows                              |
| ---------------------------------- | ------------------------------------------ |
| `1_candles_volume.png`             | candlesticks + volume                      |
| `2_volume_profile.png`             | volume profile (POC, value areas)          |
| `3_volume_by_time_heatmap.png`     | when liquidity trades (hour x 5-min)       |
| `4_volatility_by_time_heatmap.png` | when price moves (hour x 5-min)            |
| `5_price_time_heatmap.png`         | volume density across time x price         |
| `6_returns_atr.png`                | return distribution + ATR(14)              |
| `7_correlation_heatmap.png`        | cross-symbol correlation (multi-file only) |

Open `charts/dashboard.html` for an interactive view: pin any 4 charts by drag-and-drop
(enable "Edit layout"), click any chart for full size, auto-refresh, Clear/Reset.

### 4. Authenticated session — `getAuthToken.py`

Connects with a TradingView account instead of the anonymous token. Requires `TV_USERNAME`
and `TV_PASSWORD` environment variables (put them in `.env`, which is gitignored).

### 5. Protocol helpers — `helpers.py`

Frame encode/decode for the TradingView socket protocol: `sendMessage`, `iter_frames`,
`is_heartbeat`, session/chart-session generators.

## Notes

- TradingView historically caps history around 5000 bars for 1-minute (less for higher timeframes).
- OHLCV data cannot produce order-flow visuals (CVD, liquidation maps, OI/PCR, gamma) — see
  `visuals_guide.md` for what each visual type needs and how useful it is per trading style.
- See `visuals_guide.md` for a researched breakdown of visuals for crypto vs Indian (NSE/BSE) trading.

## Tests

```
python -m pytest tests
```

## Credits / original project

Originally forked from the 2020 [tradingview-scraper](https://github.com/0xrushi/tradingview-scraper)
by [rushic24](https://github.com/0xrushi); auth-token flow credited to
[euvgub](https://github.com/euvgub).
