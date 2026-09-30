import base64
import csv
import json
import math
import pathlib
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import tradingview_data.api as api  # noqa: E402
from tradingview_data.analytics import load_ohlcv  # noqa: E402
from tradingview_data.api import create_app  # noqa: E402
from tradingview_data.storage import CSV_COLUMNS, CSV_TIME_FORMAT  # noqa: E402

IST = ZoneInfo("Asia/Kolkata")
FIRST_BAR = datetime(2024, 1, 1, 9, 15, tzinfo=IST)
INTRADAY = "BINANCE_BTCUSDT/5.csv"
DAILY = "BINANCE_BTCUSDT/1D.csv"
ETH = "BINANCE_ETHUSDT/5.csv"
SECTIONS = {
    "id", "symbol", "timeframe", "bars", "interval_seconds", "intraday", "volume_profile", "return_distribution",
    "drawdown", "rolling_volatility", "activity", "seasonality", "unavailable",
}


def encode_id(relative: str) -> str:
    return base64.urlsafe_b64encode(relative.encode()).rstrip(b"=").decode()


def write_capture(path, rows=600, step=timedelta(minutes=5), start=FIRST_BAR, seed=0, flat=False):
    """Write a seeded random-walk capture in the CSV format produced by ``CsvBarStore``."""

    rng = np.random.default_rng(seed)
    close = np.full(rows, 100.0) if flat else 100 * np.exp(np.cumsum(rng.normal(0, 0.003, rows)))
    open_ = np.concatenate(([close[0]], close[:-1]))
    high = np.maximum(open_, close) * (1 + rng.uniform(0, 0.002, rows))
    low = np.minimum(open_, close) * (1 - rng.uniform(0, 0.002, rows))
    volume = rng.integers(10, 1_000, rows).astype(float)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_COLUMNS)
        for index in range(rows):
            stamp = (start + index * step).strftime(CSV_TIME_FORMAT)
            writer.writerow([f"[{index}]", stamp, open_[index], high[index], low[index], close[index], volume[index]])


def strict_json(response) -> object:
    def reject(token: str) -> None:
        raise AssertionError(f"response contains non-finite JSON constant {token}")

    return json.loads(response.text, parse_constant=reject)


@pytest.fixture
def data_dir(tmp_path):
    directory = tmp_path / "data"
    directory.mkdir()
    return directory


@pytest.fixture
def client(data_dir):
    return TestClient(create_app(data_dir))


def chart_url(relative: str) -> str:
    return f"/api/datasets/{encode_id(relative)}/charts"


# --- /api/datasets/{id}/charts ---------------------------------------------------------------------


def test_intraday_dataset_returns_every_section(data_dir, client):
    write_capture(data_dir / INTRADAY, rows=600)

    response = client.get(chart_url(INTRADAY))

    assert response.status_code == 200
    body = strict_json(response)
    assert set(body) == SECTIONS
    assert (body["id"], body["symbol"], body["timeframe"]) == (encode_id(INTRADAY), "BINANCE_BTCUSDT", "5")
    assert (body["bars"], body["interval_seconds"], body["intraday"]) == (600, 300, True)
    assert body["unavailable"] == {}

    profile = body["volume_profile"]
    assert set(profile) == {"edges", "volume", "poc", "value_low", "value_high", "total_volume"}
    assert len(profile["edges"]) == 61 and len(profile["volume"]) == 60
    assert profile["edges"] == sorted(profile["edges"])
    assert profile["edges"][0] <= profile["value_low"] <= profile["poc"] <= profile["value_high"] <= profile["edges"][-1]
    assert profile["total_volume"] == pytest.approx(sum(profile["volume"]))

    distribution = body["return_distribution"]
    assert set(distribution) == {"edges", "counts", "normal", "outliers", "stats"}
    assert len(distribution["edges"]) == 42 and len(distribution["counts"]) == 41 and len(distribution["normal"]) == 41
    assert set(distribution["outliers"]) == {"below", "above"}
    assert set(distribution["stats"]) == {
        "count", "mean_pct", "std_pct", "skew", "excess_kurtosis", "min_pct", "max_pct", "positive_pct",
        "var_95_pct", "cvar_95_pct",
    }
    assert distribution["stats"]["count"] == 599

    drawdown = body["drawdown"]
    assert set(drawdown) == {
        "time", "drawdown_pct", "max_drawdown_pct", "peak_time", "trough_time", "recovered_time",
        "current_drawdown_pct", "longest_underwater_bars",
    }
    assert len(drawdown["time"]) == len(drawdown["drawdown_pct"]) == 600
    assert max(drawdown["drawdown_pct"]) <= 0 and min(drawdown["drawdown_pct"]) == drawdown["max_drawdown_pct"]
    assert drawdown["time"][0] == int(FIRST_BAR.timestamp())

    volatility = body["rolling_volatility"]
    assert volatility["window"] == 30 and len(volatility["time"]) == len(volatility["value_pct"]) == 600
    assert volatility["value_pct"][:30] == [None] * 30 and None not in volatility["value_pct"][30:]

    activity = body["activity"]
    assert activity["hours"] == list(range(24)) and activity["weekdays"] == list(range(7))
    assert set(activity["metrics"]) == {"volume", "range_pct", "return_pct"}
    for grid in (*activity["metrics"].values(), activity["counts"]):
        assert len(grid) == 7 and all(len(row) == 24 for row in grid)
    assert sum(map(sum, activity["counts"])) == 600

    assert set(body["seasonality"]) == {"by_weekday", "by_hour"}
    assert len(body["seasonality"]["by_weekday"]["labels"]) == 7 and len(body["seasonality"]["by_hour"]["labels"]) == 24
    assert set(body["seasonality"]["by_hour"]) == {"labels", "mean_return_pct", "hit_rate_pct", "count"}


def test_activity_grid_is_in_utc_not_the_capture_timezone(data_dir, client):
    write_capture(data_dir / INTRADAY, rows=600)
    counts = strict_json(client.get(chart_url(INTRADAY)))["activity"]["counts"]
    # The first bar opens Monday 09:15 IST = 03:45 UTC, so UTC hour 3 holds 03:45, 03:50 and 03:55 only.
    assert counts[0][3] == 3 and counts[0][9] == 12 and counts[0][0] == 0


def test_daily_dataset_explains_why_intraday_sections_are_null(data_dir, client):
    write_capture(data_dir / DAILY, rows=80, step=timedelta(days=1))

    body = strict_json(client.get(chart_url(DAILY)))

    assert (body["timeframe"], body["bars"], body["interval_seconds"], body["intraday"]) == ("1D", 80, 86_400, False)
    assert body["activity"] is None and body["seasonality"]["by_hour"] is None
    assert body["unavailable"] == {
        "activity": "needs intraday bars; the median bar spacing is 86400 s",
        "seasonality.by_hour": "needs intraday bars; the median bar spacing is 86400 s",
    }
    assert body["seasonality"]["by_weekday"]["labels"] == ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    assert body["return_distribution"] is not None and body["rolling_volatility"] is not None
    assert body["drawdown"] is not None


def test_short_dataset_reports_a_reason_for_every_null_section(data_dir, client):
    write_capture(data_dir / "one.csv", rows=1)
    write_capture(data_dir / "short.csv", rows=20, step=timedelta(minutes=1))

    one = strict_json(client.get(chart_url("one.csv")))
    assert (one["bars"], one["interval_seconds"], one["intraday"], one["timeframe"]) == (1, None, False, None)
    assert one["volume_profile"]["total_volume"] > 0
    nulls = {
        "return_distribution": one["return_distribution"],
        "drawdown": one["drawdown"],
        "rolling_volatility": one["rolling_volatility"],
        "activity": one["activity"],
        "seasonality.by_weekday": one["seasonality"]["by_weekday"],
        "seasonality.by_hour": one["seasonality"]["by_hour"],
    }
    assert set(nulls.values()) == {None}
    assert set(one["unavailable"]) == set(nulls)
    assert all(isinstance(reason, str) and reason for reason in one["unavailable"].values())

    short = strict_json(client.get(chart_url("short.csv")))
    assert short["unavailable"]["return_distribution"] == "needs at least 30 bar returns; this dataset has 19"
    assert short["unavailable"]["rolling_volatility"] == "needs more than 30 bar returns; this dataset has 19"
    assert short["unavailable"]["activity"] == "needs at least 48 bars; this dataset has 20"
    assert short["drawdown"] is not None and "drawdown" not in short["unavailable"]


def test_query_parameters_shape_the_sections(data_dir, client):
    write_capture(data_dir / INTRADAY, rows=600)

    body = strict_json(client.get(chart_url(INTRADAY), params={"bins": 10, "value_area": 0.5, "window": 5, "return_bins": 10}))
    assert len(body["volume_profile"]["volume"]) == 10 and len(body["volume_profile"]["edges"]) == 11
    assert body["rolling_volatility"]["window"] == 5
    assert body["rolling_volatility"]["value_pct"][:5] == [None] * 5
    assert len(body["return_distribution"]["counts"]) == 10

    narrow = strict_json(client.get(chart_url(INTRADAY), params={"value_area": 0.5}))["volume_profile"]
    wide = strict_json(client.get(chart_url(INTRADAY), params={"value_area": 0.95}))["volume_profile"]
    assert wide["value_high"] - wide["value_low"] > narrow["value_high"] - narrow["value_low"]


def test_documented_parameter_limits_are_accepted(data_dir, client):
    write_capture(data_dir / INTRADAY, rows=600)
    body = strict_json(client.get(chart_url(INTRADAY), params={"bins": 200, "value_area": 0.95, "window": 500, "return_bins": 101}))
    assert len(body["volume_profile"]["volume"]) == 200
    assert body["rolling_volatility"]["window"] == 500
    assert len(body["return_distribution"]["counts"]) == 101


@pytest.mark.parametrize(
    "params",
    [
        {"bins": 9}, {"bins": 201}, {"bins": "many"}, {"bins": 60.5},
        {"value_area": 0.49}, {"value_area": 0.96}, {"value_area": "nan"}, {"value_area": "inf"}, {"value_area": "wide"},
        {"window": 4}, {"window": 501}, {"window": "x"},
        {"return_bins": 9}, {"return_bins": 102}, {"return_bins": "x"},
    ],
)
def test_parameter_violations_use_the_standard_422_list(data_dir, client, params):
    write_capture(data_dir / INTRADAY, rows=60)
    response = client.get(chart_url(INTRADAY), params=params)
    assert response.status_code == 422
    assert isinstance(strict_json(response)["detail"], list)


def test_chart_errors_for_unknown_and_invalid_datasets(data_dir, client):
    (data_dir / "bad.csv").write_text("a,b\n1,2\n")

    unknown = client.get("/api/datasets/unknownid/charts")
    assert unknown.status_code == 404 and unknown.json() == {"detail": "dataset not found"}

    invalid = client.get(chart_url("bad.csv"))
    assert invalid.status_code == 422
    assert "missing required columns" in invalid.json()["detail"]
    assert str(data_dir) not in invalid.json()["detail"]


def test_chart_ids_never_reach_the_filesystem_outside_the_registry(tmp_path, data_dir, client):
    write_capture(data_dir / INTRADAY, rows=60)
    write_capture(tmp_path / "outside.csv", rows=60)
    hostile = [
        "..", "../outside.csv", "..%2Foutside.csv", "%2e%2e%2foutside.csv", "/etc/passwd",
        encode_id("../outside.csv"), encode_id(str(data_dir / INTRADAY)), encode_id("./" + INTRADAY),
        encode_id("BINANCE_BTCUSDT/../BINANCE_BTCUSDT/5.csv"), encode_id(INTRADAY) + "=",
    ]
    for dataset_id in hostile:
        response = client.get(f"/api/datasets/{dataset_id}/charts")
        assert response.status_code == 404, dataset_id
        correlation = client.get("/api/charts/correlation", params={"ids": [dataset_id, encode_id(INTRADAY)]})
        assert correlation.status_code == 422 and "unknown dataset id" in correlation.json()["detail"], dataset_id
    assert client.get(chart_url(INTRADAY)).status_code == 200


def test_non_finite_values_reach_clients_as_null(data_dir, client, monkeypatch):
    write_capture(data_dir / INTRADAY, rows=60)
    monkeypatch.setattr(
        api,
        "chart_payload",
        lambda *_args, **_kwargs: {"stats": {"skew": float("nan"), "kurt": np.float64("inf")}, "value_pct": [1.0, math.nan]},
    )
    body = strict_json(client.get(chart_url(INTRADAY)))
    assert body["stats"] == {"skew": None, "kurt": None} and body["value_pct"] == [1.0, None]


def test_constant_prices_serialise_without_non_finite_tokens(data_dir, client):
    write_capture(data_dir / "flat.csv", rows=120, step=timedelta(minutes=1), flat=True)
    body = strict_json(client.get(chart_url("flat.csv")))
    assert body["drawdown"]["max_drawdown_pct"] == 0 and body["drawdown"]["recovered_time"] is None
    assert body["return_distribution"]["stats"]["std_pct"] == 0
    assert body["volume_profile"]["total_volume"] > 0


# --- /api/charts/correlation -----------------------------------------------------------------------


def correlation(client, *relatives):
    return client.get("/api/charts/correlation", params={"ids": [encode_id(relative) for relative in relatives]})


def test_correlation_of_three_datasets(data_dir, client):
    write_capture(data_dir / INTRADAY, rows=200, seed=1)
    write_capture(data_dir / ETH, rows=200, seed=2)
    write_capture(data_dir / "flat.csv", rows=200, seed=3)
    (data_dir / "flat.csv.meta.json").write_text(json.dumps({"symbol": "SOL"}))

    response = correlation(client, INTRADAY, ETH, "flat.csv")

    assert response.status_code == 200
    body = strict_json(response)
    assert set(body) == {"labels", "matrix", "observations", "start", "end"}
    assert body["labels"] == ["BINANCE_BTCUSDT-5", "BINANCE_ETHUSDT-5", "SOL"]
    assert body["observations"] == 199
    assert body["start"] == int((FIRST_BAR + timedelta(minutes=5)).timestamp())
    assert body["end"] == int((FIRST_BAR + timedelta(minutes=5 * 199)).timestamp())
    matrix = np.array(body["matrix"])
    assert matrix.shape == (3, 3) and np.allclose(np.diag(matrix), 1) and np.allclose(matrix, matrix.T)
    closes = pd.concat([load_ohlcv(data_dir / name)["close"] for name in (INTRADAY, ETH, "flat.csv")], axis=1)
    assert matrix == pytest.approx(closes.pct_change().dropna().corr().to_numpy())


def test_correlation_with_two_datasets_keeps_request_order(data_dir, client):
    write_capture(data_dir / INTRADAY, rows=50, seed=4)
    write_capture(data_dir / ETH, rows=50, seed=5)
    body = strict_json(correlation(client, ETH, INTRADAY))
    assert body["labels"] == ["BINANCE_ETHUSDT-5", "BINANCE_BTCUSDT-5"]
    assert body["matrix"][0][1] == body["matrix"][1][0]


def test_correlation_labels_stay_unique_when_symbol_and_timeframe_collide(data_dir, client):
    for seed, name in enumerate(("a.csv", "b.csv", "c.csv")):
        write_capture(data_dir / name, rows=50, seed=seed)
        (data_dir / f"{name}.meta.json").write_text(json.dumps({"symbol": "X", "timeframe": "5"}))
    assert strict_json(correlation(client, "a.csv", "b.csv", "c.csv"))["labels"] == ["X-5", "X-5-2", "X-5-3"]


def test_correlation_uses_only_shared_timestamps(data_dir, client):
    write_capture(data_dir / INTRADAY, rows=100, seed=6)
    write_capture(data_dir / ETH, rows=100, seed=7, start=FIRST_BAR + timedelta(minutes=5 * 50))
    body = strict_json(correlation(client, INTRADAY, ETH))
    assert body["observations"] == 49
    assert body["start"] == int((FIRST_BAR + timedelta(minutes=5 * 51)).timestamp())
    assert body["end"] == int((FIRST_BAR + timedelta(minutes=5 * 99)).timestamp())


def test_constant_series_correlate_to_null(data_dir, client):
    write_capture(data_dir / INTRADAY, rows=50, seed=8)
    write_capture(data_dir / "flat.csv", rows=50, flat=True)
    body = strict_json(correlation(client, INTRADAY, "flat.csv"))
    assert body["matrix"][0][1] is None and body["matrix"][1][0] is None and body["matrix"][0][0] == pytest.approx(1)


def test_correlation_rejects_bad_id_lists(data_dir, client):
    write_capture(data_dir / INTRADAY, rows=50)
    write_capture(data_dir / ETH, rows=50, seed=1)
    known = encode_id(INTRADAY)

    def detail(params):
        response = client.get("/api/charts/correlation", params=params)
        assert response.status_code == 422, params
        assert isinstance(response.json()["detail"], str), params
        return response.json()["detail"]

    assert detail({}) == "select between 2 and 20 datasets; got 0"
    assert detail({"ids": [known]}) == "select between 2 and 20 datasets; got 1"
    assert detail({"ids": [f"id{index}" for index in range(21)]}) == "select between 2 and 20 datasets; got 21"
    assert detail({"ids": [known, known]}) == "dataset ids must be unique"
    assert detail({"ids": [known, "nope"]}) == "unknown dataset id: nope"
    assert detail({"ids": [known, f"{encode_id(ETH)},{known}"]}).startswith("unknown dataset id: ")


def test_correlation_accepts_twenty_datasets(data_dir, client):
    relatives = [f"S{index:02d}.csv" for index in range(20)]
    for index, relative in enumerate(relatives):
        write_capture(data_dir / relative, rows=30, seed=index)
    body = strict_json(correlation(client, *relatives))
    assert len(body["labels"]) == 20 and np.array(body["matrix"]).shape == (20, 20)


def test_correlation_rejects_invalid_files(data_dir, client):
    write_capture(data_dir / INTRADAY, rows=50)
    (data_dir / "bad.csv").write_text("a,b\n1,2\n")
    response = correlation(client, INTRADAY, "bad.csv")
    assert response.status_code == 422
    assert response.json()["detail"].startswith("bad.csv: ")
    assert str(data_dir) not in response.json()["detail"]


def test_correlation_needs_at_least_three_overlapping_returns(data_dir, client):
    message = "fewer than 3 overlapping returns; the selected datasets do not share timestamps"
    write_capture(data_dir / INTRADAY, rows=50, seed=9)
    write_capture(data_dir / "later.csv", rows=50, seed=10, start=FIRST_BAR + timedelta(days=30))
    write_capture(data_dir / "touching.csv", rows=50, seed=11, start=FIRST_BAR + timedelta(minutes=5 * 47))

    disjoint = correlation(client, INTRADAY, "later.csv")
    assert disjoint.status_code == 422 and disjoint.json() == {"detail": message}
    overlapping_three_bars = correlation(client, INTRADAY, "touching.csv")
    assert overlapping_three_bars.status_code == 422 and overlapping_three_bars.json() == {"detail": message}

    write_capture(data_dir / "touching.csv", rows=50, seed=11, start=FIRST_BAR + timedelta(minutes=5 * 46))
    assert strict_json(correlation(client, INTRADAY, "touching.csv"))["observations"] == 3


def test_new_routes_do_not_shadow_existing_ones(data_dir, client):
    write_capture(data_dir / INTRADAY, rows=50)
    dataset_id = encode_id(INTRADAY)
    assert client.get(f"/api/datasets/{dataset_id}/bars").status_code == 200
    assert client.get(f"/api/datasets/{dataset_id}/report").status_code == 200
    assert client.get("/api/datasets").status_code == 200
    assert client.get("/api/charts").status_code == 404
    assert client.post("/api/charts/correlation").status_code == 405
