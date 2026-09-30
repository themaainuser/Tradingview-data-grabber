"""The verdict engine: what a short backtest can and cannot conclude.

A rule's signal is known at a bar's close and filled at the next bar's open, with fees, half the
spread and ATR-scaled slippage charged on both sides of every trade.  Rules that trade too rarely
get no statistics at all; the rest are tested for luck across every rule that was tried.  A run
ends in exactly one label and never in a ranking.

The engine only ever sees the frame it is given; :mod:`tradingview_data.holdout` decides which bars
that is.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

import numpy as np
import pandas as pd

from .charts import bar_interval
from .research import strategy_permutations, strategy_targets
from .verdict_stats import (
    Moments,
    bootstrap_study,
    deflated_sharpe,
    moments,
    overfitting_probability,
    participation_ratio,
    romano_wolf,
    sharpe_standard_error,
)

STRESS_MULTIPLIERS = (1.0, 1.5, 2.0)
STRESS_CHECK_MULTIPLIER = 1.5
DEFAULT_MIN_TRADES = 30
BOOTSTRAP_REPLICATES = 2000
EFFECTIVE_N_REPLICATES = 500
EFFECTIVE_N_LEVEL = 0.9
ALPHA = 0.05
DSR_THRESHOLD = 0.95
ATR_WINDOW = 14
PROBE_FRACTION = 0.75
PROBE_FRACTIONS = (0.5, 0.65, PROBE_FRACTION, 0.85, 0.95)
PBO_NOISY_BARS = 2000
PBO_NOISY_RULES = 4
SECONDS_PER_YEAR = 365 * 86_400

NEVER_TRADES = "NEVER_TRADES"
INSUFFICIENT_TRADES = "INSUFFICIENT_TRADES"
PASSED_GATE = "PASSED_GATE"
ERROR = "ERROR"
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
INDISTINGUISHABLE = "INDISTINGUISHABLE_FROM_LUCK"
CANDIDATE = "CANDIDATE"


class IntegrityError(RuntimeError):
    """A structural guarantee of the fill model failed; the run's numbers cannot be trusted."""


class LookaheadError(IntegrityError):
    """A rule's target at some bar changes when the bars after it are removed."""


@dataclass(frozen=True)
class Costs:
    """Per-side trading costs; ``slippage_k`` multiplies the previous bar's ATR(14)."""

    fee_bps_per_side: float = 10.0
    spread_bps: float = 1.0
    slippage_k: float = 0.1

    def as_dict(self) -> dict[str, float]:
        return {
            "fee_bps_per_side": self.fee_bps_per_side,
            "spread_bps": self.spread_bps,
            "slippage_k": self.slippage_k,
        }


COST_NOTES = (
    {
        "field": "fee_bps_per_side",
        "value": 10.0,
        "basis": "Binance spot taker, regular tier (VIP 0): 0.10% per side, 0.075% with BNB discount "
        "(Binance published fee schedule). Verify your own tier.",
    },
    {
        "field": "spread_bps",
        "value": 1.0,
        "basis": "Placeholder: captures contain no bid/ask data.",
    },
    {
        "field": "slippage_k",
        "value": 0.1,
        "basis": "Starting value for liquid assets (0.05-0.2 x ATR(14)); calibrate against real fills.",
    },
)


def atr14(frame: pd.DataFrame) -> np.ndarray:
    """Wilder ATR(14); a bar's value uses its own range and the previous close, so it is known at the close."""

    previous = frame["close"].shift()
    true_range = pd.concat(
        [frame["high"] - frame["low"], (frame["high"] - previous).abs(), (frame["low"] - previous).abs()], axis=1
    ).max(axis=1)
    return true_range.ewm(alpha=1 / ATR_WINDOW, adjust=False, min_periods=ATR_WINDOW).mean().to_numpy(dtype=float)


def compute_targets(frame: pd.DataFrame, strategy: Mapping[str, Any]) -> np.ndarray:
    """0/1 targets known at each bar's close; a strategy may carry its own ``target_fn(frame)``."""

    target_fn = strategy.get("target_fn")
    series = target_fn(frame) if target_fn is not None else strategy_targets(frame, dict(strategy))
    values = np.asarray(series, dtype=float)
    if values.shape != (len(frame),) or not np.isin(values, (0.0, 1.0)).all():
        raise ValueError("a strategy must return a 0 or 1 target for every bar")
    return values


class Fills:
    """Positions, gross returns and turnover of one rule, filled at each bar's open.

    ``position[t]`` is what is held during bar ``t`` (the target of bar ``t - 1``, entered at the
    open of ``t``); the position held before the open earns the close-to-open gap and the one held
    after it earns the intrabar move.  Costs depend on a multiplier, so ``net`` is computed per
    multiplier from the same fills.
    """

    def __init__(self, open_: np.ndarray, close: np.ndarray, targets: np.ndarray, atr: np.ndarray, costs: Costs) -> None:
        size = len(close)
        self.position = np.zeros(size)
        self.position[1:] = targets[:-1]
        if not np.array_equal(self.position[1:], targets[:-1]):
            raise IntegrityError("assertion failed: signals shifted one bar before fills")
        self.previous = np.concatenate(([0.0], self.position[:-1]))
        gap = np.zeros(size)
        gap[1:] = open_[1:] / close[:-1] - 1.0
        self.gross = (1.0 + self.previous * gap) * (1.0 + self.position * (close / open_ - 1.0)) - 1.0
        self.turnover = np.abs(self.position - self.previous)
        earlier_atr = np.concatenate(([np.nan], atr[:-1]))
        rate = costs.fee_bps_per_side / 1e4 + costs.spread_bps / 2.0 / 1e4 + costs.slippage_k * earlier_atr / open_
        trading = self.turnover > 0
        if np.isnan(rate[trading]).any():
            raise ValueError("trading cost is undefined at a fill because ATR(14) is not yet available")
        self.unit_cost = np.where(trading, self.turnover * np.where(trading, rate, 0.0), 0.0)

    def cost(self, multiplier: float) -> np.ndarray:
        return self.unit_cost * multiplier

    def net(self, multiplier: float) -> np.ndarray:
        return (1.0 + self.gross) * (1.0 - self.cost(multiplier)) - 1.0


@dataclass(frozen=True)
class Trades:
    """Trades entered in a window: first bar, last bar (inclusive) and whether each one closed."""

    entries: np.ndarray
    ends: np.ndarray
    closed: np.ndarray

    def returns(self, per_bar: np.ndarray) -> np.ndarray:
        """Compounded return of each trade over its bars (an open trade is marked to its last bar)."""

        return np.array([np.prod(1.0 + per_bar[first : last + 1]) - 1.0 for first, last in zip(self.entries, self.ends)])


def find_trades(fills: Fills, lo: int, hi: int) -> Trades:
    """Trades with an entry in bars ``lo`` to ``hi - 1``; the exit bar includes its gap and cost."""

    holding, earlier = fills.position[lo:hi] == 1.0, fills.previous[lo:hi] == 1.0
    entries = np.flatnonzero(holding & ~earlier) + lo
    exits = np.flatnonzero(~holding & earlier) + lo
    following = np.searchsorted(exits, entries, side="right")
    return Trades(entries, np.append(exits, hi - 1)[following], following < len(exits))


def sharpe_ratio(returns: np.ndarray, periods_per_year: float) -> Optional[float]:
    """Annualised mean over sample standard deviation, or ``None`` when the returns do not vary."""

    if len(returns) < 2 or not np.ptp(returns) > 0:
        return None
    return float(returns.mean() / returns.std(ddof=1) * math.sqrt(periods_per_year))


def sharpe_se_annualised(returns: np.ndarray, periods_per_year: float) -> Optional[float]:
    """Mertens standard error of the annualised Sharpe ratio, or ``None`` when it is undefined."""

    stats = moments(returns)
    return None if stats is None else sharpe_standard_error(stats) * math.sqrt(periods_per_year)


def iid_sharpe_se(periods_per_year: float, bars: int) -> Optional[float]:
    """Annualised Sharpe standard error of ``bars`` observations whose true Sharpe is zero."""

    return math.sqrt(periods_per_year / bars) if bars > 0 else None


def window_summary(
    fills: Fills, open_: np.ndarray, close: np.ndarray, lo: int, hi: int, periods_per_year: float
) -> dict[str, Any]:
    """Figures for bars ``lo`` to ``hi - 1`` of one rule at 1x costs (the ``RuleWindow`` fields but its name)."""

    per_bar = fills.net(1.0)
    window = per_bar[lo:hi]
    trade_net = find_trades(fills, lo, hi)
    trade_returns = trade_net.returns(per_bar)
    base = close[lo - 1] if lo > 0 else open_[lo]
    return {
        "trades": int(len(trade_net.entries)),
        "closed_trades": int(trade_net.closed.sum()),
        "exposure_pct": float(fills.position[lo:hi].mean() * 100.0) if hi > lo else 0.0,
        "net_return_pct": float((np.prod(1.0 + window) - 1.0) * 100.0),
        "sharpe": sharpe_ratio(window, periods_per_year),
        "sharpe_se": sharpe_se_annualised(window, periods_per_year),
        "mean_trade_return_pct": float(trade_returns.mean() * 100.0) if len(trade_returns) else None,
        "buy_hold_return_pct": float((close[hi - 1] / base - 1.0) * 100.0) if hi > lo else 0.0,
    }


def evaluate_window(
    history: pd.DataFrame,
    rules: Sequence[Mapping[str, Any]],
    costs: Costs,
    periods_per_year: float,
    lo: int,
) -> list[dict[str, Any]]:
    """Run ``rules`` over ``history`` and summarise bars ``lo`` onward (earlier bars only warm the indicators)."""

    open_, close, atr = history["open"].to_numpy(float), history["close"].to_numpy(float), atr14(history)
    rows = []
    for rule in rules:
        fills = Fills(open_, close, compute_targets(history, rule), atr, costs)
        summary = window_summary(fills, open_, close, lo, len(close), periods_per_year)
        rows.append({"id": rule["id"], "name": rule["name"], **summary})
    return rows


def resolve_periods_per_year(frame: pd.DataFrame, requested: Optional[float]) -> tuple[float, bool]:
    """The requested annualisation factor, or one inferred from the median bar spacing (continuous trading assumed)."""

    if requested is not None:
        return float(requested), False
    spacing, _ = bar_interval(frame)
    if spacing is None or spacing <= 0:
        raise ValueError("periods_per_year cannot be inferred from this capture; provide it")
    return SECONDS_PER_YEAR / spacing, True


def bootstrap_seed(dataset: str, fingerprint: str) -> int:
    """Seed fixed by the dataset and its sealed research segment, so repeating a run cannot fish for luck."""

    return int(hashlib.sha256((dataset + fingerprint).encode("utf-8")).hexdigest()[:8], 16)


def mean_block_length(bars: int) -> int:
    return max(2, round(bars ** (1 / 3)))


def effective_n_scale(trials: int, grid_size: int) -> float:
    """How much the ledger's N inflates the effective N: 1 until more rules were tried than the grid holds."""

    return max(1.0, trials / grid_size)


def trial_records(
    dataset: str, strategies: Sequence[Mapping[str, Any]], outcome: Mapping[str, str]
) -> list[dict[str, Any]]:
    """One ledger trial per grid rule; ``outcome`` maps rule ids to their status (missing means the run failed)."""

    return [
        {
            "key": f"{dataset}::{rule['id']}",
            "rule_id": rule["id"],
            "family": rule["family"],
            "parameters": rule["parameters"],
            "outcome": outcome.get(rule["id"], "RUN_FAILED"),
        }
        for rule in strategies
    ]


def gap_statistics(open_: np.ndarray, close: np.ndarray) -> dict[str, float]:
    """Close-to-open gap sizes in basis points: the part of the return a next-open fill earns or pays."""

    gaps = np.abs(open_[1:] / close[:-1] - 1.0) * 1e4
    return {"mean_abs": float(gaps.mean()), "p99_abs": float(np.percentile(gaps, 99)), "max_abs": float(gaps.max())}


def lookahead_probe(
    frame: pd.DataFrame, strategies: Sequence[Mapping[str, Any]], targets: Mapping[str, np.ndarray]
) -> dict[str, Any]:
    """Recompute every rule on truncated frames and require the same targets on the bars kept.

    The reported ``truncation_bar`` is the 75% cut; the other cuts matter because a rule that peeks
    one bar ahead only differs at the boundary, and does so on roughly half of the cuts.
    """

    cuts = sorted({max(2, int(len(frame) * fraction)) for fraction in PROBE_FRACTIONS})
    checked = 0
    for rule in strategies:
        if rule["id"] not in targets:
            continue
        checked += 1
        for cut in cuts:
            if not np.array_equal(compute_targets(frame.iloc[:cut], rule), targets[rule["id"]][:cut]):
                raise LookaheadError(
                    f"look-ahead integrity check failed: rule {rule['id']} changes when later bars are removed"
                )
    return {"passed": True, "rules_checked": checked, "truncation_bar": max(2, int(len(frame) * PROBE_FRACTION))}


def _evidence(
    *,
    stats: Moments,
    net: Mapping[float, np.ndarray],
    trades: Trades,
    gross_trades: np.ndarray,
    adjusted_p: float,
    ppy: float,
    sharpe_variance: float,
    trial_counts: Mapping[str, float],
) -> dict[str, Any]:
    """Everything reported for one rule that passed the trade gate."""

    dsr = deflated_sharpe(stats, sharpe_variance, trial_counts["point"])
    trade_net = {multiplier: trades.returns(series) for multiplier, series in net.items()}
    mean_gross, mean_net = float(gross_trades.mean()), float(trade_net[1.0].mean())
    round_trip, base = max(0.0, mean_gross) * 1e4, (mean_gross - mean_net) * 1e4
    stress = [
        {
            "multiplier": multiplier,
            "sharpe": sharpe_ratio(series, ppy),
            "mean_trade_return_pct": float(trade_net[multiplier].mean() * 100.0),
            "total_return_pct": float((np.prod(1.0 + series) - 1.0) * 100.0),
        }
        for multiplier, series in net.items()
    ]
    at_stress = next(item for item in stress if item["multiplier"] == STRESS_CHECK_MULTIPLIER)
    checks = {
        "bootstrap": bool(adjusted_p < ALPHA),
        "dsr": bool(dsr >= DSR_THRESHOLD),
        "stress": bool(
            at_stress["mean_trade_return_pct"] > 0 and at_stress["sharpe"] is not None and at_stress["sharpe"] > 0
        ),
    }
    return {
        "sharpe": stats.sharpe * math.sqrt(ppy),
        "sharpe_se": sharpe_standard_error(stats) * math.sqrt(ppy),
        "mean_trade_return_pct": mean_net * 100.0,
        "adjusted_p": adjusted_p,
        "dsr": dsr,
        "dsr_sensitivity": {
            "low_n": {"n": trial_counts["low"], "dsr": deflated_sharpe(stats, sharpe_variance, trial_counts["low"])},
            "high_n": {"n": trial_counts["high"], "dsr": deflated_sharpe(stats, sharpe_variance, trial_counts["high"])},
        },
        "break_even": {
            "round_trip_bps": round_trip,
            "base_round_trip_bps": base,
            "multiple": round_trip / base if base > 0 else None,
        },
        "stress": stress,
        "checks": checks,
        "candidate": all(checks.values()),
    }


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _failure_reasons(passing: Sequence[Mapping[str, Any]]) -> list[str]:
    """One sentence per group of rules that fail the same check."""

    groups = (
        ("bootstrap", f"Fail the bootstrap test (adjusted p-value {ALPHA} or higher)"),
        ("dsr", f"Fail the deflated Sharpe ratio (below {DSR_THRESHOLD})"),
        ("stress", f"Fail the {STRESS_CHECK_MULTIPLIER}x cost stress (net trade return or Sharpe not above zero)"),
    )
    reasons = []
    for check, text in groups:
        failing = [row["id"] for row in passing if not row["evidence"]["checks"][check]]
        if failing:
            reasons.append(f"{text}: {', '.join(failing)}.")
    return reasons


def _verdict(rows: Sequence[Mapping[str, Any]], min_trades: int, bars: int) -> dict[str, Any]:
    """Exactly one label, with the reasons behind it."""

    passing = [row for row in rows if row["status"] == PASSED_GATE]
    if not passing:
        most = max((row["trades"] for row in rows), default=0)
        never = sum(row["status"] == NEVER_TRADES for row in rows)
        errors = sum(row["status"] == ERROR for row in rows)
        reasons = [
            f"0 of {len(rows)} rules reached the {min_trades}-trade minimum, so no Sharpe ratio, p-value or DSR "
            "is computed.",
            f"Most trades by any rule: {most}.",
        ]
        if never:
            reasons.append(f"{_plural(never, 'rule')} never traded.")
        if errors:
            reasons.append(f"{_plural(errors, 'rule')} could not be evaluated.")
        return {
            "label": INSUFFICIENT_DATA,
            "headline": f"No rule reached {min_trades} trades on {bars} research bars (most: {most}). "
            "Nothing can be concluded or ranked.",
            "reasons": reasons,
        }
    candidates = [row["id"] for row in passing if row["evidence"]["candidate"]]
    if candidates:
        return {
            "label": CANDIDATE,
            "headline": f"{len(candidates)} of {len(passing)} rules passed the trade gate, the bootstrap test, the "
            "deflated Sharpe ratio and the 1.5x cost stress. Eligible for one holdout read.",
            "reasons": [f"Candidate rules: {', '.join(candidates)}.", *_failure_reasons(passing)],
        }
    return {
        "label": INDISTINGUISHABLE,
        "headline": f"{_plural(len(passing), 'rule')} passed the trade gate, but none also passes the bootstrap test, "
        "the deflated Sharpe ratio and the 1.5x cost stress. The results cannot be told apart from luck.",
        "reasons": _failure_reasons(passing),
    }


def _notes(min_trades: int, holdout_bars: int, has_statistics: bool, ppy: float) -> list[str]:
    """Plain sentences explaining what the report does and does not say."""

    statistics = [
        "The adjusted p-value comes from a stationary-bootstrap Romano-Wolf test of each rule's mean return in "
        "excess of passively holding the asset for the same share of time, across every rule that passed the gate.",
        "The deflated Sharpe ratio discounts each Sharpe ratio for the effective number of independent rules tried, "
        "the spread of Sharpe ratios across them, skewness, kurtosis and sample length.",
        "PBO is the share of train/test splits in which the best in-sample rule lands in the bottom half "
        "out-of-sample; it is noisy at short sample lengths.",
    ]
    return [
        "Signals are computed at a bar's close and filled at the next bar's open; the legacy Research page fills at "
        "the signal close, so its numbers differ from these.",
        f"A rule needs at least {min_trades} trades before any Sharpe ratio, p-value or DSR is computed for it; "
        "nothing is ranked.",
        f"Sharpe ratios are annualised with {ppy:,.0f} periods per year and include flat bars; standard errors are "
        "wide on short samples.",
        *(statistics if has_statistics else []),
        "N counts every rule ever evaluated on this dataset in the ledger, including discarded and failed runs; "
        "changing costs or the trade minimum does not change it.",
        f"The sealed holdout ({holdout_bars} bars) can be read once, for frozen rules, and at this length it is a "
        "sanity check, not a verdict.",
    ]


def evaluate(
    frame: pd.DataFrame,
    *,
    dataset: str,
    fingerprint: str,
    costs: Costs,
    min_trades: int = DEFAULT_MIN_TRADES,
    periods_per_year: Optional[float] = None,
    holdout_bars: int = 0,
    trials_dataset: Optional[int] = None,
    strategies: Optional[Sequence[Mapping[str, Any]]] = None,
) -> dict[str, Any]:
    """Evaluate the rule grid on ``frame`` (already cut to the research window) and return the verdict.

    ``trials_dataset`` is the ledger's N for this dataset including this run.  The result holds the
    ``verdict``, ``settings``, ``rules``, ``statistics``, ``uncertainty``, ``integrity`` and ``notes``
    of a report plus the ledger ``trials`` of this run.  Randomness is seeded from ``dataset`` and
    ``fingerprint`` only, so repeating a run gives the same numbers.
    """

    grid = list(strategies if strategies is not None else strategy_permutations())
    bars = len(frame)
    open_, close, atr = frame["open"].to_numpy(float), frame["close"].to_numpy(float), atr14(frame)
    ppy, inferred = resolve_periods_per_year(frame, periods_per_year)
    seed, block = bootstrap_seed(dataset, fingerprint), mean_block_length(bars)
    trials_dataset = len(grid) if trials_dataset is None else trials_dataset

    targets: dict[str, np.ndarray] = {}
    failures: dict[str, str] = {}
    for rule in grid:
        try:
            targets[rule["id"]] = compute_targets(frame, rule)
        except Exception as exc:  # noqa: BLE001 - one broken rule must not hide the others
            failures[rule["id"]] = str(exc) or type(exc).__name__
    probe = lookahead_probe(frame, grid, targets)

    rows: list[dict[str, Any]] = []
    runs: dict[str, tuple[Fills, Trades]] = {}
    for rule in grid:
        row = {
            "id": rule["id"],
            "family": rule["family"],
            "name": rule["name"],
            "parameters": rule["parameters"],
            "status": ERROR,
            "trades": 0,
            "closed_trades": 0,
            "exposure_pct": 0.0,
            "error": failures.get(rule["id"]),
            "evidence": None,
        }
        rows.append(row)
        if rule["id"] in failures:
            continue
        try:
            fills = Fills(open_, close, targets[rule["id"]], atr, costs)
        except IntegrityError:
            raise
        except Exception as exc:  # noqa: BLE001
            row["error"] = str(exc) or type(exc).__name__
            continue
        trades = find_trades(fills, 0, bars)
        count = len(trades.entries)
        row.update(
            trades=count,
            closed_trades=int(trades.closed.sum()),
            exposure_pct=float(fills.position[1:].mean() * 100.0),
            status=NEVER_TRADES if count == 0 else PASSED_GATE if count >= min_trades else INSUFFICIENT_TRADES,
        )
        if count and not np.ptp(fills.net(1.0)) > 0:
            row.update(status=ERROR, error="net returns are constant, so no statistic is defined")
            continue
        runs[rule["id"]] = (fills, trades)

    passing = [row for row in rows if row["status"] == PASSED_GATE]
    statistics = (
        _statistics(
            passing=passing,
            runs=runs,
            close=close,
            ppy=ppy,
            seed=seed,
            block=block,
            trials_dataset=trials_dataset,
            grid_size=len(grid),
        )
        if passing
        else None
    )
    return {
        "verdict": _verdict(rows, min_trades, bars),
        "settings": {
            "min_trades": min_trades,
            "costs": costs.as_dict(),
            "periods_per_year": ppy,
            "periods_per_year_inferred": inferred,
            "alpha": ALPHA,
            "dsr_threshold": DSR_THRESHOLD,
            "stress_multipliers": list(STRESS_MULTIPLIERS),
            "bootstrap": {"replicates": BOOTSTRAP_REPLICATES, "mean_block_length": block, "seed": seed},
        },
        "rules": rows,
        "statistics": statistics,
        "uncertainty": {
            "research_bars": bars,
            "sharpe_se_annualised_iid": iid_sharpe_se(ppy, bars),
            "holdout_bars": holdout_bars,
            "holdout_sharpe_se_annualised_iid": iid_sharpe_se(ppy, holdout_bars),
            "note": "Standard errors are for the whole research sample; any sub-window, such as the holdout or one "
            "month, has a wider one.",
        },
        "integrity": {
            "fill_model": "next_open",
            "signal_shift_verified": True,
            "lookahead_probe": probe,
            "close_to_open_gap_bps": gap_statistics(open_, close),
            "research_fingerprint": fingerprint[:16],
        },
        "notes": _notes(min_trades, holdout_bars, statistics is not None, ppy),
        "trials": trial_records(dataset, grid, {row["id"]: row["status"] for row in rows}),
    }


def _statistics(
    *,
    passing: list[dict[str, Any]],
    runs: Mapping[str, tuple[Fills, Trades]],
    close: np.ndarray,
    ppy: float,
    seed: int,
    block: int,
    trials_dataset: int,
    grid_size: int,
) -> dict[str, Any]:
    """Fill in ``evidence`` for every passing rule and return the family-level statistics block."""

    bars = len(close)
    base = {rule_id: fills.net(1.0) for rule_id, (fills, _) in runs.items()}
    stats = {rule_id: moments(series) for rule_id, series in base.items()}
    varying = [rule_id for rule_id, value in stats.items() if value is not None]
    all_returns = np.column_stack([base[rule_id] for rule_id in varying])
    benchmark = np.zeros(bars)
    benchmark[1:] = close[1:] / close[:-1] - 1.0
    evidence = np.column_stack(
        [base[row["id"]] - runs[row["id"]][0].position[1:].mean() * benchmark for row in passing]
    )
    means, ratios = bootstrap_study(
        evidence,
        all_returns,
        seed=seed,
        replicates=BOOTSTRAP_REPLICATES,
        block=block,
        participation_replicates=EFFECTIVE_N_REPLICATES,
    )
    statistic, adjusted = romano_wolf(evidence.mean(axis=0), means)

    estimate = participation_ratio(all_returns)
    tail = 100 * (1 - EFFECTIVE_N_LEVEL) / 2
    low, high = (float(value) for value in np.percentile(ratios, [tail, 100 - tail]))
    # Resampling adds noise correlation, so replicates sit below the estimate; never report an interval that excludes it.
    low, high = min(low, estimate), max(high, estimate)
    scale = effective_n_scale(trials_dataset, grid_size)
    effective = {
        "estimate": estimate,
        "low": low,
        "high": high,
        "level": EFFECTIVE_N_LEVEL,
        "rules_used": len(varying),
        "ledger_trials": trials_dataset,
        "scaled_estimate": estimate * scale,
    }
    per_period = np.array([stats[rule_id].sharpe for rule_id in varying])
    sharpe_variance = float(per_period.var(ddof=1)) if len(per_period) >= 2 else 0.0
    trial_counts = {"point": estimate * scale, "low": low * scale, "high": high * scale}

    for column, row in enumerate(passing):
        fills, trades = runs[row["id"]]
        row["evidence"] = _evidence(
            stats=stats[row["id"]],
            net={multiplier: fills.net(multiplier) for multiplier in STRESS_MULTIPLIERS},
            trades=trades,
            gross_trades=trades.returns(fills.gross),
            adjusted_p=float(adjusted[column]),
            ppy=ppy,
            sharpe_variance=sharpe_variance,
            trial_counts=trial_counts,
        )
    best = int(np.argmax(statistic))
    pbo, unavailable = overfitting_probability(np.column_stack([base[row["id"]] for row in passing]))
    if pbo is not None:
        noisy = bars < PBO_NOISY_BARS or len(passing) < PBO_NOISY_RULES
        pbo = {
            **pbo,
            "rules": len(passing),
            "noisy": noisy,
            "caveat": "Noisy at this sample length: treat PBO as a rough warning, not a measurement."
            if noisy
            else "Share of train/test splits in which the best in-sample rule ranks in the bottom half out-of-sample.",
        }
    return {
        "effective_n": effective,
        "reality_check": {
            "statistic": "studentised mean excess return over exposure-matched passive holding",
            "best_rule": passing[best]["id"],
            "p_value": float(adjusted[best]),
            "alpha": ALPHA,
            "rejected": bool(adjusted[best] < ALPHA),
            "rules_tested": len(passing),
            "replicates": BOOTSTRAP_REPLICATES,
            "mean_block_length": block,
            "seed": seed,
        },
        "pbo": pbo,
        "pbo_unavailable": unavailable,
    }
