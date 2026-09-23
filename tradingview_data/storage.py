"""Durable CSV storage for streamed OHLCV candles."""

from __future__ import annotations

import csv
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

CSV_COLUMNS = ("index", "time", "open", "high", "low", "close", "volume")
CSV_TIME_FORMAT = "%a %b %d %Y %H:%M:%S GMT%z"
SCHEMA_VERSION = 1


def parse_csv_time(value: object) -> int | None:
    """Parse a persisted candle timestamp into Unix seconds."""

    if not isinstance(value, str):
        return None
    try:
        return int(datetime.strptime(value, CSV_TIME_FORMAT).timestamp())
    except ValueError:
        try:
            return int(datetime.fromisoformat(value).timestamp())
        except ValueError:
            return None


def safe_filename(value: str) -> str:
    """Return a stable, path-safe filename component for a market symbol."""

    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    cleaned = cleaned.strip("._")
    return cleaned or "symbol"


class CsvBarStore:
    """Append candles and rewrite the current candle without duplicate rows.

    TradingView resends history after a reconnect and continuously updates the
    still-forming candle.  The store keeps timestamp keys and the byte position
    of the final row so only that final row is replaced.  Existing files are
    opened in ``r+`` rather than append mode because append mode ignores seeks
    on many platforms.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        symbol: str | None = None,
        timeframe: str | None = None,
        durable: bool = True,
    ) -> None:
        self.path = Path(path)
        self.symbol = symbol
        self.timeframe = timeframe
        self.durable = durable
        self.file: Any | None = None
        self.writer: csv.writer | None = None
        self.last_key: int | None = None
        self.last_row_position: int | None = None
        self.written: set[int] = set()
        self.rows: dict[int, list[str]] = {}

    @property
    def metadata_path(self) -> Path:
        return self.path.with_suffix(self.path.suffix + ".meta.json")

    def open(self) -> None:
        """Open the store and restore state from an existing CSV."""

        if self.file is not None:
            raise RuntimeError("CSV store is already open")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            is_new = not self.path.exists() or self.path.stat().st_size == 0
            self.file = self.path.open("w+" if is_new else "r+", newline="", encoding="utf-8")
            if is_new:
                self.writer = csv.writer(self.file)
                self.writer.writerow(CSV_COLUMNS)
                self._flush()
            else:
                self._load_existing_state()
                self.file.seek(0, os.SEEK_END)
                self.writer = csv.writer(self.file)
            self._write_or_validate_metadata()
        except Exception:
            self.close()
            raise

    def _load_existing_state(self) -> None:
        assert self.file is not None
        self.rows.clear()
        self.written.clear()
        self.last_key = None
        self.last_row_position = None
        self.file.seek(0)
        header = self.file.readline()
        if not header:
            return
        if next(csv.reader([header]), []) != list(CSV_COLUMNS):
            raise ValueError(f"{self.path} does not contain the expected OHLCV CSV header")

        positions: dict[int, int] = {}
        observed_keys: list[int] = []
        saw_invalid_row = False
        position = self.file.tell()
        line = self.file.readline()
        while line:
            next_position = self.file.tell()
            try:
                row = next(csv.reader([line]), [])
            except csv.Error:
                row = []
            if len(row) == len(CSV_COLUMNS):
                timestamp = parse_csv_time(row[1])
                if timestamp is not None:
                    self.rows[timestamp] = row
                    positions[timestamp] = position
                    observed_keys.append(timestamp)
                else:
                    saw_invalid_row = True
            else:
                saw_invalid_row = True
            position = next_position
            line = self.file.readline()

        sorted_keys = sorted(self.rows)
        if saw_invalid_row or observed_keys != sorted_keys:
            self._rewrite_all()
            return
        self.written = set(sorted_keys)
        if sorted_keys:
            self.last_key = sorted_keys[-1]
            self.last_row_position = positions[self.last_key]

    def _rewrite_all(self) -> None:
        """Rewrite sorted valid rows after a late or corrected candle arrives."""

        assert self.file is not None
        self.file.seek(0)
        self.file.truncate()
        self.writer = csv.writer(self.file)
        self.writer.writerow(CSV_COLUMNS)
        self.written = set(self.rows)
        self.last_key = None
        self.last_row_position = None
        for key in sorted(self.rows):
            position = self.file.tell()
            self.writer.writerow(self.rows[key])
            self.last_key = key
            self.last_row_position = position
        self._flush()

    def _write_or_validate_metadata(self) -> None:
        if self.symbol is None and self.timeframe is None:
            return
        expected = {
            "schema_version": SCHEMA_VERSION,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
        }
        if self.metadata_path.exists():
            try:
                actual = json.loads(self.metadata_path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise ValueError(f"unable to read metadata for {self.path}") from exc
            for key, expected_value in expected.items():
                if actual.get(key) != expected_value:
                    raise ValueError(
                        f"{self.path} belongs to {actual.get('symbol')} "
                        f"({actual.get('timeframe')}); choose a different output path"
                    )
            return

        temporary = self.metadata_path.with_suffix(self.metadata_path.suffix + ".tmp")
        temporary.write_text(json.dumps(expected, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, self.metadata_path)

    def write_bar(self, key: int, row: Sequence[object]) -> bool:
        """Persist a candle row and return whether the file changed."""

        if self.file is None or self.writer is None:
            raise RuntimeError("open the CSV store before writing bars")
        normalized = [str(value) for value in row]
        if len(normalized) != len(CSV_COLUMNS):
            raise ValueError(f"bar rows must contain exactly {len(CSV_COLUMNS)} columns")
        previous = self.rows.get(key)
        if previous == normalized:
            return False

        if self.last_key is None or key > self.last_key:
            self.file.seek(0, os.SEEK_END)
            self.last_key = key
            self.last_row_position = self.file.tell()
            self.written.add(key)
            self.rows[key] = normalized
            self.writer.writerow(normalized)
            self._flush()
            return True

        if key == self.last_key:
            if self.last_row_position is None:
                raise RuntimeError("missing position for the current candle")
            self.file.seek(self.last_row_position)
            self.file.truncate()
            self.rows[key] = normalized
            self.writer.writerow(normalized)
            self._flush()
            return True

        self.rows[key] = normalized
        self._rewrite_all()
        return True

    def _flush(self) -> None:
        assert self.file is not None
        self.file.flush()
        if self.durable:
            os.fsync(self.file.fileno())

    def close(self) -> None:
        if self.file is not None:
            self.file.close()
            self.file = None
            self.writer = None

    def __enter__(self) -> "CsvBarStore":
        self.open()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
