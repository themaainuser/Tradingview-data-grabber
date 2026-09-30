"""Append-only, hash-chained ledger behind the verdict engine.

Every seal, run, freeze and holdout read is one JSON line in ``ledger.jsonl``.  Each line carries
``hash = sha256(prev + canonical_json(entry without hash))`` so editing, removing or reordering a
line is detected when the file is read.  The ledger is the single source of truth: what has been
sealed, tried, frozen or read is derived from it on demand (event sourcing), and nothing in it can
be changed through the API.

The chain is tamper-evident, not tamper-proof: deleting the newest lines, or recomputing every hash,
cannot be detected from the file alone.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping, Optional

import numpy as np

LEDGER_FILE = "ledger.jsonl"
GENESIS = "0" * 64
ENTRY_TYPES = ("seal", "run", "freeze", "holdout_read")
TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


class LedgerIntegrityError(RuntimeError):
    """The ledger file fails its hash-chain check, so nothing may be appended to it."""


def plain(value: Any) -> Any:
    """Return ``value`` as JSON-native data: numpy scalars become Python ones and NaN/Inf become ``None``."""

    if isinstance(value, np.ndarray):
        return plain(value.tolist())
    if isinstance(value, np.generic):
        return plain(value.item())
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Mapping):
        return {str(key): plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    return value


def canonical_json(value: Any) -> str:
    """Serialise with sorted keys and no whitespace so equal data always hashes equally."""

    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def entry_hash(prev: str, entry: Mapping[str, Any]) -> str:
    """Hash of ``entry`` (every field but ``hash``) chained to the previous entry's hash."""

    body = {key: value for key, value in entry.items() if key != "hash"}
    return hashlib.sha256((prev + canonical_json(body)).encode("utf-8")).hexdigest()


def utc_now() -> datetime:
    """Current UTC time with whole-second resolution, matching the ledger's timestamps."""

    return datetime.now(timezone.utc).replace(microsecond=0)


def iso_utc(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime(TIME_FORMAT)


def iso_from_epoch(seconds: int) -> str:
    return iso_utc(datetime.fromtimestamp(seconds, tz=timezone.utc))


def entry_epoch(entry: Mapping[str, Any]) -> int:
    """Unix seconds of an entry's ``at`` stamp."""

    return int(datetime.strptime(entry["at"], TIME_FORMAT).replace(tzinfo=timezone.utc).timestamp())


class DatasetLedger:
    """Everything the ledger records about one dataset."""

    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []
        self.seal: Optional[dict[str, Any]] = None
        self.runs: list[dict[str, Any]] = []
        self.freeze: Optional[dict[str, Any]] = None
        self.holdout_read: Optional[dict[str, Any]] = None
        self.trial_keys: dict[str, dict[str, Any]] = {}

    def add(self, entry: dict[str, Any]) -> None:
        self.entries.append(entry)
        kind = entry["type"]
        if kind == "seal":
            self.seal = self.seal or entry
        elif kind == "freeze":
            self.freeze = self.freeze or entry
        elif kind == "holdout_read":
            self.holdout_read = self.holdout_read or entry
        else:
            self.runs.append(entry)
            for trial in entry["trials"]:
                seen = self.trial_keys.setdefault(
                    trial["key"], {"key": trial["key"], "rule_id": trial["rule_id"], "first_seen": entry_epoch(entry), "runs": 0}
                )
                seen["runs"] += 1

    @property
    def completed_runs(self) -> list[dict[str, Any]]:
        return [run for run in self.runs if run.get("status") == "completed"]


class LedgerState:
    """A verified read of the ledger file.

    ``intact`` is false on any hash, sequence, JSON or shape problem (``problem`` names the first).
    Well-formed entries are kept even then, so a sealed holdout stays excluded and readers can
    still display what the file says.
    """

    def __init__(self, entries: list[dict[str, Any]], intact: bool, problem: Optional[str]) -> None:
        self.entries = entries
        self.intact = intact
        self.problem = problem
        self._datasets: dict[str, DatasetLedger] = {}
        for entry in entries:
            self._datasets.setdefault(entry["dataset"], DatasetLedger()).add(entry)

    @property
    def next_seq(self) -> int:
        return len(self.entries) + 1

    @property
    def last_hash(self) -> str:
        return self.entries[-1]["hash"] if self.entries else GENESIS

    def dataset(self, key: str) -> DatasetLedger:
        """The records of dataset ``key`` (empty when it has never been touched)."""

        return self._datasets.get(key) or DatasetLedger()

    def trials(self, key: Optional[str] = None) -> int:
        """Distinct (dataset, rule) pairs ever evaluated: N for one dataset, or for all of them."""

        if key is not None:
            return len(self.dataset(key).trial_keys)
        return sum(len(item.trial_keys) for item in self._datasets.values())

    def counts(self, key: str) -> dict[str, Any]:
        """The ``ledger`` block every verdict response carries."""

        return {
            "trials_dataset": self.trials(key),
            "trials_total": self.trials(),
            "runs_dataset": len(self.dataset(key).runs),
            "intact": self.intact,
        }


_REQUIRED_FIELDS = {
    "seal": ("fraction", "holdout_start", "holdout_end", "holdout_bars", "research_bars", "research_fingerprint"),
    "run": ("run_id", "status", "settings", "trials"),
    "freeze": ("freeze_id", "run_id", "rules", "rules_hash", "frozen_at_bar"),
    "holdout_read": ("freeze_id", "result"),
}


def _well_formed(entry: Any) -> bool:
    """Whether ``entry`` has the envelope and the per-type fields the rest of the code relies on."""

    if not isinstance(entry, dict):
        return False
    envelope = (("type", str), ("dataset", str), ("hash", str), ("prev", str), ("seq", int), ("at", str))
    if any(not isinstance(entry.get(name), kind) for name, kind in envelope) or entry["type"] not in ENTRY_TYPES:
        return False
    if any(name not in entry for name in _REQUIRED_FIELDS[entry["type"]]):
        return False
    if entry["type"] == "run":
        settings = entry["settings"]
        if not isinstance(settings, dict) or not isinstance(settings.get("costs"), dict):
            return False
        return isinstance(entry["trials"], list) and all(
            isinstance(trial, dict) and isinstance(trial.get("key"), str) and isinstance(trial.get("rule_id"), str)
            for trial in entry["trials"]
        )
    return True


def _parse(raw: bytes) -> LedgerState:
    lines = raw.split(b"\n")
    problem: Optional[str] = None
    if lines[-1] == b"":
        lines.pop()
    else:
        problem = f"line {len(lines)} is incomplete"
    entries: list[dict[str, Any]] = []
    prev = GENESIS
    for number, line in enumerate(lines, start=1):
        try:
            entry = json.loads(line)
        except ValueError:
            problem = problem or f"line {number} is not valid JSON"
            continue
        if not _well_formed(entry):
            problem = problem or f"line {number} is not a valid ledger entry"
            continue
        try:
            entry_epoch(entry)
        except ValueError:
            problem = problem or f"line {number} has an invalid timestamp"
            continue
        if problem is None:
            if entry["seq"] != len(entries) + 1:
                problem = f"line {number} has sequence {entry['seq']}, expected {len(entries) + 1}"
            elif entry["prev"] != prev:
                problem = f"line {number} does not follow the previous entry"
            elif entry["hash"] != entry_hash(prev, entry):
                problem = f"line {number} does not match its hash"
        prev = entry["hash"]
        entries.append(entry)
    return LedgerState(entries, problem is None, problem)


_REGISTRY_LOCK = threading.Lock()
_LOCKS: dict[str, tuple[threading.Lock, threading.Lock]] = {}


def _locks_for(path: Path) -> tuple[threading.Lock, threading.Lock]:
    """``(transaction lock, file lock)`` shared by every ``Ledger`` on ``path`` in this process."""

    with _REGISTRY_LOCK:
        return _LOCKS.setdefault(str(path), (threading.Lock(), threading.Lock()))


class LedgerTransaction:
    """Exclusive access to the ledger: check state, do slow work, append, all without interleaving."""

    def __init__(self, ledger: "Ledger") -> None:
        self._ledger = ledger
        self.state = ledger.read()

    def require_intact(self) -> None:
        if not self.state.intact:
            raise LedgerIntegrityError("ledger integrity check failed")

    def append(
        self,
        entry_type: str,
        dataset: str,
        body: Mapping[str, Any],
        at: Optional[datetime] = None,
    ) -> dict[str, Any]:
        """Write one entry, flushed to disk, and return it; refused while the chain is broken."""

        self.require_intact()
        entry: dict[str, Any] = {
            **plain(body),
            "seq": self.state.next_seq,
            "type": entry_type,
            "at": iso_utc(at or utc_now()),
            "dataset": dataset,
            "prev": self.state.last_hash,
        }
        entry["hash"] = entry_hash(entry["prev"], entry)
        self._ledger.write_line(canonical_json(entry))
        self.state = LedgerState([*self.state.entries, entry], True, None)
        return entry


class Ledger:
    """The ledger file inside a state directory."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.path = directory / LEDGER_FILE
        self._transaction_lock, self._file_lock = _locks_for(self.path)

    def read(self) -> LedgerState:
        """Load and verify the whole chain; a file that does not exist yet is an empty, intact ledger."""

        with self._file_lock:
            try:
                raw = self.path.read_bytes()
            except FileNotFoundError:
                return LedgerState([], True, None)
        return _parse(raw)

    @contextmanager
    def transaction(self) -> Iterator[LedgerTransaction]:
        """Serialise every writer; readers are not blocked while a slow run is in progress."""

        with self._transaction_lock:
            yield LedgerTransaction(self)

    def write_line(self, line: str) -> None:
        with self._file_lock:
            self.directory.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
            try:
                os.write(descriptor, (line + "\n").encode("utf-8"))
                os.fsync(descriptor)
            finally:
                os.close(descriptor)


def _costs_text(settings: Mapping[str, Any]) -> str:
    costs = settings["costs"]
    return "/".join(f"{costs[name]:g}" for name in ("fee_bps_per_side", "spread_bps", "slippage_k"))


def describe(entry: Mapping[str, Any]) -> str:
    """One plain sentence saying what an entry records."""

    try:
        return _describe(entry)
    except (KeyError, TypeError, ValueError):
        return f"Unreadable {entry['type']} entry."


def _describe(entry: Mapping[str, Any]) -> str:
    kind = entry["type"]
    if kind == "seal":
        return (
            f"Sealed the last {entry['holdout_bars']} of {entry['research_bars'] + entry['holdout_bars']} bars "
            f"as holdout ({entry['fraction']:.0%})."
        )
    if kind == "run":
        rules, costs = len(entry["trials"]), _costs_text(entry["settings"])
        if entry["status"] == "completed":
            return f"Run {entry['run_id']}: {entry['label']}, {rules} rules, costs {costs}"
        return f"Run {entry['run_id']} failed ({entry['error']}): {rules} rules counted, costs {costs}"
    if kind == "freeze":
        return f"Froze {', '.join(rule['id'] for rule in entry['rules'])} from run {entry['run_id']} (hash {entry['rules_hash'][:12]})."
    return f"Read the holdout once for freeze {entry['freeze_id']}; it cannot be read again."

