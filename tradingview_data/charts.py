"""Static OHLCV charts and a self-contained interactive HTML gallery."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Iterable, Sequence

import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .analytics import add_indicators, load_ohlcv
from .storage import safe_filename

plt.rcParams["figure.dpi"] = 110

GREEN = "#26a69a"
RED = "#ef5350"
HEAT = "YlOrRd"


def load_csv(path: str | Path) -> pd.DataFrame:
    """Compatibility alias for the validated OHLCV loader."""

    return load_ohlcv(path)


def _save(fig: plt.Figure, outdir: str | Path, name: str, title: str) -> Path:
    destination = Path(outdir)
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / name
    fig.suptitle(title, fontsize=13, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.965))
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def _ticks(data: pd.DataFrame, count: int = 8) -> tuple[np.ndarray, list[str]]:
    positions = np.unique(np.linspace(0, len(data) - 1, min(count, len(data))).astype(int))
    labels = [data.index[position].strftime("%m-%d %H:%M") for position in positions]
    return positions, labels


def _price_bounds(data: pd.DataFrame) -> tuple[float, float]:
    low = float(data["low"].min())
    high = float(data["high"].max())
    if low == high:
        margin = max(abs(low) * 0.005, 1.0)
        return low - margin, high + margin
    return low, high


def _date_formatter(data: pd.DataFrame) -> mdates.DateFormatter:
    """Keep date-axis labels aligned with the capture timezone."""

    return mdates.DateFormatter("%m-%d %H:%M", tz=data.index.tz)


def chart_candles(data: pd.DataFrame, outdir: str | Path) -> Path:
    """Generate a candlestick and volume chart."""

    fig, (price_axis, volume_axis) = plt.subplots(
        2,
        1,
        figsize=(13, 8),
        sharex=True,
        gridspec_kw={"height_ratios": [3, 1]},
    )
    x = np.arange(len(data))
    up = (data["close"] >= data["open"]).to_numpy()
    for color, mask in ((GREEN, up), (RED, ~up)):
        subset = data.iloc[np.flatnonzero(mask)]
        positions = x[mask]
        price_axis.vlines(positions, subset["low"], subset["high"], color=color, linewidth=0.8)
        price_axis.bar(
            positions,
            (subset["close"] - subset["open"]).abs(),
            bottom=subset[["open", "close"]].min(axis=1),
            color=color,
            width=0.7,
            edgecolor=color,
        )
    volume_axis.bar(x, data["volume"], color=np.where(up, GREEN, RED), width=0.8)
    positions, labels = _ticks(data)
    volume_axis.set_xticks(positions, labels, rotation=30, ha="right")
    price_axis.set_ylabel("price")
    volume_axis.set_ylabel("volume")
    price_axis.grid(alpha=0.2)
    volume_axis.grid(alpha=0.15, axis="y")
    return _save(fig, outdir, "1_candles_volume.png", "Candles + Volume")


def volume_profile(data: pd.DataFrame, bins: int = 60, value_area: float = 0.7) -> dict[str, np.ndarray | float]:
    """Distribute OHLCV volume across price bins and calculate POC/value area."""

    if bins < 2:
        raise ValueError("bins must be at least 2")
    low, high = _price_bounds(data)
    edges = np.linspace(low, high, bins + 1)
    mids = (edges[:-1] + edges[1:]) / 2
    profile = np.zeros(bins)

    for row in data[["high", "low", "volume"]].itertuples(index=False):
        candle_high, candle_low, volume = map(float, row)
        if candle_high <= candle_low:
            index = np.clip(np.searchsorted(edges, candle_high, side="right") - 1, 0, bins - 1)
            profile[index] += volume
            continue
        span = candle_high - candle_low
        overlaps = np.maximum(
            0,
            np.minimum(candle_high, edges[1:]) - np.maximum(candle_low, edges[:-1]),
        )
        profile += volume * overlaps / span

    poc_index = int(np.argmax(profile))
    selected: set[int] = {poc_index}
    target = profile.sum() * value_area
    covered = profile[poc_index]
    lower, upper = poc_index - 1, poc_index + 1
    while covered < target and (lower >= 0 or upper < bins):
        lower_volume = profile[lower] if lower >= 0 else -1
        upper_volume = profile[upper] if upper < bins else -1
        if upper_volume >= lower_volume:
            selected.add(upper)
            covered += upper_volume
            upper += 1
        else:
            selected.add(lower)
            covered += lower_volume
            lower -= 1
    return {
        "edges": edges,
        "mids": mids,
        "profile": profile,
        "poc": float(mids[poc_index]),
        "value_low": float(edges[min(selected)]),
        "value_high": float(edges[max(selected) + 1]),
    }


def chart_volume_profile(data: pd.DataFrame, outdir: str | Path) -> Path:
    """Generate volume-at-price, POC, and 70% value-area visualization."""

    profile = volume_profile(data)
    edges = profile["edges"]
    mids = profile["mids"]
    values = profile["profile"]
    assert isinstance(edges, np.ndarray) and isinstance(mids, np.ndarray) and isinstance(values, np.ndarray)
    poc = float(profile["poc"])
    value_low = float(profile["value_low"])
    value_high = float(profile["value_high"])
    fig, (histogram_axis, price_axis) = plt.subplots(
        1,
        2,
        figsize=(12, 7),
        sharey=True,
        gridspec_kw={"width_ratios": [1, 3]},
    )
    normalized = (values - values.min()) / max(float(values.max() - values.min()), 1e-9)
    histogram_axis.barh(
        mids,
        values,
        height=edges[1] - edges[0],
        color=plt.get_cmap(HEAT)(normalized),
        edgecolor="none",
    )
    histogram_axis.invert_xaxis()
    for axis in (histogram_axis, price_axis):
        axis.axhline(poc, color="#1565c0", linewidth=1.2, linestyle="--", label="POC")
        axis.axhspan(value_low, value_high, color="#ffca28", alpha=0.16, label="70% value area")
    histogram_axis.set_ylabel("price")
    histogram_axis.set_title("Volume profile")
    price_axis.plot(data.index, data["close"], color="#263238", linewidth=1.2)
    price_axis.fill_between(data.index, data["low"], data["high"], alpha=0.15, color="#78909c")
    price_axis.xaxis.set_major_formatter(_date_formatter(data))
    price_axis.grid(alpha=0.2)
    price_axis.legend(loc="best", fontsize=8)
    return _save(fig, outdir, "2_volume_profile.png", "Volume Profile / Value Area")


def _time_grid(data: pd.DataFrame) -> pd.DataFrame:
    frame = data.copy()
    frame["hour"] = frame.index.hour
    frame["slot"] = (frame.index.minute // 5) * 5
    return frame


def _heatmap_axis(axis: plt.Axes, pivot: pd.DataFrame, cmap: str, label: str) -> None:
    image = axis.imshow(pivot, aspect="auto", cmap=cmap, interpolation="nearest")
    axis.set_yticks(range(len(pivot.index)), [str(value) for value in pivot.index])
    axis.set_xticks(range(len(pivot.columns)), [f"{value:02d}" for value in pivot.columns], rotation=90, fontsize=7)
    axis.set_xlabel("minute-of-hour (5-minute slots)")
    axis.set_ylabel("hour of day")
    axis.figure.colorbar(image, ax=axis, label=label)


def chart_time_volume_heatmap(data: pd.DataFrame, outdir: str | Path) -> Path:
    """Generate liquidity-by-time heatmap."""

    frame = _time_grid(data)
    pivot = frame.pivot_table(index="hour", columns="slot", values="volume", aggfunc="sum", fill_value=0)
    pivot = pivot.reindex(index=range(24), columns=range(0, 60, 5), fill_value=0)
    fig, axis = plt.subplots(figsize=(13, 6))
    _heatmap_axis(axis, pivot, HEAT, "volume")
    return _save(fig, outdir, "3_volume_by_time_heatmap.png", "When Does Liquidity Trade?")


def chart_volatility_heatmap(data: pd.DataFrame, outdir: str | Path) -> Path:
    """Generate average intra-candle range-by-time heatmap."""

    frame = _time_grid(data)
    frame["range_pct"] = np.where(
        frame["open"] != 0,
        (frame["high"] - frame["low"]) / frame["open"] * 100,
        np.nan,
    )
    pivot = frame.pivot_table(index="hour", columns="slot", values="range_pct", aggfunc="mean")
    pivot = pivot.reindex(index=range(24), columns=range(0, 60, 5)).fillna(0)
    fig, axis = plt.subplots(figsize=(13, 6))
    _heatmap_axis(axis, pivot, "RdYlGn_r", "average bar range %")
    return _save(fig, outdir, "4_volatility_by_time_heatmap.png", "Where Does Price Move?")


def chart_price_time_heatmap(data: pd.DataFrame, outdir: str | Path) -> Path:
    """Generate a volume-density heatmap across time and price."""

    low, high = _price_bounds(data)
    time_index = np.arange(len(data))
    density, _, _ = np.histogram2d(
        time_index,
        (data["high"] + data["low"]) / 2,
        bins=[max(len(data), 1), 80],
        range=[[0, max(len(data), 1)], [low, high]],
        weights=data["volume"],
    )
    fig, axis = plt.subplots(figsize=(13, 6))
    image = axis.imshow(
        density.T,
        aspect="auto",
        cmap=HEAT,
        interpolation="nearest",
        extent=[0, max(len(data), 1), low, high],
    )
    positions, labels = _ticks(data)
    axis.set_xticks(positions, labels, rotation=30, ha="right")
    axis.set_ylabel("price")
    fig.colorbar(image, ax=axis, label="volume density")
    return _save(fig, outdir, "5_price_time_heatmap.png", "Volume Density Across Time × Price")


def chart_returns_atr(data: pd.DataFrame, outdir: str | Path) -> Path:
    """Generate return distribution and ATR trend charts."""

    enriched = add_indicators(data)
    returns = enriched["close"].pct_change().dropna() * 100
    fig, (return_axis, atr_axis) = plt.subplots(2, 1, figsize=(13, 7))
    if returns.empty:
        return_axis.text(0.5, 0.5, "At least two bars are needed for returns", ha="center", va="center")
    else:
        return_axis.hist(returns, bins=min(50, max(10, len(returns) // 2)), color="#5c6bc0", alpha=0.8)
        return_axis.axvline(0, color="#263238", linewidth=0.8)
    return_axis.set_xlabel("bar return %")
    return_axis.set_ylabel("count")
    return_axis.grid(alpha=0.2)
    atr_axis.plot(enriched.index, enriched["atr_14"], color="#ef6c00", linewidth=1.3, label="ATR(14)")
    atr_axis.set_ylabel("ATR")
    atr_axis.xaxis.set_major_formatter(_date_formatter(data))
    atr_axis.grid(alpha=0.2)
    atr_axis.legend(loc="best")
    return _save(fig, outdir, "6_returns_atr.png", "Returns Distribution + ATR(14)")


def chart_technical_indicators(data: pd.DataFrame, outdir: str | Path) -> Path:
    """Generate price, RSI, and MACD technical-indicator panels."""

    frame = add_indicators(data)
    fig, (price_axis, rsi_axis, macd_axis) = plt.subplots(3, 1, figsize=(13, 10), sharex=True)
    price_axis.plot(frame.index, frame["close"], color="#263238", linewidth=1.3, label="close")
    price_axis.plot(frame.index, frame["ema_20"], color="#fb8c00", linewidth=1.0, label="EMA 20")
    price_axis.plot(frame.index, frame["sma_20"], color="#5e35b1", linewidth=1.0, label="SMA 20")
    price_axis.fill_between(frame.index, frame["bb_lower"], frame["bb_upper"], color="#90caf9", alpha=0.25, label="Bollinger bands")
    price_axis.plot(frame.index, frame["vwap"], color="#00897b", linewidth=1.0, label="VWAP")
    price_axis.set_ylabel("price")
    price_axis.grid(alpha=0.2)
    price_axis.legend(loc="best", ncol=3, fontsize=8)

    rsi_axis.plot(frame.index, frame["rsi_14"], color="#6a1b9a", linewidth=1.2, label="RSI 14")
    rsi_axis.axhline(70, color=RED, linestyle="--", linewidth=0.8)
    rsi_axis.axhline(30, color=GREEN, linestyle="--", linewidth=0.8)
    rsi_axis.fill_between(frame.index, 30, 70, color="#eceff1", alpha=0.7)
    rsi_axis.set_ylim(-1, 101)
    rsi_axis.set_ylabel("RSI")
    rsi_axis.grid(alpha=0.2)

    histogram_colors = np.where(frame["macd_hist"].fillna(0) >= 0, GREEN, RED)
    macd_axis.bar(frame.index, frame["macd_hist"], color=histogram_colors, width=0.02, alpha=0.65, label="histogram")
    macd_axis.plot(frame.index, frame["macd"], color="#1565c0", linewidth=1.1, label="MACD")
    macd_axis.plot(frame.index, frame["macd_signal"], color="#ef6c00", linewidth=1.1, label="signal")
    macd_axis.axhline(0, color="#263238", linewidth=0.7)
    macd_axis.set_ylabel("MACD")
    macd_axis.grid(alpha=0.2)
    macd_axis.legend(loc="best", fontsize=8)
    macd_axis.xaxis.set_major_formatter(_date_formatter(data))
    fig.autofmt_xdate()
    return _save(fig, outdir, "7_technical_indicators.png", "Trend, Momentum, and Volatility")


def chart_correlation(datasets: Sequence[tuple[str, pd.DataFrame]], outdir: str | Path) -> Path | None:
    """Generate a close-return correlation heatmap for overlapping symbols."""

    closes: list[pd.Series] = []
    labels: list[str] = []
    for label, data in datasets:
        closes.append(data["close"].rename(label))
        labels.append(label)
    combined = pd.concat(closes, axis=1, join="inner").dropna()
    if len(combined) < 2:
        return None
    correlation = combined.pct_change().dropna().corr()
    if correlation.empty:
        return None
    fig, axis = plt.subplots(figsize=(max(7, len(labels) * 1.25), max(6, len(labels) * 1.1)))
    image = axis.imshow(correlation, cmap="RdYlGn", vmin=-1, vmax=1)
    axis.set_xticks(range(len(correlation.columns)), correlation.columns, rotation=35, ha="right")
    axis.set_yticks(range(len(correlation.index)), correlation.index)
    for row in range(len(correlation.index)):
        for column in range(len(correlation.columns)):
            axis.text(column, row, f"{correlation.iloc[row, column]:.2f}", ha="center", va="center", fontsize=9)
    fig.colorbar(image, ax=axis, label="return correlation")
    return _save(fig, outdir, "8_correlation_heatmap.png", "Cross-Symbol Return Correlation")


def build_dashboard(outdir: str | Path, images: Iterable[tuple[Path, str]]) -> Path:
    """Build an offline gallery with full-size previews and persisted pins."""

    output = Path(outdir)
    cards: list[str] = []
    payload: list[dict[str, str]] = []
    for path, label in images:
        relative = path.relative_to(output).as_posix()
        payload.append({"path": relative, "label": label})
        safe_path = html.escape(relative, quote=True)
        safe_label = html.escape(label, quote=True)
        cards.append(
            "<article class='chart-card' data-search='{label_lower}'>"
            "<button class='preview' type='button' data-src='{path}' data-label='{label}' aria-label='Open {label} full size'>"
            "<img src='{path}' alt='{label}' loading='lazy' decoding='async'><span class='chart-title'>{label_text}</span></button>"
            "<button class='pin' type='button' data-src='{path}' data-label='{label}' aria-pressed='false'>Pin chart</button></article>".format(
                path=safe_path,
                label=safe_label,
                label_lower=html.escape(label.lower(), quote=True),
                label_text=html.escape(label),
            )
        )
    data_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    data_json = data_json.replace("</", "<\\/").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    document = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Market Data Gallery</title><style>
:root {
  color-scheme: dark;
  --page: #09131f;
  --surface: #101e2d;
  --surface-raised: #16283b;
  --surface-hover: #1b3148;
  --ink: #f0f6fb;
  --muted: #aabed0;
  --line: #31485e;
  --accent: #48c7b7;
  --accent-strong: #87f0df;
  --accent-soft: rgb(72 199 183 / 15%);
  --danger: #ffadad;
  --radius-panel: 20px;
  --radius-control: 10px;
  --shadow-panel: 0 20px 48px rgb(0 0 0 / 22%), 0 2px 8px rgb(0 0 0 / 16%);
  --motion-fast: 160ms;
}

* { box-sizing: border-box; }

html {
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

body {
  min-width: 320px;
  margin: 0;
  background:
    radial-gradient(circle at 5% -10%, rgb(72 199 183 / 18%), transparent 32rem),
    radial-gradient(circle at 94% 2%, rgb(76 139 255 / 16%), transparent 26rem),
    var(--page);
  color: var(--ink);
  font: 15px/1.5 Inter, ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
}

button, input { font: inherit; }

.shell { width: min(1360px, calc(100% - 48px)); margin: auto; }

.hero {
  border-bottom: 1px solid rgb(255 255 255 / 8%);
  background: linear-gradient(135deg, #0c1d2d 0%, #102d44 100%);
}

.hero-inner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  padding: 38px 0 34px;
}

.brand { display: flex; align-items: center; gap: 15px; }

.brand-mark {
  display: grid;
  width: 48px;
  height: 48px;
  place-items: center;
  border: 1px solid rgb(255 255 255 / 16%);
  border-radius: 15px;
  background: linear-gradient(145deg, rgb(126 240 223 / 28%), rgb(72 139 255 / 20%));
  color: var(--accent-strong);
  box-shadow: inset 0 1px 0 rgb(255 255 255 / 13%);
  font-size: 23px;
  font-weight: 800;
}

.eyebrow {
  margin: 0 0 2px;
  color: var(--accent-strong);
  font-size: 11px;
  font-weight: 750;
  letter-spacing: .14em;
  text-transform: uppercase;
}

h1, h2 { text-wrap: balance; }

h1 { margin: 0; font-size: clamp(1.65rem, 2.4vw, 2.25rem); letter-spacing: -.04em; }

.subtitle { max-width: 680px; margin: 9px 0 0; color: var(--muted); text-wrap: pretty; }

.offline-badge {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  min-height: 36px;
  padding: 7px 11px;
  border: 1px solid rgb(135 240 223 / 30%);
  border-radius: 999px;
  background: rgb(72 199 183 / 12%);
  color: var(--accent-strong);
  font-size: 12px;
  font-weight: 750;
  white-space: nowrap;
}

.offline-badge::before {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: currentColor;
  box-shadow: 0 0 0 4px rgb(135 240 223 / 10%);
  content: "";
}

main { padding: 28px 0 64px; }

.summary-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
  margin-bottom: 22px;
}

.summary-card, .section-panel {
  border: 1px solid var(--line);
  border-radius: var(--radius-panel);
  background: linear-gradient(145deg, rgb(22 40 59 / 96%), rgb(14 29 44 / 96%));
  box-shadow: var(--shadow-panel);
}

.summary-card { min-height: 108px; padding: 17px 19px; }
.summary-label { color: var(--muted); font-size: 12px; font-weight: 700; }
.summary-value { margin-top: 7px; color: var(--ink); font-size: 28px; font-weight: 780; letter-spacing: -.045em; font-variant-numeric: tabular-nums; }
.summary-detail { color: var(--muted); font-size: 11px; text-wrap: pretty; }

.section-panel { padding: 20px; }
.section-panel + .section-panel { margin-top: 20px; }

.section-heading {
  display: flex;
  align-items: start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

h2 { margin: 0; color: var(--ink); font-size: 17px; letter-spacing: -.02em; }
.section-copy { margin: 4px 0 0; color: var(--muted); font-size: 12px; text-wrap: pretty; }

.count {
  flex: 0 0 auto;
  padding: 4px 8px;
  border-radius: 999px;
  background: var(--accent-soft);
  color: var(--accent-strong);
  font-size: 11px;
  font-weight: 750;
  font-variant-numeric: tabular-nums;
}

.toolbar { display: flex; align-items: end; gap: 10px; flex-wrap: wrap; margin-bottom: 17px; }
.search-field { display: grid; flex: 1 1 250px; gap: 5px; }
.search-field label { color: var(--muted); font-size: 11px; font-weight: 700; }

.search-field input {
  min-height: 42px;
  padding: 9px 12px;
  border: 1px solid var(--line);
  border-radius: var(--radius-control);
  outline: none;
  background: #0c1927;
  color: var(--ink);
  box-shadow: inset 0 1px 1px rgb(0 0 0 / 20%);
  transition-property: border-color, box-shadow, background-color;
  transition-duration: var(--motion-fast);
  transition-timing-function: ease-out;
}

.search-field input:hover { border-color: #53718e; }
.search-field input:focus { border-color: var(--accent); box-shadow: 0 0 0 3px rgb(72 199 183 / 17%); }

button {
  min-height: 42px;
  padding: 9px 12px;
  border: 1px solid var(--line);
  border-radius: var(--radius-control);
  background: var(--surface-raised);
  color: var(--ink);
  cursor: pointer;
  font-size: 13px;
  font-weight: 720;
  transition-property: color, background-color, border-color, box-shadow, transform;
  transition-duration: var(--motion-fast);
  transition-timing-function: ease-out;
}

button:hover { border-color: #63839e; background: var(--surface-hover); }
button:active { transform: scale(.96); }
button:focus-visible, .preview:focus-visible, .search-field input:focus-visible { outline: 3px solid rgb(135 240 223 / 35%); outline-offset: 2px; }
button:disabled { cursor: not-allowed; opacity: .48; }

.clear { color: var(--danger); }
.clear:hover { border-color: rgb(255 173 173 / 55%); background: rgb(255 173 173 / 10%); }

.pins, .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 16px; }

.chart-card {
  display: grid;
  gap: 9px;
  padding: 8px;
  border: 1px solid var(--line);
  border-radius: 18px;
  background: linear-gradient(160deg, rgb(25 45 65 / 92%), rgb(15 29 43 / 92%));
  box-shadow: 0 12px 28px rgb(0 0 0 / 16%);
  transition-property: border-color, box-shadow, background-color;
  transition-duration: var(--motion-fast);
  transition-timing-function: ease-out;
}

.chart-card:hover { border-color: #50718d; box-shadow: 0 16px 32px rgb(0 0 0 / 24%); }

.preview {
  display: block;
  min-height: 0;
  padding: 0;
  border: 0;
  border-radius: 10px;
  background: transparent;
  text-align: left;
}

.preview:hover { background: transparent; }
.preview:active { transform: scale(.96); }
.preview img {
  display: block;
  width: 100%;
  aspect-ratio: 1.42;
  border-radius: 10px;
  outline: 1px solid rgb(255 255 255 / 12%);
  background: #08131e;
  object-fit: cover;
}

.chart-title { display: block; padding: 10px 3px 2px; color: var(--ink); font-size: 13px; font-weight: 720; text-wrap: pretty; }
.pin[aria-pressed="true"] { border-color: rgb(135 240 223 / 42%); background: var(--accent-soft); color: var(--accent-strong); }

.empty-state {
  margin: 0;
  padding: 28px 16px;
  border: 1px dashed #46627b;
  border-radius: 12px;
  color: var(--muted);
  text-align: center;
  text-wrap: pretty;
}

.status { min-height: 1.3em; margin: 11px 0 0; color: var(--muted); font-size: 12px; }

dialog {
  width: min(96vw, 1400px);
  max-height: 94vh;
  padding: 0;
  border: 1px solid #486580;
  border-radius: var(--radius-panel);
  background: #0e1d2c;
  color: var(--ink);
  box-shadow: 0 28px 70px rgb(0 0 0 / 48%);
}

dialog::backdrop { background: rgb(2 9 16 / 76%); }
.modal-inner { padding: 17px; }
.modal-header { display: flex; align-items: start; justify-content: space-between; gap: 16px; margin-bottom: 14px; }
.modal-header h2 { font-size: 15px; }
.modal-header button { flex: 0 0 auto; }
dialog img { display: block; width: 100%; max-height: 78vh; border-radius: 12px; outline: 1px solid rgb(255 255 255 / 12%); background: #08131e; object-fit: contain; }

@media (max-width: 760px) {
  .shell { width: min(100% - 28px, 1360px); }
  .hero-inner { align-items: flex-start; flex-direction: column; padding: 28px 0 25px; }
  .summary-grid { grid-template-columns: 1fr; gap: 10px; }
  .summary-card { min-height: 96px; }
  .section-panel { padding: 16px; }
}

@media (max-width: 480px) {
  .toolbar > button { width: 100%; }
  .section-heading { align-items: start; }
  .pins, .grid { grid-template-columns: 1fr; }
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: .01ms !important; animation-iteration-count: 1 !important; scroll-behavior: auto !important; transition-duration: .01ms !important; }
  button:active, .preview:active { transform: none; }
}
</style></head><body>
<header class="hero"><div class="shell hero-inner"><div class="brand"><div class="brand-mark" aria-hidden="true">↗</div><div><p class="eyebrow">Offline market workspace</p><h1>Market Data Gallery</h1><p class="subtitle">Inspect generated charts, keep your most useful views close, and open any chart at full resolution.</p></div></div><span class="offline-badge">Local &amp; offline</span></div></header>
<main class="shell"><section class="summary-grid" aria-label="Gallery summary"><article class="summary-card"><div class="summary-label">Charts available</div><div class="summary-value" id="chart-count">—</div><div class="summary-detail">generated views in this report</div></article><article class="summary-card"><div class="summary-label">Pinned charts</div><div class="summary-value" id="pin-count">0</div><div class="summary-detail">stored only in this browser</div></article><article class="summary-card"><div class="summary-label">Workspace mode</div><div class="summary-value">Offline</div><div class="summary-detail">no network service is required</div></article></section>
<section class="section-panel" aria-labelledby="pinned-title"><div class="section-heading"><div><h2 id="pinned-title">Pinned charts</h2><p class="section-copy">Keep up to four frequently used views here.</p></div><span class="count" id="pinned-count-label">0 pinned</span></div><div class="toolbar"><button id="refresh" type="button">Refresh images</button><button id="clear" class="clear" type="button">Clear pins</button></div><div id="pins" class="pins" aria-live="polite"></div><p id="status" class="status" aria-live="polite"></p></section>
<section class="section-panel" aria-labelledby="library-title"><div class="section-heading"><div><h2 id="library-title">Chart library</h2><p class="section-copy">Select a chart to inspect it at full size, or pin it for later.</p></div><span class="count" id="library-count">—</span></div><div class="toolbar"><div class="search-field"><label for="chart-search">Search charts</label><input id="chart-search" type="search" placeholder="e.g. volatility, volume, correlation"></div></div><div id="gallery" class="grid">__CARDS__</div><p id="gallery-empty" class="empty-state" hidden>No charts match that search.</p></section></main>
<dialog id="modal" aria-labelledby="modal-label"><div class="modal-inner"><div class="modal-header"><h2 id="modal-label">Chart preview</h2><button id="close" type="button">Close preview</button></div><img id="modal-image" alt="Expanded chart"></div></dialog>
<script>
const images = __IMAGE_DATA__;
const storageKey = "tvdata:pins";
const maxPins = 4;
const byId = (id) => document.getElementById(id);
const pins = byId("pins");
const gallery = byId("gallery");
const status = byId("status");
const modal = byId("modal");

const selected = () => {
  try {
    const value = JSON.parse(localStorage.getItem(storageKey));
    return Array.isArray(value) ? value.filter((path) => images.some((image) => image.path === path)) : [];
  } catch {
    return [];
  }
};

const save = (paths) => {
  try {
    localStorage.setItem(storageKey, JSON.stringify(paths));
    return true;
  } catch {
    status.textContent = "Pins could not be saved in this browser.";
    return false;
  }
};

const findImage = (path) => images.find((image) => image.path === path);

const openPreview = (item) => {
  if (!item) return;
  byId("modal-image").src = item.path;
  byId("modal-image").alt = item.label;
  byId("modal-label").textContent = item.label;
  if (!modal.open) modal.showModal();
};

const previewButton = (item) => {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "preview";
  button.dataset.src = item.path;
  button.setAttribute("aria-label", `Open ${item.label} full size`);
  const image = document.createElement("img");
  image.src = item.path;
  image.alt = item.label;
  image.loading = "lazy";
  image.decoding = "async";
  const title = document.createElement("span");
  title.className = "chart-title";
  title.textContent = item.label;
  button.append(image, title);
  return button;
};

const pinButton = (item, isPinned) => {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "pin";
  button.dataset.src = item.path;
  button.dataset.label = item.label;
  button.setAttribute("aria-pressed", String(isPinned));
  button.textContent = isPinned ? "Pinned" : "Pin chart";
  return button;
};

const updatePinControls = (paths) => {
  document.querySelectorAll(".pin").forEach((button) => {
    const isPinned = paths.includes(button.dataset.src);
    button.setAttribute("aria-pressed", String(isPinned));
    button.textContent = isPinned ? "Pinned" : "Pin chart";
  });
};

const renderPins = (message = "") => {
  const paths = selected();
  const chosen = paths.map(findImage).filter(Boolean);
  pins.replaceChildren();
  if (!chosen.length) {
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent = "No pinned charts yet. Pin up to four views from the chart library.";
    pins.append(empty);
  } else {
    chosen.forEach((item) => {
      const card = document.createElement("article");
      card.className = "chart-card";
      card.append(previewButton(item), pinButton(item, true));
      pins.append(card);
    });
  }
  byId("chart-count").textContent = images.length;
  byId("pin-count").textContent = chosen.length;
  byId("pinned-count-label").textContent = `${chosen.length} pinned`;
  byId("clear").disabled = !chosen.length;
  updatePinControls(paths);
  if (message) status.textContent = message;
};

const filterLibrary = () => {
  const query = byId("chart-search").value.trim().toLowerCase();
  let visible = 0;
  gallery.querySelectorAll(".chart-card").forEach((card) => {
    const matches = !query || card.dataset.search.includes(query);
    card.hidden = !matches;
    if (matches) visible += 1;
  });
  byId("library-count").textContent = `${visible} of ${images.length}`;
  byId("gallery-empty").hidden = visible !== 0;
};

document.addEventListener("click", (event) => {
  const target = event.target instanceof Element ? event.target : null;
  const preview = target?.closest(".preview");
  if (preview) {
    openPreview(findImage(preview.dataset.src));
    return;
  }
  const pin = target?.closest(".pin");
  if (!pin) return;
  const paths = selected();
  const exists = paths.includes(pin.dataset.src);
  const next = exists ? paths.filter((path) => path !== pin.dataset.src) : [...paths, pin.dataset.src].slice(-maxPins);
  if (save(next)) renderPins(exists ? "Chart removed from pins." : "Chart pinned for quick access.");
});

byId("chart-search").addEventListener("input", filterLibrary);
byId("clear").addEventListener("click", () => {
  if (save([])) renderPins("Pinned charts cleared.");
});
byId("refresh").addEventListener("click", () => {
  document.querySelectorAll("img[src]").forEach((image) => {
    const source = image.getAttribute("src").split("?")[0];
    image.src = `${source}?v=${Date.now()}`;
  });
  status.textContent = "Chart images refreshed.";
});
byId("close").addEventListener("click", () => modal.close());
modal.addEventListener("click", (event) => {
  if (event.target === modal) modal.close();
});
renderPins();
filterLibrary();
</script></body></html>"""
    document = document.replace("__CARDS__", "\n".join(cards)).replace("__IMAGE_DATA__", data_json)
    path = output / "dashboard.html"
    path.write_text(document, encoding="utf-8")
    return path


def build_html(outdir: str | Path) -> Path:
    """Compatibility helper that builds a dashboard from existing PNG files."""

    output = Path(outdir)
    images = [(path, path.stem.replace("_", " ").title()) for path in sorted(output.rglob("*.png"))]
    return build_dashboard(output, images)


def generate_charts(
    files: Sequence[str | Path],
    outdir: str | Path = "charts",
    *,
    include_indicators: bool = True,
) -> list[Path]:
    """Generate all visualizations without overwriting multi-symbol outputs."""

    if not files:
        raise ValueError("provide at least one CSV file")
    output = Path(outdir)
    output.mkdir(parents=True, exist_ok=True)
    multi_symbol = len(files) > 1
    generated: list[Path] = []
    dashboard_images: list[tuple[Path, str]] = []
    datasets: list[tuple[str, pd.DataFrame]] = []
    used_names: set[str] = set()

    for source in files:
        source_path = Path(source)
        label = source_path.stem
        directory_name = safe_filename(label)
        suffix = 2
        original_name = directory_name
        while directory_name in used_names:
            directory_name = f"{original_name}-{suffix}"
            suffix += 1
        used_names.add(directory_name)
        destination = output / directory_name if multi_symbol else output
        data = load_ohlcv(source_path)
        datasets.append((label, data))
        chart_paths = [
            chart_candles(data, destination),
            chart_volume_profile(data, destination),
            chart_time_volume_heatmap(data, destination),
            chart_volatility_heatmap(data, destination),
            chart_price_time_heatmap(data, destination),
            chart_returns_atr(data, destination),
        ]
        if include_indicators:
            chart_paths.append(chart_technical_indicators(data, destination))
        generated.extend(chart_paths)
        dashboard_images.extend((path, f"{label} · {path.stem.replace('_', ' ').title()}") for path in chart_paths)

    if len(datasets) > 1:
        correlation = chart_correlation(datasets, output)
        if correlation is not None:
            generated.append(correlation)
            dashboard_images.append((correlation, "Cross-symbol return correlation"))
    generated.append(build_dashboard(output, dashboard_images))
    return generated
