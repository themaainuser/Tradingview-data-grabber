"""Rules for the verdict endpoints: what may be appended to the ledger, and when.

Each writer runs inside one ledger transaction: it checks the chain, derives state from the ledger,
does its (possibly slow) work and appends, so two requests cannot both pass the same check.  All
state is read back from the ledger; nothing is kept in memory between requests.
"""

from __future__ import annotations

import copy
import hashlib
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, Optional, Sequence

import pandas as pd

from .charts import _epoch_seconds
from .holdout import (
    DEFAULT_FRACTION,
    HistoryChanged,
    Seal,
    forward_result,
    plan_seal,
    read_holdout,
    research_window,
    verify_research_segment,
)
from .ledger import (
    Ledger,
    LedgerIntegrityError,
    LedgerState,
    LedgerTransaction,
    canonical_json,
    describe,
    entry_epoch,
    iso_from_epoch,
    utc_now,
)
from .research import strategy_permutations
from .verdict import (
    ALPHA,
    BOOTSTRAP_REPLICATES,
    CANDIDATE,
    COST_NOTES,
    DEFAULT_MIN_TRADES,
    DSR_THRESHOLD,
    STRESS_MULTIPLIERS,
    Costs,
    IntegrityError,
    LookaheadError,
    evaluate,
    trial_records,
)


class VerdictError(Exception):
    """A request the engine refuses, with the HTTP status and message to answer with."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass(frozen=True)
class DatasetView:
    """A validated capture: its id, ledger key (relative path), identity and parsed bars."""

    id: str
    key: str
    symbol: str
    timeframe: Optional[str]
    frame: pd.DataFrame

    def identity(self) -> dict[str, Any]:
        return {"id": self.id, "symbol": self.symbol, "timeframe": self.timeframe, "path": self.key}


def defaults() -> dict[str, Any]:
    """The settings a run uses unless told otherwise, with the basis of each cost default."""

    return {
        "min_trades": DEFAULT_MIN_TRADES,
        "holdout_fraction": DEFAULT_FRACTION,
        "costs": Costs().as_dict(),
        "cost_notes": [dict(note) for note in COST_NOTES],
        "bootstrap_replicates": BOOTSTRAP_REPLICATES,
        "alpha": ALPHA,
        "dsr_threshold": DSR_THRESHOLD,
        "stress_multipliers": list(STRESS_MULTIPLIERS),
    }


def holdout_view(seal: dict[str, Any], read: Optional[dict[str, Any]]) -> dict[str, Any]:
    """The ``Holdout`` object for a seal entry and (when the holdout was read) its read entry."""

    return {
        "fraction": seal["fraction"],
        "start": seal["holdout_start"],
        "end": seal["holdout_end"],
        "bars": seal["holdout_bars"],
        "sealed_at": entry_epoch(seal),
        "status": "unread" if read is None else "read",
        "read_at": None if read is None else entry_epoch(read),
    }


def freeze_view(entry: dict[str, Any]) -> dict[str, Any]:
    """The ``Freeze`` object for a freeze entry."""

    return {
        "id": entry["freeze_id"],
        "run_id": entry["run_id"],
        "rule_ids": [rule["id"] for rule in entry["rules"]],
        "rules": entry["rules"],
        "frozen_at": entry_epoch(entry),
        "forward_start": entry["frozen_at_bar"],
        "hash": entry["rules_hash"],
    }


def build_report(
    *,
    view: DatasetView,
    seal_entry: dict[str, Any],
    created_now: bool,
    research: pd.DataFrame,
    result: dict[str, Any],
    run_id: str,
    moment: datetime,
    counts: dict[str, Any],
) -> dict[str, Any]:
    """Assemble the ``Report`` from the engine's result and the ledger context of the run."""

    times = _epoch_seconds(research)
    return {
        "run_id": run_id,
        "created_at": int(moment.timestamp()),
        "dataset": view.identity(),
        "verdict": result["verdict"],
        "settings": result["settings"],
        "data": {
            "bars_total": len(view.frame),
            "research_bars": len(research),
            "research_start": int(times[0]),
            "research_end": int(times[-1]),
            "forward_bars": int((_epoch_seconds(view.frame) > seal_entry["holdout_end"]).sum()),
            "holdout": {**holdout_view(seal_entry, None), "created_now": created_now},
        },
        "ledger": counts,
        "rules": result["rules"],
        "statistics": result["statistics"],
        "uncertainty": result["uncertainty"],
        "integrity": result["integrity"],
        "notes": result["notes"],
    }


class VerdictService:
    """The verdict workflow over one ledger."""

    def __init__(self, state_dir: Path) -> None:
        self.ledger = Ledger(state_dir)

    @contextmanager
    def _transaction(self) -> Iterator[LedgerTransaction]:
        with self.ledger.transaction() as tx:
            try:
                tx.require_intact()
            except LedgerIntegrityError as exc:
                raise VerdictError(409, str(exc)) from exc
            yield tx

    @staticmethod
    def _plan_seal(view: DatasetView, fraction: float) -> dict[str, Any]:
        try:
            return plan_seal(view.frame, view.symbol, view.timeframe, fraction)
        except ValueError as exc:
            raise VerdictError(422, str(exc)) from exc

    @staticmethod
    def _verify(view: DatasetView, seal: Seal) -> None:
        try:
            verify_research_segment(view.frame, seal, view.symbol, view.timeframe)
        except HistoryChanged as exc:
            raise VerdictError(409, str(exc)) from exc

    def restrict(self, state: LedgerState, view_key: str, frame: pd.DataFrame) -> tuple[pd.DataFrame, Optional[int]]:
        """``frame`` cut to its research window and the number of bars cut (``None`` when nothing is sealed)."""

        entry = state.dataset(view_key).seal
        if entry is None:
            return frame, None
        research = research_window(frame, Seal.from_entry(entry))
        return research, len(frame) - len(research)

    def overview(self, view: DatasetView) -> dict[str, Any]:
        """Everything the ledger says about ``view``; never appends."""

        state = self.ledger.read()
        record = state.dataset(view.key)
        holdout = holdout_view(record.seal, record.holdout_read) if record.seal else None
        latest = None
        if record.completed_runs:
            latest = copy.deepcopy(record.completed_runs[-1]["report"])
            if holdout is not None:
                latest["data"]["holdout"] = {**holdout, "created_now": latest["data"]["holdout"]["created_now"]}
        return {
            "dataset": {**view.identity(), "rows": len(view.frame)},
            "sealed": record.seal is not None,
            "holdout": holdout,
            "ledger": state.counts(view.key),
            "latest": latest,
            "freeze": freeze_view(record.freeze) if record.freeze else None,
            "holdout_read": record.holdout_read["result"] if record.holdout_read else None,
            "defaults": defaults(),
        }

    def ledger_view(self, view: DatasetView, limit: int) -> dict[str, Any]:
        """The newest ``limit`` ledger entries of ``view`` (oldest first) and its trial keys."""

        state = self.ledger.read()
        record = state.dataset(view.key)
        return {
            "intact": state.intact,
            "total_entries": len(record.entries),
            "trials": {
                "dataset": len(record.trial_keys),
                "total": state.trials(),
                "keys": list(record.trial_keys.values()),
            },
            "entries": [
                {**{key: entry[key] for key in ("seq", "type", "at", "hash", "prev")}, "summary": describe(entry)}
                for entry in record.entries[-limit:]
            ],
        }

    def seal(self, view: DatasetView, fraction: float) -> dict[str, Any]:
        """Seal the last ``fraction`` of the capture as holdout; one seal per dataset."""

        with self._transaction() as tx:
            if tx.state.dataset(view.key).seal is not None:
                raise VerdictError(409, "this dataset already has a sealed holdout")
            entry = tx.append("seal", view.key, self._plan_seal(view, fraction))
            return {"holdout": holdout_view(entry, None)}

    def run(
        self,
        view: DatasetView,
        *,
        min_trades: int,
        costs: Costs,
        periods_per_year: Optional[float],
    ) -> dict[str, Any]:
        """Evaluate the rule grid on the research window and append the run (even a failed one) to the ledger."""

        with self._transaction() as tx:
            record = tx.state.dataset(view.key)
            created_now = record.seal is None
            seal_entry = record.seal or tx.append("seal", view.key, self._plan_seal(view, DEFAULT_FRACTION))
            seal = Seal.from_entry(seal_entry)
            self._verify(view, seal)
            research = research_window(view.frame, seal)
            record = tx.state.dataset(view.key)
            grid = strategy_permutations()
            moment = utc_now()
            run_id = f"r-{tx.state.next_seq}"
            new_keys = {f"{view.key}::{rule['id']}" for rule in grid}
            trials_dataset = len(set(record.trial_keys) | new_keys)
            times = _epoch_seconds(research)
            body: dict[str, Any] = {
                "run_id": run_id,
                "dataset_id": view.id,
                "data_range": {"start": int(times[0]), "end": int(times[-1]), "bars": len(research)},
                "settings": {
                    "costs": costs.as_dict(),
                    "min_trades": min_trades,
                    "periods_per_year": periods_per_year,
                    "periods_per_year_inferred": periods_per_year is None,
                },
            }
            try:
                result = evaluate(
                    research,
                    dataset=view.key,
                    fingerprint=seal.fingerprint,
                    costs=costs,
                    min_trades=min_trades,
                    periods_per_year=periods_per_year,
                    holdout_bars=seal.holdout_bars,
                    trials_dataset=trials_dataset,
                    strategies=grid,
                )
            except Exception as exc:  # noqa: BLE001 - every attempt that examined the data is a trial
                message = str(exc) or type(exc).__name__
                tx.append(
                    "run",
                    view.key,
                    {
                        **body,
                        "status": "failed",
                        "error": message,
                        "label": None,
                        "report": None,
                        "trials": trial_records(view.key, grid, {}),
                    },
                    at=moment,
                )
                if isinstance(exc, LookaheadError):
                    raise VerdictError(500, "look-ahead integrity check failed") from exc
                if isinstance(exc, IntegrityError):
                    raise VerdictError(500, f"integrity check failed: {message}") from exc
                raise VerdictError(500, "the verdict run failed; it was recorded in the ledger as a failed run") from exc
            report = build_report(
                view=view,
                seal_entry=seal_entry,
                created_now=created_now,
                research=research,
                result=result,
                run_id=run_id,
                moment=moment,
                counts={
                    "trials_dataset": trials_dataset,
                    "trials_total": tx.state.trials() - len(record.trial_keys) + trials_dataset,
                    "runs_dataset": len(record.runs) + 1,
                    "intact": True,
                },
            )
            entry = tx.append(
                "run",
                view.key,
                {
                    **body,
                    "settings": {
                        key: result["settings"][key]
                        for key in ("costs", "min_trades", "periods_per_year", "periods_per_year_inferred")
                    },
                    "status": "completed",
                    "error": None,
                    "label": result["verdict"]["label"],
                    "report": report,
                    "trials": result["trials"],
                },
                at=moment,
            )
            return entry["report"]

    def freeze(self, view: DatasetView, run_id: str, rule_ids: Sequence[str]) -> dict[str, Any]:
        """Freeze 1-2 candidate rules of the latest completed run; one freeze per seal."""

        with self._transaction() as tx:
            record = tx.state.dataset(view.key)
            if record.freeze is not None:
                raise VerdictError(409, f"this seal already has a frozen rule set ({record.freeze['freeze_id']}); it cannot be replaced")
            latest = record.completed_runs[-1] if record.completed_runs else None
            if latest is None:
                raise VerdictError(422, "no completed run exists for this dataset")
            if latest["run_id"] != run_id:
                raise VerdictError(422, f"run {run_id} is not the latest completed run ({latest['run_id']})")
            report = latest["report"]
            if report["verdict"]["label"] != CANDIDATE:
                raise VerdictError(422, f"run {run_id} is {report['verdict']['label']}; only a CANDIDATE run can be frozen")
            rules = {rule["id"]: rule for rule in report["rules"]}
            for rule_id in rule_ids:
                rule = rules.get(rule_id)
                if rule is None:
                    raise VerdictError(422, f"unknown rule id: {rule_id}")
                if not (rule["evidence"] and rule["evidence"]["candidate"]):
                    raise VerdictError(422, f"rule {rule_id} is not a candidate in run {run_id}")
            frozen = [{key: rules[rule_id][key] for key in ("id", "name", "family", "parameters")} for rule_id in rule_ids]
            settings = {key: latest["settings"][key] for key in ("costs", "min_trades", "periods_per_year")}
            digest = hashlib.sha256(canonical_json({"rules": frozen, **settings}).encode("utf-8")).hexdigest()
            entry = tx.append(
                "freeze",
                view.key,
                {
                    "freeze_id": f"f-{tx.state.next_seq}",
                    "run_id": run_id,
                    "rules": frozen,
                    "settings": settings,
                    "rules_hash": digest,
                    "frozen_at_bar": int(_epoch_seconds(view.frame)[-1]),
                },
            )
            return freeze_view(entry)

    def read_holdout(self, view: DatasetView, freeze_id: str) -> dict[str, Any]:
        """Evaluate the frozen rules on the holdout.  Allowed once per seal; the lock spans check, compute and append."""

        with self._transaction() as tx:
            record = tx.state.dataset(view.key)
            if record.seal is None:
                raise VerdictError(409, "this dataset has no sealed holdout")
            if record.holdout_read is not None:
                when = iso_from_epoch(entry_epoch(record.holdout_read))
                raise VerdictError(409, f"holdout already read on {when}; it cannot be read again")
            if record.freeze is None:
                raise VerdictError(409, "the holdout can only be read after the rules are frozen; freeze them first")
            if record.freeze["freeze_id"] != freeze_id:
                raise VerdictError(422, f"unknown freeze_id: {freeze_id}")
            seal = Seal.from_entry(record.seal)
            self._verify(view, seal)
            settings = record.freeze["settings"]
            moment = utc_now()
            try:
                window = read_holdout(
                    view.frame, seal, record.freeze["rules"], Costs(**settings["costs"]), settings["periods_per_year"]
                )
            except Exception as exc:  # noqa: BLE001 - nothing was shown, so nothing is appended
                raise VerdictError(500, "the holdout evaluation failed; the holdout was not read") from exc
            result = {"freeze_id": freeze_id, "read_at": int(moment.timestamp()), **window}
            entry = tx.append("holdout_read", view.key, {"freeze_id": freeze_id, "result": result}, at=moment)
            return entry["result"]

    def forward(self, view: DatasetView) -> dict[str, Any]:
        """Evaluate the frozen rules on bars captured since the freeze; never stored."""

        record = self.ledger.read().dataset(view.key)
        if record.freeze is None:
            raise VerdictError(409, "no rules are frozen for this dataset")
        settings = record.freeze["settings"]
        window = forward_result(
            view.frame,
            record.freeze["frozen_at_bar"],
            record.freeze["rules"],
            Costs(**settings["costs"]),
            settings["periods_per_year"],
        )
        return {"freeze": freeze_view(record.freeze), **window}
