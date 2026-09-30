import base64
import hashlib
import json
import math
import pathlib
import re
import shutil
import sys
import threading
import time
from types import SimpleNamespace

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import tradingview_data.verdict as engine  # noqa: E402
import tradingview_data.verdict_service as service  # noqa: E402
from tradingview_data.analytics import load_ohlcv  # noqa: E402
from tradingview_data.api import create_app  # noqa: E402
from tradingview_data.cli import build_parser, main  # noqa: E402

from verdict_data import random_walk_frame, regime_frame, write_capture  # noqa: E402

BTC = "BINANCE_BTCUSDT/60.csv"
ETH = "BINANCE_ETHUSDT/60.csv"
GRID_SIZE = 16
HOUR = 3600
FULL_TRENDING = regime_frame(10300)


def encode_id(relative):
    return base64.urlsafe_b64encode(relative.encode()).rstrip(b"=").decode()


def epoch(frame, position):
    return int(frame.index[position].timestamp())


def strict_json(response):
    def reject(token):
        raise AssertionError(f"response contains non-finite JSON constant {token}")

    return json.loads(response.text, parse_constant=reject)


def boom(*_args, **_kwargs):
    raise RuntimeError("boom")


def post_run(client, relative=BTC, **body):
    return client.post("/api/verdict/run", json={"dataset_id": encode_id(relative), **body})


def ledger_entries(state_dir):
    return [json.loads(line) for line in (state_dir / "ledger.jsonl").read_text().splitlines()]


def holdout_reads(state_dir):
    return [entry for entry in ledger_entries(state_dir) if entry["type"] == "holdout_read"]


def stable(report):
    """A report without the two fields that legitimately differ between identical runs."""

    copy = json.loads(json.dumps(report))
    copy.pop("created_at")
    copy["data"]["holdout"].pop("sealed_at")
    return copy


def edit_csv_value(path, bar, column=-1, value="999"):
    lines = path.read_text().splitlines()
    cells = lines[bar + 1].split(",")
    cells[column] = value
    lines[bar + 1] = ",".join(cells)
    path.write_text("\n".join(lines) + "\n")


@pytest.fixture
def data_dir(tmp_path):
    directory = tmp_path / "data"
    directory.mkdir()
    return directory


@pytest.fixture
def state_dir(tmp_path):
    return tmp_path / "state"


@pytest.fixture
def client(data_dir, state_dir):
    return TestClient(create_app(data_dir, state_dir=state_dir))


@pytest.fixture
def short(data_dir, client):
    """A 1,000-bar hourly capture shaped like the real one: no rule reaches 30 trades."""

    write_capture(data_dir / BTC, random_walk_frame(1000, 0))
    return encode_id(BTC)


@pytest.fixture(scope="module")
def candidate_env(tmp_path_factory):
    root = tmp_path_factory.mktemp("candidate")
    write_capture(root / "data" / BTC, FULL_TRENDING.iloc[:10000])
    client = TestClient(create_app(root / "data", state_dir=root / "state"))
    response = post_run(client)
    assert response.status_code == 200, response.text
    return SimpleNamespace(root=root, report=response.json())


@pytest.fixture
def candidate(candidate_env, tmp_path):
    """A private copy of a trending dataset that has been sealed and judged CANDIDATE."""

    data, state = tmp_path / "candidate-data", tmp_path / "candidate-state"
    shutil.copytree(candidate_env.root / "data", data)
    shutil.copytree(candidate_env.root / "state", state)
    report = candidate_env.report
    winners = [rule["id"] for rule in report["rules"] if rule["evidence"] and rule["evidence"]["candidate"]]
    losers = [rule["id"] for rule in report["rules"] if not (rule["evidence"] and rule["evidence"]["candidate"])]
    return SimpleNamespace(
        data=data, state=state, client=TestClient(create_app(data, state_dir=state)), report=report,
        id=encode_id(BTC), winners=winners, loser=losers[0],
    )


def freeze(candidate, rule_ids=None, run_id=None):
    return candidate.client.post(
        f"/api/verdict/{candidate.id}/freeze",
        json={"run_id": run_id or candidate.report["run_id"], "rule_ids": rule_ids or candidate.winners[:1]},
    )


def read_holdout(candidate, freeze_id):
    return candidate.client.post(f"/api/verdict/{candidate.id}/holdout/read", json={"freeze_id": freeze_id})


# --- the run endpoint and the current capture (acceptance) ---------------------------------------------


def test_the_current_capture_is_insufficient_data_and_ranks_nothing(client, short):
    response = client.post("/api/verdict/run", json={"dataset_id": short})
    assert response.status_code == 200
    report = strict_json(response)
    assert report["verdict"]["label"] == "INSUFFICIENT_DATA"
    assert report["statistics"] is None
    assert max(rule["trades"] for rule in report["rules"]) < 30
    assert all(rule["evidence"] is None for rule in report["rules"])
    assert {rule["status"] for rule in report["rules"]} <= {"INSUFFICIENT_TRADES", "NEVER_TRADES"}
    assert [rule["id"] for rule in report["rules"]] == [rule["id"] for rule in engine.strategy_permutations()]
    assert not [key for key in re.findall(r'"([^"]+)":', response.text) if re.search(r"rank|score|winner", key)]
    assert report["verdict"]["headline"].startswith("No rule reached 30 trades on 800 research bars")
    assert "Nothing can be concluded or ranked" in report["verdict"]["headline"]


def test_the_report_has_exactly_the_documented_shape(client, short):
    report = client.post("/api/verdict/run", json={"dataset_id": short}).json()
    assert set(report) == {
        "run_id", "created_at", "dataset", "verdict", "settings", "data", "ledger", "rules", "statistics",
        "uncertainty", "integrity", "notes",
    }
    assert report["dataset"] == {"id": short, "symbol": "BINANCE_BTCUSDT", "timeframe": "60", "path": BTC}
    assert set(report["verdict"]) == {"label", "headline", "reasons"}
    assert report["settings"] == {
        "min_trades": 30,
        "costs": {"fee_bps_per_side": 10.0, "spread_bps": 1.0, "slippage_k": 0.1},
        "periods_per_year": 8760.0,
        "periods_per_year_inferred": True,
        "alpha": 0.05,
        "dsr_threshold": 0.95,
        "stress_multipliers": [1.0, 1.5, 2.0],
        "bootstrap": {"replicates": 2000, "mean_block_length": 9, "seed": report["settings"]["bootstrap"]["seed"]},
    }
    data = report["data"]
    assert {key: data[key] for key in ("bars_total", "research_bars", "forward_bars")} == {
        "bars_total": 1000, "research_bars": 800, "forward_bars": 0
    }
    assert data["research_end"] - data["research_start"] == 799 * HOUR
    assert set(data["holdout"]) == {"fraction", "start", "end", "bars", "sealed_at", "status", "read_at", "created_now"}
    assert (data["holdout"]["status"], data["holdout"]["read_at"], data["holdout"]["created_now"]) == ("unread", None, True)
    assert data["holdout"]["start"] == data["research_end"] + HOUR and data["holdout"]["bars"] == 200
    assert set(report["uncertainty"]) == {
        "research_bars", "sharpe_se_annualised_iid", "holdout_bars", "holdout_sharpe_se_annualised_iid", "note"
    }
    assert set(report["integrity"]) == {
        "fill_model", "signal_shift_verified", "lookahead_probe", "close_to_open_gap_bps", "research_fingerprint"
    }
    assert len(report["integrity"]["research_fingerprint"]) == 16
    assert set(report["rules"][0]) == {
        "id", "family", "name", "parameters", "status", "trades", "closed_trades", "exposure_pct", "error", "evidence"
    }
    assert any("fills at the signal close" in note for note in report["notes"])
    assert any("sanity check, not a verdict" in note for note in report["notes"])


def test_a_candidate_report_carries_every_statistic_the_contract_lists(candidate):
    report = candidate.report
    assert report["verdict"]["label"] == "CANDIDATE" and candidate.winners
    statistics = report["statistics"]
    assert set(statistics) == {"effective_n", "reality_check", "pbo", "pbo_unavailable"}
    assert set(statistics["effective_n"]) == {
        "estimate", "low", "high", "level", "rules_used", "ledger_trials", "scaled_estimate"
    }
    assert set(statistics["reality_check"]) == {
        "statistic", "best_rule", "p_value", "alpha", "rejected", "rules_tested", "replicates", "mean_block_length", "seed"
    }
    assert set(statistics["pbo"]) == {"value", "blocks", "combinations", "rules", "noisy", "caveat"}
    evidence = next(rule for rule in report["rules"] if rule["evidence"])["evidence"]
    assert set(evidence) == {
        "sharpe", "sharpe_se", "mean_trade_return_pct", "adjusted_p", "dsr", "dsr_sensitivity", "break_even", "stress",
        "checks", "candidate",
    }
    assert set(evidence["dsr_sensitivity"]) == {"low_n", "high_n"} and set(evidence["dsr_sensitivity"]["low_n"]) == {"n", "dsr"}
    assert set(evidence["break_even"]) == {"round_trip_bps", "base_round_trip_bps", "multiple"}
    assert [item["multiplier"] for item in evidence["stress"]] == [1.0, 1.5, 2.0]
    assert set(evidence["stress"][0]) == {"multiplier", "sharpe", "mean_trade_return_pct", "total_return_pct"}
    assert set(evidence["checks"]) == {"bootstrap", "dsr", "stress"}
    gated = [rule for rule in report["rules"] if rule["evidence"] is None]
    assert all(rule["status"] in ("INSUFFICIENT_TRADES", "NEVER_TRADES") for rule in gated)
    assert report["data"]["research_bars"] == 8000
    assert report["uncertainty"]["sharpe_se_annualised_iid"] == pytest.approx(math.sqrt(8760 / 8000))


def test_settings_are_echoed_and_periods_per_year_can_be_given(client, short):
    costs = {"fee_bps_per_side": 4, "spread_bps": 0, "slippage_k": 0}
    report = post_run(client, BTC, min_trades=5, costs=costs, periods_per_year=252).json()
    assert report["settings"]["min_trades"] == 5
    assert report["settings"]["costs"] == {"fee_bps_per_side": 4.0, "spread_bps": 0.0, "slippage_k": 0.0}
    assert (report["settings"]["periods_per_year"], report["settings"]["periods_per_year_inferred"]) == (252.0, False)
    assert report["verdict"]["label"] == "INDISTINGUISHABLE_FROM_LUCK"


def test_a_run_is_deterministic_and_reproducible_from_the_same_data(tmp_path, data_dir):
    write_capture(data_dir / BTC, random_walk_frame(1000, 0))
    reports = []
    for name in ("first", "second"):
        client = TestClient(create_app(data_dir, state_dir=tmp_path / name))
        reports.append(stable(post_run(client, BTC, min_trades=10).json()))
    assert json.dumps(reports[0], sort_keys=True) == json.dumps(reports[1], sort_keys=True)


# --- the sealed holdout --------------------------------------------------------------------------------


def test_changing_every_holdout_bar_leaves_the_research_report_bit_identical(tmp_path):
    frame = random_walk_frame(1000, 0)
    scrambled = frame.copy()
    scrambled.iloc[800:] = random_walk_frame(1000, 99).iloc[800:].to_numpy()
    reports, files = [], []
    for name, bars in (("original", frame), ("scrambled", scrambled)):
        directory = tmp_path / name
        write_capture(directory / BTC, bars)
        files.append((directory / BTC).read_bytes())
        client = TestClient(create_app(directory, state_dir=tmp_path / f"{name}-state"))
        reports.append(stable(post_run(client, BTC, min_trades=10).json()))
    assert files[0] != files[1], "the holdout bars must really differ"
    assert reports[0]["verdict"]["label"] != "INSUFFICIENT_DATA", "statistics must be in play for this test to bite"
    assert json.dumps(reports[0], sort_keys=True) == json.dumps(reports[1], sort_keys=True)


def test_a_run_seals_the_last_fifth_and_stores_the_range(client, short, state_dir):
    frame = random_walk_frame(1000, 0)
    holdout = post_run(client).json()["data"]["holdout"]
    assert (holdout["start"], holdout["end"], holdout["bars"]) == (epoch(frame, 800), epoch(frame, 999), 200)
    seal = ledger_entries(state_dir)[0]
    assert seal["type"] == "seal" and seal["dataset"] == BTC
    assert (seal["holdout_start"], seal["holdout_end"], seal["holdout_bars"], seal["research_bars"]) == (
        epoch(frame, 800), epoch(frame, 999), 200, 800
    )
    assert len(seal["research_fingerprint"]) == 64
    assert post_run(client).json()["data"]["holdout"]["created_now"] is False


@pytest.mark.parametrize("fraction,research", [(0.1, 900), (0.25, 750), (0.3, 700)])
def test_an_explicit_seal_uses_the_requested_fraction(client, short, fraction, research):
    response = client.post(f"/api/verdict/{short}/seal", json={"holdout_fraction": fraction})
    assert response.status_code == 200
    holdout = response.json()["holdout"]
    assert set(response.json()) == {"holdout"} and holdout["fraction"] == fraction
    assert holdout["bars"] == 1000 - research and holdout["status"] == "unread" and holdout["read_at"] is None
    report = post_run(client).json()
    assert report["data"]["research_bars"] == research and report["data"]["holdout"]["created_now"] is False


def test_sealing_defaults_to_twenty_percent_and_happens_once(client, short):
    assert client.post(f"/api/verdict/{short}/seal").json()["holdout"]["fraction"] == 0.2
    second = client.post(f"/api/verdict/{short}/seal", json={"holdout_fraction": 0.3})
    assert second.status_code == 409 and isinstance(second.json()["detail"], str)
    assert client.get(f"/api/verdict/{short}").json()["holdout"]["fraction"] == 0.2


@pytest.mark.parametrize("fraction", [0.09, 0.31, 0, 1, -0.2, "most"])
def test_seal_fractions_outside_ten_to_thirty_percent_are_rejected(client, short, fraction):
    response = client.post(f"/api/verdict/{short}/seal", json={"holdout_fraction": fraction})
    assert response.status_code == 422 and isinstance(response.json()["detail"], list)
    assert client.get(f"/api/verdict/{short}").json()["sealed"] is False


def test_captures_under_a_hundred_bars_cannot_be_sealed_or_judged(data_dir, client, state_dir):
    write_capture(data_dir / BTC, random_walk_frame(99, 0))
    write_capture(data_dir / ETH, random_walk_frame(100, 0))
    for response in (client.post(f"/api/verdict/{encode_id(BTC)}/seal"), post_run(client, BTC)):
        assert response.status_code == 422 and "100 bars" in response.json()["detail"]
    assert not state_dir.exists(), "a refused run examined no data, so it logs nothing"
    report = post_run(client, ETH).json()
    assert report["data"]["research_bars"] == 80 and report["verdict"]["label"] == "INSUFFICIENT_DATA"


def test_bars_captured_after_the_seal_are_forward_data_not_holdout(data_dir, client):
    frame = random_walk_frame(1050, 0)
    write_capture(data_dir / BTC, frame.iloc[:1000])
    first = post_run(client, min_trades=10).json()
    write_capture(data_dir / BTC, frame)
    second = post_run(client, min_trades=10).json()
    assert first["data"]["forward_bars"] == 0 and second["data"]["forward_bars"] == 50
    assert second["data"]["bars_total"] == 1050 and second["data"]["research_bars"] == 800
    assert second["data"]["holdout"]["bars"] == 200 and second["data"]["holdout"]["end"] == epoch(frame, 999)
    assert json.dumps(first["rules"], sort_keys=True) == json.dumps(second["rules"], sort_keys=True)


def test_history_rewritten_before_the_seal_is_refused_but_holdout_edits_are_not(data_dir, client):
    write_capture(data_dir / BTC, random_walk_frame(1000, 0))
    assert post_run(client).status_code == 200
    edit_csv_value(data_dir / BTC, bar=950)
    assert post_run(client).status_code == 200
    edit_csv_value(data_dir / BTC, bar=10)
    response = post_run(client)
    assert response.status_code == 409
    assert response.json() == {"detail": "the bars before the seal changed since sealing"}


def test_a_replaced_or_truncated_capture_fails_the_fingerprint(data_dir, client):
    write_capture(data_dir / BTC, random_walk_frame(1000, 0))
    assert post_run(client).status_code == 200
    write_capture(data_dir / BTC, random_walk_frame(1000, 1))
    assert post_run(client).status_code == 409
    write_capture(data_dir / BTC, random_walk_frame(1000, 0).iloc[:500])
    assert post_run(client).status_code == 409


def test_the_legacy_research_route_stops_at_the_seal_and_says_so_only_when_sealed(data_dir, client):
    write_capture(data_dir / BTC, random_walk_frame(1000, 0))
    write_capture(data_dir / ETH, random_walk_frame(1000, 1))
    ids = [encode_id(BTC), encode_id(ETH)]
    before = client.post("/api/research/run", json={"dataset_ids": ids}).json()
    assert "sealed_holdouts" not in before["metadata"] and [asset["rows"] for asset in before["assets"]] == [1000, 1000]
    client.post(f"/api/verdict/{ids[0]}/seal", json={"holdout_fraction": 0.25})
    after = client.post("/api/research/run", json={"dataset_ids": ids}).json()
    assert after["metadata"]["sealed_holdouts"] == [{"dataset_id": ids[0], "excluded_bars": 250}]
    assert [asset["rows"] for asset in after["assets"]] == [750, 1000]
    only_eth = client.post("/api/research/run", json={"dataset_ids": [ids[1]]}).json()
    assert "sealed_holdouts" not in only_eth["metadata"]
    assert {key: value for key, value in after["metadata"].items() if key != "sealed_holdouts"} == before["metadata"]


def test_explorer_routes_still_show_every_bar(client, short):
    client.post(f"/api/verdict/{short}/seal")
    assert client.get(f"/api/datasets/{short}/bars").json()["rows"] == 1000


# --- the ledger and N (acceptance) ------------------------------------------------------------------------


def test_changing_costs_and_settings_never_changes_n(client, short):
    seen = []
    for body in (
        {},
        {"costs": {"fee_bps_per_side": 50, "spread_bps": 5, "slippage_k": 1}},
        {"min_trades": 5, "costs": {"fee_bps_per_side": 0, "spread_bps": 0, "slippage_k": 0}, "periods_per_year": 365},
    ):
        seen.append(post_run(client, BTC, **body).json()["ledger"])
    assert [item["trials_dataset"] for item in seen] == [GRID_SIZE] * 3
    assert [item["runs_dataset"] for item in seen] == [1, 2, 3]
    assert [item["trials_total"] for item in seen] == [GRID_SIZE] * 3
    assert client.get(f"/api/verdict/{short}").json()["ledger"] == {
        "trials_dataset": 16, "trials_total": 16, "runs_dataset": 3, "intact": True
    }


def test_n_is_not_a_request_field(client, short):
    report = post_run(client, BTC, trials=1, n=1, ledger={"trials_dataset": 1}).json()
    assert report["ledger"]["trials_dataset"] == GRID_SIZE


def test_a_second_dataset_adds_its_own_trials_and_a_failed_run_still_counts(data_dir, client, short, monkeypatch):
    write_capture(data_dir / ETH, random_walk_frame(1000, 1))
    post_run(client, BTC)
    post_run(client, ETH)
    overview = client.get(f"/api/verdict/{short}").json()["ledger"]
    assert (overview["trials_dataset"], overview["trials_total"]) == (16, 32)

    write_capture(data_dir / "SOL.csv", random_walk_frame(1000, 2))
    monkeypatch.setattr(engine, "lookahead_probe", boom)
    failed = post_run(client, "SOL.csv")
    assert failed.status_code == 500
    assert isinstance(failed.json()["detail"], str) and "boom" not in failed.json()["detail"]
    monkeypatch.undo()
    view = client.get(f"/api/verdict/{encode_id('SOL.csv')}").json()
    assert view["ledger"] == {"trials_dataset": 16, "trials_total": 48, "runs_dataset": 1, "intact": True}
    assert view["latest"] is None
    entries = client.get(f"/api/verdict/{encode_id('SOL.csv')}/ledger").json()["entries"]
    assert [entry["type"] for entry in entries] == ["seal", "run"] and "failed (boom)" in entries[1]["summary"]


def test_a_failed_run_does_not_make_an_earlier_candidate_stale(candidate, monkeypatch):
    monkeypatch.setattr(engine, "lookahead_probe", boom)
    assert post_run(candidate.client).status_code == 500
    monkeypatch.undo()
    assert freeze(candidate).status_code == 200


def test_a_lookahead_failure_is_logged_and_answers_500(data_dir, client, state_dir, monkeypatch):
    write_capture(data_dir / BTC, random_walk_frame(1000, 0))
    cheat = {
        "id": "cheat", "family": "cheat", "name": "cheat", "parameters": {},
        "target_fn": lambda frame: (frame["close"].shift(-1) > frame["close"]).astype(float),
    }
    monkeypatch.setattr(service, "strategy_permutations", lambda: [cheat, *engine.strategy_permutations()])
    response = post_run(client)
    assert response.status_code == 500 and response.json() == {"detail": "look-ahead integrity check failed"}
    run = ledger_entries(state_dir)[-1]
    assert run["type"] == "run" and run["status"] == "failed" and "look-ahead" in run["error"]
    assert len(run["trials"]) == GRID_SIZE + 1 and run["report"] is None


def test_n_survives_a_restart_and_the_ledger_is_shared_between_app_instances(data_dir, state_dir, client, short):
    post_run(client)
    post_run(client, costs={"fee_bps_per_side": 1})
    restarted = TestClient(create_app(data_dir, state_dir=state_dir))
    assert restarted.get(f"/api/verdict/{short}").json() == client.get(f"/api/verdict/{short}").json()
    assert restarted.get(f"/api/verdict/{short}").json()["ledger"]["runs_dataset"] == 2
    assert restarted.post(f"/api/verdict/{short}/seal").status_code == 409
    post_run(restarted)
    assert client.get(f"/api/verdict/{short}").json()["ledger"]["runs_dataset"] == 3


def test_the_ledger_endpoint_lists_trial_keys_and_the_newest_entries_oldest_first(data_dir, client, short):
    write_capture(data_dir / ETH, random_walk_frame(1000, 1))
    for _ in range(3):
        post_run(client)
    post_run(client, ETH)
    body = client.get(f"/api/verdict/{short}/ledger").json()
    assert set(body) == {"intact", "total_entries", "trials", "entries"} and body["intact"] is True
    assert body["total_entries"] == 4
    assert body["trials"]["dataset"] == 16 and body["trials"]["total"] == 32
    key = body["trials"]["keys"][0]
    assert set(key) == {"key", "rule_id", "first_seen", "runs"} and key["key"] == f"{BTC}::{key['rule_id']}"
    assert isinstance(key["first_seen"], int) and key["runs"] == 3
    assert [entry["type"] for entry in body["entries"]] == ["seal", "run", "run", "run"]
    assert [entry["seq"] for entry in body["entries"]] == sorted(entry["seq"] for entry in body["entries"])
    assert body["entries"][1]["summary"].endswith("INSUFFICIENT_DATA, 16 rules, costs 10/1/0.1")
    assert body["entries"][1]["prev"] == body["entries"][0]["hash"]
    newest = client.get(f"/api/verdict/{short}/ledger", params={"limit": 2}).json()["entries"]
    assert [entry["seq"] for entry in newest] == [body["entries"][2]["seq"], body["entries"][3]["seq"]]


@pytest.mark.parametrize("limit", [0, 501, -1, "many"])
def test_ledger_limit_is_bounded(client, short, limit):
    assert client.get(f"/api/verdict/{short}/ledger", params={"limit": limit}).status_code == 422


def test_a_tampered_ledger_is_reported_and_refuses_every_mutation(data_dir, client, short, state_dir):
    write_capture(data_dir / ETH, random_walk_frame(1000, 1))
    post_run(client)
    post_run(client)
    path = state_dir / "ledger.jsonl"
    lines = path.read_text().splitlines()
    path.write_text("\n".join([lines[0], lines[2], lines[1]]) + "\n")
    overview = client.get(f"/api/verdict/{short}")
    assert overview.status_code == 200 and overview.json()["ledger"]["intact"] is False
    assert client.get(f"/api/verdict/{short}/ledger").json()["intact"] is False
    refused = [
        post_run(client),
        post_run(client, ETH),
        client.post(f"/api/verdict/{encode_id(ETH)}/seal"),
        client.post(f"/api/verdict/{short}/freeze", json={"run_id": "r-2", "rule_ids": ["sma-5-20"]}),
        client.post(f"/api/verdict/{short}/holdout/read", json={"freeze_id": "f-3"}),
    ]
    assert [response.status_code for response in refused] == [409] * 5
    assert {response.json()["detail"] for response in refused} == {"ledger integrity check failed"}
    assert path.read_text().splitlines() == [lines[0], lines[2], lines[1]]
    research = client.post("/api/research/run", json={"dataset_ids": [short]}).json()
    assert research["metadata"]["sealed_holdouts"][0]["excluded_bars"] == 200


def test_the_overview_before_any_run_reports_defaults_and_never_writes(client, short, state_dir):
    body = client.get(f"/api/verdict/{short}").json()
    assert set(body) == {"dataset", "sealed", "holdout", "ledger", "latest", "freeze", "holdout_read", "defaults"}
    assert body["dataset"] == {"id": short, "symbol": "BINANCE_BTCUSDT", "timeframe": "60", "path": BTC, "rows": 1000}
    assert (body["sealed"], body["holdout"], body["latest"], body["freeze"], body["holdout_read"]) == (
        False, None, None, None, None
    )
    assert body["ledger"] == {"trials_dataset": 0, "trials_total": 0, "runs_dataset": 0, "intact": True}
    defaults = body["defaults"]
    assert {key: value for key, value in defaults.items() if key != "cost_notes"} == {
        "min_trades": 30,
        "holdout_fraction": 0.2,
        "costs": {"fee_bps_per_side": 10.0, "spread_bps": 1.0, "slippage_k": 0.1},
        "bootstrap_replicates": 2000,
        "alpha": 0.05,
        "dsr_threshold": 0.95,
        "stress_multipliers": [1.0, 1.5, 2.0],
    }
    notes = {note["field"]: note for note in defaults["cost_notes"]}
    assert list(notes) == ["fee_bps_per_side", "spread_bps", "slippage_k"]
    assert notes["fee_bps_per_side"]["basis"].startswith("Binance spot taker, regular tier (VIP 0): 0.10% per side")
    assert notes["fee_bps_per_side"]["value"] == 10.0 and "Verify your own tier" in notes["fee_bps_per_side"]["basis"]
    assert notes["spread_bps"]["basis"] == "Placeholder: captures contain no bid/ask data."
    assert client.get(f"/api/verdict/{short}/ledger").json()["entries"] == []
    assert not state_dir.exists()


def test_the_overview_returns_the_latest_report_and_the_holdout_status(client, short):
    report = post_run(client).json()
    body = client.get(f"/api/verdict/{short}").json()
    assert body["sealed"] is True and body["latest"] == report
    assert body["holdout"] == {key: report["data"]["holdout"][key] for key in body["holdout"]}
    assert body["ledger"] == report["ledger"]


def test_the_default_state_dir_is_hidden_inside_the_data_dir(data_dir):
    write_capture(data_dir / BTC, random_walk_frame(1000, 0))
    client = TestClient(create_app(data_dir))
    post_run(client)
    assert (data_dir / ".tvdata-verdict" / "ledger.jsonl").exists()
    assert client.get("/api/health").json()["dataset_count"] == 1
    assert [item["path"] for item in client.get("/api/datasets").json()["datasets"]] == [BTC]


# --- freeze, the single holdout read and forward data (acceptance) -----------------------------------------


def test_the_holdout_cannot_be_read_without_a_freeze(candidate, client, short):
    response = read_holdout(candidate, "f-3")
    assert response.status_code == 409 and "freeze" in response.json()["detail"]
    assert candidate.client.get(f"/api/verdict/{candidate.id}").json()["holdout"]["status"] == "unread"
    unsealed = client.post(f"/api/verdict/{short}/holdout/read", json={"freeze_id": "f-3"})
    assert unsealed.status_code == 409 and "no sealed holdout" in unsealed.json()["detail"]


def test_freezing_needs_the_latest_completed_candidate_run_and_candidate_rules(candidate):
    before = len(ledger_entries(candidate.state))
    wrong_rule = freeze(candidate, [candidate.loser])
    assert wrong_rule.status_code == 422 and "is not a candidate" in wrong_rule.json()["detail"]
    unknown = freeze(candidate, ["sma-1-2"])
    assert unknown.status_code == 422 and unknown.json()["detail"] == "unknown rule id: sma-1-2"
    stale = freeze(candidate, run_id="r-1")
    assert stale.status_code == 422 and "not the latest completed run" in stale.json()["detail"]
    run_id = candidate.report["run_id"]
    for body in (
        {"run_id": run_id, "rule_ids": []},
        {"run_id": run_id, "rule_ids": ["sma-5-20", "sma-10-20", "sma-5-50"]},
        {"run_id": run_id, "rule_ids": ["sma-5-20", "sma-5-20"]},
        {"rule_ids": ["sma-5-20"]},
    ):
        bad = candidate.client.post(f"/api/verdict/{candidate.id}/freeze", json=body)
        assert bad.status_code == 422 and isinstance(bad.json()["detail"], list)
    assert len(ledger_entries(candidate.state)) == before


def test_only_a_candidate_run_can_be_frozen(client, short):
    body = {"run_id": "r-2", "rule_ids": ["sma-5-20"]}
    assert client.post(f"/api/verdict/{short}/freeze", json=body).status_code == 422
    report = post_run(client).json()
    insufficient = client.post(
        f"/api/verdict/{short}/freeze", json={"run_id": report["run_id"], "rule_ids": ["sma-5-20"]}
    )
    assert insufficient.status_code == 422
    assert insufficient.json()["detail"] == f"run {report['run_id']} is INSUFFICIENT_DATA; only a CANDIDATE run can be frozen"


def test_a_newer_completed_run_makes_the_older_candidate_run_stale(candidate):
    newer = post_run(candidate.client).json()
    assert newer["run_id"] != candidate.report["run_id"]
    stale = freeze(candidate)
    assert stale.status_code == 422 and newer["run_id"] in stale.json()["detail"]
    assert freeze(candidate, run_id=newer["run_id"]).status_code == 200


def test_a_valid_freeze_records_the_rules_settings_hash_and_forward_start(candidate):
    rule_ids = candidate.winners[:2]
    response = freeze(candidate, rule_ids)
    assert response.status_code == 200
    frozen = strict_json(response)
    assert set(frozen) == {"id", "run_id", "rule_ids", "rules", "frozen_at", "forward_start", "hash"}
    assert frozen["rule_ids"] == rule_ids and frozen["run_id"] == candidate.report["run_id"]
    assert [set(rule) for rule in frozen["rules"]] == [{"id", "name", "family", "parameters"}] * len(rule_ids)
    assert frozen["forward_start"] == epoch(FULL_TRENDING, 9999) and isinstance(frozen["frozen_at"], int)
    payload = {
        "rules": frozen["rules"],
        "costs": candidate.report["settings"]["costs"],
        "min_trades": 30,
        "periods_per_year": candidate.report["settings"]["periods_per_year"],
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert frozen["hash"] == digest
    entry = ledger_entries(candidate.state)[-1]
    assert entry["type"] == "freeze" and entry["frozen_at_bar"] == frozen["forward_start"]
    assert candidate.client.get(f"/api/verdict/{candidate.id}").json()["freeze"] == frozen


def test_a_second_freeze_is_refused_even_for_different_rules(candidate):
    assert freeze(candidate, candidate.winners[:1]).status_code == 200
    again = freeze(candidate, candidate.winners[:1])
    assert again.status_code == 409 and "cannot be replaced" in again.json()["detail"]
    assert freeze(candidate, candidate.winners[-1:]).status_code == 409


def test_the_holdout_is_read_once_and_the_second_read_fails(candidate):
    frozen = freeze(candidate, candidate.winners[:2]).json()
    wrong = read_holdout(candidate, "f-999")
    assert wrong.status_code == 422 and "unknown freeze_id" in wrong.json()["detail"]
    assert candidate.client.get(f"/api/verdict/{candidate.id}").json()["holdout"]["status"] == "unread"

    first = read_holdout(candidate, frozen["id"])
    assert first.status_code == 200
    result = strict_json(first)
    assert set(result) == {"freeze_id", "read_at", "start", "end", "bars", "rules", "caveat", "sharpe_se_annualised_iid"}
    assert (result["start"], result["end"], result["bars"]) == (epoch(FULL_TRENDING, 8000), epoch(FULL_TRENDING, 9999), 2000)
    assert [rule["id"] for rule in result["rules"]] == frozen["rule_ids"]
    assert set(result["rules"][0]) == {
        "id", "name", "trades", "closed_trades", "exposure_pct", "net_return_pct", "sharpe", "sharpe_se",
        "mean_trade_return_pct", "buy_hold_return_pct",
    }
    assert result["caveat"].startswith("With 2000 holdout bars the annualised Sharpe standard error is about +/-")
    assert result["caveat"].endswith("This is a sanity check, not a verdict.")
    assert result["sharpe_se_annualised_iid"] == pytest.approx(math.sqrt(8760 / 2000))
    assert not any(re.search(r"pass|fail|verdict|candidate", key) for key in result["rules"][0])
    closes = load_ohlcv(candidate.data / BTC)["close"].to_numpy()
    assert result["rules"][0]["buy_hold_return_pct"] == pytest.approx((closes[9999] / closes[7999] - 1) * 100)

    second = read_holdout(candidate, frozen["id"])
    assert second.status_code == 409
    assert re.fullmatch(
        r"holdout already read on \d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ; it cannot be read again", second.json()["detail"]
    )
    assert freeze(candidate, candidate.winners[-1:]).status_code == 409
    assert read_holdout(candidate, "f-7").status_code == 409

    overview = candidate.client.get(f"/api/verdict/{candidate.id}").json()
    assert overview["holdout_read"] == result and overview["holdout"]["status"] == "read"
    assert overview["holdout"]["read_at"] == result["read_at"]
    assert overview["latest"]["data"]["holdout"]["status"] == "read"
    reads = holdout_reads(candidate.state)
    assert len(reads) == 1 and reads[0]["result"] == result and reads[0]["freeze_id"] == frozen["id"]
    summaries = candidate.client.get(f"/api/verdict/{candidate.id}/ledger").json()["entries"]
    assert any("Read the holdout once" in entry["summary"] for entry in summaries)


def test_concurrent_reads_let_exactly_one_through(candidate, monkeypatch):
    frozen = freeze(candidate).json()
    real = service.read_holdout

    def slow(*args, **kwargs):
        time.sleep(0.3)
        return real(*args, **kwargs)

    monkeypatch.setattr(service, "read_holdout", slow)
    statuses, barrier = [], threading.Barrier(2)

    def attempt():
        session = SimpleNamespace(client=TestClient(candidate.client.app), id=candidate.id)
        barrier.wait()
        statuses.append(read_holdout(session, frozen["id"]).status_code)

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(statuses) == [200, 409]
    assert len(holdout_reads(candidate.state)) == 1


def test_a_failed_holdout_computation_consumes_nothing(candidate, monkeypatch):
    frozen = freeze(candidate).json()
    real = service.read_holdout
    monkeypatch.setattr(service, "read_holdout", boom)
    failed = read_holdout(candidate, frozen["id"])
    assert failed.status_code == 500 and "boom" not in failed.json()["detail"]
    assert not holdout_reads(candidate.state)
    monkeypatch.setattr(service, "read_holdout", real)
    assert read_holdout(candidate, frozen["id"]).status_code == 200


def test_a_holdout_read_is_refused_when_the_history_before_the_seal_changed(candidate):
    frozen = freeze(candidate).json()
    edit_csv_value(candidate.data / BTC, bar=10)
    response = read_holdout(candidate, frozen["id"])
    assert response.status_code == 409 and "changed since sealing" in response.json()["detail"]
    assert not holdout_reads(candidate.state)


def test_forward_data_needs_a_freeze_then_evaluates_only_bars_captured_after_it(candidate):
    assert candidate.client.get(f"/api/verdict/{candidate.id}/forward").status_code == 409
    write_capture(candidate.data / BTC, FULL_TRENDING.iloc[:10100])
    latest = post_run(candidate.client).json()
    assert latest["data"]["forward_bars"] == 100
    frozen = freeze(candidate, run_id=latest["run_id"]).json()
    assert frozen["forward_start"] == epoch(FULL_TRENDING, 10099)

    waiting = strict_json(candidate.client.get(f"/api/verdict/{candidate.id}/forward"))
    assert set(waiting) == {"freeze", "start", "end", "bars", "waiting", "rules", "caveat", "sharpe_se_annualised_iid"}
    assert waiting["freeze"] == frozen and waiting["waiting"] is True and waiting["bars"] == 0 and waiting["end"] is None
    assert waiting["start"] == frozen["forward_start"] and waiting["sharpe_se_annualised_iid"] is None
    assert all(rule["trades"] == 0 and rule["sharpe"] is None for rule in waiting["rules"])

    entries_before = len(ledger_entries(candidate.state))
    write_capture(candidate.data / BTC, FULL_TRENDING.iloc[:10150])
    live = strict_json(candidate.client.get(f"/api/verdict/{candidate.id}/forward"))
    assert live["waiting"] is False and live["bars"] == 50 and live["end"] == epoch(FULL_TRENDING, 10149)
    assert live["sharpe_se_annualised_iid"] == pytest.approx(math.sqrt(8760 / 50))
    assert [rule["id"] for rule in live["rules"]] == frozen["rule_ids"]
    assert live["caveat"].startswith("With 50 forward bars")
    assert len(ledger_entries(candidate.state)) == entries_before, "forward results are never stored"

    result = read_holdout(candidate, frozen["id"]).json()
    assert (result["end"], result["bars"]) == (epoch(FULL_TRENDING, 9999), 2000), "forward bars never enter the holdout"


# --- protocol ---------------------------------------------------------------------------------------------

TRAVERSAL_IDS = [
    "..",
    "../../etc/passwd",
    "%2e%2e%2f%2e%2e%2fetc%2fpasswd",
    "..%2f..%2fetc",
    encode_id("../secret.csv"),
    encode_id("/etc/passwd"),
    "nope",
]


@pytest.mark.parametrize("dataset_id", TRAVERSAL_IDS)
def test_dataset_ids_shaped_like_paths_are_404_and_reach_no_file(client, state_dir, tmp_path, dataset_id):
    (tmp_path / "secret.csv").write_text("time,open,high,low,close,volume\n")
    calls = [
        client.get(f"/api/verdict/{dataset_id}"),
        client.get(f"/api/verdict/{dataset_id}/ledger"),
        client.get(f"/api/verdict/{dataset_id}/forward"),
        client.post(f"/api/verdict/{dataset_id}/seal"),
        client.post(f"/api/verdict/{dataset_id}/freeze", json={"run_id": "r-2", "rule_ids": ["sma-5-20"]}),
        client.post(f"/api/verdict/{dataset_id}/holdout/read", json={"freeze_id": "f-3"}),
        client.post("/api/verdict/run", json={"dataset_id": dataset_id}),
    ]
    assert [response.status_code for response in calls] == [404] * 7
    assert {response.json()["detail"] for response in calls} <= {"dataset not found", "Not Found"}
    assert not state_dir.exists()


def test_unknown_datasets_are_404_with_the_standard_message(client):
    response = client.get(f"/api/verdict/{encode_id('nothing.csv')}")
    assert response.status_code == 404 and response.json() == {"detail": "dataset not found"}


def test_unreadable_captures_are_422_and_log_nothing(data_dir, client, state_dir):
    (data_dir / "bad.csv").write_text("x,y\n1,2\n")
    bad = encode_id("bad.csv")
    for response in (
        client.get(f"/api/verdict/{bad}"),
        client.post("/api/verdict/run", json={"dataset_id": bad}),
        client.post(f"/api/verdict/{bad}/seal"),
    ):
        assert response.status_code == 422 and isinstance(response.json()["detail"], str)
    assert not state_dir.exists()


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"dataset_id": 3},
        {"dataset_id": "x", "min_trades": 0},
        {"dataset_id": "x", "min_trades": 1001},
        {"dataset_id": "x", "min_trades": 2.5},
        {"dataset_id": "x", "costs": {"fee_bps_per_side": -1}},
        {"dataset_id": "x", "costs": {"fee_bps_per_side": 500.1}},
        {"dataset_id": "x", "costs": {"spread_bps": 1000.1}},
        {"dataset_id": "x", "costs": {"slippage_k": 5.1}},
        {"dataset_id": "x", "costs": {"slippage_k": "cheap"}},
        {"dataset_id": "x", "periods_per_year": 0},
        {"dataset_id": "x", "periods_per_year": -5},
    ],
)
def test_run_validation_errors_use_the_standard_422_list(client, body):
    response = client.post("/api/verdict/run", json=body)
    assert response.status_code == 422 and isinstance(response.json()["detail"], list)


def test_run_accepts_the_documented_boundaries_and_rejects_non_finite_numbers(client, short):
    edge = {"min_trades": 1000, "costs": {"fee_bps_per_side": 500, "spread_bps": 1000, "slippage_k": 5}}
    assert post_run(client, BTC, **edge).status_code == 200
    assert post_run(client, BTC, min_trades=1, costs={"fee_bps_per_side": 0, "spread_bps": 0, "slippage_k": 0}).status_code == 200
    body = '{"dataset_id": "x", "costs": {"fee_bps_per_side": NaN}}'
    response = client.post("/api/verdict/run", content=body, headers={"Content-Type": "application/json"})
    assert response.status_code == 422 and strict_json(response)["detail"][0]["input"] is None


def test_freeze_and_read_bodies_are_validated(client, short):
    assert client.post(f"/api/verdict/{short}/holdout/read", json={}).status_code == 422
    assert client.post(f"/api/verdict/{short}/freeze", json={"run_id": "r-2"}).status_code == 422


def test_openapi_lists_the_verdict_operations(client):
    paths = client.get("/api/openapi.json").json()["paths"]
    assert set(paths["/api/verdict/run"]) == {"post"}
    assert set(paths["/api/verdict/{dataset_id}"]) == {"get"}
    assert set(paths["/api/verdict/{dataset_id}/ledger"]) == {"get"}
    assert set(paths["/api/verdict/{dataset_id}/forward"]) == {"get"}
    for tail in ("seal", "freeze", "holdout/read"):
        assert set(paths[f"/api/verdict/{{dataset_id}}/{tail}"]) == {"post"}


def test_serve_accepts_a_state_dir(data_dir, tmp_path, monkeypatch):
    assert build_parser().parse_args(["serve"]).state_dir is None
    assert build_parser().parse_args(["serve", "--state-dir", "keep"]).state_dir == "keep"
    uvicorn = pytest.importorskip("uvicorn")
    captured = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, **kwargs: captured.update(app=app))
    kept = tmp_path / "kept"
    assert main(["serve", "--data-dir", str(data_dir), "--state-dir", str(kept)]) == 0
    write_capture(data_dir / BTC, random_walk_frame(1000, 0))
    assert post_run(TestClient(captured["app"])).status_code == 200
    assert (kept / "ledger.jsonl").exists() and not (data_dir / ".tvdata-verdict").exists()


def test_responses_are_strict_json(client, short):
    report = strict_json(client.post("/api/verdict/run", json={"dataset_id": short, "min_trades": 1}))
    assert report["rules"] and strict_json(client.get(f"/api/verdict/{short}"))["latest"] == report
