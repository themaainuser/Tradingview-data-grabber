"""Compatibility entry point for modular chart generation."""

from pathlib import Path

from tradingview_data.charts import (
    GREEN,
    HEAT,
    RED,
    _save,
    _time_grid,
    build_dashboard,
    build_html,
    chart_candles,
    chart_correlation as _chart_correlation,
    chart_price_time_heatmap,
    chart_returns_atr,
    chart_technical_indicators,
    chart_time_volume_heatmap,
    chart_volatility_heatmap,
    chart_volume_profile,
    generate_charts,
    load_csv as _load_csv,
    volume_profile,
)
from tradingview_data.analytics import parse_time
from tradingview_data.cli import legacy_charts_main

time_grid = _time_grid


def load_csv(path):
    """Load validated bars while retaining the old unbracketed index field."""

    data = _load_csv(path)
    if "index" not in data:
        return data
    data = data.copy()
    data["index"] = data["index"].astype(str).str.replace(r"[\[\]]", "", regex=True)
    return data


def save(fig, outdir, name, title):
    """Retain the original figure-saving helper."""

    return _save(fig, outdir, name, title)


def chart_correlation(files, outdir):
    """Accept the original sequence of CSV paths as well as loaded datasets."""

    items = list(files)
    if all(isinstance(item, tuple) and len(item) == 2 for item in items):
        return _chart_correlation(items, outdir)
    return _chart_correlation([(Path(path).stem, load_csv(path)) for path in items], outdir)


def main():
    return legacy_charts_main()

__all__ = [
    "GREEN",
    "HEAT",
    "RED",
    "build_dashboard",
    "build_html",
    "chart_candles",
    "chart_correlation",
    "chart_price_time_heatmap",
    "chart_returns_atr",
    "chart_technical_indicators",
    "chart_time_volume_heatmap",
    "chart_volatility_heatmap",
    "chart_volume_profile",
    "generate_charts",
    "load_csv",
    "main",
    "parse_time",
    "save",
    "time_grid",
    "volume_profile",
]


if __name__ == "__main__":
    raise SystemExit(main())
