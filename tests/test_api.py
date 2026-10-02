import base64
import csv
import json
import math
import os
import pathlib
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import tradingview_data.api as api  # noqa: E402
from tradingview_data.analytics import load_ohlcv, market_report  # noqa: E402
from tradingview_data.api import DatasetRepository, _json_safe, create_app  # noqa: E402
from tradingview_data.cli import build_parser, main  # noqa: E402
from tradingview_data.research import strategy_permutations  # noqa: E402
from tradingview_data.storage import CSV_COLUMNS, CSV_TIME_FORMAT, CsvBarStore  # noqa: E402

IST = ZoneInfo("Asia/Kolkata")
FIRST_BAR = datetime(2024, 1, 1, 9, 15, tzinfo=IST)
FIRST_EPOCH = int(FIRST_BAR.timestamp())
BTC = "BINANCE_BTCUSDT/5.csv"
ETH = "BINANCE_ETHUSDT/5.csv"
COLUMN_NAMES = ["time", "open", "high", "low", "close", "volume"]


def encode_id(relative: str) -> str:
    return base64.urlsafe_b64encode(relative.encode()).rstrip(b"=").decode()


def bar_time(index: int) -> int:
    return FIRST_EPOCH + index * 60


def write_capture(path: pathlib.Path, rows: int = 60, seed: int = 0) -> dict:
    """Write a seeded random-walk capture in the CSV format produced by ``CsvBarStore``."""

    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 0.5, rows))
    open_ = np.concatenate(([close[0]], close[:-1]))
    high = np.maximum(open_, close) + rng.uniform(0.1, 0.5, rows)
    low = np.minimum(open_, close) - rng.uniform(0.1, 0.5, rows)
    volume = rng.integers(10, 1_000, rows).astype(float)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_COLUMNS)
        for index in range(rows):
            stamp = (FIRST_BAR + timedelta(minutes=index)).strftime(CSV_TIME_FORMAT)
            writer.writerow([f"[{index}]", stamp, open_[index], high[index], low[index], close[index], volume[index]])
    return {"open": open_, "high": high, "low": low, "close": close, "volume": volume}


def strict_json(response) -> object:
    """Parse a response the way a strict client would: NaN/Infinity literals are errors."""

    def reject(token: str) -> None:
        raise AssertionError(f"response contains non-finite JSON constant {token}")

    return json.loads(response.text, parse_constant=reject)


def dataset_ids(client: TestClient) -> dict:
    listing = client.get("/api/datasets").json()["datasets"]
    return {item["path"]: item["id"] for item in listing}


@pytest.fixture
def data_dir(tmp_path):
    directory = tmp_path / "data"
    directory.mkdir()
    return directory


@pytest.fixture
def client(data_dir):
    return TestClient(create_app(data_dir))


@pytest.fixture
def populated(data_dir, client):
    """Two by-timeframe captures and one flat capture; returns ``{relative path: id}``."""

    write_capture(data_dir / BTC, seed=1)
    write_capture(data_dir / ETH, seed=2)
    write_capture(data_dir / "flat.csv", seed=3)
    return dataset_ids(client)


# --- health and listing ---------------------------------------------------------------------------


def test_health_reports_absolute_data_dir_and_dataset_count(data_dir, client):
    assert client.get("/api/health").json() == {
        "status": "ok",
        "data_dir": str(data_dir.resolve()),
        "dataset_count": 0,
    }
    write_capture(data_dir / BTC)
    write_capture(data_dir / "flat.csv")
    assert client.get("/api/health").json()["dataset_count"] == 2


def test_relative_data_dir_is_reported_as_an_absolute_path(data_dir, monkeypatch):
    monkeypatch.chdir(data_dir.parent)
    health = TestClient(create_app("data")).get("/api/health").json()
    assert pathlib.Path(health["data_dir"]).is_absolute()


def test_empty_data_dir_lists_nothing(client):
    response = client.get("/api/datasets")
    assert response.status_code == 200
    assert response.json() == {"datasets": []}


def test_missing_data_dir_is_an_empty_dashboard_not_an_error(tmp_path):
    missing = TestClient(create_app(tmp_path / "not-created-yet"))
    assert missing.get("/api/datasets").json() == {"datasets": []}
    assert missing.get("/api/health").json()["dataset_count"] == 0


def test_lists_by_timeframe_and_flat_layouts(data_dir, client, populated):
    listing = {item["path"]: item for item in client.get("/api/datasets").json()["datasets"]}
    assert set(listing) == {BTC, ETH, "flat.csv"}

    btc = listing[BTC]
    assert set(btc) == {
        "id", "symbol", "timeframe", "path", "rows", "size_bytes", "modified", "start", "end", "valid", "error",
    }
    assert (btc["symbol"], btc["timeframe"]) == ("BINANCE_BTCUSDT", "5")
    assert btc["rows"] == 60
    assert btc["size_bytes"] == (data_dir / BTC).stat().st_size
    assert btc["start"] == bar_time(0)
    assert btc["end"] == bar_time(59)
    assert btc["valid"] is True and btc["error"] is None
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", btc["modified"])

    flat = listing["flat.csv"]
    assert (flat["symbol"], flat["timeframe"]) == ("flat", None)


def test_ids_are_unique_url_safe_slugs_derived_from_the_relative_path(populated):
    assert len(set(populated.values())) == 3
    for relative, dataset_id in populated.items():
        assert re.fullmatch(r"[A-Za-z0-9_-]+", dataset_id)
        assert dataset_id == encode_id(relative)


def test_listing_is_sorted_by_symbol_then_timeframe(data_dir, client):
    for relative in ("ZED/1.csv", "ALPHA/5.csv", "ALPHA/15.csv", "ALPHA/1D.csv", "MID.csv"):
        write_capture(data_dir / relative)
    order = [(item["symbol"], item["timeframe"]) for item in client.get("/api/datasets").json()["datasets"]]
    assert order == [("ALPHA", "15"), ("ALPHA", "1D"), ("ALPHA", "5"), ("MID", None), ("ZED", "1")]


def test_metadata_sidecar_supplies_symbol_and_timeframe(data_dir, client):
    path = data_dir / "BINANCE_BTCUSDT" / "5.csv"
    with CsvBarStore(path, symbol="BINANCE:BTCUSDT", timeframe="5", durable=False) as store:
        for index in range(3):
            stamp = (FIRST_BAR + timedelta(minutes=index)).strftime(CSV_TIME_FORMAT)
            store.write_bar(bar_time(index), [f"[{index}]", stamp, 10, 11, 9, 10, 5])
    assert path.with_name("5.csv.meta.json").exists()

    (item,) = client.get("/api/datasets").json()["datasets"]
    assert (item["symbol"], item["timeframe"]) == ("BINANCE:BTCUSDT", "5")
    assert item["path"] == BTC


def test_sidecar_applies_to_flat_files_and_unusable_sidecars_are_ignored(data_dir, client):
    write_capture(data_dir / "ETHUSDT.csv")
    (data_dir / "ETHUSDT.csv.meta.json").write_text(json.dumps({"symbol": "BINANCE:ETHUSDT", "timeframe": "60"}))
    write_capture(data_dir / "SOL.csv")
    (data_dir / "SOL.csv.meta.json").write_text("{not json")
    write_capture(data_dir / "ADA.csv")
    (data_dir / "ADA.csv.meta.json").write_text(json.dumps({"symbol": 7, "timeframe": ""}))

    found = {item["path"]: (item["symbol"], item["timeframe"]) for item in client.get("/api/datasets").json()["datasets"]}
    assert found == {
        "ETHUSDT.csv": ("BINANCE:ETHUSDT", "60"),
        "SOL.csv": ("SOL", None),
        "ADA.csv": ("ADA", None),
    }


def test_ignores_hidden_sidecar_non_csv_directory_and_deep_paths(data_dir, client):
    write_capture(data_dir / BTC)
    write_capture(data_dir / ".hidden.csv")
    write_capture(data_dir / ".cache" / "5.csv")
    write_capture(data_dir / "BINANCE_BTCUSDT" / ".6.csv")
    write_capture(data_dir / "too" / "deep" / "5.csv")
    (data_dir / "notes.txt").write_text("hello")
    (data_dir / "BINANCE_BTCUSDT" / "5.csv.meta.json").write_text("{}")
    (data_dir / "folder.csv").mkdir()
    paths = [item["path"] for item in client.get("/api/datasets").json()["datasets"]]
    assert paths == [BTC]
    assert client.get("/api/health").json()["dataset_count"] == 1


def test_symlinks_leaving_the_data_dir_are_not_listed(tmp_path, data_dir, client):
    write_capture(tmp_path / "outside" / "5.csv")
    try:
        os.symlink(tmp_path / "outside", data_dir / "LINKED", target_is_directory=True)
        os.symlink(tmp_path / "outside" / "5.csv", data_dir / "escape.csv")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are unavailable on this platform")
    assert client.get("/api/datasets").json() == {"datasets": []}


def test_invalid_csvs_are_listed_as_invalid_without_failing_the_listing(data_dir, client):
    write_capture(data_dir / BTC)
    (data_dir / "no_columns.csv").write_text("a,b\n1,2\n")
    (data_dir / "empty.csv").write_text("")
    (data_dir / "no_valid_rows.csv").write_text(",".join(CSV_COLUMNS) + "\n[0],garbage,x,y,z,w,v\n")

    listing = {item["path"]: item for item in client.get("/api/datasets").json()["datasets"]}
    assert listing[BTC]["valid"] is True
    for name in ("no_columns.csv", "empty.csv", "no_valid_rows.csv"):
        item = listing[name]
        assert item["valid"] is False
        assert (item["rows"], item["start"], item["end"]) == (0, None, None)
        assert item["error"]
        assert str(data_dir) not in item["error"]
    assert "missing required columns" in listing["no_columns.csv"]["error"]
    assert "no_columns.csv" in listing["no_columns.csv"]["error"]


def test_unexpected_parser_failures_are_reported_per_dataset(data_dir, client, monkeypatch):
    write_capture(data_dir / "good.csv")
    write_capture(data_dir / "boom.csv")
    real_load = api.load_ohlcv

    def flaky(path):
        if pathlib.Path(path).name == "boom.csv":
            raise OverflowError("timestamp out of range")
        return real_load(path)

    monkeypatch.setattr(api, "load_ohlcv", flaky)
    listing = {item["path"]: item for item in client.get("/api/datasets").json()["datasets"]}
    assert listing["good.csv"]["valid"] is True
    assert listing["boom.csv"]["valid"] is False
    assert listing["boom.csv"]["error"] == "timestamp out of range"


def test_new_captures_appear_without_restarting(data_dir, client):
    assert client.get("/api/datasets").json() == {"datasets": []}
    write_capture(data_dir / BTC)
    assert [item["path"] for item in client.get("/api/datasets").json()["datasets"]] == [BTC]


def test_openapi_documents_every_endpoint(client):
    paths = set(client.get("/api/openapi.json").json()["paths"])
    assert paths == {
        "/api/health",
        "/api/datasets",
        "/api/datasets/{dataset_id}/bars",
        "/api/datasets/{dataset_id}/report",
        "/api/datasets/{dataset_id}/charts",
        "/api/charts/correlation",
        "/api/research/run",
        "/api/sentiment/fear-greed",
        "/api/providers",
        "/api/providers/{provider_id}/catalog",
        "/api/providers/{provider_id}/query",
        "/api/trading/environments",
        "/api/trading/{env}/account",
        "/api/trading/{env}/account/configurations",
        "/api/trading/{env}/account/activities",
        "/api/trading/{env}/account/activities/{activity_type}",
        "/api/trading/{env}/account/portfolio-history",
        "/api/trading/{env}/clock",
        "/api/trading/{env}/calendar",
        "/api/trading/{env}/assets",
        "/api/trading/{env}/assets/{symbol_or_id}",
        "/api/trading/{env}/options/contracts",
        "/api/trading/{env}/options/contracts/{symbol_or_id}",
        "/api/trading/{env}/quote/{symbol}",
        "/api/trading/{env}/orders",
        "/api/trading/{env}/orders/by-client-id/{client_order_id}",
        "/api/trading/{env}/orders/{order_id}",
        "/api/trading/{env}/positions",
        "/api/trading/{env}/positions/{symbol_or_id}",
        "/api/trading/{env}/positions/{symbol_or_id}/exercise",
        "/api/trading/{env}/positions/{symbol_or_id}/do-not-exercise",
        "/api/trading/{env}/watchlists",
        "/api/trading/{env}/watchlists/{watchlist_id}",
        "/api/trading/{env}/watchlists/{watchlist_id}/assets",
        "/api/trading/{env}/watchlists/{watchlist_id}/assets/{symbol}",
        "/api/verdict/run",
        "/api/verdict/{dataset_id}",
        "/api/verdict/{dataset_id}/seal",
        "/api/verdict/{dataset_id}/ledger",
        "/api/verdict/{dataset_id}/freeze",
        "/api/verdict/{dataset_id}/holdout/read",
        "/api/verdict/{dataset_id}/forward",
    }


# --- bars -----------------------------------------------------------------------------------------


def test_bars_columnar_payload_uses_epoch_seconds(data_dir, client):
    expected = write_capture(data_dir / BTC, rows=60, seed=1)
    dataset_id = dataset_ids(client)[BTC]

    response = client.get(f"/api/datasets/{dataset_id}/bars")
    assert response.status_code == 200
    body = strict_json(response)
    assert set(body) == {
        "id", "symbol", "timeframe", "rows", "total_rows", "dropped_rows", "duplicate_rows_collapsed", "columns", "quality",
    }
    assert (body["id"], body["symbol"], body["timeframe"]) == (dataset_id, "BINANCE_BTCUSDT", "5")
    assert (body["rows"], body["total_rows"]) == (60, 60)
    assert (body["dropped_rows"], body["duplicate_rows_collapsed"]) == (0, 0)

    columns = body["columns"]
    assert list(columns) == COLUMN_NAMES
    assert all(len(values) == 60 for values in columns.values())
    assert all(type(value) is int for value in columns["time"])
    assert columns["time"] == [bar_time(index) for index in range(60)]
    for name, values in expected.items():
        assert columns[name] == pytest.approx(values)

    assert body["quality"]["valid_rows"] == 60
    assert body["quality"]["source"] == BTC


def test_bars_report_dropped_and_duplicate_rows_for_the_whole_file(data_dir, client):
    write_capture(data_dir / BTC, rows=10)
    with (data_dir / BTC).open("a", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["[3]", (FIRST_BAR + timedelta(minutes=3)).strftime(CSV_TIME_FORMAT), 1, 2, 1, 2, 5])
        writer.writerow(["[x]", (FIRST_BAR + timedelta(minutes=99)).strftime(CSV_TIME_FORMAT), 5, 1, 1, 5, 5])
    dataset_id = dataset_ids(client)[BTC]

    body = client.get(f"/api/datasets/{dataset_id}/bars", params={"limit": 2}).json()
    assert (body["rows"], body["total_rows"]) == (2, 10)
    assert (body["dropped_rows"], body["duplicate_rows_collapsed"]) == (1, 1)
    assert body["quality"]["input_rows"] == 12


def test_limit_returns_the_most_recent_bars(data_dir, client):
    write_capture(data_dir / BTC)
    url = f"/api/datasets/{dataset_ids(client)[BTC]}/bars"
    body = client.get(url, params={"limit": 5}).json()
    assert body["rows"] == 5 and body["total_rows"] == 60
    assert body["columns"]["time"] == [bar_time(index) for index in range(55, 60)]
    assert all(len(values) == 5 for values in body["columns"].values())
    assert client.get(url, params={"limit": 1000}).json()["rows"] == 60


def test_start_and_end_are_inclusive_and_compose_with_limit(data_dir, client):
    write_capture(data_dir / BTC)
    url = f"/api/datasets/{dataset_ids(client)[BTC]}/bars"

    window = client.get(url, params={"start": bar_time(10), "end": bar_time(19)}).json()
    assert window["columns"]["time"] == [bar_time(index) for index in range(10, 20)]
    assert window["total_rows"] == 60

    assert client.get(url, params={"start": bar_time(55)}).json()["columns"]["time"] == [
        bar_time(index) for index in range(55, 60)
    ]
    assert client.get(url, params={"end": bar_time(2)}).json()["columns"]["time"] == [bar_time(i) for i in range(3)]
    assert client.get(url, params={"start": bar_time(10) - 1, "end": bar_time(12) + 59}).json()["rows"] == 3
    assert client.get(url, params={"start": float(bar_time(10)), "end": bar_time(10)}).json()["rows"] == 1

    tail = client.get(url, params={"start": bar_time(10), "end": bar_time(19), "limit": 3}).json()
    assert tail["columns"]["time"] == [bar_time(17), bar_time(18), bar_time(19)]


def test_empty_windows_return_empty_columns(data_dir, client):
    write_capture(data_dir / BTC)
    url = f"/api/datasets/{dataset_ids(client)[BTC]}/bars"
    for params in ({"start": FIRST_EPOCH + 10_000_000}, {"end": FIRST_EPOCH - 1}):
        body = client.get(url, params=params).json()
        assert body["rows"] == 0 and body["total_rows"] == 60
        assert body["columns"] == {name: [] for name in COLUMN_NAMES}


def test_bars_errors_use_standard_shapes(data_dir, client):
    write_capture(data_dir / BTC)
    (data_dir / "bad.csv").write_text("a,b\n1,2\n")
    ids = dataset_ids(client)
    url = f"/api/datasets/{ids[BTC]}/bars"

    missing = client.get("/api/datasets/unknownid/bars")
    assert missing.status_code == 404
    assert isinstance(missing.json()["detail"], str)

    reversed_window = client.get(url, params={"start": 200, "end": 100})
    assert reversed_window.status_code == 422
    assert "start" in reversed_window.json()["detail"]

    for params in ({"limit": 0}, {"limit": 5_000_001}, {"limit": "x"}, {"start": "abc"}, {"end": "nan"}, {"start": "inf"}):
        rejected = client.get(url, params=params)
        assert rejected.status_code == 422, params
        assert isinstance(rejected.json()["detail"], list), params
    assert client.get(url, params={"limit": 5_000_000}).status_code == 200

    invalid = client.get(f"/api/datasets/{ids['bad.csv']}/bars")
    assert invalid.status_code == 422
    assert "missing required columns" in invalid.json()["detail"]
    assert str(data_dir) not in invalid.json()["detail"]


# --- path traversal -------------------------------------------------------------------------------


def test_ids_never_reach_the_filesystem_outside_the_registry(tmp_path, data_dir, client):
    write_capture(data_dir / BTC)
    write_capture(tmp_path / "outside.csv")
    hostile = [
        "..",
        "../outside.csv",
        "..%2Foutside.csv",
        "%2e%2e%2foutside.csv",
        BTC,
        str(data_dir / BTC),
        "/etc/passwd",
        encode_id("../outside.csv"),
        encode_id(str(tmp_path / "outside.csv")),
        encode_id(str(data_dir / BTC)),
        encode_id("./" + BTC),
        encode_id("BINANCE_BTCUSDT/../BINANCE_BTCUSDT/5.csv"),
        encode_id(BTC.lower()),
        encode_id("outside.csv"),
        encode_id(BTC) + "=",
    ]
    for dataset_id in hostile:
        assert client.get(f"/api/datasets/{dataset_id}/bars").status_code == 404, dataset_id
        assert client.get(f"/api/datasets/{dataset_id}/report").status_code == 404, dataset_id
        research = client.post("/api/research/run", json={"dataset_ids": [dataset_id]})
        assert research.status_code == 422, dataset_id
        assert "unknown dataset id" in research.json()["detail"], dataset_id
    assert client.get(f"/api/datasets/{encode_id(BTC)}/bars").status_code == 200


# --- report ---------------------------------------------------------------------------------------


def test_report_matches_market_report(data_dir, client):
    write_capture(data_dir / BTC, rows=60, seed=4)
    response = client.get(f"/api/datasets/{dataset_ids(client)[BTC]}/report")
    assert response.status_code == 200
    body = strict_json(response)
    expected = market_report(load_ohlcv(data_dir / BTC))
    assert set(body) == {"quality", "latest", "performance", "indicators", "signals"}
    for section in ("latest", "performance", "indicators", "signals"):
        assert body[section] == expected[section]
    assert body["quality"]["source"] == BTC


def test_report_errors(data_dir, client):
    (data_dir / "bad.csv").write_text("a,b\n1,2\n")
    assert client.get("/api/datasets/nope/report").status_code == 404
    invalid = client.get(f"/api/datasets/{dataset_ids(client)['bad.csv']}/report")
    assert invalid.status_code == 422
    assert "missing required columns" in invalid.json()["detail"]


def test_too_short_series_serialise_missing_metrics_as_null(data_dir, client):
    write_capture(data_dir / "one_bar.csv", rows=1)
    dataset_id = dataset_ids(client)["one_bar.csv"]

    report = strict_json(client.get(f"/api/datasets/{dataset_id}/report"))
    assert report["indicators"]["sma_20"] is None
    assert report["indicators"]["rsi_14"] is None
    assert report["signals"]["rsi"] == "unavailable"

    bars = strict_json(client.get(f"/api/datasets/{dataset_id}/bars"))
    assert bars["rows"] == 1
    assert bars["quality"]["median_interval_seconds"] is None


# --- research -------------------------------------------------------------------------------------


def test_research_run_labels_assets_by_symbol_and_timeframe(client, populated, monkeypatch):
    def no_model_calls(*_args, **_kwargs):
        raise AssertionError("the API must not call a model endpoint")

    monkeypatch.setattr("tradingview_data.research.request_model_notes", no_model_calls)
    response = client.post(
        "/api/research/run",
        json={
            "dataset_ids": [populated[BTC], populated[ETH], populated["flat.csv"]],
            "fee_bps": 2.5,
            "periods_per_year": 365,
        },
    )
    assert response.status_code == 200
    report = strict_json(response)
    assert set(report) == {"schema_version", "metadata", "assets", "results", "model_notes", "disclosures"}
    assert report["schema_version"] == 1
    assert [asset["symbol"] for asset in report["assets"]] == ["BINANCE_BTCUSDT-5", "BINANCE_ETHUSDT-5", "flat"]
    assert report["metadata"]["fee_bps_per_position_change"] == 2.5
    assert report["metadata"]["periods_per_year"] == 365
    assert len(report["results"]) == 3 * len(strategy_permutations())
    assert report["model_notes"] == []


def test_research_defaults_and_short_series(data_dir, client):
    write_capture(data_dir / "short.csv", rows=3)
    dataset_id = dataset_ids(client)["short.csv"]
    response = client.post("/api/research/run", json={"dataset_ids": [dataset_id]})
    assert response.status_code == 200
    metadata = strict_json(response)["metadata"]
    assert (metadata["fee_bps_per_position_change"], metadata["periods_per_year"]) == (5, 252)


def test_research_labels_stay_unique_when_symbol_and_timeframe_collide(data_dir, client):
    for seed, name in enumerate(("a.csv", "b.csv")):
        write_capture(data_dir / name, seed=seed)
        (data_dir / f"{name}.meta.json").write_text(json.dumps({"symbol": "X", "timeframe": "5"}))
    ids = dataset_ids(client)
    response = client.post("/api/research/run", json={"dataset_ids": [ids["a.csv"], ids["b.csv"]]})
    assert [asset["symbol"] for asset in response.json()["assets"]] == ["X-5", "X-5-2"]


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"dataset_ids": []},
        {"dataset_ids": ["a"] * 2},
        {"dataset_ids": [f"id{index}" for index in range(21)]},
        {"dataset_ids": "abc"},
        {"dataset_ids": ["a"], "fee_bps": -0.1},
        {"dataset_ids": ["a"], "fee_bps": 10_001},
        {"dataset_ids": ["a"], "fee_bps": "cheap"},
        {"dataset_ids": ["a"], "periods_per_year": 0},
        {"dataset_ids": ["a"], "periods_per_year": -252},
    ],
)
def test_research_body_validation_uses_the_standard_422_list(client, body):
    response = client.post("/api/research/run", json=body)
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)


def test_research_rejects_non_finite_numbers(client):
    for payload in ('{"dataset_ids":["a"],"fee_bps":NaN}', '{"dataset_ids":["a"],"periods_per_year":Infinity}'):
        response = client.post("/api/research/run", content=payload, headers={"Content-Type": "application/json"})
        assert response.status_code == 422
        detail = strict_json(response)["detail"]
        assert isinstance(detail, list) and detail[0]["input"] is None


def test_research_accepts_the_documented_boundaries(data_dir, client):
    write_capture(data_dir / "short.csv", rows=3)
    dataset_id = dataset_ids(client)["short.csv"]
    for fee in (0, 10_000):
        assert client.post("/api/research/run", json={"dataset_ids": [dataset_id], "fee_bps": fee}).status_code == 200


def test_research_reports_unknown_and_invalid_datasets_as_detail_strings(data_dir, client):
    (data_dir / "bad.csv").write_text("a,b\n1,2\n")
    ids = dataset_ids(client)

    unknown = client.post("/api/research/run", json={"dataset_ids": ["missing"]})
    assert unknown.status_code == 422
    assert unknown.json() == {"detail": "unknown dataset id: missing"}

    invalid = client.post("/api/research/run", json={"dataset_ids": [ids["bad.csv"]]})
    assert invalid.status_code == 422
    assert invalid.json()["detail"].startswith("bad.csv: ")
    assert str(data_dir) not in invalid.json()["detail"]


def test_research_value_errors_become_422(data_dir, client, monkeypatch):
    write_capture(data_dir / "short.csv", rows=3)
    dataset_id = dataset_ids(client)["short.csv"]

    def refuse(*_args, **_kwargs):
        raise ValueError("no usable rows")

    monkeypatch.setattr(api, "build_research", refuse)
    response = client.post("/api/research/run", json={"dataset_ids": [dataset_id]})
    assert response.status_code == 422
    assert response.json() == {"detail": "no usable rows"}


# --- JSON safety ----------------------------------------------------------------------------------


def test_json_safe_replaces_non_finite_numbers_and_numpy_types():
    payload = {
        "nan": float("nan"),
        "inf": math.inf,
        "ninf": -math.inf,
        "np_nan": np.float64("nan"),
        "np_int": np.int64(7),
        "np_bool": np.bool_(True),
        "nested": [(1.5, float("nan")), {"deep": [np.float32("inf")]}],
        "array": np.array([1.0, np.nan, np.inf, 2.5]),
        "ints": np.arange(3),
        "matrix": np.array([[1.0, np.nan], [2.0, 3.0]]),
        1: "int key",
        "text": "keep",
        "none": None,
    }
    safe = _json_safe(payload)
    assert safe == {
        "nan": None,
        "inf": None,
        "ninf": None,
        "np_nan": None,
        "np_int": 7,
        "np_bool": True,
        "nested": [[1.5, None], {"deep": [None]}],
        "array": [1.0, None, None, 2.5],
        "ints": [0, 1, 2],
        "matrix": [[1.0, None], [2.0, 3.0]],
        "1": "int key",
        "text": "keep",
        "none": None,
    }
    assert type(safe["np_int"]) is int and type(safe["np_bool"]) is bool
    json.dumps(safe, allow_nan=False)


def test_non_finite_values_from_the_engine_reach_clients_as_null(data_dir, client, monkeypatch):
    write_capture(data_dir / "short.csv", rows=3)
    dataset_id = dataset_ids(client)["short.csv"]
    monkeypatch.setattr(
        api,
        "build_research",
        lambda *_args, **_kwargs: {"sharpe": float("nan"), "curve": [1.0, math.inf], "n": np.float64("-inf")},
    )
    response = client.post("/api/research/run", json={"dataset_ids": [dataset_id]})
    assert response.status_code == 200
    assert strict_json(response) == {"sharpe": None, "curve": [1.0, None], "n": None}


# --- cache ----------------------------------------------------------------------------------------


@pytest.fixture
def load_counter(monkeypatch):
    calls = []
    real_load = api.load_ohlcv

    def counting(path):
        calls.append(pathlib.Path(path).name)
        return real_load(path)

    monkeypatch.setattr(api, "load_ohlcv", counting)
    return calls


def test_repeated_requests_reuse_the_parsed_frame(data_dir, client, load_counter):
    write_capture(data_dir / BTC)
    dataset_id = dataset_ids(client)[BTC]
    client.get(f"/api/datasets/{dataset_id}/bars")
    client.get(f"/api/datasets/{dataset_id}/bars", params={"limit": 3})
    client.get(f"/api/datasets/{dataset_id}/report")
    client.get("/api/datasets")
    assert load_counter == ["5.csv"]


def test_invalid_files_are_not_reparsed_on_every_listing(data_dir, client, load_counter):
    (data_dir / "bad.csv").write_text("a,b\n1,2\n")
    client.get("/api/datasets")
    client.get("/api/datasets")
    assert load_counter == ["bad.csv"]


def test_growing_capture_is_reloaded_and_does_not_evict_other_datasets(data_dir, load_counter):
    repository = DatasetRepository(data_dir.resolve(), cache_size=2)
    write_capture(data_dir / "live.csv", rows=10)
    write_capture(data_dir / "other.csv", rows=10)
    files = {file.relative: file for file in repository.scan()}
    repository.load(files["live.csv"])
    repository.load(files["other.csv"])

    for rows in (20, 30, 40):
        write_capture(data_dir / "live.csv", rows=rows)
        live = {file.relative: file for file in repository.scan()}["live.csv"]
        assert len(repository.load(live).data) == rows
    repository.load(files["other.csv"])
    assert load_counter.count("other.csv") == 1
    assert load_counter.count("live.csv") == 4


def test_cache_is_bounded(data_dir, load_counter):
    repository = DatasetRepository(data_dir.resolve(), cache_size=2)
    for name in ("a.csv", "b.csv", "c.csv"):
        write_capture(data_dir / name, rows=5)
    files = sorted(repository.scan(), key=lambda file: file.relative)
    for file in files:
        repository.load(file)
    repository.load(files[2])
    repository.load(files[0])
    assert load_counter == ["a.csv", "b.csv", "c.csv", "a.csv"]


def test_concurrent_requests_parse_a_file_once(data_dir, load_counter):
    write_capture(data_dir / BTC)
    repository = DatasetRepository(data_dir.resolve())
    (file,) = repository.scan()
    barrier = threading.Barrier(8)

    def load():
        barrier.wait()
        return repository.load(file)

    with ThreadPoolExecutor(max_workers=8) as pool:
        frames = [future.result() for future in [pool.submit(load) for _ in range(8)]]
    assert load_counter == ["5.csv"]
    assert all(frame is frames[0] for frame in frames)


# --- static hosting -------------------------------------------------------------------------------


@pytest.fixture
def static_dir(tmp_path):
    root = tmp_path / "build"
    (root / "_app" / "immutable").mkdir(parents=True)
    (root / "index.html").write_text("<!doctype html><title>dashboard</title>")
    (root / "robots.txt").write_text("User-agent: *")
    (root / "_app" / "immutable" / "app.abc123.js").write_text("console.log(1)")
    (tmp_path / "secret.txt").write_text("top secret")
    return root


@pytest.fixture
def hosted(data_dir, static_dir):
    return TestClient(create_app(data_dir, static_dir))


def test_static_root_serves_index_without_caching(hosted):
    response = hosted.get("/")
    assert response.status_code == 200
    assert "dashboard" in response.text
    assert response.headers["cache-control"] == "no-cache"
    assert hosted.get("/index.html").headers["cache-control"] == "no-cache"


def test_hashed_assets_are_immutable_and_revalidate_cheaply(hosted):
    response = hosted.get("/_app/immutable/app.abc123.js")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"
    again = hosted.get("/_app/immutable/app.abc123.js", headers={"If-None-Match": response.headers["etag"]})
    assert again.status_code == 304
    assert again.headers["cache-control"] == "public, max-age=31536000, immutable"


def test_other_static_files_are_served_as_is(hosted):
    response = hosted.get("/robots.txt")
    assert response.status_code == 200 and response.text == "User-agent: *"
    assert "immutable" not in response.headers.get("cache-control", "")


def test_unknown_routes_fall_back_to_the_spa_index(hosted):
    for route in ("/research", "/datasets/abc/explore", "/apiary", "/missing.png"):
        response = hosted.get(route)
        assert response.status_code == 200, route
        assert "dashboard" in response.text, route
        assert response.headers["cache-control"] == "no-cache", route


def test_unknown_api_paths_stay_json_404s(hosted):
    for method in ("get", "post", "delete"):
        response = getattr(hosted, method)("/api/unknown")
        assert response.status_code == 404, method
        assert response.json() == {"detail": "Not Found"}
    assert hosted.get("/api").status_code == 404
    assert hosted.get("/api/datasets/x/nope").json() == {"detail": "Not Found"}


def test_missing_hashed_assets_are_404_not_html(hosted):
    assert hosted.get("/_app/immutable/app.stale.js").status_code == 404


def test_static_hosting_cannot_read_outside_the_build_directory(hosted):
    for route in ("/../secret.txt", "/%2e%2e/secret.txt", "/_app/../../secret.txt", "/..%2fsecret.txt"):
        response = hosted.get(route)
        assert "top secret" not in response.text, route


def test_api_routes_win_over_static_files(data_dir, hosted):
    write_capture(data_dir / BTC)
    assert hosted.get("/api/health").json()["status"] == "ok"
    assert [item["path"] for item in hosted.get("/api/datasets").json()["datasets"]] == [BTC]
    assert hosted.get("/api/openapi.json").status_code == 200


def test_without_a_static_dir_or_with_a_missing_one_only_the_api_is_served(tmp_path, data_dir):
    for app in (create_app(data_dir), create_app(data_dir, tmp_path / "nope")):
        api_only = TestClient(app)
        assert api_only.get("/").status_code == 404
        assert api_only.get("/api/health").status_code == 200


# --- CORS -----------------------------------------------------------------------------------------


def test_cors_is_disabled_by_default(client):
    response = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert "access-control-allow-origin" not in response.headers


def test_cors_allows_only_configured_origins(data_dir):
    cors = TestClient(create_app(data_dir, cors_origins=["http://localhost:5173"]))
    allowed = cors.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
    denied = cors.get("/api/health", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in denied.headers
    preflight = cors.options(
        "/api/research/run",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == "http://localhost:5173"


# --- CLI ------------------------------------------------------------------------------------------


def test_serve_parser_defaults():
    args = build_parser().parse_args(["serve"])
    assert (args.data_dir, args.host, args.port) == ("data", "127.0.0.1", 8000)
    assert args.static_dir is None and args.cors_origin == []


def test_serve_builds_the_app_and_hands_it_to_uvicorn(data_dir, static_dir, monkeypatch):
    uvicorn = pytest.importorskip("uvicorn")
    captured = {}

    def fake_run(app, **kwargs):
        captured.update(app=app, **kwargs)

    monkeypatch.setattr(uvicorn, "run", fake_run)
    code = main(
        [
            "serve",
            "--data-dir", str(data_dir),
            "--host", "0.0.0.0",
            "--port", "9123",
            "--static-dir", str(static_dir),
            "--cors-origin", "http://localhost:5173",
            "--cors-origin", "http://127.0.0.1:5173",
        ]
    )
    assert code == 0
    assert (captured["host"], captured["port"]) == ("0.0.0.0", 9123)
    app = captured["app"]
    assert isinstance(app, FastAPI)
    served = TestClient(app)
    assert served.get("/api/health").json()["data_dir"] == str(data_dir.resolve())
    assert "dashboard" in served.get("/").text
    origin = "http://127.0.0.1:5173"
    assert served.get("/api/health", headers={"Origin": origin}).headers["access-control-allow-origin"] == origin


def test_serve_warns_about_a_missing_static_dir_but_still_serves(data_dir, tmp_path, monkeypatch, capsys):
    uvicorn = pytest.importorskip("uvicorn")
    calls = []
    monkeypatch.setattr(uvicorn, "run", lambda app, **kwargs: calls.append(kwargs))
    assert main(["serve", "--data-dir", str(data_dir), "--static-dir", str(tmp_path / "nope")]) == 0
    assert len(calls) == 1
    assert "not found" in capsys.readouterr().err


def test_serve_explains_how_to_install_missing_optional_dependencies(data_dir, monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "uvicorn", None)
    assert main(["serve", "--data-dir", str(data_dir)]) == 2
    assert 'pip install -e ".[api]"' in capsys.readouterr().err


def test_interactive_docs_live_under_api_so_the_dashboard_can_own_docs(data_dir, hosted):
    # Swagger and ReDoc sit under /api; the bare /docs path belongs to the single-page app.
    for path in ("/api/docs", "/api/redoc"):
        response = hosted.get(path)
        assert response.status_code == 200, path
        assert "text/html" in response.headers["content-type"]
    assert "swagger" in hosted.get("/api/docs").text.lower()

    spa = hosted.get("/docs")
    assert spa.status_code == 200
    assert "swagger" not in spa.text.lower()
    assert spa.text == hosted.get("/").text  # SPA fallback: the client router renders the page
    assert hosted.get("/openapi.json").text == spa.text

    api_only = TestClient(create_app(data_dir))
    assert api_only.get("/docs").status_code == 404
    assert api_only.get("/api/docs").status_code == 200
