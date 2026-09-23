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
        payload.append({"path": relative, "label": html.escape(label, quote=True)})
        cards.append(
            "<article class='card'><button class='preview' data-src='{}' data-label='{}'>"
            "<img src='{}' alt='{}'><span>{}</span></button>"
            "<button class='pin' data-src='{}' data-label='{}'>Pin</button></article>".format(
                html.escape(relative, quote=True),
                html.escape(label, quote=True),
                html.escape(relative, quote=True),
                html.escape(label, quote=True),
                html.escape(label),
                html.escape(relative, quote=True),
                html.escape(label, quote=True),
            )
        )
    data_json = json.dumps(payload).replace("</", "<\\/")
    document = f"""<!doctype html>
<html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>
<title>TradingView Data Gallery</title><style>
:root {{ color-scheme: dark; --card: #1d2731; --ink: #e8edf2; --accent: #26a69a; }}
* {{ box-sizing: border-box; }} body {{ margin: 0; background: #101820; color: var(--ink); font: 15px system-ui, sans-serif; }}
header {{ padding: 28px max(24px, calc((100vw - 1200px) / 2)); background: linear-gradient(125deg, #0b3341, #17293c); }}
h1 {{ margin: 0 0 6px; }} p {{ color: #bbcad5; }} main {{ max-width: 1200px; padding: 24px; margin: auto; }}
.toolbar {{ display: flex; gap: 10px; flex-wrap: wrap; margin: 12px 0 20px; }} button {{ color: var(--ink); background: #263746; border: 1px solid #496171; border-radius: 7px; padding: 8px 12px; cursor: pointer; }} button:hover {{ border-color: var(--accent); }}
.pins, .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 16px; }} .card {{ background: var(--card); border-radius: 10px; padding: 10px; box-shadow: 0 6px 20px #0004; }}
.preview {{ padding: 0; width: 100%; background: none; border: 0; text-align: left; }} .preview img {{ width: 100%; display: block; border-radius: 6px; background: #0b1118; }} .preview span {{ display: block; padding: 9px 2px 3px; font-weight: 600; }} .pin {{ margin-top: 6px; }}
dialog {{ width: min(96vw, 1400px); background: #101820; border: 1px solid #496171; border-radius: 10px; color: var(--ink); }} dialog img {{ width: 100%; max-height: 82vh; object-fit: contain; }} dialog button {{ float: right; }}
</style></head><body><header><h1>Market Data Gallery</h1><p>Offline charts with technical indicators, volume profile, and correlation.</p></header>
<main><section><h2>Pinned charts</h2><div class='toolbar'><button id='refresh'>Refresh images</button><button id='clear'>Clear pins</button></div><div id='pins' class='pins'></div></section>
<section><h2>Chart library</h2><div class='grid'>{''.join(cards)}</div></section></main><dialog id='modal'><button id='close'>Close</button><h2 id='modal-label'></h2><img id='modal-image' alt='Expanded chart'></dialog>
<script>const images={data_json}; const storageKey='tvdata:pins'; const pins=document.querySelector('#pins');
function selected() {{ try {{ return JSON.parse(localStorage.getItem(storageKey)) || []; }} catch {{ return []; }} }}
function render() {{ const chosen=selected(); pins.innerHTML=chosen.length ? chosen.map(src => {{ const item=images.find(i=>i.path===src); return item ? `<article class="card"><button class="preview" data-src="${{item.path}}" data-label="${{item.label}}"><img src="${{item.path}}" alt="${{item.label}}"><span>${{item.label}}</span></button><button class="unpin" data-src="${{item.path}}">Unpin</button></article>` : ''; }}).join('') : '<p>No pinned charts yet.</p>'; bind(); }}
function bind() {{ document.querySelectorAll('.preview').forEach(button=>button.onclick=()=>{{ document.querySelector('#modal-image').src=button.dataset.src; document.querySelector('#modal-label').textContent=button.dataset.label; document.querySelector('#modal').showModal(); }}); document.querySelectorAll('.pin').forEach(button=>button.onclick=()=>{{ const values=selected(); if(!values.includes(button.dataset.src)) localStorage.setItem(storageKey, JSON.stringify([...values, button.dataset.src].slice(-4))); render(); }}); document.querySelectorAll('.unpin').forEach(button=>button.onclick=()=>{{ localStorage.setItem(storageKey, JSON.stringify(selected().filter(src=>src!==button.dataset.src))); render(); }}); }}
document.querySelector('#close').onclick=()=>document.querySelector('#modal').close(); document.querySelector('#clear').onclick=()=>{{ localStorage.removeItem(storageKey); render(); }}; document.querySelector('#refresh').onclick=()=>document.querySelectorAll('img').forEach(image=>{{ const src=image.getAttribute('src').split('?')[0]; image.src=src+'?v='+Date.now(); }}); bind(); render();</script></body></html>"""
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
