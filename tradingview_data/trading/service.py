"""Trading operations for the paper and live environments, in the order a trader needs them.

Every method returns the same envelope::

    {"environment", "status", "message", "code", "http_status", "outcome_unknown", "client_order_id",
     "data", "fetched_at", "elapsed_ms"}

Problems at Alpaca (a refused order, a bad key, a rate limit, an outage) are a ``status`` and Alpaca's own
words in ``message``; they are not exceptions. Exceptions are for what is wrong with the request before
it leaves (:class:`TradingInputError`, ``KeyError`` for an unknown environment) or for an environment
that is switched off (:class:`TradingBlocked`).

Every request that changes something is checked first, appended to an audit log and sent exactly once:
nothing is retried, because a retried order could be placed twice.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Optional
from urllib.parse import quote

from ..providers.common import HttpRequest
from . import views as V
from .client import DATA_URL, ENVIRONMENTS, Outcome, TradingClient
from .validation import (
    TradingInputError,
    asset_kind,
    clean_query,
    symbol_text,
    validate_config,
    validate_order,
    validate_replace,
    validate_watchlist,
)

log = logging.getLogger(__name__)

ASSET_CACHE_SECONDS = 600.0
_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_SYMBOL_LIST = r"[A-Za-z0-9][A-Za-z0-9._/\-]{0,31}"
_ASSET_CLASSES = ("us_equity", "crypto", "us_option")

_ORDERS_QUERY = {
    "status": ("enum", ("open", "closed", "all")),
    "limit": ("int", 1, 500),
    "after": ("moment",),
    "until": ("moment",),
    "direction": ("enum", ("asc", "desc")),
    "nested": ("bool",),
    "symbols": ("list", _SYMBOL_LIST, 100),
    "side": ("enum", ("buy", "sell")),
    "asset_class": ("list", "|".join(_ASSET_CLASSES), 3),
}
_ACTIVITIES_QUERY = {
    "activity_types": ("list", r"[A-Z_]{2,12}", 20),
    "category": ("enum", ("trade_activity", "non_trade_activity")),
    "order_id": ("regex", r"[0-9a-fA-F-]{36}", "an order ID"),
    "date": ("moment",),
    "until": ("moment",),
    "after": ("moment",),
    "direction": ("enum", ("asc", "desc")),
    "page_size": ("int", 1, 100),
    "page_token": ("text", 120),
}
_HISTORY_QUERY = {
    "period": ("regex", r"\d{1,3}[DWMA]", "a number and a unit, such as 1D, 1W, 1M or 1A"),
    "timeframe": ("regex", r"1Min|5Min|15Min|1H|1D", "1Min, 5Min, 15Min, 1H or 1D"),
    "intraday_reporting": ("enum", ("market_hours", "extended_hours", "continuous")),
    "pnl_reset": ("enum", ("no_reset", "per_day")),
    "start": ("moment",),
    "end": ("moment",),
    "cashflow_types": ("list", r"[A-Z_]{2,12}", 20),
}
_CALENDAR_QUERY = {"start": ("date",), "end": ("date",), "date_type": ("enum", ("TRADING", "SETTLEMENT"))}
_CONTRACTS_QUERY = {
    "underlying_symbols": ("list", _SYMBOL_LIST, 20),
    "show_deliverables": ("bool",),
    "status": ("enum", ("active", "inactive")),
    "expiration_date": ("date",),
    "expiration_date_gte": ("date",),
    "expiration_date_lte": ("date",),
    "root_symbol": ("text", 10),
    "type": ("enum", ("call", "put")),
    "style": ("enum", ("american", "european")),
    "strike_price_gte": ("number",),
    "strike_price_lte": ("number",),
    "page_token": ("text", 200),
    "limit": ("int", 1, 1000),
    "ppind": ("bool",),
}
_ASSETS_QUERY = {
    "search": ("text", 40),
    "asset_class": ("enum", _ASSET_CLASSES[:2]),
    "exchange": ("text", 12),
    "status": ("enum", ("active", "inactive")),
    "tradable": ("bool",),
    "limit": ("int", 1, 100),
}
_CLOSE_QUERY = {"qty": ("number",), "percentage": ("number",)}
_QUOTE_QUERY = {"asset_class": ("enum", _ASSET_CLASSES)}


class TradingBlocked(PermissionError):
    """The environment exists but is switched off (live trading before it is turned on)."""


def _id(value: str, what: str) -> str:
    if not _UUID.match(value or ""):
        raise TradingInputError(f"{what} must be a UUID such as 61e69015-8549-4bfd-b9c3-01e75843f47d.")
    return value


def _path(symbol: str) -> str:
    """A symbol or asset ID as one URL path segment (``BTC/USD`` becomes ``BTC%2FUSD``, as Alpaca asks)."""

    if _UUID.match(symbol or ""):
        return symbol
    return quote(symbol_text(symbol), safe="")


class AuditLog:
    """One JSON line per request that changes something, with what was sent and what came back. Never a key."""

    def __init__(self, path: Optional[Path], clock: Callable[[], float]) -> None:
        self._path = path
        self._clock = clock
        self._lock = threading.Lock()

    def record(self, entry: Mapping[str, Any]) -> None:
        if self._path is None:
            return
        line = json.dumps({"time": datetime.fromtimestamp(self._clock(), timezone.utc).isoformat(timespec="seconds"), **entry}, default=str)
        try:
            with self._lock:
                # What was ordered is private to this user: the directory and the file are owner-only whatever the umask.
                self._path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                descriptor = os.open(self._path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
                with os.fdopen(descriptor, "a", encoding="utf-8") as handle:
                    if hasattr(os, "fchmod"):
                        os.fchmod(handle.fileno(), 0o600)
                    handle.write(line + "\n")
        except OSError:  # a log that cannot be written must not stop a trade the user asked for
            log.warning("could not write the trading audit log %s", self._path, exc_info=True)


class TradingService:
    def __init__(
        self,
        http: Optional[HttpRequest] = None,
        clock: Callable[[], float] = time.time,
        getenv: Optional[Callable[[str], Optional[str]]] = None,
        audit_path: Optional[Path] = None,
    ) -> None:
        self._clock = clock
        self._clients = {env_id: TradingClient(env, http, getenv) for env_id, env in ENVIRONMENTS.items()}
        self._audit = AuditLog(audit_path, clock)
        self._assets: dict[tuple[str, str, str], tuple[float, Outcome]] = {}
        self._assets_lock = threading.Lock()

    # --- environments -----------------------------------------------------------------------------

    def environments(self) -> dict[str, Any]:
        """Which environments exist and whether each is ready. Never a key, and no request to Alpaca."""

        listed = []
        for client in self._clients.values():
            env = client.environment
            enabled = client.enabled()
            listed.append(
                {
                    "id": env.id,
                    "label": env.label,
                    "real_money": env.real_money,
                    "base_url": env.base_url,
                    "enabled": enabled,
                    "configured": client.configured(),
                    "key_env": env.key_env,
                    "secret_env": env.secret_env,
                    "fallback_key_env": env.fallback_key_env,
                    "fallback_secret_env": env.fallback_secret_env,
                    "enable_env": env.enable_env,
                    "note": None if enabled else f"Live trading is off. Set {env.enable_env}=true, with {env.key_env} and {env.secret_env}, in the backend's environment and restart it.",
                }
            )
        return {"default": "paper", "environments": listed}

    def _client(self, env_id: str) -> TradingClient:
        client = self._clients[env_id]  # KeyError for an unknown environment
        if not client.enabled():
            env = client.environment
            raise TradingBlocked(f"{env.label} is switched off. Set {env.enable_env}=true in the backend's environment and restart it to allow it.")
        return client

    # --- the envelope ---------------------------------------------------------------------------------

    def _envelope(self, env_id: str, outcome: Outcome, view: Optional[Callable[[Any], Any]] = None, client_order_id: Optional[str] = None) -> dict[str, Any]:
        data = view(outcome.data) if outcome.status == "ok" and view is not None else None
        return {
            "environment": env_id,
            "status": outcome.status,
            "message": (outcome.message or "")[:600] or None,
            "code": outcome.code,
            "http_status": outcome.http_status,
            "outcome_unknown": outcome.outcome_unknown,
            "client_order_id": client_order_id,
            "data": data,
            "fetched_at": int(self._clock()) if outcome.status != "not_configured" else None,
            "elapsed_ms": outcome.elapsed_ms,
        }

    def _run(
        self,
        env_id: str,
        method: str,
        path: str,
        view: Optional[Callable[[Any], Any]] = None,
        *,
        query: Optional[list[tuple[str, str]]] = None,
        body: Any = None,
        action: Optional[str] = None,
        sent: Optional[Mapping[str, Any]] = None,
        base_url: Optional[str] = None,
        auth_statuses: tuple[int, ...] = (401,),
        client_order_id: Optional[str] = None,
    ) -> dict[str, Any]:
        client = self._client(env_id)
        outcome = client.call(method, path, query=query, body=body, base_url=base_url, auth_statuses=auth_statuses)
        envelope = self._envelope(env_id, outcome, view, client_order_id)
        if action:
            self._audit.record({"environment": env_id, "action": action, "request": dict(sent or {}), "status": outcome.status, "http_status": outcome.http_status, "message": envelope["message"], "outcome_unknown": outcome.outcome_unknown, "result": _audit_result(envelope["data"])})
        return envelope

    # --- account ------------------------------------------------------------------------------------------

    def account(self, env_id: str) -> dict[str, Any]:
        return self._run(env_id, "GET", "/v2/account", V.account_view)

    def configurations(self, env_id: str) -> dict[str, Any]:
        return self._run(env_id, "GET", "/v2/account/configurations", V.config_view)

    def update_configurations(self, env_id: str, payload: Any) -> dict[str, Any]:
        body = validate_config(payload)
        return self._run(env_id, "PATCH", "/v2/account/configurations", V.config_view, body=body, action="update_configurations", sent=body)

    def activities(self, env_id: str, params: Mapping[str, str], activity_type: Optional[str] = None) -> dict[str, Any]:
        query = clean_query(params, _ACTIVITIES_QUERY)
        path = "/v2/account/activities"
        if activity_type:
            if not re.fullmatch(r"[A-Z_]{2,12}", activity_type):
                raise TradingInputError("The activity type must be capital letters such as FILL, DIV or TRANS.")
            path += f"/{activity_type}"

        def view(raw: Any) -> dict[str, Any]:
            items = V._each(raw, V.activity_view)
            return {"activities": items, "next_page_token": items[-1]["id"] if items else None}

        return self._run(env_id, "GET", path, view, query=query)

    def history(self, env_id: str, params: Mapping[str, str]) -> dict[str, Any]:
        return self._run(env_id, "GET", "/v2/account/portfolio/history", V.history_view, query=clean_query(params, _HISTORY_QUERY))

    # --- market -----------------------------------------------------------------------------------------------

    def clock(self, env_id: str) -> dict[str, Any]:
        return self._run(env_id, "GET", "/v2/clock", V.clock_view)

    def calendar(self, env_id: str, params: Mapping[str, str]) -> dict[str, Any]:
        query = clean_query(params, _CALENDAR_QUERY)
        return self._run(env_id, "GET", "/v2/calendar", lambda raw: {"days": V._each(raw, V.calendar_view)}, query=query)

    def asset(self, env_id: str, symbol_or_id: str) -> dict[str, Any]:
        return self._run(env_id, "GET", f"/v2/assets/{_path(symbol_or_id)}", V.asset_view)

    def assets(self, env_id: str, params: Mapping[str, str]) -> dict[str, Any]:
        """Assets matching a search, best match first. The full list is big (thousands of assets), so it is
        fetched once per ten minutes and searched here."""

        opts = dict(clean_query(params, _ASSETS_QUERY))
        asset_class, status = opts.get("asset_class", "us_equity"), opts.get("status", "active")
        client = self._client(env_id)
        key = (env_id, asset_class, status)
        with self._assets_lock:
            cached = self._assets.get(key)
            if cached and self._clock() - cached[0] < ASSET_CACHE_SECONDS:
                outcome = cached[1]
            else:
                outcome = client.call("GET", "/v2/assets", query=[("status", status), ("asset_class", asset_class)])
                if outcome.status == "ok" and isinstance(outcome.data, list):
                    self._assets[key] = (self._clock(), outcome)
        needle = opts.get("search", "").lower()
        exchange = opts.get("exchange", "").upper()
        tradable = None if "tradable" not in opts else opts["tradable"] == "true"
        limit = int(opts.get("limit", "50"))

        def view(raw: Any) -> dict[str, Any]:
            matched = _rank_assets(raw if isinstance(raw, list) else [], needle, exchange, tradable)
            return {"assets": [V.asset_view(a) for a in matched[:limit]], "total": len(matched)}

        return self._envelope(env_id, outcome, view)

    def contract(self, env_id: str, symbol_or_id: str) -> dict[str, Any]:
        return self._run(env_id, "GET", f"/v2/options/contracts/{_path(symbol_or_id)}", V.contract_view)

    def contracts(self, env_id: str, params: Mapping[str, str]) -> dict[str, Any]:
        query = clean_query(params, _CONTRACTS_QUERY)

        def view(raw: Any) -> dict[str, Any]:
            body = raw if isinstance(raw, dict) else {}
            return {"contracts": V._each(body.get("option_contracts"), V.contract_view), "next_page_token": V.text(body.get("next_page_token"))}

        return self._run(env_id, "GET", "/v2/options/contracts", view, query=query)

    def quote(self, env_id: str, symbol: str, params: Mapping[str, str]) -> dict[str, Any]:
        """Bid, ask, last and the day so far for one symbol, from Alpaca's market data (the same keys)."""

        name = symbol_text(symbol)
        kind = dict(clean_query(params, _QUOTE_QUERY)).get("asset_class") or asset_kind(name)
        if kind == "us_equity":
            path, query = f"/v2/stocks/{quote(name, safe='')}/snapshot", []
        elif kind == "crypto":
            path, query = "/v1beta3/crypto/us/snapshots", [("symbols", name)]
        else:
            path, query = "/v1beta1/options/snapshots", [("symbols", name)]
        outcome = self._client(env_id).call("GET", path, query=query, base_url=DATA_URL, auth_statuses=(401, 403))
        if outcome.status == "ok" and V.snapshot_for(name, kind, outcome.data) is None:
            outcome = Outcome("not_found", outcome.http_status, f"Alpaca has no quote for {name}. Check the symbol.", None, None, outcome.elapsed_ms)
        return self._envelope(env_id, outcome, lambda raw: V.quote_view(name, kind, raw))

    # --- orders --------------------------------------------------------------------------------------------------

    def orders(self, env_id: str, params: Mapping[str, str]) -> dict[str, Any]:
        query = clean_query(params, _ORDERS_QUERY)
        if not any(name == "nested" for name, _ in query):
            query.append(("nested", "true"))
        return self._run(env_id, "GET", "/v2/orders", lambda raw: {"orders": V._each(raw, V.order_view)}, query=query)

    def order(self, env_id: str, order_id: str) -> dict[str, Any]:
        return self._run(env_id, "GET", f"/v2/orders/{_id(order_id, 'The order ID')}", V.order_view, query=[("nested", "true")])

    def order_by_client_id(self, env_id: str, client_order_id: str) -> dict[str, Any]:
        if not client_order_id or len(client_order_id) > 128:
            raise TradingInputError("client_order_id must be 1 to 128 characters.")
        return self._run(env_id, "GET", "/v2/orders:by_client_order_id", V.order_view, query=[("client_order_id", client_order_id)])

    def place_order(self, env_id: str, payload: Any) -> dict[str, Any]:
        self._client(env_id)
        body = validate_order(payload)
        body.setdefault("client_order_id", "tvdata-" + uuid.uuid4().hex)
        return self._run(env_id, "POST", "/v2/orders", V.order_view, body=body, action="place_order", sent=body, client_order_id=body["client_order_id"])

    def replace_order(self, env_id: str, order_id: str, payload: Any) -> dict[str, Any]:
        order_id = _id(order_id, "The order ID")
        body = validate_replace(payload)
        return self._run(env_id, "PATCH", f"/v2/orders/{order_id}", V.order_view, body=body, action="replace_order", sent={"order_id": order_id, **body})

    def cancel_order(self, env_id: str, order_id: str) -> dict[str, Any]:
        order_id = _id(order_id, "The order ID")
        return self._run(env_id, "DELETE", f"/v2/orders/{order_id}", None, action="cancel_order", sent={"order_id": order_id})

    def cancel_all_orders(self, env_id: str) -> dict[str, Any]:
        return self._run(env_id, "DELETE", "/v2/orders", lambda raw: {"results": V.bulk_view(raw, "id")}, action="cancel_all_orders")

    # --- positions -------------------------------------------------------------------------------------------------

    def positions(self, env_id: str) -> dict[str, Any]:
        return self._run(env_id, "GET", "/v2/positions", lambda raw: {"positions": V._each(raw, V.position_view)})

    def position(self, env_id: str, symbol_or_id: str) -> dict[str, Any]:
        return self._run(env_id, "GET", f"/v2/positions/{_path(symbol_or_id)}", V.position_view)

    def close_position(self, env_id: str, symbol_or_id: str, params: Mapping[str, str]) -> dict[str, Any]:
        """Sell or buy back the whole position, or ``qty`` shares of it, or ``percentage`` percent of it."""

        query = clean_query(params, _CLOSE_QUERY)
        opts = dict(query)
        if "qty" in opts and "percentage" in opts:
            raise TradingInputError("Give either qty or percentage, not both.")
        for name, value in opts.items():
            if float(value) <= 0:
                raise TradingInputError(f"{name} must be greater than zero.")
        if "percentage" in opts and float(opts["percentage"]) > 100:
            raise TradingInputError("percentage must be at most 100.")
        return self._run(env_id, "DELETE", f"/v2/positions/{_path(symbol_or_id)}", V.order_view, query=query, action="close_position", sent={"symbol": symbol_or_id, **opts})

    def close_all_positions(self, env_id: str, params: Mapping[str, str]) -> dict[str, Any]:
        query = clean_query(params, {"cancel_orders": ("bool",)})
        return self._run(env_id, "DELETE", "/v2/positions", lambda raw: {"results": V.bulk_view(raw, "symbol")}, query=query, action="close_all_positions", sent=dict(query))

    def exercise(self, env_id: str, symbol_or_id: str) -> dict[str, Any]:
        return self._run(env_id, "POST", f"/v2/positions/{_path(symbol_or_id)}/exercise", None, action="exercise_option", sent={"contract": symbol_or_id})

    def do_not_exercise(self, env_id: str, symbol_or_id: str) -> dict[str, Any]:
        return self._run(env_id, "POST", f"/v2/positions/{_path(symbol_or_id)}/do-not-exercise", None, action="do_not_exercise_option", sent={"contract": symbol_or_id})

    # --- watchlists -----------------------------------------------------------------------------------------------------

    def watchlists(self, env_id: str) -> dict[str, Any]:
        return self._run(env_id, "GET", "/v2/watchlists", lambda raw: {"watchlists": V._each(raw, V.watchlist_view)})

    def watchlist(self, env_id: str, watchlist_id: str) -> dict[str, Any]:
        return self._run(env_id, "GET", f"/v2/watchlists/{_id(watchlist_id, 'The watchlist ID')}", V.watchlist_view)

    def create_watchlist(self, env_id: str, payload: Any) -> dict[str, Any]:
        body = validate_watchlist(payload, creating=True)
        return self._run(env_id, "POST", "/v2/watchlists", V.watchlist_view, body=body, action="create_watchlist", sent=body)

    def update_watchlist(self, env_id: str, watchlist_id: str, payload: Any) -> dict[str, Any]:
        watchlist_id = _id(watchlist_id, "The watchlist ID")
        body = validate_watchlist(payload, creating=False)
        return self._run(env_id, "PUT", f"/v2/watchlists/{watchlist_id}", V.watchlist_view, body=body, action="update_watchlist", sent={"watchlist_id": watchlist_id, **body})

    def delete_watchlist(self, env_id: str, watchlist_id: str) -> dict[str, Any]:
        watchlist_id = _id(watchlist_id, "The watchlist ID")
        return self._run(env_id, "DELETE", f"/v2/watchlists/{watchlist_id}", None, action="delete_watchlist", sent={"watchlist_id": watchlist_id})

    def add_watchlist_asset(self, env_id: str, watchlist_id: str, symbol: Any) -> dict[str, Any]:
        watchlist_id = _id(watchlist_id, "The watchlist ID")
        name = symbol_text(symbol)
        return self._run(env_id, "POST", f"/v2/watchlists/{watchlist_id}", V.watchlist_view, body={"symbol": name}, action="add_watchlist_asset", sent={"watchlist_id": watchlist_id, "symbol": name})

    def remove_watchlist_asset(self, env_id: str, watchlist_id: str, symbol: str) -> dict[str, Any]:
        watchlist_id = _id(watchlist_id, "The watchlist ID")
        name = symbol_text(symbol)
        return self._run(env_id, "DELETE", f"/v2/watchlists/{watchlist_id}/{quote(name, safe='')}", V.watchlist_view, action="remove_watchlist_asset", sent={"watchlist_id": watchlist_id, "symbol": name})


def _rank_assets(assets: list[Any], needle: str, exchange: str, tradable: Optional[bool]) -> list[dict[str, Any]]:
    """Assets that match, an exact symbol first, then symbols that start with the search, then names that contain it."""

    ranked = []
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        symbol, name = str(asset.get("symbol") or "").lower(), str(asset.get("name") or "").lower()
        if exchange and str(asset.get("exchange") or "").upper() != exchange:
            continue
        if tradable is not None and bool(asset.get("tradable")) != tradable:
            continue
        if not needle:
            rank = 3
        elif symbol == needle:
            rank = 0
        elif symbol.startswith(needle):
            rank = 1
        elif needle in symbol or needle in name:
            rank = 2
        else:
            continue
        ranked.append((rank, len(symbol), symbol, asset))
    ranked.sort(key=lambda item: item[:3])
    return [item[3] for item in ranked]


def _audit_result(data: Any) -> Any:
    """The few fields of an answer worth keeping in the audit log: which order, which state."""

    if isinstance(data, dict):
        kept = {name: data[name] for name in ("id", "client_order_id", "status", "symbol", "side", "qty", "notional", "filled_qty") if name in data and data[name] is not None}
        if "results" in data:
            kept["results"] = [{k: r.get(k) for k in ("id", "symbol", "status")} for r in data["results"]]
        return kept or None
    return None
