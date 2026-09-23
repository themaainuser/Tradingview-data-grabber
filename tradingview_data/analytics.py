"""OHLCV validation, indicator calculation, and machine-readable reports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REQUIRED_COLUMNS = ("time", "open", "high", "low", "close", "volume")


class OhlcvValidationError(ValueError):
    """Raised when a CSV cannot provide usable OHLCV rows."""


def parse_time(value: object) -> pd.Timestamp | pd.NaT:
    """Parse legacy stream timestamps and common ISO/CSV variants."""

    text = str(value).strip()
    if not text:
        return pd.NaT
    text = text.rsplit(" (", 1)[0] if text.endswith(")") and " (" in text else text
    for fmt in (
        "%a %b %d %Y %H:%M:%S GMT%z",
        "%Y/%m/%d, %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
    ):
        parsed = pd.to_datetime(text, format=fmt, errors="coerce")
        if not pd.isna(parsed):
            return _normalize_timezone(parsed)
    parsed = pd.to_datetime(text, errors="coerce")
    return _normalize_timezone(parsed) if not pd.isna(parsed) else pd.NaT


def _normalize_timezone(value: pd.Timestamp) -> pd.Timestamp:
    """Keep captures on one predictable timezone for sorting and charting."""

    if value.tzinfo is None:
        return value.tz_localize("Asia/Kolkata")
    return value.tz_convert("Asia/Kolkata")


def load_ohlcv(path: str | Path) -> pd.DataFrame:
    """Load, validate, sort, and de-duplicate a captured OHLCV CSV.

    Invalid rows are dropped and their count is retained in ``DataFrame.attrs``.
    A duplicate timestamp keeps its final row, matching the final value of a
    forming candle after a reconnect.
    """

    source = Path(path)
    try:
        raw = pd.read_csv(source)
    except (OSError, UnicodeDecodeError, pd.errors.EmptyDataError, pd.errors.ParserError) as exc:
        raise OhlcvValidationError(f"unable to read {source}: {exc}") from exc

    missing = [column for column in REQUIRED_COLUMNS if column not in raw.columns]
    if missing:
        raise OhlcvValidationError(f"{source} is missing required columns: {', '.join(missing)}")

    data = raw.copy()
    data["time"] = data["time"].map(parse_time)
    for column in ("open", "high", "low", "close", "volume"):
        data[column] = pd.to_numeric(data[column], errors="coerce")

    valid = data[list(REQUIRED_COLUMNS)].notna().all(axis=1)
    numeric = data[["open", "high", "low", "close", "volume"]]
    valid &= np.isfinite(numeric).all(axis=1)
    valid &= (data[["open", "high", "low", "close"]] > 0).all(axis=1)
    valid &= data["volume"] >= 0
    valid &= data["high"] >= data[["open", "close", "low"]].max(axis=1)
    valid &= data["low"] <= data[["open", "close", "high"]].min(axis=1)
    dropped_rows = int((~valid).sum())
    data = data.loc[valid].copy()
    duplicate_rows = int(data.duplicated(subset="time", keep="last").sum())
    data = data.drop_duplicates(subset="time", keep="last").sort_values("time").set_index("time")
    data.index.name = "time"
    if data.empty:
        raise OhlcvValidationError(f"{source} contains no valid OHLCV rows")

    data.attrs.update(
        source_path=str(source),
        input_rows=len(raw),
        dropped_rows=dropped_rows,
        duplicate_rows=duplicate_rows,
    )
    return data


def add_indicators(data: pd.DataFrame) -> pd.DataFrame:
    """Return a copy enriched with SMA, EMA, RSI, MACD, ATR, bands, and VWAP."""

    if data.empty:
        raise OhlcvValidationError("cannot calculate indicators for an empty data set")
    frame = data.copy()
    close = frame["close"]
    frame["sma_20"] = close.rolling(20, min_periods=20).mean()
    frame["ema_20"] = close.ewm(span=20, adjust=False, min_periods=20).mean()

    delta = close.diff()
    gains = delta.clip(lower=0)
    losses = -delta.clip(upper=0)
    average_gain = gains.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    average_loss = losses.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    relative_strength = average_gain / average_loss.replace(0, np.nan)
    frame["rsi_14"] = 100 - (100 / (1 + relative_strength))
    frame.loc[(average_loss == 0) & (average_gain > 0), "rsi_14"] = 100.0
    frame.loc[(average_gain == 0) & (average_loss > 0), "rsi_14"] = 0.0
    frame.loc[(average_gain == 0) & (average_loss == 0), "rsi_14"] = 50.0

    frame["ema_12"] = close.ewm(span=12, adjust=False, min_periods=12).mean()
    frame["ema_26"] = close.ewm(span=26, adjust=False, min_periods=26).mean()
    frame["macd"] = frame["ema_12"] - frame["ema_26"]
    frame["macd_signal"] = frame["macd"].ewm(span=9, adjust=False, min_periods=9).mean()
    frame["macd_hist"] = frame["macd"] - frame["macd_signal"]

    previous_close = close.shift()
    true_range = pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - previous_close).abs(),
            (frame["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    frame["atr_14"] = true_range.rolling(14, min_periods=14).mean()

    frame["bb_middle"] = frame["sma_20"]
    deviation = close.rolling(20, min_periods=20).std(ddof=0)
    frame["bb_upper"] = frame["bb_middle"] + 2 * deviation
    frame["bb_lower"] = frame["bb_middle"] - 2 * deviation

    typical_price = (frame["high"] + frame["low"] + close) / 3
    cumulative_volume = frame["volume"].cumsum().replace(0, np.nan)
    frame["vwap"] = (typical_price * frame["volume"]).cumsum() / cumulative_volume
    return frame


def _number(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    return round(float(value), 8)


def data_quality_report(data: pd.DataFrame) -> dict[str, Any]:
    """Describe capture quality, including cadence and gaps where detectable."""

    intervals = data.index.to_series().diff().dropna().dt.total_seconds()
    median_interval = float(intervals.median()) if not intervals.empty else None
    gaps: list[dict[str, Any]] = []
    if median_interval and median_interval > 0:
        for timestamp, seconds in intervals[intervals > median_interval * 1.5].items():
            gaps.append({"after": timestamp.isoformat(), "seconds": round(float(seconds), 3)})
    return {
        "source": data.attrs.get("source_path"),
        "input_rows": data.attrs.get("input_rows", len(data)),
        "valid_rows": len(data),
        "dropped_rows": data.attrs.get("dropped_rows", 0),
        "duplicate_rows_collapsed": data.attrs.get("duplicate_rows", 0),
        "start": data.index[0].isoformat(),
        "end": data.index[-1].isoformat(),
        "median_interval_seconds": _number(median_interval),
        "gaps": gaps,
    }


def market_report(data: pd.DataFrame) -> dict[str, Any]:
    """Create a compact, JSON-serializable technical summary of OHLCV data."""

    enriched = add_indicators(data)
    latest = enriched.iloc[-1]
    first_close = float(enriched["close"].iloc[0])
    period_return = ((float(latest["close"]) / first_close) - 1) * 100 if first_close else None
    lookback = enriched.tail(min(20, len(enriched)))
    rsi = _number(latest["rsi_14"])
    macd = _number(latest["macd"])
    signal = _number(latest["macd_signal"])
    return {
        "quality": data_quality_report(data),
        "latest": {
            "time": enriched.index[-1].isoformat(),
            "open": _number(latest["open"]),
            "high": _number(latest["high"]),
            "low": _number(latest["low"]),
            "close": _number(latest["close"]),
            "volume": _number(latest["volume"]),
        },
        "performance": {
            "period_return_pct": _number(period_return),
            "range_pct": _number((latest["high"] - latest["low"]) / latest["open"] * 100),
            "support_20": _number(lookback["low"].min()),
            "resistance_20": _number(lookback["high"].max()),
        },
        "indicators": {
            "sma_20": _number(latest["sma_20"]),
            "ema_20": _number(latest["ema_20"]),
            "rsi_14": rsi,
            "macd": macd,
            "macd_signal": signal,
            "atr_14": _number(latest["atr_14"]),
            "atr_pct": _number(latest["atr_14"] / latest["close"] * 100),
            "vwap": _number(latest["vwap"]),
            "bollinger_upper": _number(latest["bb_upper"]),
            "bollinger_lower": _number(latest["bb_lower"]),
        },
        "signals": {
            "rsi": "unavailable" if rsi is None else "overbought" if rsi >= 70 else "oversold" if rsi <= 30 else "neutral",
            "macd": "unavailable" if macd is None or signal is None else "bullish" if macd >= signal else "bearish",
            "ema_trend": "unavailable"
            if pd.isna(latest["ema_20"])
            else "above_ema_20" if latest["close"] >= latest["ema_20"] else "below_ema_20",
        },
    }


def write_enriched_csv(data: pd.DataFrame, path: str | Path) -> Path:
    """Persist calculated indicators alongside the normalized OHLCV rows."""

    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    add_indicators(data).reset_index().to_csv(output, index=False)
    return output


def write_report(report: dict[str, Any], path: str | Path) -> Path:
    """Write a market report atomically to prevent partial JSON files."""

    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(output)
    return output
