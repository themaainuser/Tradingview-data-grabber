"""HTTP routes for trading, under ``/api/trading``.

Two guards protect them, because they can spend money and the server has no login:

* the ``Host`` header must be a local name (or one listed in ``TVDATA_TRADING_ALLOWED_HOSTS``), which
  stops a web page from reaching the server by pointing its own domain at 127.0.0.1;
* every request that changes something must carry ``X-Tvdata-Trading: 1``. A browser will not add a
  header like that to a request made from another site without first asking the server, and the
  server does not agree.
"""

from __future__ import annotations

import os
from typing import Any, Callable, Dict, Iterable, Optional

from fastapi import APIRouter, Body, Depends, FastAPI, HTTPException, Request
from fastapi.responses import Response

from .service import TradingBlocked, TradingService
from .validation import TradingInputError

WRITE_HEADER = "x-tvdata-trading"
LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1")
HOSTS_ENV = "TVDATA_TRADING_ALLOWED_HOSTS"


def allowed_hosts(extra: Iterable[str] = ()) -> frozenset[str]:
    """The local names, ``extra``, and whatever ``TVDATA_TRADING_ALLOWED_HOSTS`` lists (comma separated)."""

    configured = [name.strip().lower() for name in os.environ.get(HOSTS_ENV, "").split(",") if name.strip()]
    return frozenset([*LOCAL_HOSTS, *(name.lower() for name in extra), *configured])


def host_name(header: str) -> str:
    """The host part of a ``Host`` header: no port, no brackets around an IPv6 address."""

    host = header.strip().lower()
    if host.startswith("["):
        return host[1 : host.find("]")] if "]" in host else host
    return host.rsplit(":", 1)[0] if host.count(":") == 1 else host


def register_trading_routes(app: FastAPI, service: TradingService, respond: Callable[[Any], Response], hosts: Optional[Iterable[str]] = None) -> None:
    """Adds the trading routes. ``respond`` serialises a payload (the API's NaN-safe JSON response)."""

    allowed = allowed_hosts(hosts or ())

    def local_only(request: Request) -> None:
        name = host_name(request.headers.get("host", ""))
        if name not in allowed:
            raise HTTPException(status_code=403, detail=f"Trading is not served to the host {name!r}. Open the dashboard through localhost, or list this name in {HOSTS_ENV} and restart the backend.")

    def may_change(request: Request) -> None:
        local_only(request)
        if request.headers.get(WRITE_HEADER) != "1":
            raise HTTPException(status_code=403, detail="This request changes something and must come from the dashboard: it has no X-Tvdata-Trading header.")

    reading = APIRouter(prefix="/api/trading", dependencies=[Depends(local_only)])
    writing = APIRouter(prefix="/api/trading", dependencies=[Depends(may_change)])

    def answer(action: Callable[[], Dict[str, Any]]) -> Response:
        try:
            return respond(action())
        except KeyError:
            raise HTTPException(status_code=404, detail="Unknown trading environment: use paper or live.") from None
        except TradingBlocked as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from None
        except TradingInputError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None

    def query(request: Request) -> Dict[str, str]:
        return dict(request.query_params)

    # --- reading -------------------------------------------------------------------------------------------

    @reading.get("/environments")
    def environments() -> Response:
        """Paper and live: whether each is switched on and has keys. Never a key."""

        return respond(service.environments())

    @reading.get("/{env}/account")
    def account(env: str) -> Response:
        return answer(lambda: service.account(env))

    @reading.get("/{env}/account/configurations")
    def configurations(env: str) -> Response:
        return answer(lambda: service.configurations(env))

    @reading.get("/{env}/account/activities")
    def activities(env: str, request: Request) -> Response:
        return answer(lambda: service.activities(env, query(request)))

    @reading.get("/{env}/account/activities/{activity_type}")
    def activities_of_type(env: str, activity_type: str, request: Request) -> Response:
        return answer(lambda: service.activities(env, query(request), activity_type))

    @reading.get("/{env}/account/portfolio-history")
    def history(env: str, request: Request) -> Response:
        return answer(lambda: service.history(env, query(request)))

    @reading.get("/{env}/clock")
    def clock(env: str) -> Response:
        return answer(lambda: service.clock(env))

    @reading.get("/{env}/calendar")
    def calendar(env: str, request: Request) -> Response:
        return answer(lambda: service.calendar(env, query(request)))

    @reading.get("/{env}/assets")
    def assets(env: str, request: Request) -> Response:
        return answer(lambda: service.assets(env, query(request)))

    @reading.get("/{env}/assets/{symbol_or_id:path}")
    def asset(env: str, symbol_or_id: str) -> Response:
        return answer(lambda: service.asset(env, symbol_or_id))

    @reading.get("/{env}/options/contracts")
    def contracts(env: str, request: Request) -> Response:
        return answer(lambda: service.contracts(env, query(request)))

    @reading.get("/{env}/options/contracts/{symbol_or_id}")
    def contract(env: str, symbol_or_id: str) -> Response:
        return answer(lambda: service.contract(env, symbol_or_id))

    @reading.get("/{env}/quote/{symbol:path}")
    def quote(env: str, symbol: str, request: Request) -> Response:
        return answer(lambda: service.quote(env, symbol, query(request)))

    @reading.get("/{env}/orders")
    def orders(env: str, request: Request) -> Response:
        return answer(lambda: service.orders(env, query(request)))

    @reading.get("/{env}/orders/by-client-id/{client_order_id}")
    def order_by_client_id(env: str, client_order_id: str) -> Response:
        return answer(lambda: service.order_by_client_id(env, client_order_id))

    @reading.get("/{env}/orders/{order_id}")
    def order(env: str, order_id: str) -> Response:
        return answer(lambda: service.order(env, order_id))

    @reading.get("/{env}/positions")
    def positions(env: str) -> Response:
        return answer(lambda: service.positions(env))

    @reading.get("/{env}/positions/{symbol_or_id:path}")
    def position(env: str, symbol_or_id: str) -> Response:
        return answer(lambda: service.position(env, symbol_or_id))

    @reading.get("/{env}/watchlists")
    def watchlists(env: str) -> Response:
        return answer(lambda: service.watchlists(env))

    @reading.get("/{env}/watchlists/{watchlist_id}")
    def watchlist(env: str, watchlist_id: str) -> Response:
        return answer(lambda: service.watchlist(env, watchlist_id))

    # --- changing things -----------------------------------------------------------------------------------------

    @writing.patch("/{env}/account/configurations")
    def update_configurations(env: str, body: Dict[str, Any] = Body(...)) -> Response:
        return answer(lambda: service.update_configurations(env, body))

    @writing.post("/{env}/orders")
    def place_order(env: str, body: Dict[str, Any] = Body(...)) -> Response:
        return answer(lambda: service.place_order(env, body))

    @writing.delete("/{env}/orders")
    def cancel_all_orders(env: str) -> Response:
        return answer(lambda: service.cancel_all_orders(env))

    @writing.patch("/{env}/orders/{order_id}")
    def replace_order(env: str, order_id: str, body: Dict[str, Any] = Body(...)) -> Response:
        return answer(lambda: service.replace_order(env, order_id, body))

    @writing.delete("/{env}/orders/{order_id}")
    def cancel_order(env: str, order_id: str) -> Response:
        return answer(lambda: service.cancel_order(env, order_id))

    @writing.post("/{env}/positions/{symbol_or_id}/exercise")
    def exercise(env: str, symbol_or_id: str) -> Response:
        return answer(lambda: service.exercise(env, symbol_or_id))

    @writing.post("/{env}/positions/{symbol_or_id}/do-not-exercise")
    def do_not_exercise(env: str, symbol_or_id: str) -> Response:
        return answer(lambda: service.do_not_exercise(env, symbol_or_id))

    @writing.delete("/{env}/positions")
    def close_all_positions(env: str, request: Request) -> Response:
        return answer(lambda: service.close_all_positions(env, query(request)))

    @writing.delete("/{env}/positions/{symbol_or_id:path}")
    def close_position(env: str, symbol_or_id: str, request: Request) -> Response:
        return answer(lambda: service.close_position(env, symbol_or_id, query(request)))

    @writing.post("/{env}/watchlists")
    def create_watchlist(env: str, body: Dict[str, Any] = Body(...)) -> Response:
        return answer(lambda: service.create_watchlist(env, body))

    @writing.put("/{env}/watchlists/{watchlist_id}")
    def update_watchlist(env: str, watchlist_id: str, body: Dict[str, Any] = Body(...)) -> Response:
        return answer(lambda: service.update_watchlist(env, watchlist_id, body))

    @writing.delete("/{env}/watchlists/{watchlist_id}")
    def delete_watchlist(env: str, watchlist_id: str) -> Response:
        return answer(lambda: service.delete_watchlist(env, watchlist_id))

    @writing.post("/{env}/watchlists/{watchlist_id}/assets")
    def add_watchlist_asset(env: str, watchlist_id: str, body: Dict[str, Any] = Body(...)) -> Response:
        return answer(lambda: service.add_watchlist_asset(env, watchlist_id, body.get("symbol")))

    @writing.delete("/{env}/watchlists/{watchlist_id}/assets/{symbol}")
    def remove_watchlist_asset(env: str, watchlist_id: str, symbol: str) -> Response:
        return answer(lambda: service.remove_watchlist_asset(env, watchlist_id, symbol))

    app.include_router(reading)
    app.include_router(writing)
