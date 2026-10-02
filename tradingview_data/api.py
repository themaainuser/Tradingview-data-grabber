"""FastAPI adapter that serves captured OHLCV data to the dashboard.

The API never fabricates data: it only reports CSV captures found under the
configured data directory.  The one thing it writes is the verdict engine's ledger, in a hidden
state directory.  Dataset ids are resolved exclusively through a
registry built by scanning that directory, so client input is never joined
into a filesystem path.
"""

from __future__ import annotations

import base64
import json
import math
import os
import threading
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import cached_property
from pathlib import Path
from typing import Annotated, Any, Callable, Mapping, Optional, Sequence, Union

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import Scope

from . import __version__
from .analytics import data_quality_report, load_ohlcv, market_report
from .charts import chart_payload, correlation_matrix
from .holdout import DEFAULT_FRACTION, MAX_FRACTION, MIN_FRACTION
from .providers.base import ProviderRegistry
from .providers.registry import default_registry
from .providers.routes import register_provider_routes
from .research import build_research, unique_label
from .sentiment import FearGreedService, SentimentUnavailable, build_response
from .verdict import DEFAULT_MIN_TRADES, Costs
from .verdict_service import DatasetView, VerdictError, VerdictService

MAX_BAR_LIMIT = 5_000_000
MAX_RESEARCH_DATASETS = 20
MAX_CORRELATION_DATASETS = 20
FRAME_CACHE_SIZE = 16
PRICE_COLUMNS = ("open", "high", "low", "close", "volume")
IMMUTABLE_CACHE_CONTROL = "public, max-age=31536000, immutable"
STATE_DIR_NAME = ".tvdata-verdict"
MAX_LEDGER_LIMIT = 500


def _json_safe(value: Any) -> Any:
    """Return ``value`` with JSON-incompatible content replaced.

    NaN and +/-Infinity become ``None`` and numpy scalars/arrays become plain
    Python values.  Numeric arrays take a vectorised path so a multi-million
    bar response is not walked element by element in Python.
    """

    if isinstance(value, np.ndarray):
        if value.dtype.kind in "iub":
            return value.tolist()
        if value.dtype.kind == "f" and value.ndim == 1:
            items = value.tolist()
            for position in np.flatnonzero(~np.isfinite(value)).tolist():
                items[position] = None
            return items
        return _json_safe(value.tolist())
    if isinstance(value, np.generic):
        return _json_safe(value.item())
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _json(payload: Any) -> JSONResponse:
    """Sanitize ``payload`` and wrap it in a response that rejects stray NaNs."""

    return JSONResponse(_json_safe(payload))


class HealthResponse(BaseModel):
    status: str
    data_dir: str
    dataset_count: int


class DatasetSummary(BaseModel):
    """One capture file; ``start``/``end`` are Unix epoch seconds."""

    id: str
    symbol: str
    timeframe: Optional[str]
    path: str
    rows: int
    size_bytes: int
    modified: str
    start: Optional[int]
    end: Optional[int]
    valid: bool
    error: Optional[str]


class DatasetList(BaseModel):
    datasets: list[DatasetSummary]


class BarColumns(BaseModel):
    time: list[int]
    open: list[float]
    high: list[float]
    low: list[float]
    close: list[float]
    volume: list[float]


class BarsResponse(BaseModel):
    id: str
    symbol: str
    timeframe: Optional[str]
    rows: int
    total_rows: int
    dropped_rows: int
    duplicate_rows_collapsed: int
    columns: BarColumns
    quality: dict[str, Any]


class ResearchRequest(BaseModel):
    """Body of ``POST /api/research/run``."""

    dataset_ids: list[str] = Field(min_length=1, max_length=MAX_RESEARCH_DATASETS)
    fee_bps: float = Field(default=5.0, ge=0, le=10_000, allow_inf_nan=False)
    periods_per_year: float = Field(default=252.0, gt=0, allow_inf_nan=False)

    @field_validator("dataset_ids")
    @classmethod
    def _unique_ids(cls, ids: list[str]) -> list[str]:
        if len(set(ids)) != len(ids):
            raise ValueError("dataset_ids must be unique")
        return ids


class CostsRequest(BaseModel):
    """Per-side trading costs of ``POST /api/verdict/run``."""

    fee_bps_per_side: float = Field(default=Costs().fee_bps_per_side, ge=0, le=500, allow_inf_nan=False)
    spread_bps: float = Field(default=Costs().spread_bps, ge=0, le=1000, allow_inf_nan=False)
    slippage_k: float = Field(default=Costs().slippage_k, ge=0, le=5, allow_inf_nan=False)


class VerdictRunRequest(BaseModel):
    """Body of ``POST /api/verdict/run``; ``periods_per_year`` is inferred from the bar spacing when null."""

    dataset_id: str
    min_trades: int = Field(default=DEFAULT_MIN_TRADES, ge=1, le=1000)
    costs: CostsRequest = Field(default_factory=CostsRequest)
    periods_per_year: Optional[float] = Field(default=None, gt=0, allow_inf_nan=False)


class SealRequest(BaseModel):
    """Body of ``POST /api/verdict/{id}/seal``."""

    holdout_fraction: float = Field(default=DEFAULT_FRACTION, ge=MIN_FRACTION, le=MAX_FRACTION, allow_inf_nan=False)


class FreezeRequest(BaseModel):
    """Body of ``POST /api/verdict/{id}/freeze``."""

    run_id: str
    rule_ids: list[str] = Field(min_length=1, max_length=2)

    @field_validator("rule_ids")
    @classmethod
    def _unique_rules(cls, ids: list[str]) -> list[str]:
        if len(set(ids)) != len(ids):
            raise ValueError("rule_ids must be unique")
        return ids


class HoldoutReadRequest(BaseModel):
    """Body of ``POST /api/verdict/{id}/holdout/read``."""

    freeze_id: str


class DatasetError(ValueError):
    """A capture file cannot be read as OHLCV data."""


@dataclass(frozen=True)
class DatasetFile:
    """A CSV found by scanning the data directory."""

    path: Path
    relative: str
    nested: bool
    size: int
    mtime_ns: int

    @property
    def id(self) -> str:
        """Opaque URL-safe slug derived from the relative path."""

        return base64.urlsafe_b64encode(self.relative.encode("utf-8")).rstrip(b"=").decode("ascii")

    @property
    def signature(self) -> tuple[str, int, int]:
        return (str(self.path), self.mtime_ns, self.size)


@dataclass
class LoadedDataset:
    """A validated frame plus values derived from it on first use."""

    data: pd.DataFrame

    @cached_property
    def times(self) -> np.ndarray:
        """Sorted bar times as UTC Unix seconds (independent of the display timezone)."""

        return self.data.index.as_unit("s").asi8

    @cached_property
    def quality(self) -> dict[str, Any]:
        return data_quality_report(self.data)


def _text(value: object) -> Optional[str]:
    return value.strip() or None if isinstance(value, str) else None


def _read_metadata(path: Path) -> dict[str, Any]:
    """Read the ``*.csv.meta.json`` sidecar written by ``CsvBarStore``, if usable."""

    try:
        payload = json.loads(path.with_name(path.name + ".meta.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _identity(file: DatasetFile) -> tuple[str, Optional[str]]:
    """Return ``(symbol, timeframe)`` from the sidecar, else from the file layout."""

    metadata = _read_metadata(file.path)
    if file.nested:
        derived_symbol, derived_timeframe = file.path.parent.name, file.path.stem
    else:
        derived_symbol, derived_timeframe = file.path.stem, None
    return (
        _text(metadata.get("symbol")) or derived_symbol,
        _text(metadata.get("timeframe")) or derived_timeframe,
    )


def _iso_utc(mtime_ns: int) -> str:
    moment = datetime.fromtimestamp(mtime_ns / 1_000_000_000, tz=timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _load(file: DatasetFile) -> Union[LoadedDataset, str]:
    """Parse a capture, returning an error message instead of raising."""

    try:
        data = load_ohlcv(file.path)
    except Exception as exc:  # noqa: BLE001 - arbitrary file content must not break listings
        return (str(exc) or type(exc).__name__).replace(str(file.path), file.relative)
    data.attrs["source_path"] = file.relative
    return LoadedDataset(data)


class DatasetRepository:
    """Scan the data directory and cache parsed frames.

    Frames are cached by ``(path, mtime_ns, size)`` in a small LRU.  A live
    capture that keeps growing replaces its own entry rather than evicting
    other datasets.  Loads are serialised per path so simultaneous requests for
    one file parse it once.
    """

    def __init__(self, root: Path, cache_size: int = FRAME_CACHE_SIZE) -> None:
        self.root = root
        self._cache_size = cache_size
        self._entries: OrderedDict[str, tuple[tuple[str, int, int], Union[LoadedDataset, str]]] = OrderedDict()
        self._lock = threading.Lock()
        self._load_locks: dict[str, threading.Lock] = {}

    def scan(self) -> list[DatasetFile]:
        """List ``<symbol_dir>/<timeframe>.csv`` and flat ``<name>.csv`` files."""

        found: list[DatasetFile] = []
        for entry in self._children(self.root):
            if entry.is_dir():
                found.extend(
                    file
                    for child in self._children(entry)
                    if (file := self._describe_file(child, nested=True)) is not None
                )
            elif (file := self._describe_file(entry, nested=False)) is not None:
                found.append(file)
        return found

    def registry(self) -> dict[str, DatasetFile]:
        """Map ids to files; the only way a client-supplied id reaches the disk."""

        return {file.id: file for file in self.scan()}

    def load(self, file: DatasetFile) -> LoadedDataset:
        """Return the parsed frame for ``file`` or raise :class:`DatasetError`."""

        signature = file.signature
        with self._lock:
            cached = self._lookup(signature)
            load_lock = self._load_locks.setdefault(signature[0], threading.Lock())
        if cached is None:
            with load_lock:
                with self._lock:
                    cached = self._lookup(signature)
                if cached is None:
                    cached = _load(file)
                    with self._lock:
                        self._entries[signature[0]] = (signature, cached)
                        self._entries.move_to_end(signature[0])
                        while len(self._entries) > self._cache_size:
                            self._entries.popitem(last=False)
        if isinstance(cached, str):
            raise DatasetError(cached)
        return cached

    def summarize(self, file: DatasetFile) -> DatasetSummary:
        symbol, timeframe = _identity(file)
        common: dict[str, Any] = {
            "id": file.id,
            "symbol": symbol,
            "timeframe": timeframe,
            "path": file.relative,
            "size_bytes": file.size,
            "modified": _iso_utc(file.mtime_ns),
        }
        try:
            times = self.load(file).times
        except DatasetError as exc:
            return DatasetSummary(**common, rows=0, start=None, end=None, valid=False, error=str(exc))
        return DatasetSummary(
            **common, rows=len(times), start=int(times[0]), end=int(times[-1]), valid=True, error=None
        )

    def _lookup(self, signature: tuple[str, int, int]) -> Union[LoadedDataset, str, None]:
        entry = self._entries.get(signature[0])
        if entry is None or entry[0] != signature:
            return None
        self._entries.move_to_end(signature[0])
        return entry[1]

    @staticmethod
    def _children(directory: Path) -> list[Path]:
        try:
            return [child for child in directory.iterdir() if not child.name.startswith(".")]
        except OSError:
            return []

    def _describe_file(self, path: Path, *, nested: bool) -> Optional[DatasetFile]:
        if path.suffix.lower() != ".csv":
            return None
        try:
            # Reject symlinks that leave the data directory.
            if not path.is_file() or not path.resolve().is_relative_to(self.root):
                return None
            stat = path.stat()
        except OSError:
            return None
        return DatasetFile(
            path=path,
            relative=path.relative_to(self.root).as_posix(),
            nested=nested,
            size=stat.st_size,
            mtime_ns=stat.st_mtime_ns,
        )


class SpaStaticFiles(StaticFiles):
    """Serve a built single-page app next to the API.

    Unknown paths fall back to ``index.html``; ``/api`` and missing hashed
    assets stay real 404s.  Hashed ``_app/`` assets are cached forever and
    HTML is always revalidated.
    """

    def __init__(self, directory: Path) -> None:
        super().__init__(directory=directory)
        self._asset_dir = directory / "_app"

    async def get_response(self, path: str, scope: Scope) -> Response:
        if path == "api" or path.startswith("api/"):
            raise StarletteHTTPException(status_code=404)
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404 or path.startswith("_app/"):
                raise
            return await super().get_response("index.html", scope)

    def file_response(
        self,
        full_path: Union[str, "os.PathLike[str]"],
        stat_result: os.stat_result,
        scope: Scope,
        status_code: int = 200,
    ) -> Response:
        response = super().file_response(full_path, stat_result, scope, status_code)
        served = Path(full_path)
        if served.is_relative_to(self._asset_dir):
            response.headers["Cache-Control"] = IMMUTABLE_CACHE_CONTROL
        elif served.suffix == ".html":
            response.headers["Cache-Control"] = "no-cache"
        return response


def create_app(
    data_dir: Union[str, Path],
    static_dir: Union[str, Path, None] = None,
    cors_origins: Sequence[str] = (),
    fear_greed: Optional[FearGreedService] = None,
    state_dir: Union[str, Path, None] = None,
    providers: Optional[ProviderRegistry] = None,
) -> FastAPI:
    """Build the dashboard API for the captures stored in ``data_dir``.

    ``static_dir`` optionally hosts a built frontend at ``/``, ``cors_origins`` enables CORS for the
    listed origins (off by default because the dev server proxies ``/api``), and ``fear_greed``
    replaces the CoinMarketCap-backed Fear & Greed service (tests inject a fake; by default nothing
    is fetched until the first request).  ``state_dir`` holds the verdict engine's ledger; it defaults
    to a hidden directory inside ``data_dir``, which the dataset scan ignores.  ``providers`` is the
    registry of external data providers (Alpha Vantage, Marketstack and Alpaca by default); nothing is fetched until a query.
    """

    root = Path(data_dir).expanduser().resolve()
    repository = DatasetRepository(root)
    verdicts = VerdictService(Path(state_dir).expanduser().resolve() if state_dir else root / STATE_DIR_NAME)
    # Interactive docs live under /api so the bare /docs path can belong to the dashboard's own
    # documentation page (the SPA fallback serves it).
    app = FastAPI(
        title="TradingView Data Grabber dashboard API",
        version=__version__,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_request: Any, exc: RequestValidationError) -> Response:
        # FastAPI echoes rejected input (which may be NaN/Infinity) back in the error list.
        return JSONResponse(status_code=422, content=_json_safe({"detail": jsonable_encoder(exc.errors())}))

    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(cors_origins),
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type"],
        )

    def open_dataset(dataset_id: str) -> tuple[DatasetFile, LoadedDataset]:
        file = repository.registry().get(dataset_id)
        if file is None:
            raise HTTPException(status_code=404, detail="dataset not found")
        try:
            return file, repository.load(file)
        except DatasetError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    def verdict_view(dataset_id: str) -> DatasetView:
        file, loaded = open_dataset(dataset_id)
        symbol, timeframe = _identity(file)
        return DatasetView(id=file.id, key=file.relative, symbol=symbol, timeframe=timeframe, frame=loaded.data)

    def verdict_answer(action: Callable[[], Any]) -> Response:
        try:
            return _json(action())
        except VerdictError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    @app.get("/api/health", response_model=HealthResponse)
    def health() -> Response:
        return _json({"status": "ok", "data_dir": str(root), "dataset_count": len(repository.scan())})

    @app.get("/api/datasets", response_model=DatasetList)
    def list_datasets() -> Response:
        summaries = [repository.summarize(file) for file in repository.scan()]
        summaries.sort(key=lambda item: (item.symbol, item.timeframe or "", item.path))
        return _json({"datasets": [summary.model_dump() for summary in summaries]})

    @app.get("/api/datasets/{dataset_id}/bars", response_model=BarsResponse)
    def get_bars(
        dataset_id: str,
        limit: Annotated[Optional[int], Query(ge=1, le=MAX_BAR_LIMIT, description="return only the last N bars")] = None,
        start: Annotated[Optional[float], Query(allow_inf_nan=False, description="first bar, epoch seconds")] = None,
        end: Annotated[Optional[float], Query(allow_inf_nan=False, description="last bar, epoch seconds")] = None,
    ) -> Response:
        """Columnar OHLCV; ``limit`` keeps the tail of the ``start``..``end`` window.

        ``quality`` and the dropped/duplicate counters describe the whole file,
        not just the returned window.
        """

        if start is not None and end is not None and start > end:
            raise HTTPException(status_code=422, detail="start must not be greater than end")
        file, loaded = open_dataset(dataset_id)
        times = loaded.times
        low = 0 if start is None else int(np.searchsorted(times, start, side="left"))
        high = len(times) if end is None else int(np.searchsorted(times, end, side="right"))
        if limit is not None:
            low = max(low, high - limit)
        window = loaded.data.iloc[low:high]
        symbol, timeframe = _identity(file)
        quality = loaded.quality
        return _json(
            {
                "id": dataset_id,
                "symbol": symbol,
                "timeframe": timeframe,
                "rows": high - low,
                "total_rows": len(times),
                "dropped_rows": quality["dropped_rows"],
                "duplicate_rows_collapsed": quality["duplicate_rows_collapsed"],
                "columns": {
                    "time": times[low:high],
                    **{name: window[name].to_numpy(dtype=float) for name in PRICE_COLUMNS},
                },
                "quality": quality,
            }
        )

    @app.get("/api/datasets/{dataset_id}/report")
    def get_report(dataset_id: str) -> Response:
        _, loaded = open_dataset(dataset_id)
        return _json(market_report(loaded.data))

    @app.get("/api/datasets/{dataset_id}/charts")
    def get_charts(
        dataset_id: str,
        bins: Annotated[int, Query(ge=10, le=200, description="volume-profile price bins")] = 60,
        value_area: Annotated[
            float, Query(ge=0.5, le=0.95, allow_inf_nan=False, description="share of volume inside the value area")
        ] = 0.7,
        window: Annotated[int, Query(ge=5, le=500, description="rolling-volatility window in bars")] = 30,
        return_bins: Annotated[int, Query(ge=10, le=101, description="return-histogram bins")] = 41,
    ) -> Response:
        """Server-computed chart data; a section that cannot be computed is null and explained in ``unavailable``."""

        file, loaded = open_dataset(dataset_id)
        symbol, timeframe = _identity(file)
        payload = chart_payload(loaded.data, bins=bins, value_area=value_area, window=window, return_bins=return_bins)
        return _json({"id": dataset_id, "symbol": symbol, "timeframe": timeframe, **payload})

    @app.get("/api/charts/correlation")
    def get_correlation(
        ids: Annotated[
            Optional[list[str]], Query(description="dataset ids; repeat the parameter for 2-20 unique datasets")
        ] = None,
    ) -> Response:
        """Close-to-close return correlation over the timestamps the datasets share."""

        selected = ids or []
        if not 2 <= len(selected) <= MAX_CORRELATION_DATASETS:
            raise HTTPException(
                status_code=422,
                detail=f"select between 2 and {MAX_CORRELATION_DATASETS} datasets; got {len(selected)}",
            )
        if len(set(selected)) != len(selected):
            raise HTTPException(status_code=422, detail="dataset ids must be unique")
        registry = repository.registry()
        datasets: list[tuple[str, pd.DataFrame]] = []
        labels: set[str] = set()
        for dataset_id in selected:
            file = registry.get(dataset_id)
            if file is None:
                raise HTTPException(status_code=422, detail=f"unknown dataset id: {dataset_id}")
            try:
                loaded = repository.load(file)
            except DatasetError as exc:
                raise HTTPException(status_code=422, detail=f"{file.relative}: {exc}") from exc
            symbol, timeframe = _identity(file)
            datasets.append((unique_label(f"{symbol}-{timeframe}" if timeframe else symbol, labels), loaded.data))
        result = correlation_matrix(datasets)
        if result is None:
            raise HTTPException(
                status_code=422,
                detail="fewer than 3 overlapping returns; the selected datasets do not share timestamps",
            )
        return _json(result)

    register_provider_routes(app, providers or default_registry(), _json)

    sentiment = fear_greed or FearGreedService()

    @app.get("/api/sentiment/fear-greed")
    def get_fear_greed(
        days: Annotated[Optional[int], Query(ge=1, le=3650, description="only the last N days of history")] = None,
    ) -> Response:
        """CoinMarketCap's Crypto Fear & Greed Index, read by this server (no API key).

        502 when CoinMarketCap cannot be read and no earlier reading is cached; when one is cached it
        is served with ``stale: true`` instead. Nothing is ever substituted for a missing reading.
        """

        try:
            snapshot = sentiment.get()
        except SentimentUnavailable as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return _json(build_response(snapshot, days))

    @app.post("/api/research/run")
    def run_research(body: ResearchRequest) -> Response:
        """Backtest the built-in strategy grid; ``assets[i]`` matches ``dataset_ids[i]``."""

        registry = repository.registry()
        ledger_state = verdicts.ledger.read()
        sealed: list[dict[str, Any]] = []
        datasets: list[tuple[str, str, pd.DataFrame]] = []
        for dataset_id in body.dataset_ids:
            file = registry.get(dataset_id)
            if file is None:
                raise HTTPException(status_code=422, detail=f"unknown dataset id: {dataset_id}")
            try:
                loaded = repository.load(file)
            except DatasetError as exc:
                raise HTTPException(status_code=422, detail=f"{file.relative}: {exc}") from exc
            symbol, timeframe = _identity(file)
            frame, excluded = verdicts.restrict(ledger_state, file.relative, loaded.data)
            if excluded is not None:
                sealed.append({"dataset_id": dataset_id, "excluded_bars": excluded})
            datasets.append((f"{symbol}-{timeframe}" if timeframe else symbol, file.relative, frame))
        try:
            report = build_research(datasets, fee_bps=body.fee_bps, periods_per_year=body.periods_per_year)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if sealed:
            report["metadata"]["sealed_holdouts"] = sealed
        return _json(report)

    @app.post("/api/verdict/run")
    def run_verdict(body: VerdictRunRequest) -> Response:
        """Judge the built-in rule grid on the research window; appends the run to the ledger.

        Seals the default holdout first when the dataset has none.  Ends in exactly one label and never
        ranks rules.
        """

        view = verdict_view(body.dataset_id)
        return verdict_answer(
            lambda: verdicts.run(
                view,
                min_trades=body.min_trades,
                costs=Costs(**body.costs.model_dump()),
                periods_per_year=body.periods_per_year,
            )
        )

    @app.get("/api/verdict/{dataset_id}")
    def get_verdict(dataset_id: str) -> Response:
        """Seal, ledger counts, latest report, freeze and holdout result; never writes."""

        view = verdict_view(dataset_id)
        return verdict_answer(lambda: verdicts.overview(view))

    @app.post("/api/verdict/{dataset_id}/seal")
    def seal_verdict(dataset_id: str, body: SealRequest = SealRequest()) -> Response:
        """Seal the last ``holdout_fraction`` of the capture; 409 when already sealed."""

        view = verdict_view(dataset_id)
        return verdict_answer(lambda: verdicts.seal(view, body.holdout_fraction))

    @app.get("/api/verdict/{dataset_id}/ledger")
    def get_verdict_ledger(
        dataset_id: str,
        limit: Annotated[int, Query(ge=1, le=MAX_LEDGER_LIMIT, description="newest N entries")] = 100,
    ) -> Response:
        """The hash-chained trial ledger for the dataset, oldest entry first."""

        view = verdict_view(dataset_id)
        return verdict_answer(lambda: verdicts.ledger_view(view, limit))

    @app.post("/api/verdict/{dataset_id}/freeze")
    def freeze_verdict(dataset_id: str, body: FreezeRequest) -> Response:
        """Freeze one or two candidate rules of the latest run; 409 once the seal has a freeze."""

        view = verdict_view(dataset_id)
        return verdict_answer(lambda: verdicts.freeze(view, body.run_id, body.rule_ids))

    @app.post("/api/verdict/{dataset_id}/holdout/read")
    def read_verdict_holdout(dataset_id: str, body: HoldoutReadRequest) -> Response:
        """Read the sealed holdout for the frozen rules; 409 on any second attempt."""

        view = verdict_view(dataset_id)
        return verdict_answer(lambda: verdicts.read_holdout(view, body.freeze_id))

    @app.get("/api/verdict/{dataset_id}/forward")
    def get_verdict_forward(dataset_id: str) -> Response:
        """Frozen rules on bars captured since the freeze (nothing is stored); 409 without a freeze."""

        view = verdict_view(dataset_id)
        return verdict_answer(lambda: verdicts.forward(view))

    if static_dir is not None:
        static_root = Path(static_dir).expanduser().resolve()
        if static_root.is_dir():
            # Mounted last so every API route above wins over the SPA fallback.
            app.mount("/", SpaStaticFiles(static_root), name="dashboard")
    return app
