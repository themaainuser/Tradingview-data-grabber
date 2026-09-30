import math
import pathlib
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import tradingview_data.charts as charts  # noqa: E402
from tradingview_data.charts import (  # noqa: E402
    MAX_SERIES_POINTS,
    activity_heatmap,
    bar_interval,
    chart_drawdown,
    chart_payload,
    chart_return_distribution,
    chart_seasonality,
    correlation_matrix,
    drawdown_series,
    return_distribution,
    rolling_volatility,
    seasonality,
    volume_profile,
)

KOLKATA = "Asia/Kolkata"


def make_frame(closes, freq="5min", start="2024-01-01 00:00", volume=None, seed=0):
    """OHLCV frame with a Kolkata-normalised index, like ``load_ohlcv`` returns; ``start`` is UTC."""

    rng = np.random.default_rng(seed)
    close = np.asarray(closes, dtype=float)
    open_ = np.concatenate(([close[0]], close[:-1]))
    high = np.maximum(open_, close) * (1 + rng.uniform(0, 0.001, len(close)))
    low = np.minimum(open_, close) * (1 - rng.uniform(0, 0.001, len(close)))
    if volume is None:
        volume = rng.integers(1, 1_000, len(close)).astype(float)
    index = pd.date_range(start, periods=len(close), freq=freq, tz="UTC").tz_convert(KOLKATA)
    index.name = "time"
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume}, index=index
    )


def random_walk(rows, seed=0, sigma=0.002):
    rng = np.random.default_rng(seed)
    return 100 * np.exp(np.cumsum(rng.normal(0, sigma, rows)))


def closes_from_returns(returns_pct, first=100.0):
    return first * np.concatenate(([1.0], np.cumprod(1 + np.asarray(returns_pct) / 100)))


def epoch(frame, position):
    return int(frame.index[position].timestamp())


def phi(value, mean, std):
    return 0.5 * (1 + math.erf((value - mean) / (std * math.sqrt(2))))


# --- bar interval ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("freq", "seconds", "intraday"),
    [("1min", 60, True), ("1h", 3_600, True), ("23h", 82_800, True), ("D", 86_400, False), ("W", 604_800, False)],
)
def test_bar_interval_is_the_median_spacing(freq, seconds, intraday):
    frame = make_frame(random_walk(60), freq=freq)
    assert bar_interval(frame) == (seconds, intraday)


def test_bar_interval_ignores_a_few_gaps_and_needs_two_bars():
    frame = make_frame(random_walk(60), freq="1min")
    gappy = frame.drop(frame.index[10:20])
    assert bar_interval(gappy) == (60, True)
    assert bar_interval(frame.iloc[:1]) == (None, False)
    assert bar_interval(frame.iloc[:2]) == (60, True)


# --- return distribution ----------------------------------------------------------------------------


def test_return_distribution_needs_thirty_returns():
    assert return_distribution(make_frame(random_walk(30))) is None
    assert return_distribution(make_frame(random_walk(31))) is not None
    assert return_distribution(make_frame(random_walk(1))) is None


def test_return_distribution_shape_and_accounting():
    frame = make_frame(random_walk(5_000, seed=3))
    result = return_distribution(frame, bins=41)
    returns = frame["close"].pct_change().dropna().to_numpy() * 100
    edges = np.array(result["edges"])

    assert len(result["edges"]) == 42 and len(result["counts"]) == 41 and len(result["normal"]) == 41
    assert np.all(np.diff(edges) > 0)
    assert edges[0] == pytest.approx(np.percentile(returns, 0.5))
    assert edges[-1] == pytest.approx(np.percentile(returns, 99.5))
    assert np.allclose(np.diff(edges), np.diff(edges)[0])
    outliers = result["outliers"]
    assert outliers["below"] == int((returns < edges[0]).sum())
    assert outliers["above"] == int((returns > edges[-1]).sum())
    assert sum(result["counts"]) + outliers["below"] + outliers["above"] == len(returns)
    assert outliers["below"] + outliers["above"] == pytest.approx(0.01 * len(returns), abs=0.005 * len(returns))


def test_return_distribution_normal_overlay_uses_the_fitted_normal():
    frame = make_frame(random_walk(5_000, seed=4))
    result = return_distribution(frame, bins=25)
    returns = frame["close"].pct_change().dropna().to_numpy() * 100
    mean, std, n = returns.mean(), returns.std(ddof=1), len(returns)
    edges = result["edges"]
    expected = [n * (phi(hi, mean, std) - phi(lo, mean, std)) for lo, hi in zip(edges[:-1], edges[1:])]
    assert result["normal"] == pytest.approx(expected)
    # Gaussian returns: the 0.5-99.5 span holds about 99% of the fitted mass and the fit tracks the counts.
    assert sum(result["normal"]) == pytest.approx(0.99 * n, rel=0.01)
    assert max(abs(c - e) for c, e in zip(result["counts"], result["normal"])) < 0.25 * max(result["normal"])


def test_return_distribution_stats_match_pandas_and_numpy():
    frame = make_frame(random_walk(2_000, seed=5))
    stats = return_distribution(frame)["stats"]
    returns = (frame["close"].pct_change().dropna() * 100).reset_index(drop=True)
    var = np.percentile(returns, 5)

    assert set(stats) == {
        "count", "mean_pct", "std_pct", "skew", "excess_kurtosis", "min_pct", "max_pct", "positive_pct",
        "var_95_pct", "cvar_95_pct",
    }
    assert stats["count"] == len(returns) == 1_999
    assert stats["mean_pct"] == pytest.approx(returns.mean())
    assert stats["std_pct"] == pytest.approx(returns.std(ddof=1))
    assert stats["skew"] == pytest.approx(returns.skew())
    assert stats["excess_kurtosis"] == pytest.approx(returns.kurt())
    assert (stats["min_pct"], stats["max_pct"]) == (returns.min(), returns.max())
    assert stats["positive_pct"] == pytest.approx((returns > 0).mean() * 100)
    assert stats["var_95_pct"] == pytest.approx(var) and stats["var_95_pct"] < 0
    assert stats["cvar_95_pct"] == pytest.approx(returns[returns <= var].mean())
    assert stats["cvar_95_pct"] <= stats["var_95_pct"]


def test_return_distribution_from_known_returns():
    known = [-2 + 0.1 * step for step in range(20)] + [0.1 + 0.1 * step for step in range(20)]
    frame = make_frame(closes_from_returns(known))
    result = return_distribution(frame, bins=10)
    stats = result["stats"]

    assert stats["count"] == 40
    assert stats["positive_pct"] == 50.0
    assert stats["mean_pct"] == pytest.approx(np.mean(known))
    assert (stats["min_pct"], stats["max_pct"]) == pytest.approx((-2.0, 2.0))
    assert stats["var_95_pct"] == pytest.approx(np.percentile(known, 5))
    assert stats["cvar_95_pct"] == pytest.approx(np.mean([v for v in known if v <= np.percentile(known, 5)]))
    assert sum(result["counts"]) + sum(result["outliers"].values()) == 40


def test_return_distribution_with_constant_prices_has_non_degenerate_bins():
    frame = make_frame([100.0] * 40)
    result = return_distribution(frame, bins=11)
    edges = np.array(result["edges"])

    assert np.all(np.diff(edges) > 0) and edges[0] < 0 < edges[-1]
    assert sum(result["counts"]) == 39 and max(result["counts"]) == 39
    assert result["counts"].index(39) == result["normal"].index(max(result["normal"]))
    assert sum(result["normal"]) == pytest.approx(39)
    assert result["outliers"] == {"below": 0, "above": 0}
    stats = result["stats"]
    assert (stats["std_pct"], stats["mean_pct"], stats["var_95_pct"], stats["cvar_95_pct"]) == (0, 0, 0, 0)
    assert stats["positive_pct"] == 0


def test_return_distribution_rejects_zero_bins():
    with pytest.raises(ValueError, match="bins"):
        return_distribution(make_frame(random_walk(60)), bins=0)


# --- drawdown -------------------------------------------------------------------------------------


def test_drawdown_needs_two_bars():
    assert drawdown_series(make_frame([100.0])) is None
    assert drawdown_series(make_frame([100.0, 99.0])) is not None


def test_drawdown_of_a_recovered_path():
    closes = [100, 110, 99, 105, 120, 90, 100, 95, 125]
    frame = make_frame(closes)
    result = drawdown_series(frame)

    expected = [0, 0, -10, (105 / 110 - 1) * 100, 0, -25, (100 / 120 - 1) * 100, (95 / 120 - 1) * 100, 0]
    assert result["drawdown_pct"] == pytest.approx(expected)
    assert result["time"] == [epoch(frame, position) for position in range(9)]
    assert result["max_drawdown_pct"] == pytest.approx(-25)
    assert result["peak_time"] == epoch(frame, 4)
    assert result["trough_time"] == epoch(frame, 5)
    assert result["recovered_time"] == epoch(frame, 8)
    assert result["current_drawdown_pct"] == 0
    assert result["longest_underwater_bars"] == 3


def test_drawdown_without_recovery_reports_the_open_drawdown():
    frame = make_frame([100, 120, 90, 100])
    result = drawdown_series(frame)
    assert result["recovered_time"] is None
    assert result["peak_time"] == epoch(frame, 1) and result["trough_time"] == epoch(frame, 2)
    assert result["current_drawdown_pct"] == pytest.approx((100 / 120 - 1) * 100)
    assert result["longest_underwater_bars"] == 2
    assert all(value <= 0 for value in result["drawdown_pct"])


def test_drawdown_peak_is_the_last_bar_at_the_peak_price():
    frame = make_frame([100, 100, 90])
    assert drawdown_series(frame)["peak_time"] == epoch(frame, 1)


@pytest.mark.parametrize("closes", [[100, 101, 102, 103], [100.0] * 5])
def test_drawdown_of_a_path_that_never_falls(closes):
    frame = make_frame(closes)
    result = drawdown_series(frame)
    assert result["drawdown_pct"] == [0] * len(closes)
    assert result["max_drawdown_pct"] == 0 and result["current_drawdown_pct"] == 0
    assert result["peak_time"] == result["trough_time"] == epoch(frame, 0)
    assert result["recovered_time"] is None
    assert result["longest_underwater_bars"] == 0


def test_drawdown_decimation_keeps_troughs_and_both_ends():
    closes = random_walk(10_000, seed=8)
    closes[6_001] *= 0.6
    frame = make_frame(closes, freq="1min")
    result = drawdown_series(frame)
    full = (closes / np.maximum.accumulate(closes) - 1) * 100

    assert len(result["time"]) == len(result["drawdown_pct"]) <= MAX_SERIES_POINTS
    assert result["time"][0] == epoch(frame, 0) and result["time"][-1] == epoch(frame, 9_999)
    assert result["time"] == sorted(set(result["time"]))
    assert min(result["drawdown_pct"]) == pytest.approx(full.min()) == pytest.approx(result["max_drawdown_pct"])
    assert result["trough_time"] == epoch(frame, int(full.argmin()))
    assert result["current_drawdown_pct"] == pytest.approx(full[-1])
    positions = np.searchsorted(frame.index.as_unit("s").asi8, result["time"])
    assert result["drawdown_pct"] == pytest.approx(full[positions].tolist())


def test_drawdown_longest_underwater_spans_the_whole_series_when_never_recovered():
    frame = make_frame([100, 90, 91, 92, 93])
    assert drawdown_series(frame)["longest_underwater_bars"] == 4


# --- rolling volatility -----------------------------------------------------------------------------


def test_rolling_volatility_needs_more_than_window_returns():
    assert rolling_volatility(make_frame(random_walk(31)), window=30) is None
    assert rolling_volatility(make_frame(random_walk(32)), window=30) is not None
    with pytest.raises(ValueError, match="window"):
        rolling_volatility(make_frame(random_walk(60)), window=1)


def test_rolling_volatility_matches_pandas_with_warm_up_none():
    closes = random_walk(200, seed=9)
    frame = make_frame(closes)
    result = rolling_volatility(frame, window=20)
    reference = pd.Series(closes).pct_change().mul(100).rolling(20).std(ddof=1)

    assert result["window"] == 20
    assert result["time"] == [epoch(frame, position) for position in range(200)]
    assert result["value_pct"][:20] == [None] * 20
    assert result["value_pct"][20:] == pytest.approx(reference.iloc[20:].tolist())


def test_rolling_volatility_of_constant_prices_is_zero():
    result = rolling_volatility(make_frame([100.0] * 40), window=10)
    assert result["value_pct"][:10] == [None] * 10
    assert result["value_pct"][10:] == pytest.approx([0.0] * 30, abs=1e-12)


def test_rolling_volatility_decimation_keeps_last_value_of_each_bucket():
    closes = random_walk(10_000, seed=10)
    frame = make_frame(closes, freq="1min")
    result = rolling_volatility(frame, window=30)
    reference = pd.Series(closes).pct_change().mul(100).rolling(30).std(ddof=1).to_numpy()
    positions = np.searchsorted(frame.index.as_unit("s").asi8, result["time"])

    assert len(result["time"]) <= MAX_SERIES_POINTS
    assert positions[0] == 0 and positions[-1] == 9_999
    assert np.all(np.diff(positions) > 0) and np.diff(positions).max() <= 8
    assert result["value_pct"][0] is None
    kept = np.array([np.nan if value is None else value for value in result["value_pct"]])
    assert np.allclose(kept, reference[positions], equal_nan=True)


# --- activity heat map ------------------------------------------------------------------------------


def test_activity_needs_intraday_bars_and_enough_of_them():
    assert activity_heatmap(make_frame(random_walk(100), freq="D")) is None
    assert activity_heatmap(make_frame(random_walk(100), freq="W")) is None
    assert activity_heatmap(make_frame(random_walk(47), freq="1min")) is None
    assert activity_heatmap(make_frame(random_walk(1), freq="1min")) is None
    assert activity_heatmap(make_frame(random_walk(48), freq="1min")) is not None


def test_activity_uses_utc_hours_and_weekdays_not_the_capture_timezone():
    # One bar per UTC hour of a Monday-to-Sunday week: 00:00 UTC is 05:30 in Kolkata, so any
    # reliance on the normalised index would shift cells by 5 hours and, late in the day, by a weekday.
    volume = [100 * weekday + hour for weekday in range(7) for hour in range(24)]
    frame = make_frame(random_walk(168), freq="1h", start="2024-01-01 00:00", volume=np.array(volume, dtype=float))
    assert frame.index[0].hour == 5

    result = activity_heatmap(frame)

    assert result["hours"] == list(range(24)) and result["weekdays"] == list(range(7))
    assert result["metrics"]["volume"] == [[100.0 * w + h for h in range(24)] for w in range(7)]
    assert result["counts"] == [[1] * 24 for _ in range(7)]
    for metric in result["metrics"].values():
        assert len(metric) == 7 and all(len(row) == 24 for row in metric)


def test_activity_cell_means_and_empty_cells():
    closes = random_walk(60, seed=12)
    frame = make_frame(closes, freq="1min", start="2024-01-01 10:00")
    result = activity_heatmap(frame)
    range_pct = ((frame["high"] - frame["low"]) / frame["open"] * 100).mean()
    returns = pd.Series(closes).pct_change().dropna().mul(100)

    assert result["counts"][0][10] == 60 and sum(map(sum, result["counts"])) == 60
    assert result["metrics"]["volume"][0][10] == pytest.approx(frame["volume"].mean())
    assert result["metrics"]["range_pct"][0][10] == pytest.approx(range_pct)
    assert result["metrics"]["return_pct"][0][10] == pytest.approx(returns.mean())
    for metric in result["metrics"].values():
        assert [cell for row in metric for cell in row if cell is not None] == [metric[0][10]]


def test_activity_handles_zero_volume_and_flat_prices():
    frame = make_frame([100.0] * 60, freq="1min", volume=np.zeros(60))
    result = activity_heatmap(frame)
    weekday, hour = frame.index[0].tz_convert("UTC").dayofweek, frame.index[0].tz_convert("UTC").hour
    assert result["metrics"]["volume"][weekday][hour] == 0
    assert result["metrics"]["return_pct"][weekday][hour] == 0


# --- seasonality ----------------------------------------------------------------------------------------


def test_seasonality_blocks_follow_their_data_requirements():
    assert seasonality(make_frame(random_walk(30), freq="D")) == {"by_weekday": None, "by_hour": None}
    daily = seasonality(make_frame(random_walk(31), freq="D"))
    assert daily["by_weekday"] is not None and daily["by_hour"] is None
    short_intraday = seasonality(make_frame(random_walk(48), freq="1h"))
    assert short_intraday["by_weekday"] is not None and short_intraday["by_hour"] is None
    assert seasonality(make_frame(random_walk(49), freq="1h"))["by_hour"] is not None
    assert seasonality(make_frame(random_walk(1), freq="1h")) == {"by_weekday": None, "by_hour": None}


def test_seasonality_weekday_uses_utc_and_the_bars_own_return():
    # Bars open at 22:00 UTC, which is already the next day in Kolkata.
    bars = 70
    returns = [1.0 if day % 7 == 2 else -0.1 for day in range(1, bars)]
    frame = make_frame(closes_from_returns(returns), freq="D", start="2024-01-01 22:00")
    block = seasonality(frame)["by_weekday"]

    assert block["labels"] == ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    assert block["hit_rate_pct"] == [0, 0, 100, 0, 0, 0, 0]
    assert block["mean_return_pct"][2] == pytest.approx(1.0)
    assert block["mean_return_pct"][3] == pytest.approx(-0.1)
    assert sum(block["count"]) == bars - 1 and block["count"][0] == 9


def test_seasonality_hour_uses_utc():
    bars = 24 * 10
    returns = [1.0 if step % 24 == 3 else -0.1 for step in range(1, bars)]
    frame = make_frame(closes_from_returns(returns), freq="1h", start="2024-01-01 00:00")
    block = seasonality(frame)["by_hour"]

    assert block["labels"] == [f"{hour:02d}" for hour in range(24)]
    assert [hour for hour, rate in enumerate(block["hit_rate_pct"]) if rate == 100] == [3]
    assert block["mean_return_pct"][3] == pytest.approx(1.0)
    assert block["count"][0] == 9 and block["count"][3] == 10 and sum(block["count"]) == bars - 1


def test_seasonality_matches_a_groupby_reference():
    closes = random_walk(500, seed=13)
    frame = make_frame(closes, freq="1h", start="2024-02-03 07:00")
    result = seasonality(frame)
    returns = pd.Series(closes, index=frame.index.tz_convert("UTC")).pct_change().dropna() * 100

    by_hour = returns.groupby(returns.index.hour)
    assert result["by_hour"]["mean_return_pct"] == pytest.approx(by_hour.mean().tolist())
    assert result["by_hour"]["hit_rate_pct"] == pytest.approx(by_hour.apply(lambda group: (group > 0).mean() * 100).tolist())
    assert result["by_hour"]["count"] == by_hour.size().tolist()
    by_day = returns.groupby(returns.index.dayofweek)
    assert result["by_weekday"]["mean_return_pct"] == pytest.approx(by_day.mean().tolist())


def test_seasonality_leaves_unobserved_buckets_empty():
    frame = make_frame(random_walk(60), freq="1min", start="2024-01-01 10:00")
    block = seasonality(frame)["by_hour"]
    assert block["count"][10] == 59 and sum(block["count"]) == 59
    assert block["mean_return_pct"][10] is not None
    assert [value for value in block["mean_return_pct"] if value is None] == [None] * 23
    assert [value for value in block["hit_rate_pct"] if value is None] == [None] * 23


# --- correlation ----------------------------------------------------------------------------------------


def test_correlation_matrix_of_identical_and_inverse_series():
    closes = random_walk(200, seed=14)
    first = make_frame(closes, freq="1min")
    inverse = make_frame(100 * 100 / closes, freq="1min")
    result = correlation_matrix([("A", first), ("B", first.copy()), ("C", inverse)])
    matrix = np.array(result["matrix"])

    assert result["labels"] == ["A", "B", "C"]
    assert result["observations"] == 199
    assert np.allclose(np.diag(matrix), 1) and np.allclose(matrix, matrix.T)
    assert matrix[0, 1] == pytest.approx(1.0)
    assert matrix[0, 2] < -0.99
    assert result["start"] == epoch(first, 1) and result["end"] == epoch(first, 199)


def test_correlation_matrix_uses_only_shared_timestamps():
    first = make_frame(random_walk(100, seed=15), freq="1min", start="2024-01-01 00:00")
    second = make_frame(random_walk(100, seed=16), freq="1min", start="2024-01-01 00:50")
    result = correlation_matrix([("A", first), ("B", second)])

    assert result["observations"] == 49
    assert result["start"] == epoch(second, 1) and result["end"] == epoch(first, 99)


def test_correlation_matrix_matches_the_pandas_reference():
    first, second = (make_frame(random_walk(300, seed=seed), freq="1h") for seed in (17, 18))
    expected = pd.concat([first["close"], second["close"]], axis=1).pct_change().dropna().corr().to_numpy()
    result = correlation_matrix([("A", first), ("B", second)])
    assert np.array(result["matrix"]) == pytest.approx(expected)


def test_correlation_matrix_needs_three_overlapping_returns():
    frame = make_frame(random_walk(50, seed=19), freq="1min")
    assert correlation_matrix([("A", frame.iloc[:3]), ("B", frame.iloc[:3])]) is None
    assert correlation_matrix([("A", frame.iloc[:4]), ("B", frame.iloc[:4])])["observations"] == 3
    later = make_frame(random_walk(50, seed=20), freq="1min", start="2024-06-01 00:00")
    assert correlation_matrix([("A", frame), ("B", later)]) is None
    assert correlation_matrix([]) is None


def test_correlation_of_a_constant_series_is_nan_not_an_error():
    varying = make_frame(random_walk(40, seed=21), freq="1min")
    flat = make_frame([100.0] * 40, freq="1min")
    matrix = np.array(correlation_matrix([("A", varying), ("B", flat)])["matrix"])
    assert np.isnan(matrix[0, 1]) and matrix[0, 0] == pytest.approx(1)


# --- volume profile ---------------------------------------------------------------------------------


def reference_volume_profile(data, bins=60, value_area=0.7):
    """The original per-bar implementation, kept to prove the vectorised one returns the same numbers."""

    low, high = charts._price_bounds(data)
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
        overlaps = np.maximum(0, np.minimum(candle_high, edges[1:]) - np.maximum(candle_low, edges[:-1]))
        profile += volume * overlaps / span
    poc_index = int(np.argmax(profile))
    selected = {poc_index}
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


def assert_same_profile(data, **kwargs):
    actual = volume_profile(data, **kwargs)
    expected = reference_volume_profile(data, **kwargs)
    assert np.array_equal(actual["edges"], expected["edges"])
    assert np.array_equal(actual["mids"], expected["mids"])
    np.testing.assert_allclose(actual["profile"], expected["profile"], rtol=1e-12, atol=0)
    for key in ("poc", "value_low", "value_high"):
        assert actual[key] == expected[key]


@pytest.mark.parametrize(("bins", "value_area"), [(2, 0.5), (60, 0.7), (200, 0.95)])
def test_vectorised_volume_profile_matches_the_reference_implementation(bins, value_area):
    rng = np.random.default_rng(22)
    frame = make_frame(random_walk(3_000, seed=22, sigma=0.004), freq="1min")
    flat = rng.random(len(frame)) < 0.1
    frame.loc[flat, "high"] = frame.loc[flat, "low"] = frame.loc[flat, "close"]
    frame.loc[rng.random(len(frame)) < 0.1, "volume"] = 0.0
    assert_same_profile(frame, bins=bins, value_area=value_area)


def test_volume_profile_is_chunk_size_independent(monkeypatch):
    frame = make_frame(random_walk(1_000, seed=23, sigma=0.004), freq="1min")
    expected = volume_profile(frame)["profile"]
    monkeypatch.setattr(charts, "PROFILE_CHUNK_ELEMENTS", 250)
    np.testing.assert_allclose(volume_profile(frame)["profile"], expected, rtol=1e-12, atol=0)
    assert_same_profile(frame)


def flat_bars(frame):
    return frame.assign(open=frame["close"], high=frame["close"], low=frame["close"])


@pytest.mark.parametrize(
    "frame",
    [
        flat_bars(make_frame([100.0])),
        flat_bars(make_frame([100.0] * 5)),
        make_frame(random_walk(20, seed=24), volume=np.zeros(20)),
    ],
    ids=["single-bar", "constant-price", "zero-volume"],
)
def test_volume_profile_edge_cases_match_the_reference(frame):
    assert_same_profile(frame)


def test_volume_profile_conserves_total_volume():
    frame = make_frame(random_walk(2_000, seed=25), freq="1min")
    assert volume_profile(frame)["profile"].sum() == pytest.approx(frame["volume"].sum())


# --- payload bundle ---------------------------------------------------------------------------------------


def test_payload_for_intraday_data_has_every_section():
    frame = make_frame(random_walk(400, seed=26), freq="15min")
    payload = chart_payload(frame, bins=20, value_area=0.6, window=10, return_bins=15)

    assert payload["bars"] == 400 and payload["interval_seconds"] == 900 and payload["intraday"] is True
    assert payload["unavailable"] == {}
    profile = payload["volume_profile"]
    assert len(profile["edges"]) == 21 and len(profile["volume"]) == 20
    assert profile["edges"][0] <= profile["value_low"] <= profile["poc"] <= profile["value_high"] <= profile["edges"][-1]
    assert profile["total_volume"] == pytest.approx(frame["volume"].sum())
    assert len(payload["return_distribution"]["counts"]) == 15
    assert payload["rolling_volatility"]["window"] == 10
    assert payload["activity"] is not None and payload["drawdown"] is not None
    assert payload["seasonality"]["by_weekday"] is not None and payload["seasonality"]["by_hour"] is not None


def test_payload_explains_every_missing_section_for_daily_data():
    payload = chart_payload(make_frame(random_walk(20, seed=27), freq="D"))

    assert payload["intraday"] is False and payload["interval_seconds"] == 86_400
    assert payload["unavailable"] == {
        "return_distribution": "needs at least 30 bar returns; this dataset has 19",
        "rolling_volatility": "needs more than 30 bar returns; this dataset has 19",
        "activity": "needs intraday bars; the median bar spacing is 86400 s",
        "seasonality.by_weekday": "needs at least 30 bar returns; this dataset has 19",
        "seasonality.by_hour": "needs intraday bars; the median bar spacing is 86400 s",
    }
    assert payload["return_distribution"] is None and payload["activity"] is None
    assert payload["seasonality"] == {"by_weekday": None, "by_hour": None}
    assert payload["drawdown"] is not None


def test_payload_for_a_single_bar_only_keeps_the_volume_profile():
    frame = make_frame([100.0], volume=np.array([5.0]))
    payload = chart_payload(frame)

    assert payload["bars"] == 1 and payload["interval_seconds"] is None and payload["intraday"] is False
    assert payload["volume_profile"]["total_volume"] == 5.0
    assert set(payload["unavailable"]) == {
        "return_distribution", "drawdown", "rolling_volatility", "activity", "seasonality.by_weekday", "seasonality.by_hour",
    }
    assert payload["unavailable"]["drawdown"] == "needs at least 2 bars; this dataset has 1"
    assert payload["unavailable"]["activity"] == "needs at least 48 bars; this dataset has 1"
    assert payload["unavailable"]["seasonality.by_hour"] == "needs at least 48 bar returns; this dataset has 0"


def test_payload_blames_the_bar_count_for_short_intraday_data():
    payload = chart_payload(make_frame(random_walk(40, seed=28), freq="1min"))
    assert payload["unavailable"]["activity"] == "needs at least 48 bars; this dataset has 40"
    assert payload["unavailable"]["seasonality.by_hour"] == "needs at least 48 bar returns; this dataset has 39"
    assert "return_distribution" not in payload["unavailable"]


# --- PNG renderers skip what cannot be computed -----------------------------------------------------------


def test_png_charts_return_none_when_their_data_is_unavailable(tmp_path):
    frame = make_frame([100.0], volume=np.array([5.0]))
    assert chart_return_distribution(frame, tmp_path) is None
    assert chart_drawdown(frame, tmp_path) is None
    assert chart_seasonality(frame, tmp_path) is None
    assert list(tmp_path.iterdir()) == []


def test_png_charts_render_for_flat_and_trending_prices(tmp_path):
    for name, closes in (("flat", [100.0] * 60), ("rising", list(np.linspace(100, 160, 60)))):
        frame = make_frame(closes, freq="1min")
        for chart in (chart_return_distribution, chart_drawdown, chart_seasonality):
            path = chart(frame, tmp_path / name)
            assert path is not None and path.read_bytes().startswith(b"\x89PNG")
