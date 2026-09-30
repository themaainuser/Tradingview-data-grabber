import hashlib
import json
import os
import pathlib
import sys
import threading
from datetime import datetime, timezone

import numpy as np
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from tradingview_data import ledger as ledger_module  # noqa: E402
from tradingview_data.ledger import (  # noqa: E402
    GENESIS,
    Ledger,
    LedgerIntegrityError,
    canonical_json,
    describe,
    entry_hash,
    plain,
)

DATASET = "BINANCE_BTCUSDT/60.csv"
COSTS = {"fee_bps_per_side": 10.0, "spread_bps": 1.0, "slippage_k": 0.1}


def seal_body():
    return {
        "fraction": 0.2,
        "holdout_start": 800,
        "holdout_end": 999,
        "holdout_bars": 200,
        "research_bars": 800,
        "research_fingerprint": "f" * 64,
    }


def run_body(run_id, rules=("sma-5-20", "sma-10-20"), status="completed", error=None):
    return {
        "run_id": run_id,
        "status": status,
        "error": error,
        "label": "INSUFFICIENT_DATA" if status == "completed" else None,
        "settings": {"costs": COSTS, "min_trades": 30},
        "trials": [
            {"key": f"{DATASET}::{rule}", "rule_id": rule, "family": "x", "parameters": {}, "outcome": "NEVER_TRADES"}
            for rule in rules
        ],
    }


def append(ledger, kind, dataset, body):
    with ledger.transaction() as tx:
        return tx.append(kind, dataset, body)


def filled(tmp_path):
    ledger = Ledger(tmp_path / "state")
    append(ledger, "seal", DATASET, seal_body())
    append(ledger, "run", DATASET, run_body("r-2"))
    append(ledger, "run", DATASET, run_body("r-3", rules=("sma-5-20", "rsi-20-50")))
    return ledger


def lines_of(ledger):
    return ledger.path.read_text().splitlines()


def test_entries_are_chained_by_sha256_over_prev_and_canonical_body(tmp_path):
    ledger = filled(tmp_path)
    entries = [json.loads(line) for line in lines_of(ledger)]
    assert [entry["seq"] for entry in entries] == [1, 2, 3]
    assert entries[0]["prev"] == GENESIS
    for before, entry in zip(entries, entries[1:]):
        assert entry["prev"] == before["hash"]
    for entry in entries:
        body = {key: value for key, value in entry.items() if key != "hash"}
        expected = hashlib.sha256((entry["prev"] + json.dumps(body, sort_keys=True, separators=(",", ":"))).encode()).hexdigest()
        assert entry["hash"] == expected == entry_hash(entry["prev"], entry)
        assert set(entry) >= {"seq", "type", "at", "dataset", "prev", "hash"}
        assert datetime.strptime(entry["at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def test_a_ledger_that_does_not_exist_yet_is_empty_and_intact_and_is_created_on_first_append(tmp_path):
    ledger = Ledger(tmp_path / "deep" / "state")
    state = ledger.read()
    assert state.intact and state.entries == [] and state.trials() == 0
    assert not ledger.path.exists()
    append(ledger, "seal", DATASET, seal_body())
    assert ledger.path.exists()


def test_state_is_derived_from_the_ledger_and_survives_a_restart(tmp_path):
    filled(tmp_path)
    state = Ledger(tmp_path / "state").read()
    record = state.dataset(DATASET)
    assert state.intact and len(record.runs) == 2 and record.seal["holdout_bars"] == 200
    assert state.trials(DATASET) == 3 and state.trials() == 3
    assert state.counts(DATASET) == {"trials_dataset": 3, "trials_total": 3, "runs_dataset": 2, "intact": True}
    counts = {key["rule_id"]: key["runs"] for key in record.trial_keys.values()}
    assert counts == {"sma-5-20": 2, "sma-10-20": 1, "rsi-20-50": 1}


def test_n_counts_distinct_dataset_rule_pairs_including_failed_runs_and_other_datasets(tmp_path):
    ledger = filled(tmp_path)
    append(ledger, "run", "ETH.csv", run_body("r-4", rules=("sma-5-20",)) | {"trials": [
        {"key": "ETH.csv::sma-5-20", "rule_id": "sma-5-20", "family": "x", "parameters": {}, "outcome": "RUN_FAILED"}
    ]})
    append(ledger, "run", DATASET, run_body("r-5", status="failed", error="boom"))
    state = ledger.read()
    assert state.trials(DATASET) == 3 and state.trials("ETH.csv") == 1 and state.trials() == 4
    assert len(state.dataset(DATASET).runs) == 3 and len(state.dataset(DATASET).completed_runs) == 2


def test_first_seal_freeze_and_read_win(tmp_path):
    ledger = Ledger(tmp_path)
    append(ledger, "seal", DATASET, seal_body())
    append(ledger, "seal", DATASET, {**seal_body(), "holdout_bars": 5})
    record = ledger.read().dataset(DATASET)
    assert record.seal["holdout_bars"] == 200 and len(record.entries) == 2


@pytest.mark.parametrize(
    "tamper",
    [
        pytest.param(lambda lines: [lines[0].replace('"holdout_bars":200', '"holdout_bars":20'), *lines[1:]], id="edit-a-value"),
        pytest.param(lambda lines: [lines[0], *lines[2:]], id="remove-a-middle-line"),
        pytest.param(lambda lines: lines[1:], id="remove-the-first-line"),
        pytest.param(lambda lines: [lines[0], lines[2], lines[1]], id="reorder"),
        pytest.param(lambda lines: [*lines, "{not json"], id="garbage-line"),
        pytest.param(lambda lines: [lines[0], "", *lines[1:]], id="blank-line"),
        pytest.param(lambda lines: [lines[0], json.dumps({"type": "run"}), *lines[1:]], id="foreign-entry"),
        pytest.param(lambda lines: [lines[0], lines[1], lines[1]], id="duplicate-line"),
    ],
)
def test_any_edit_removal_or_reorder_breaks_the_chain_and_blocks_appends(tmp_path, tamper):
    ledger = filled(tmp_path)
    ledger.path.write_text("\n".join(tamper(lines_of(ledger))) + "\n")
    state = ledger.read()
    assert state.intact is False and state.problem
    assert state.counts(DATASET)["intact"] is False
    with pytest.raises(LedgerIntegrityError, match="ledger integrity check failed"):
        append(ledger, "run", DATASET, run_body("r-9"))


def test_a_torn_last_line_is_detected(tmp_path):
    ledger = filled(tmp_path)
    text = ledger.path.read_text()
    ledger.path.write_text(text[: len(text) // 2 + len(text) // 3])
    assert ledger.read().intact is False
    ledger.path.write_text(text.rstrip("\n"))
    state = ledger.read()
    assert state.intact is False and "incomplete" in state.problem


def test_well_formed_entries_still_inform_readers_when_the_chain_is_broken(tmp_path):
    ledger = filled(tmp_path)
    lines = lines_of(ledger)
    ledger.path.write_text("\n".join([lines[0], "{not json", lines[2]]) + "\n")
    state = ledger.read()
    assert not state.intact and state.dataset(DATASET).seal is not None and len(state.dataset(DATASET).runs) == 1


def test_appends_fsync_one_line_and_hold_the_process_lock(tmp_path, monkeypatch):
    synced = []
    real_fsync = os.fsync
    monkeypatch.setattr(ledger_module.os, "fsync", lambda descriptor: synced.append(descriptor) or real_fsync(descriptor))
    ledger = Ledger(tmp_path)
    append(ledger, "seal", DATASET, seal_body())
    assert len(synced) == 1 and len(lines_of(ledger)) == 1
    assert Ledger(tmp_path)._transaction_lock is ledger._transaction_lock


def test_concurrent_writers_never_fork_the_chain(tmp_path):
    ledger = Ledger(tmp_path)

    def writer(name):
        for number in range(15):
            append(Ledger(tmp_path), "run", DATASET, run_body(f"{name}-{number}", rules=(f"{name}-{number}",)))

    threads = [threading.Thread(target=writer, args=(name,)) for name in "xyz"]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    state = ledger.read()
    assert state.intact and [entry["seq"] for entry in state.entries] == list(range(1, 46))
    assert state.trials(DATASET) == 45


def test_plain_makes_numpy_and_non_finite_values_json_safe(tmp_path):
    cleaned = plain({"a": np.float64("nan"), "b": np.array([1.0, np.inf]), "c": (np.int64(3), {"d": float("-inf")})})
    assert cleaned == {"a": None, "b": [1.0, None], "c": [3, {"d": None}]}
    with pytest.raises(ValueError):
        canonical_json({"x": float("nan")})
    ledger = Ledger(tmp_path)
    append(ledger, "seal", DATASET, {**seal_body(), "extra": np.float64("nan")})
    assert ledger.read().intact and json.loads(lines_of(ledger)[0])["extra"] is None


def test_every_entry_type_has_a_plain_sentence(tmp_path):
    ledger = filled(tmp_path)
    append(ledger, "run", DATASET, run_body("r-4", status="failed", error="boom"))
    append(
        ledger,
        "freeze",
        DATASET,
        {"freeze_id": "f-5", "run_id": "r-3", "rules": [{"id": "sma-5-20"}], "rules_hash": "a" * 64, "frozen_at_bar": 1, "settings": {}},
    )
    append(ledger, "holdout_read", DATASET, {"freeze_id": "f-5", "result": {}})
    sentences = [describe(entry) for entry in ledger.read().entries]
    assert sentences[0] == "Sealed the last 200 of 1000 bars as holdout (20%)."
    assert sentences[1] == "Run r-2: INSUFFICIENT_DATA, 2 rules, costs 10/1/0.1"
    assert sentences[3].startswith("Run r-4 failed (boom)")
    assert sentences[4].startswith("Froze sma-5-20 from run r-3") and sentences[5].startswith("Read the holdout once")
    assert describe({"type": "run", "run_id": "x"}).startswith("Unreadable run")
