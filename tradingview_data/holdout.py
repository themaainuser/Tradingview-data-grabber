"""Sealed holdout: which bars research may see, and the only code that may read the rest.

Sealing fixes the holdout range for a capture.  Research sees bars strictly before ``holdout_start``
through :func:`research_window`; bars captured after the seal are forward data, neither research nor
holdout.  Only :func:`read_holdout` touches the holdout bars, and the service calls it at most once
per seal.  A fingerprint of the research segment detects history that changed after sealing.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

import numpy as np
import pandas as pd

from .charts import _epoch_seconds
from .verdict import Costs, evaluate_window, iid_sharpe_se

MIN_SEAL_BARS = 100
MIN_FRACTION, MAX_FRACTION, DEFAULT_FRACTION = 0.10, 0.30, 0.20
PRICE_COLUMNS = ("open", "high", "low", "close", "volume")


class HistoryChanged(RuntimeError):
    """The bars before the seal no longer match the fingerprint taken when sealing."""


@dataclass(frozen=True)
class Seal:
    """The parts of a sealed holdout that research and reads depend on (times are UTC epoch seconds)."""

    fraction: float
    holdout_start: int
    holdout_end: int
    holdout_bars: int
    research_bars: int
    fingerprint: str

    @classmethod
    def from_entry(cls, entry: Mapping[str, Any]) -> "Seal":
        return cls(
            fraction=entry["fraction"],
            holdout_start=entry["holdout_start"],
            holdout_end=entry["holdout_end"],
            holdout_bars=entry["holdout_bars"],
            research_bars=entry["research_bars"],
            fingerprint=entry["research_fingerprint"],
        )


def research_fingerprint(research: pd.DataFrame, symbol: str, timeframe: Optional[str], fraction: float) -> str:
    """SHA-256 over the research segment's times and OHLCV values plus its identity."""

    times = _epoch_seconds(research)
    digest = hashlib.sha256()
    digest.update(np.ascontiguousarray(times, dtype="<i8").tobytes())
    for column in PRICE_COLUMNS:
        digest.update(np.ascontiguousarray(research[column].to_numpy(), dtype="<f8").tobytes())
    digest.update(f"{times[0]}|{symbol}|{timeframe}|{fraction!r}".encode("utf-8"))
    return digest.hexdigest()


def plan_seal(frame: pd.DataFrame, symbol: str, timeframe: Optional[str], fraction: float) -> dict[str, Any]:
    """Ledger body of a seal that holds back the last ``fraction`` of ``frame``; ``ValueError`` if too short."""

    times = _epoch_seconds(frame)
    if len(times) < MIN_SEAL_BARS:
        raise ValueError(f"at least {MIN_SEAL_BARS} bars are needed to seal a holdout; this capture has {len(times)}")
    research_bars = math.floor(round(len(times) * (1 - fraction), 9))
    return {
        "fraction": fraction,
        "holdout_start": int(times[research_bars]),
        "holdout_end": int(times[-1]),
        "holdout_bars": len(times) - research_bars,
        "research_bars": research_bars,
        "research_fingerprint": research_fingerprint(frame.iloc[:research_bars], symbol, timeframe, fraction),
        "symbol": symbol,
        "timeframe": timeframe,
    }


def research_window(frame: pd.DataFrame, seal: Seal) -> pd.DataFrame:
    """The bars research may use: everything strictly before the holdout."""

    cut = int(np.searchsorted(_epoch_seconds(frame), seal.holdout_start, side="left"))
    return frame.iloc[:cut]


def verify_research_segment(frame: pd.DataFrame, seal: Seal, symbol: str, timeframe: Optional[str]) -> None:
    """Raise :class:`HistoryChanged` unless the research bars still match the sealed fingerprint."""

    research = research_window(frame, seal)
    if not len(research) or research_fingerprint(research, symbol, timeframe, seal.fraction) != seal.fingerprint:
        raise HistoryChanged("the bars before the seal changed since sealing")


def _holdout_frame(frame: pd.DataFrame, seal: Seal) -> tuple[pd.DataFrame, int]:
    """Bars up to the holdout's end and the position of its first bar; private to :func:`read_holdout`."""

    times = _epoch_seconds(frame)
    first = int(np.searchsorted(times, seal.holdout_start, side="left"))
    last = int(np.searchsorted(times, seal.holdout_end, side="right"))
    return frame.iloc[:last], first


def _caveat(noun: str, bars: int, periods_per_year: float) -> str:
    se = iid_sharpe_se(periods_per_year, bars)
    if se is None:
        return f"There are no {noun} bars to evaluate yet."
    return (
        f"With {bars} {noun} bars the annualised Sharpe standard error is about +/-{se:.1f} even if the true "
        "Sharpe is zero. This is a sanity check, not a verdict."
    )


def read_holdout(
    frame: pd.DataFrame,
    seal: Seal,
    rules: Sequence[Mapping[str, Any]],
    costs: Costs,
    periods_per_year: float,
) -> dict[str, Any]:
    """Evaluate frozen ``rules`` on the holdout at 1x costs; callers must enforce the one-read rule.

    Targets use every bar up to the holdout's end (earlier bars are warm-up context) and the position
    at the first holdout bar is the target of the last research bar.  No pass/fail is given.
    """

    history, first = _holdout_frame(frame, seal)
    bars = len(history) - first
    return {
        "start": seal.holdout_start,
        "end": seal.holdout_end,
        "bars": bars,
        "rules": evaluate_window(history, rules, costs, periods_per_year, first),
        "caveat": _caveat("holdout", bars, periods_per_year),
        "sharpe_se_annualised_iid": iid_sharpe_se(periods_per_year, bars),
    }


def forward_result(
    frame: pd.DataFrame,
    forward_start: int,
    rules: Sequence[Mapping[str, Any]],
    costs: Costs,
    periods_per_year: float,
) -> dict[str, Any]:
    """Evaluate frozen ``rules`` on bars captured after ``forward_start`` (history only warms indicators)."""

    times = _epoch_seconds(frame)
    first = int(np.searchsorted(times, forward_start, side="right"))
    bars = len(times) - first
    return {
        "start": forward_start,
        "end": int(times[-1]) if bars else None,
        "bars": bars,
        "waiting": bars == 0,
        "rules": evaluate_window(frame, rules, costs, periods_per_year, first),
        "caveat": _caveat("forward", bars, periods_per_year),
        "sharpe_se_annualised_iid": iid_sharpe_se(periods_per_year, bars),
    }
