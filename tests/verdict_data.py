"""Seeded synthetic OHLCV for the verdict tests; generators only, nothing is committed as data."""

from __future__ import annotations

import csv
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from tradingview_data.storage import CSV_COLUMNS, CSV_TIME_FORMAT

IST = ZoneInfo("Asia/Kolkata")


def frame_from_returns(returns: np.ndarray, seed: int, freq: str = "h", start: str = "2024-01-01") -> pd.DataFrame:
    """OHLCV whose close-to-close log returns are ``returns``, with small opening gaps and wicks."""

    rows = len(returns)
    rng = np.random.default_rng(seed + 1000)
    close = 100 * np.exp(np.cumsum(returns))
    open_ = np.concatenate(([close[0]], close[:-1])) * (1 + rng.normal(0, 0.0005, rows))
    high = np.maximum(open_, close) * (1 + rng.uniform(0, 0.002, rows))
    low = np.minimum(open_, close) * (1 - rng.uniform(0, 0.002, rows))
    index = pd.date_range(start, periods=rows, freq=freq, tz="UTC", name="time")
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": np.ones(rows)}, index=index
    )


def random_walk_frame(rows: int, seed: int, vol: float = 0.004) -> pd.DataFrame:
    """Hourly bars of a driftless random walk: no rule has any edge."""

    return frame_from_returns(np.random.default_rng(seed).normal(0, vol, rows), seed)


def regime_frame(
    rows: int, seed: int = 7, vol: float = 0.004, drift: float = 0.0012, mean_length: int = 300
) -> pd.DataFrame:
    """Hourly bars with persistent up and down drifts (positively autocorrelated returns) that trend rules can catch."""

    rng = np.random.default_rng(seed)
    sign, position, current = np.empty(rows), 0, 1.0
    while position < rows:
        length = rng.geometric(1 / mean_length)
        sign[position : position + length] = current
        current = -current if rng.random() < 0.5 else current
        position += length
    return frame_from_returns(sign * drift + rng.normal(0, vol, rows), seed)


def write_capture(path: Path, frame: pd.DataFrame) -> None:
    """Write ``frame`` in the CSV format produced by ``CsvBarStore`` (times in IST, like real captures)."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_COLUMNS)
        for number, (stamp, bar) in enumerate(frame.iterrows()):
            writer.writerow(
                [
                    f"[{number}]",
                    stamp.tz_convert(IST).strftime(CSV_TIME_FORMAT),
                    bar["open"],
                    bar["high"],
                    bar["low"],
                    bar["close"],
                    bar["volume"],
                ]
            )
