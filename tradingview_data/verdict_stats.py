"""Statistics behind the verdict engine, in plain numpy.

Deflated Sharpe ratio (Bailey & Lopez de Prado, 2014), effective number of trials from the
correlation matrix, a stationary bootstrap (Politis & Romano, 1994) feeding a Romano-Wolf stepdown
test, and probability of backtest overfitting by combinatorially symmetric cross-validation
(Bailey, Borwein, Lopez de Prado & Zhu, 2017).
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from typing import Iterator, Optional

import numpy as np

EULER_GAMMA = 0.5772156649015329
TINY = 1e-12
CHUNK_ELEMENTS = 2_000_000
MAX_PBO_BLOCKS = 16
MIN_PBO_BLOCK_BARS = 40

_ACKLAM_A = (-3.969683028665376e01, 2.209460984245205e02, -2.759285104469687e02, 1.383577518672690e02, -3.066479806614716e01, 2.506628277459239e00)
_ACKLAM_B = (-5.447609879822406e01, 1.615858368580409e02, -1.556989798598866e02, 6.680131188771972e01, -1.328068155288572e01)
_ACKLAM_C = (-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e00, -2.549732539343734e00, 4.374664141464968e00, 2.938163982698783e00)
_ACKLAM_D = (7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00, 3.754408661907416e00)


def norm_cdf(value: float) -> float:
    """Standard normal CDF."""

    return 0.5 * math.erfc(-value / math.sqrt(2.0))


def norm_ppf(probability: float) -> float:
    """Inverse standard normal CDF (Acklam's rational approximation plus one Halley step)."""

    if probability <= 0.0:
        return -math.inf
    if probability >= 1.0:
        return math.inf
    a, b, c, d = _ACKLAM_A, _ACKLAM_B, _ACKLAM_C, _ACKLAM_D
    if probability < 0.02425:
        q = math.sqrt(-2.0 * math.log(probability))
        x = (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0)
    elif probability > 1.0 - 0.02425:
        q = math.sqrt(-2.0 * math.log(1.0 - probability))
        x = -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0)
    else:
        q = probability - 0.5
        r = q * q
        x = (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1.0)
    error = norm_cdf(x) - probability
    step = error * math.sqrt(2.0 * math.pi) * math.exp(x * x / 2.0)
    return x - step / (1.0 + x * step / 2.0)


@dataclass(frozen=True)
class Moments:
    """Sample moments of a return series; ``sharpe`` is per period and ``kurtosis`` is raw (normal = 3)."""

    count: int
    mean: float
    std: float
    skew: float
    kurtosis: float

    @property
    def sharpe(self) -> float:
        return self.mean / self.std


def moments(returns: np.ndarray) -> Optional[Moments]:
    """Moments of ``returns``, or ``None`` when there are under three observations or no variation."""

    count = len(returns)
    if count < 3 or not np.ptp(returns) > 0:
        return None
    mean = float(returns.mean())
    centred = returns - mean
    population_std = math.sqrt(float(np.mean(centred**2)))
    return Moments(
        count=count,
        mean=mean,
        std=float(returns.std(ddof=1)),
        skew=float(np.mean(centred**3)) / population_std**3,
        kurtosis=float(np.mean(centred**4)) / population_std**4,
    )


def _sharpe_variance(sharpe: float, skew: float, kurtosis: float) -> float:
    """Asymptotic variance of a Sharpe estimate times its sample length (Mertens, 2002)."""

    return max(1.0 - skew * sharpe + (kurtosis - 1.0) / 4.0 * sharpe**2, TINY)


def sharpe_standard_error(stats: Moments) -> float:
    """Standard error of the per-period Sharpe ratio allowing for skew and fat tails."""

    return math.sqrt(_sharpe_variance(stats.sharpe, stats.skew, stats.kurtosis) / (stats.count - 1))


def expected_max_sharpe(variance: float, trials: float) -> float:
    """Sharpe ratio the best of ``trials`` unskilled rules is expected to show (``SR0``)."""

    trials = max(trials, 1.0)
    if trials <= 1.0 or variance <= 0.0:
        return 0.0
    blend = (1.0 - EULER_GAMMA) * norm_ppf(1.0 - 1.0 / trials) + EULER_GAMMA * norm_ppf(1.0 - 1.0 / (trials * math.e))
    return max(0.0, math.sqrt(variance) * blend)


def deflated_sharpe(stats: Moments, variance: float, trials: float) -> float:
    """Probability that the true Sharpe exceeds what ``trials`` unskilled rules would reach by luck."""

    benchmark = expected_max_sharpe(variance, trials)
    spread = math.sqrt(_sharpe_variance(stats.sharpe, stats.skew, stats.kurtosis))
    return norm_cdf((stats.sharpe - benchmark) * math.sqrt(stats.count - 1) / spread)


def participation_ratio(returns: np.ndarray) -> float:
    """``(sum of eigenvalues)^2 / sum of squared eigenvalues`` of the correlation matrix.

    It is 1 for identical columns and the column count for uncorrelated ones.  Columns that do not
    vary are ignored; fewer than two varying columns return their count.
    """

    varying = returns[:, np.ptp(returns, axis=0) > 0]
    if varying.shape[1] < 2:
        return float(varying.shape[1])
    eigenvalues = np.clip(np.linalg.eigvalsh(np.corrcoef(varying, rowvar=False)), 0.0, None)
    return float(eigenvalues.sum() ** 2 / np.sum(eigenvalues**2))


def stationary_indices(
    rng: np.random.Generator, length: int, block: int, replicates: int
) -> Iterator[tuple[int, np.ndarray]]:
    """Yield ``(first replicate, index matrix)`` chunks of a Politis-Romano stationary bootstrap.

    Each replicate walks the series circularly and restarts at a random position with probability
    ``1 / block`` per step, so block lengths are geometric with mean ``block``.  Chunking keeps
    memory flat for long series and depends only on ``length``, so results are reproducible.
    """

    rows = max(1, min(replicates, CHUNK_ELEMENTS // length))
    position = np.arange(length)
    done = 0
    while done < replicates:
        count = min(rows, replicates - done)
        restart = rng.random((count, length)) < 1.0 / block
        restart[:, 0] = True
        starts = rng.integers(0, length, size=(count, length))
        last = np.maximum.accumulate(np.where(restart, position, 0), axis=1)
        origin = np.take_along_axis(starts, last, axis=1)
        yield done, (origin + position - last) % length
        done += count


def bootstrap_study(
    evidence: np.ndarray,
    returns: np.ndarray,
    *,
    seed: int,
    replicates: int,
    block: int,
    participation_replicates: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Resample once and report what both tests need.

    Returns the bootstrap means of every ``evidence`` column (``replicates`` x columns) and the
    participation ratio of ``returns`` on the first ``participation_replicates`` replicates.
    """

    rng = np.random.default_rng(seed)
    series = np.ascontiguousarray(evidence.T)
    means = np.empty((replicates, series.shape[0]))
    ratios: list[float] = []
    for first, indices in stationary_indices(rng, evidence.shape[0], block, replicates):
        rows = slice(first, first + len(indices))
        for column, values in enumerate(series):
            means[rows, column] = values[indices].mean(axis=1)
        for row in range(max(0, min(len(indices), participation_replicates - first))):
            ratios.append(participation_ratio(returns[indices[row]]))
    return means, np.asarray(ratios)


def romano_wolf(observed: np.ndarray, bootstrap_means: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Studentised statistics and stepdown-adjusted p-values for "mean return is not above zero".

    Each statistic is ``mean / bootstrap standard deviation``.  Rules are taken from the largest
    statistic down; a rule's p-value is the share of null replicates whose maximum over the rules
    not yet rejected reaches its statistic, and is never below the previous rule's.  A rule with no
    bootstrap variation gets p = 1.
    """

    sigma = bootstrap_means.std(axis=0, ddof=1)
    usable = sigma > 0
    scale = np.where(usable, sigma, 1.0)
    statistics = np.where(usable, observed / scale, 0.0)
    null = np.where(usable, (bootstrap_means - observed) / scale, -np.inf)
    order = [int(column) for column in np.argsort(-statistics, kind="stable") if usable[column]]
    adjusted = np.ones(len(observed))
    running = 0.0
    for position, column in enumerate(order):
        strongest_null = null[:, order[position:]].max(axis=1)
        running = max(running, float(np.mean(strongest_null >= statistics[column])))
        adjusted[column] = running
    return statistics, adjusted


def _window_sharpe(total: np.ndarray, squares: np.ndarray, count: int) -> np.ndarray:
    mean = total / count
    std = np.sqrt(np.maximum((squares - count * mean**2) / (count - 1), 0.0))
    return np.divide(mean, std, out=np.zeros_like(mean), where=std > 0)


def overfitting_probability(returns: np.ndarray) -> tuple[Optional[dict[str, float]], Optional[str]]:
    """Probability of backtest overfitting by CSCV over the columns of ``returns``.

    Returns ``(result, None)`` or ``(None, reason)``.  The last ``blocks * block length`` rows are
    cut into ``blocks`` equal blocks, every way of training on half and testing on the other half is
    scored from per-block sums, and the result is the share of splits where the rule that won the
    training half ranks in the bottom half of the test half.
    """

    length, rules = returns.shape
    if rules < 2:
        return None, "needs at least 2 rules that passed the trade-count gate"
    blocks = min(MAX_PBO_BLOCKS, 2 * (length // MIN_PBO_BLOCK_BARS))
    if blocks < 4:
        return None, f"needs at least {2 * MIN_PBO_BLOCK_BARS} research bars for 4 blocks (have {length})"
    size = length // blocks
    cut = returns[length - blocks * size :].reshape(blocks, size, rules)
    sums, squares = cut.sum(axis=1), (cut**2).sum(axis=1)
    splits = np.array(list(itertools.combinations(range(blocks), blocks // 2)))
    train = np.zeros((len(splits), blocks))
    np.put_along_axis(train, splits, 1.0, axis=1)
    half = blocks // 2 * size
    train_sharpe = _window_sharpe(train @ sums, train @ squares, half)
    test_sharpe = _window_sharpe(sums.sum(axis=0) - train @ sums, squares.sum(axis=0) - train @ squares, half)
    winner = np.argmax(train_sharpe, axis=1)
    score = test_sharpe[np.arange(len(splits)), winner][:, None]
    below = (test_sharpe < score).sum(axis=1)
    tied = (test_sharpe == score).sum(axis=1)
    omega = (below + (tied + 1) / 2) / (rules + 1)
    logit = np.log(omega / (1.0 - omega))
    return {"value": float(np.mean(logit <= 0)), "blocks": blocks, "combinations": len(splits)}, None
