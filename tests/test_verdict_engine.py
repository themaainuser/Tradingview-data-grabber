import hashlib
import json
import math
import pathlib
import re
import sys
from statistics import NormalDist

import numpy as np
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from tradingview_data.research import strategy_permutations, strategy_positions, strategy_targets  # noqa: E402
from tradingview_data.verdict import (  # noqa: E402
    CANDIDATE,
    INDISTINGUISHABLE,
    INSUFFICIENT_DATA,
    INSUFFICIENT_TRADES,
    NEVER_TRADES,
    PASSED_GATE,
    Costs,
    Fills,
    LookaheadError,
    atr14,
    bootstrap_seed,
    compute_targets,
    evaluate,
    find_trades,
    gap_statistics,
    lookahead_probe,
    resolve_periods_per_year,
    sharpe_ratio,
    window_summary,
)
from tradingview_data.verdict_stats import (  # noqa: E402
    Moments,
    bootstrap_study,
    deflated_sharpe,
    expected_max_sharpe,
    moments,
    norm_cdf,
    norm_ppf,
    overfitting_probability,
    participation_ratio,
    romano_wolf,
    sharpe_standard_error,
    stationary_indices,
)

from verdict_data import frame_from_returns, random_walk_frame, regime_frame  # noqa: E402

GRID = strategy_permutations()
FINGERPRINT = "ab" * 32


def scan_keys(value):
    """Every dict key anywhere inside a JSON-like structure."""

    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from scan_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from scan_keys(item)


def judge(frame, **overrides):
    settings = {"dataset": "x.csv", "fingerprint": FINGERPRINT, "costs": Costs()}
    return evaluate(frame, **{**settings, **overrides})


def causal_violations(frame, target_fn, cuts):
    """Cut points where the target at bar ``k`` depends on any bar after ``k``."""

    full = np.asarray(target_fn(frame), dtype=float)
    other = random_walk_frame(len(frame), seed=777)
    bad = []
    for k in cuts:
        truncated = np.asarray(target_fn(frame.iloc[: k + 1]), dtype=float)
        scrambled = frame.copy()
        scrambled.iloc[k + 1 :] = other.iloc[k + 1 :].to_numpy()
        scrambled_targets = np.asarray(target_fn(scrambled), dtype=float)
        if not (
            np.array_equal(truncated, full[: k + 1])
            and truncated[k] == full[k]
            and np.array_equal(scrambled_targets[: k + 1], full[: k + 1])
        ):
            bad.append(k)
    return bad


def next_bar_cheat(frame):
    return (frame["close"].shift(-1) > frame["close"]).astype(float)


def centred_mean_cheat(frame):
    return (frame["close"] > frame["close"].rolling(9, center=True, min_periods=1).mean()).astype(float)


def cheating_rule(target_fn):
    return {"id": "cheat", "family": "cheat", "name": "cheat", "parameters": {}, "target_fn": target_fn}


# --- look-ahead (acceptance) -----------------------------------------------------------------------


@pytest.mark.parametrize("rule", GRID, ids=[rule["id"] for rule in GRID])
@pytest.mark.parametrize("seed", [0, 1])
def test_no_rule_uses_the_current_bars_future(rule, seed):
    frame = random_walk_frame(320, seed)
    cuts = list(range(20, 320, 13))
    assert causal_violations(frame, lambda data: strategy_targets(data, rule), cuts) == []


@pytest.mark.parametrize("rule", GRID, ids=[rule["id"] for rule in GRID])
def test_fills_take_the_previous_bars_target_exactly(rule):
    frame = random_walk_frame(400, 3)
    targets = compute_targets(frame, rule)
    fills = Fills(frame["open"].to_numpy(), frame["close"].to_numpy(), targets, atr14(frame), Costs())
    assert fills.position[0] == 0.0
    assert np.array_equal(fills.position[1:], targets[:-1])
    assert np.array_equal(fills.position, strategy_positions(frame, rule).to_numpy())


@pytest.mark.parametrize("cheat", [next_bar_cheat, centred_mean_cheat])
def test_a_cheating_strategy_is_caught_by_the_same_test_and_by_the_runtime_probe(cheat):
    frame = random_walk_frame(320, 0)
    cuts = list(range(20, 320, 13))
    assert causal_violations(frame, cheat, cuts), "the look-ahead test must be able to fail"
    with pytest.raises(LookaheadError, match="look-ahead integrity check failed"):
        lookahead_probe(frame, [cheating_rule(cheat)], {"cheat": compute_targets(frame, cheating_rule(cheat))})
    with pytest.raises(LookaheadError):
        judge(frame, strategies=[cheating_rule(cheat), *GRID])


def test_probe_passes_for_the_grid_and_reports_what_it_checked():
    frame = random_walk_frame(400, 1)
    report = judge(frame)
    assert report["integrity"]["lookahead_probe"] == {"passed": True, "rules_checked": 16, "truncation_bar": 300}
    assert report["integrity"]["signal_shift_verified"] is True
    assert report["integrity"]["fill_model"] == "next_open"


def test_legacy_positions_are_the_shifted_targets():
    frame = random_walk_frame(200, 4)
    for rule in GRID:
        expected = strategy_targets(frame, rule).shift(1).fillna(0.0).to_numpy()
        assert np.array_equal(strategy_positions(frame, rule).to_numpy(), expected)


# --- fill and cost arithmetic ----------------------------------------------------------------------

OPEN = np.array([100, 100, 100, 102, 106, 106, 106, 107.0])
CLOSE = np.array([100, 100, 102, 105.06, 106, 106, 108.12, 107.0])
TARGETS = np.array([0, 1, 1, 0, 0, 1, 0, 0.0])
ATR = np.ones(8)
COSTS = Costs(fee_bps_per_side=10, spread_bps=4, slippage_k=0.5)


def side_cost(open_price, multiplier=1.0):
    """Fee 10 bps + half of 4 bps spread + 0.5 x ATR 1.0 of slippage, at the fill's open."""

    return multiplier * (0.001 + 0.0002 + 0.5 * 1.0 / open_price)


def test_entry_at_the_open_and_the_gap_is_earned_before_an_exit():
    fills = Fills(OPEN, CLOSE, TARGETS, ATR, COSTS)
    assert fills.position.tolist() == [0, 0, 1, 1, 0, 0, 1, 0]
    assert fills.turnover.tolist() == [0, 0, 1, 0, 1, 0, 1, 1]
    gap_into_exit, gap_after_second_entry = 106 / 105.06 - 1, 107 / 108.12 - 1
    assert fills.gross == pytest.approx([0, 0, 0.02, 0.03, gap_into_exit, 0, 0.02, gap_after_second_entry])
    assert fills.position[4] == 0 and fills.gross[4] > 0


def test_costs_are_charged_on_both_sides_of_every_trade():
    fills = Fills(OPEN, CLOSE, TARGETS, ATR, COSTS)
    expected = {2: side_cost(100), 4: side_cost(106), 6: side_cost(106), 7: side_cost(107)}
    assert fills.cost(1.0) == pytest.approx([expected.get(bar, 0.0) for bar in range(8)])
    assert fills.cost(2.0) == pytest.approx([2 * expected.get(bar, 0.0) for bar in range(8)])
    net = fills.net(1.0)
    assert net[2] == pytest.approx(1.02 * (1 - side_cost(100)) - 1)
    assert net[4] == pytest.approx((106 / 105.06) * (1 - side_cost(106)) - 1)


def test_trade_returns_compound_entry_to_exit_bar_and_scale_with_the_multiplier():
    fills = Fills(OPEN, CLOSE, TARGETS, ATR, COSTS)
    trades = find_trades(fills, 0, 8)
    assert trades.entries.tolist() == [2, 6] and trades.ends.tolist() == [4, 7] and trades.closed.tolist() == [True, True]
    for multiplier in (1.0, 1.5, 2.0):
        first = 1.02 * (1 - side_cost(100, multiplier)) * 1.03 * (106 / 105.06) * (1 - side_cost(106, multiplier)) - 1
        second = 1.02 * (1 - side_cost(106, multiplier)) * (107 / 108.12) * (1 - side_cost(107, multiplier)) - 1
        assert trades.returns(fills.net(multiplier)) == pytest.approx([first, second])
    gross_first = 1.02 * 1.03 * (106 / 105.06) - 1
    assert trades.returns(fills.gross) == pytest.approx([gross_first, 1.02 * (107 / 108.12) - 1])


def test_zero_costs_make_net_equal_gross():
    fills = Fills(OPEN, CLOSE, TARGETS, ATR, Costs(0, 0, 0))
    assert np.array_equal(fills.net(1.0), fills.gross)
    assert np.array_equal(fills.net(2.0), fills.gross)


def test_a_trade_still_open_at_the_last_bar_is_marked_to_market_and_flagged():
    fills = Fills(OPEN, CLOSE, np.array([0, 1, 1, 1, 1, 1, 1, 1.0]), ATR, COSTS)
    trades = find_trades(fills, 0, 8)
    assert trades.entries.tolist() == [2] and trades.ends.tolist() == [7] and trades.closed.tolist() == [False]
    expected = np.prod(1 + fills.net(1.0)[2:8]) - 1
    assert trades.returns(fills.net(1.0)) == pytest.approx([expected])


def test_windows_count_only_entries_inside_them_but_keep_the_carried_position():
    fills = Fills(OPEN, CLOSE, TARGETS, ATR, COSTS)
    trades = find_trades(fills, 3, 8)
    assert trades.entries.tolist() == [6]
    summary = window_summary(fills, OPEN, CLOSE, 3, 8, periods_per_year=8760)
    assert summary["trades"] == 1 and summary["closed_trades"] == 1
    assert summary["exposure_pct"] == pytest.approx(2 / 5 * 100)
    assert summary["net_return_pct"] == pytest.approx((np.prod(1 + fills.net(1.0)[3:8]) - 1) * 100)
    assert summary["buy_hold_return_pct"] == pytest.approx((107 / 102 - 1) * 100)


def test_an_undefined_cost_at_a_fill_raises_but_no_fill_means_no_cost():
    with pytest.raises(ValueError, match="ATR"):
        Fills(OPEN, CLOSE, TARGETS, np.full(8, np.nan), COSTS)
    flat = Fills(OPEN, CLOSE, np.zeros(8), np.full(8, np.nan), COSTS)
    assert not flat.net(1.0).any()


def test_atr14_is_wilder_smoothing_of_true_range_and_causal():
    frame = random_walk_frame(40, 2)
    high, low, close = (frame[name].to_numpy() for name in ("high", "low", "close"))
    true_range = [high[0] - low[0]] + [
        max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1])) for i in range(1, 40)
    ]
    smoothed = [true_range[0]]
    for value in true_range[1:]:
        smoothed.append(smoothed[-1] * 13 / 14 + value / 14)
    atr = atr14(frame)
    assert np.isnan(atr[:13]).all()
    assert atr[13:] == pytest.approx(smoothed[13:])
    assert np.array_equal(atr14(frame.iloc[:25])[13:], atr[13:25])


def test_gap_statistics_and_periods_per_year():
    stats = gap_statistics(np.array([1.0, 1.01, 0.99]), np.array([1.0, 1.0, 1.0]))
    assert stats["max_abs"] == pytest.approx(100.0) and stats["mean_abs"] == pytest.approx(100.0)
    hourly = random_walk_frame(50, 1)
    assert resolve_periods_per_year(hourly, None) == (8760.0, True)
    assert resolve_periods_per_year(hourly, 252) == (252.0, False)
    assert resolve_periods_per_year(random_walk_frame(50, 1).resample("D").last().dropna(), None)[0] == 365.0


def test_sharpe_ratio_is_annualised_and_undefined_for_flat_series():
    returns = np.array([0.01, -0.005, 0.02, 0.0])
    assert sharpe_ratio(returns, 4) == pytest.approx(returns.mean() / returns.std(ddof=1) * 2)
    assert sharpe_ratio(np.zeros(10), 252) is None


# --- gate, labels and "nothing is ranked" -----------------------------------------------------------


# Seeds whose 800 research bars look like the real capture (no rule reaches 30 trades; a driftless walk
# sometimes does: seed 2 has exactly 30 and correctly passes the gate).
@pytest.mark.parametrize("seed", [0, 1, 3, 4])
def test_current_capture_shape_is_insufficient_data_and_ranks_nothing(seed):
    research = random_walk_frame(1000, seed).iloc[:800]
    report = judge(research)
    assert max(rule["trades"] for rule in report["rules"]) < 30
    assert report["verdict"]["label"] == INSUFFICIENT_DATA
    assert report["statistics"] is None
    assert all(rule["evidence"] is None for rule in report["rules"])
    assert "Nothing can be concluded or ranked" in report["verdict"]["headline"]
    assert not [key for key in scan_keys(report) if re.search(r"rank|score", key)]


def test_zero_trade_and_under_minimum_rules_get_no_statistics_at_all():
    # A steady climb never makes RSI oversold, and every SMA rule enters once and never leaves.
    report = judge(frame_from_returns(np.full(300, 0.001), seed=0))
    statuses = {rule["id"]: rule["status"] for rule in report["rules"]}
    assert statuses["rsi-20-50"] == NEVER_TRADES and statuses["sma-10-20"] == INSUFFICIENT_TRADES
    assert report["verdict"]["label"] == INSUFFICIENT_DATA
    forbidden = {"sharpe", "sharpe_se", "dsr", "p_value", "adjusted_p"}
    for rule in report["rules"]:
        assert rule["evidence"] is None
        assert not forbidden & set(scan_keys(rule))
        assert set(rule) == {
            "id", "family", "name", "parameters", "status", "trades", "closed_trades", "exposure_pct", "error", "evidence"
        }


def test_rules_come_back_in_grid_order_and_raising_min_trades_only_removes_rules_from_the_gate():
    frame = random_walk_frame(1000, 0).iloc[:800]
    previous = None
    for min_trades in (1, 10, 30):
        report = judge(frame, min_trades=min_trades)
        assert [rule["id"] for rule in report["rules"]] == [rule["id"] for rule in GRID]
        passed = {rule["id"] for rule in report["rules"] if rule["status"] == PASSED_GATE}
        assert all(
            rule["status"] == NEVER_TRADES if rule["trades"] == 0 else rule["status"] in (PASSED_GATE, INSUFFICIENT_TRADES)
            for rule in report["rules"]
        )
        assert previous is None or passed <= previous
        previous = passed
    assert previous == set()


def test_a_rule_that_cannot_be_evaluated_is_an_error_trial_not_a_crash():
    def broken(_frame):
        raise RuntimeError("boom")

    frame = random_walk_frame(400, 0)
    report = judge(frame, strategies=[{"id": "broken", "family": "x", "name": "broken", "parameters": {}, "target_fn": broken}, GRID[1]])
    assert [rule["status"] for rule in report["rules"]][0] == "ERROR"
    assert report["rules"][0]["error"] == "boom"
    assert [trial["outcome"] for trial in report["trials"]][0] == "ERROR"
    assert len(report["trials"]) == 2


# --- statistics --------------------------------------------------------------------------------------


def test_inverse_normal_matches_known_values_and_the_standard_library():
    assert norm_ppf(0.975) == pytest.approx(1.959964, abs=1e-6)
    assert norm_ppf(0.5) == 0.0
    assert norm_ppf(0.995) == pytest.approx(2.575829, abs=1e-6)
    assert norm_ppf(0.05) == pytest.approx(-1.644854, abs=1e-6)
    reference = NormalDist()
    for probability in (1e-9, 1e-6, 0.001, 0.02, 0.3, 0.7, 0.98, 0.999999):
        assert norm_ppf(probability) == pytest.approx(reference.inv_cdf(probability), abs=1e-9)
        assert norm_cdf(norm_ppf(probability)) == pytest.approx(probability, rel=1e-9)
    assert norm_ppf(0.0) == -math.inf and norm_ppf(1.0) == math.inf


def reference_dsr(returns, trials, sharpe_variance):
    """The published formula written out with plain Python and the standard library's normal."""

    count = len(returns)
    mean = sum(returns) / count
    std = math.sqrt(sum((value - mean) ** 2 for value in returns) / (count - 1))
    pop = math.sqrt(sum((value - mean) ** 2 for value in returns) / count)
    skew = sum((value - mean) ** 3 for value in returns) / count / pop**3
    kurtosis = sum((value - mean) ** 4 for value in returns) / count / pop**4
    sharpe = mean / std
    normal = NormalDist()
    gamma = 0.5772156649
    if trials <= 1:
        benchmark = 0.0
    else:
        benchmark = math.sqrt(sharpe_variance) * (
            (1 - gamma) * normal.inv_cdf(1 - 1 / trials) + gamma * normal.inv_cdf(1 - 1 / (trials * math.e))
        )
    radicand = 1 - skew * sharpe + (kurtosis - 1) / 4 * sharpe**2
    return normal.cdf((sharpe - max(0.0, benchmark)) * math.sqrt(count - 1) / math.sqrt(radicand))


def skewed_returns(seed=5, count=600, drift=0.0015):
    rng = np.random.default_rng(seed)
    return rng.standard_t(5, count) * 0.01 + drift + 0.004 * (rng.random(count) < 0.05)


@pytest.mark.parametrize("trials", [2.0, 3.2, 7.0, 40.0])
def test_dsr_matches_an_independent_reference(trials):
    returns = skewed_returns()
    stats = moments(returns)
    assert deflated_sharpe(stats, 0.0004, trials) == pytest.approx(reference_dsr(list(returns), trials, 0.0004), abs=1e-9)


def test_dsr_falls_as_n_grows_and_equals_psr_against_zero_at_one_trial():
    stats = moments(skewed_returns())
    values = [deflated_sharpe(stats, 0.0004, trials) for trials in (1, 2, 4, 8, 16, 64)]
    assert all(later <= earlier for earlier, later in zip(values, values[1:]))
    assert values[1] > values[-1]
    radicand = 1 - stats.skew * stats.sharpe + (stats.kurtosis - 1) / 4 * stats.sharpe**2
    psr = norm_cdf(stats.sharpe * math.sqrt(stats.count - 1) / math.sqrt(radicand))
    assert values[0] == pytest.approx(psr)
    assert deflated_sharpe(stats, 0.0004, 0.3) == pytest.approx(psr)
    assert expected_max_sharpe(0.0, 50) == 0.0 and expected_max_sharpe(0.0004, 1.0) == 0.0


def test_mertens_standard_error_formula():
    stats = Moments(count=101, mean=0.1, std=1.0, skew=0.0, kurtosis=3.0)
    assert sharpe_standard_error(stats) == pytest.approx(math.sqrt((1 + 0.5 * 0.01) / 100))
    fat = Moments(count=101, mean=0.1, std=1.0, skew=-1.0, kurtosis=9.0)
    assert sharpe_standard_error(fat) == pytest.approx(math.sqrt((1 + 0.1 + 2 * 0.01) / 100))


def test_effective_n_is_one_for_identical_columns_and_about_m_for_independent_ones():
    rng = np.random.default_rng(0)
    same = np.tile(rng.normal(0, 0.01, (800, 1)), (1, 5))
    assert participation_ratio(same) == pytest.approx(1.0)
    independent = rng.normal(0, 0.01, (2000, 8))
    assert 7.5 < participation_ratio(independent) <= 8.0
    flat = np.column_stack([same, np.zeros(800)])
    assert participation_ratio(flat) == pytest.approx(1.0)
    assert participation_ratio(np.zeros((10, 3))) == 0.0


def fixed_rule(rule_id, bits):
    return {"id": rule_id, "family": "fixed", "name": rule_id, "parameters": {}, "target_fn": lambda frame: bits[: len(frame)]}


def random_bits(seed, rows):
    bits = np.random.default_rng(seed).integers(0, 2, rows).astype(float)
    bits[:20] = 0.0
    return bits


def test_reported_effective_n_for_identical_rules_and_its_interval_brackets_the_estimate():
    frame = random_walk_frame(600, 0)
    same = random_bits(1, 600)
    identical = judge(frame, costs=Costs(0, 0, 0), min_trades=5, strategies=[fixed_rule(f"same-{n}", same) for n in range(3)])
    effective = identical["statistics"]["effective_n"]
    assert (effective["estimate"], effective["low"], effective["high"]) == pytest.approx((1.0, 1.0, 1.0))
    assert effective["rules_used"] == 3 and effective["level"] == 0.9

    mixed = judge(frame, costs=Costs(0, 0, 0), min_trades=5, strategies=[fixed_rule(f"r{n}", random_bits(n, 600)) for n in range(6)])
    effective = mixed["statistics"]["effective_n"]
    assert 1.0 < effective["estimate"] < 6.0
    assert effective["low"] <= effective["estimate"] <= effective["high"] and effective["low"] < effective["high"]


def test_the_ledger_count_scales_the_effective_n_and_deflates_dsr():
    frame = random_walk_frame(600, 0)
    rules = [fixed_rule(f"r{n}", random_bits(n, 600)) for n in range(4)]
    base = judge(frame, costs=Costs(0, 0, 0), min_trades=5, strategies=rules, trials_dataset=4)
    more = judge(frame, costs=Costs(0, 0, 0), min_trades=5, strategies=rules, trials_dataset=12)
    first, second = base["statistics"]["effective_n"], more["statistics"]["effective_n"]
    assert (first["ledger_trials"], second["ledger_trials"]) == (4, 12)
    assert second["estimate"] == first["estimate"] and second["scaled_estimate"] == pytest.approx(3 * first["estimate"])
    assert [rule["evidence"]["dsr"] for rule in more["rules"]] != [rule["evidence"]["dsr"] for rule in base["rules"]]
    assert all(
        after["evidence"]["dsr"] <= before["evidence"]["dsr"] + 1e-12 for before, after in zip(base["rules"], more["rules"])
    )
    sensitivity = base["rules"][0]["evidence"]["dsr_sensitivity"]
    assert sensitivity["low_n"]["n"] <= first["scaled_estimate"] <= sensitivity["high_n"]["n"]
    assert sensitivity["low_n"]["dsr"] >= sensitivity["high_n"]["dsr"]


def test_stationary_bootstrap_blocks_have_the_requested_mean_length():
    rng = np.random.default_rng(0)
    (first, indices), *rest = list(stationary_indices(rng, 500, 10, 40))
    assert first == 0 and not rest and indices.shape == (40, 500)
    assert indices.min() >= 0 and indices.max() < 500
    continues = (indices[:, 1:] == (indices[:, :-1] + 1) % 500).mean()
    assert continues == pytest.approx(1 - 1 / 10, abs=0.02)


def test_bootstrap_study_is_reproducible_for_a_seed_and_differs_between_seeds():
    rng = np.random.default_rng(1)
    evidence = rng.normal(0, 0.01, (300, 3))
    args = dict(seed=5, replicates=120, block=7, participation_replicates=30)
    means, ratios = bootstrap_study(evidence, evidence, **args)
    again, again_ratios = bootstrap_study(evidence, evidence, **args)
    assert np.array_equal(means, again) and np.array_equal(ratios, again_ratios)
    assert means.shape == (120, 3) and ratios.shape == (30,)
    assert bootstrap_study(evidence, evidence, **{**args, "seed": 6})[0].tolist() != means.tolist()


def test_stepdown_p_values_are_monotone_in_statistic_order_and_within_bounds():
    rng = np.random.default_rng(2)
    shifts = np.array([0.0, 0.0, 0.02, 0.05, 0.0, 0.0])
    evidence = rng.normal(0, 1.0, (800, 6)) * 0.01 + shifts * 0.01 * 6
    evidence[:, 5] = 0.0
    means, _ = bootstrap_study(evidence, evidence, seed=3, replicates=1000, block=9, participation_replicates=10)
    statistics, adjusted = romano_wolf(evidence.mean(axis=0), means)
    assert ((adjusted >= 0) & (adjusted <= 1)).all()
    usable = [column for column in np.argsort(-statistics, kind="stable") if column != 5]
    assert (np.diff(adjusted[usable]) >= 0).all()
    assert adjusted[3] < 0.05 and adjusted[0] > 0.05
    assert adjusted[5] == 1.0


def test_pbo_is_near_one_half_for_noise_and_low_for_a_planted_dominant_rule():
    rng = np.random.default_rng(4)
    noise = rng.normal(0, 0.01, (4000, 8))
    result, reason = overfitting_probability(noise)
    assert reason is None and 0.3 <= result["value"] <= 0.7
    assert (result["blocks"], result["combinations"]) == (16, 12870)
    planted = noise.copy()
    planted[:, 0] += 0.004
    assert overfitting_probability(planted)[0]["value"] < 0.1


def test_pbo_reports_why_it_is_unavailable():
    rng = np.random.default_rng(0)
    assert overfitting_probability(rng.normal(size=(500, 1)))[0] is None
    assert "at least 2 rules" in overfitting_probability(rng.normal(size=(500, 1)))[1]
    assert "80 research bars" in overfitting_probability(rng.normal(size=(60, 3)))[1]
    result, _ = overfitting_probability(rng.normal(size=(100, 3)))
    assert (result["blocks"], result["combinations"]) == (4, 6)


def test_pbo_carries_its_noisy_caveat_at_short_sample_lengths():
    report = judge(random_walk_frame(1000, 0).iloc[:800], min_trades=5)
    pbo = report["statistics"]["pbo"]
    assert pbo["noisy"] is True and pbo["caveat"].startswith("Noisy at this sample length")
    assert 0.0 <= pbo["value"] <= 1.0 and report["statistics"]["pbo_unavailable"] is None
    counts = sorted(rule["trades"] for rule in report["rules"])
    assert counts[-1] > counts[-2]
    only_one = judge(random_walk_frame(1000, 0).iloc[:800], min_trades=counts[-1])
    assert only_one["statistics"]["pbo"] is None and "at least 2 rules" in only_one["statistics"]["pbo_unavailable"]


def test_reports_are_deterministic_and_the_seed_ignores_costs_and_settings():
    frame = random_walk_frame(800, 2)
    first = judge(frame, min_trades=10)
    second = judge(frame, min_trades=10)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    other_settings = judge(frame, min_trades=15, costs=Costs(25, 3, 0.2))
    assert other_settings["settings"]["bootstrap"]["seed"] == first["settings"]["bootstrap"]["seed"]
    assert bootstrap_seed("x.csv", FINGERPRINT) == int(hashlib.sha256(("x.csv" + FINGERPRINT).encode()).hexdigest()[:8], 16)
    assert bootstrap_seed("y.csv", FINGERPRINT) != bootstrap_seed("x.csv", FINGERPRINT)
    assert bootstrap_seed("x.csv", "cd" * 32) != bootstrap_seed("x.csv", FINGERPRINT)


def test_uncertainty_block_and_integrity_numbers():
    frame = random_walk_frame(800, 2)
    report = judge(frame, holdout_bars=200)
    uncertainty = report["uncertainty"]
    assert uncertainty["sharpe_se_annualised_iid"] == pytest.approx(math.sqrt(8760 / 800))
    assert uncertainty["holdout_sharpe_se_annualised_iid"] == pytest.approx(math.sqrt(8760 / 200))
    assert uncertainty["research_bars"] == 800 and uncertainty["holdout_bars"] == 200
    gaps = report["integrity"]["close_to_open_gap_bps"]
    assert 0 <= gaps["mean_abs"] <= gaps["p99_abs"] <= gaps["max_abs"]
    assert report["integrity"]["research_fingerprint"] == FINGERPRINT[:16]


# --- both non-insufficient outcomes are reachable ---------------------------------------------------


@pytest.fixture(scope="module")
def trending():
    frame = regime_frame(8000)
    return frame, judge(frame)


def test_a_pure_random_walk_is_indistinguishable_from_luck():
    # Fixed seed: a driftless walk still yields a false CANDIDATE in about 5% of random draws at the family
    # level (that is what alpha = 0.05 means), so the seed is pinned to keep the suite deterministic.
    report = judge(random_walk_frame(8000, 1))
    passed = [rule for rule in report["rules"] if rule["status"] == PASSED_GATE]
    reality = report["statistics"]["reality_check"]
    print("random walk:", report["verdict"]["label"], len(passed), "rules passed the gate, RC p =", reality["p_value"])
    assert report["verdict"]["label"] == INDISTINGUISHABLE
    assert passed and not reality["rejected"]
    assert not any(rule["evidence"]["candidate"] for rule in passed)


def test_a_trending_series_yields_a_candidate_that_passes_all_three_checks(trending):
    _, report = trending
    winners = [rule for rule in report["rules"] if rule["evidence"] and rule["evidence"]["candidate"]]
    best = max(winners, key=lambda rule: rule["evidence"]["dsr"])
    print("trending:", report["verdict"]["label"], [rule["id"] for rule in winners], best["evidence"]["adjusted_p"], best["evidence"]["dsr"])
    assert report["verdict"]["label"] == CANDIDATE
    assert winners and all(all(rule["evidence"]["checks"].values()) for rule in winners)
    assert report["statistics"]["reality_check"]["rejected"] is True
    assert best["evidence"]["adjusted_p"] < 0.05 and best["evidence"]["dsr"] >= 0.95
    assert best["evidence"]["break_even"]["multiple"] > 1.5
    assert report["verdict"]["reasons"][0].startswith("Candidate rules:")


def test_high_costs_flip_the_same_series_to_not_a_candidate(trending):
    frame, _ = trending
    report = judge(frame, costs=Costs(fee_bps_per_side=200))
    print("fee 200 bps:", report["verdict"]["label"], {rule["id"]: rule["evidence"]["checks"] for rule in report["rules"] if rule["evidence"]})
    assert report["verdict"]["label"] == INDISTINGUISHABLE
    assert not any(rule["evidence"]["candidate"] for rule in report["rules"] if rule["evidence"])


def test_the_cost_stress_alone_can_flip_a_rule_that_passes_bootstrap_and_dsr():
    frame = regime_frame(20000)
    rule = GRID[1]
    base = judge(frame, strategies=[rule])
    evidence = base["rules"][0]["evidence"]
    assert base["verdict"]["label"] == CANDIDATE
    # Pick the per-side fee that puts the 1x round trip at 70% of break-even, so 1.5x costs exceed it.
    fee = 10 + (0.7 * evidence["break_even"]["round_trip_bps"] - evidence["break_even"]["base_round_trip_bps"]) / 2
    stressed = judge(frame, strategies=[rule], costs=Costs(fee_bps_per_side=fee))
    flipped = stressed["rules"][0]["evidence"]
    means = [item["mean_trade_return_pct"] for item in flipped["stress"]]
    print("stress flip: fee", round(fee, 1), "checks", flipped["checks"], "mean trade % at 1x/1.5x/2x", [round(m, 3) for m in means])
    assert flipped["checks"] == {"bootstrap": True, "dsr": True, "stress": False}
    assert means[0] > 0 > means[1] > means[2]
    assert stressed["verdict"]["label"] == INDISTINGUISHABLE
    assert "1.5x cost stress" in stressed["verdict"]["reasons"][0]
