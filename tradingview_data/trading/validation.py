"""Checks every trading request before anything is sent to Alpaca.

Alpaca is the authority, and it answers a bad order with its own message. These checks exist so that
a mistake that is certain is caught first and in plain words, above all values that would otherwise
be ignored silently: a ``limit_price`` on a market order reads like a price cap and is not one. A rule
is enforced here only when Alpaca's documentation states it; anything unclear is left to Alpaca.

Values leave here as the strings Alpaca takes, and numbers are never rounded.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Optional, Sequence

from ..providers.common import valid_moment


class TradingInputError(ValueError):
    """A request that is wrong in a way that can be said in one plain sentence."""


SIDES = ("buy", "sell")
ORDER_TYPES = ("market", "limit", "stop", "stop_limit", "trailing_stop")
TIME_IN_FORCE = ("day", "gtc", "opg", "cls", "ioc", "fok")
ORDER_CLASSES = ("simple", "bracket", "oco", "oto", "mleg")
POSITION_INTENTS = ("buy_to_open", "buy_to_close", "sell_to_open", "sell_to_close")

# What Alpaca documents for each kind of asset (the `type`, `time_in_force` and `order_class` field descriptions).
_TYPES = {
    "us_equity": ORDER_TYPES,
    "us_option": ("market", "limit", "stop", "stop_limit"),
    "crypto": ("market", "limit", "stop_limit"),
}
_TIME_IN_FORCE = {"us_equity": TIME_IN_FORCE, "us_option": ("day", "gtc"), "crypto": ("gtc", "ioc")}
_CLASSES = {"us_equity": ("simple", "oco", "oto", "bracket"), "us_option": ("simple",), "crypto": ("simple",)}
_KIND_NAMES = {"us_equity": "stocks and ETFs", "us_option": "options", "crypto": "crypto"}

_SYMBOL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/\-]{0,31}$")
_OPTION_SYMBOL = re.compile(r"^[A-Z0-9.]{1,6}\d{6}[CP]\d{8}$")
_ORDER_FIELDS = {
    "symbol", "side", "type", "time_in_force", "qty", "notional", "limit_price", "stop_price", "trail_price",
    "trail_percent", "extended_hours", "client_order_id", "order_class", "take_profit", "stop_loss", "position_intent", "legs",
}
_MAX_DECIMALS = 9
_CLIENT_ID_MAX = 128


def asset_kind(symbol: str) -> str:
    """``crypto`` for a pair with a slash (``BTC/USD``), ``us_option`` for an OCC contract symbol, else ``us_equity``."""

    if "/" in symbol:
        return "crypto"
    return "us_option" if _OPTION_SYMBOL.match(symbol) else "us_equity"


# --- scalars --------------------------------------------------------------------------------------


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _text(payload: Mapping[str, Any], name: str, limit: int = 200) -> Optional[str]:
    value = payload.get(name)
    if _blank(value):
        return None
    if not isinstance(value, str):
        raise TradingInputError(f"{name} must be text.")
    if len(value) > limit:
        raise TradingInputError(f"{name} is too long (limit {limit} characters).")
    return value.strip()


def _choice(payload: Mapping[str, Any], name: str, allowed: Sequence[str], *, required: bool = False) -> Optional[str]:
    value = _text(payload, name)
    if value is None:
        if required:
            raise TradingInputError(f"{name} is required.")
        return None
    value = value.lower()
    if value not in allowed:
        raise TradingInputError(f"{name} must be one of: {', '.join(allowed)}.")
    return value


def _decimal(payload: Mapping[str, Any], name: str, *, negative: bool = False, zero: bool = False, whole: bool = False) -> Optional[str]:
    """A finite decimal as the string Alpaca takes; positive unless ``negative``/``zero`` allow more."""

    value = payload.get(name)
    if _blank(value):
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise TradingInputError(f"{name} must be a number.")
    try:
        number = Decimal(str(value).strip())
    except InvalidOperation:
        raise TradingInputError(f"{name} must be a number.") from None
    if not number.is_finite():
        raise TradingInputError(f"{name} must be a number.")
    if (number == 0 and not zero) or (number < 0 and not negative):
        raise TradingInputError(f"{name} must be greater than zero.")
    if whole and number != number.to_integral_value():
        raise TradingInputError(f"{name} must be a whole number.")
    if -number.as_tuple().exponent > _MAX_DECIMALS:  # type: ignore[operator]
        raise TradingInputError(f"{name} can have at most {_MAX_DECIMALS} decimal places.")
    return format(number, "f")


def _boolean(payload: Mapping[str, Any], name: str) -> Optional[bool]:
    value = payload.get(name)
    if value is None:
        return None
    if not isinstance(value, bool):
        raise TradingInputError(f"{name} must be true or false.")
    return value


def symbol_text(value: Any, name: str = "symbol") -> str:
    """An upper-case symbol; letters, digits and ``. - /`` only, so it can never reshape a URL."""

    if not isinstance(value, str) or not _SYMBOL.match(value.strip()):
        raise TradingInputError(f"{name} must be a symbol such as AAPL, BTC/USD or AAPL260116C00250000.")
    return value.strip().upper()


def _only(payload: Mapping[str, Any], allowed: set[str], what: str) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise TradingInputError(f"Unknown {what} field {unknown[0]!r}.")


def _intent(payload: Mapping[str, Any], side: Optional[str], where: str) -> Optional[str]:
    intent = _choice(payload, "position_intent", POSITION_INTENTS)
    if intent and side and not intent.startswith(side):
        raise TradingInputError(f"{where}position_intent {intent} does not match side {side}.")
    return intent


# --- orders ---------------------------------------------------------------------------------------


def validate_order(payload: Any) -> dict[str, Any]:
    """The body to send to ``POST /v2/orders``, or a :class:`TradingInputError` saying what is wrong."""

    if not isinstance(payload, dict):
        raise TradingInputError("The order must be an object.")
    _only(payload, _ORDER_FIELDS, "order")
    order_class = _choice(payload, "order_class", ORDER_CLASSES) or "simple"
    if order_class == "mleg":
        return _validate_multileg(payload)
    if payload.get("legs"):
        raise TradingInputError("legs are only for order_class mleg.")
    symbol = symbol_text(payload.get("symbol"))
    side = _choice(payload, "side", SIDES, required=True)
    kind = asset_kind(symbol)
    where = _KIND_NAMES[kind]
    order_type = _choice(payload, "type", ORDER_TYPES, required=True)
    tif = _choice(payload, "time_in_force", TIME_IN_FORCE, required=True)
    assert order_type and tif and side
    if order_type not in _TYPES[kind]:
        raise TradingInputError(f"{order_type} orders are not available for {where}; use one of: {', '.join(_TYPES[kind])}.")
    if tif not in _TIME_IN_FORCE[kind]:
        raise TradingInputError(f"time_in_force {tif} is not available for {where}; use one of: {', '.join(_TIME_IN_FORCE[kind])}.")
    if order_class not in _CLASSES[kind]:
        raise TradingInputError(f"order_class {order_class} is not available for {where}; use one of: {', '.join(_CLASSES[kind])}.")

    body: dict[str, Any] = {"symbol": symbol, "side": side, "type": order_type, "time_in_force": tif}
    qty, notional = _decimal(payload, "qty"), _decimal(payload, "notional")
    if qty is None and notional is None:
        raise TradingInputError("Give a qty (shares or contracts) or a notional (a dollar amount).")
    if qty is not None and notional is not None:
        raise TradingInputError("Give either qty or notional, not both.")
    if notional is not None:
        if kind == "us_option":
            raise TradingInputError("notional is not available for options; use qty.")
        if order_type != "market":
            raise TradingInputError("notional orders must be market orders.")
        if kind == "us_equity" and tif != "day":
            raise TradingInputError("notional orders must use time_in_force day.")
        body["notional"] = notional
    if qty is not None:
        number = Decimal(qty)
        if kind == "us_option" and number != number.to_integral_value():
            raise TradingInputError("Options are traded in whole contracts.")
        if kind == "us_equity" and number != number.to_integral_value():
            if tif != "day":
                raise TradingInputError("Fractional quantities need time_in_force day.")
            if order_type == "trailing_stop":
                raise TradingInputError("Fractional quantities are not available for trailing stops.")
        body["qty"] = qty

    _prices(payload, body, order_type)
    if tif in ("opg", "cls", "ioc", "fok") and order_type not in ("market", "limit"):
        raise TradingInputError(f"time_in_force {tif} is only for market and limit orders.")
    extended = _boolean(payload, "extended_hours")
    if extended:
        if order_type != "limit" or tif not in ("day", "gtc"):
            raise TradingInputError("extended_hours works only with limit orders and time_in_force day or gtc.")
        body["extended_hours"] = True
    client_id = _text(payload, "client_order_id", _CLIENT_ID_MAX)
    if client_id:
        body["client_order_id"] = client_id
    intent = _intent(payload, side, "")
    if intent:
        if kind != "us_option":
            raise TradingInputError("position_intent is only for options.")
        body["position_intent"] = intent
    _exits(payload, body, order_class, order_type)
    return body


def _prices(payload: Mapping[str, Any], body: dict[str, Any], order_type: str) -> None:
    """The price fields an order of this type needs, and a refusal for any it would ignore."""

    wanted = {
        "limit_price": order_type in ("limit", "stop_limit"),
        "stop_price": order_type in ("stop", "stop_limit"),
    }
    for name, needed in wanted.items():
        value = _decimal(payload, name)
        if needed and value is None:
            raise TradingInputError(f"{name} is required for a {order_type} order.")
        if value is not None and not needed:
            raise TradingInputError(f"{name} does not apply to a {order_type} order and would be ignored; remove it.")
        if value is not None:
            body[name] = value
    trail_price, trail_percent = _decimal(payload, "trail_price"), _decimal(payload, "trail_percent")
    if order_type == "trailing_stop":
        if (trail_price is None) == (trail_percent is None):
            raise TradingInputError("A trailing stop needs exactly one of trail_price or trail_percent.")
        if trail_price is not None:
            body["trail_price"] = trail_price
        if trail_percent is not None:
            body["trail_percent"] = trail_percent
    elif trail_price is not None or trail_percent is not None:
        raise TradingInputError("trail_price and trail_percent are only for trailing_stop orders.")


def _exits(payload: Mapping[str, Any], body: dict[str, Any], order_class: str, order_type: str) -> None:
    """Bracket, one-cancels-other and one-triggers-other orders: which exit legs each needs."""

    take_profit, stop_loss = payload.get("take_profit"), payload.get("stop_loss")
    has_tp, has_sl = not _blank(take_profit), not _blank(stop_loss)
    if order_class == "simple":
        if has_tp or has_sl:
            raise TradingInputError("take_profit and stop_loss need order_class bracket, oto or oco.")
        return
    body["order_class"] = order_class
    if order_class in ("bracket", "oco") and not (has_tp and has_sl):
        raise TradingInputError(f"A {order_class} order needs both take_profit and stop_loss.")
    if order_class == "oto" and has_tp == has_sl:
        raise TradingInputError("An oto order needs exactly one of take_profit or stop_loss.")
    if order_class in ("bracket", "oto") and order_type not in ("market", "limit"):
        raise TradingInputError(f"The entry order of a {order_class} order must be a market or limit order.")
    if order_class == "oco" and order_type != "limit":
        raise TradingInputError("An oco order is a limit order that exits an open position; use type limit.")
    if has_tp:
        leg = _leg(take_profit, "take_profit", {"limit_price"})
        price = _decimal(leg, "limit_price")
        if price is None:
            raise TradingInputError("take_profit.limit_price is required.")
        body["take_profit"] = {"limit_price": price}
    if has_sl:
        leg = _leg(stop_loss, "stop_loss", {"stop_price", "limit_price"})
        stop = _decimal(leg, "stop_price")
        if stop is None:
            raise TradingInputError("stop_loss.stop_price is required.")
        limit = _decimal(leg, "limit_price")
        body["stop_loss"] = {"stop_price": stop, **({"limit_price": limit} if limit else {})}


def _leg(value: Any, name: str, allowed: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TradingInputError(f"{name} must be an object.")
    _only(value, allowed, name)
    return value


def _validate_multileg(payload: Mapping[str, Any]) -> dict[str, Any]:
    """A multi-leg options order: two to four legs, one net price (a debit is positive, a credit negative)."""

    for name in ("symbol", "side", "notional", "stop_price", "trail_price", "trail_percent", "take_profit", "stop_loss", "position_intent"):
        if not _blank(payload.get(name)):
            raise TradingInputError(f"{name} does not apply to a multi-leg order; set it on the legs.")
    if payload.get("extended_hours"):
        raise TradingInputError("extended_hours does not apply to options.")
    order_type = _choice(payload, "type", ("market", "limit"), required=True)
    tif = _choice(payload, "time_in_force", ("day", "gtc"), required=True)
    assert order_type and tif
    qty = _decimal(payload, "qty", whole=True)
    if qty is None:
        raise TradingInputError("qty is required: the number of units of the whole strategy.")
    body: dict[str, Any] = {"order_class": "mleg", "type": order_type, "time_in_force": tif, "qty": qty}
    limit = _decimal(payload, "limit_price", negative=True, zero=True)
    if order_type == "limit" and limit is None:
        raise TradingInputError("limit_price is required for a limit order: positive for a debit, negative for a credit.")
    if order_type == "market" and limit is not None:
        raise TradingInputError("limit_price does not apply to a market order and would be ignored; remove it.")
    if limit is not None:
        body["limit_price"] = limit
    client_id = _text(payload, "client_order_id", _CLIENT_ID_MAX)
    if client_id:
        body["client_order_id"] = client_id
    legs = payload.get("legs")
    if not isinstance(legs, list) or not 2 <= len(legs) <= 4:
        raise TradingInputError("A multi-leg order needs two to four legs.")
    seen: set[str] = set()
    body["legs"] = []
    for number, raw in enumerate(legs, start=1):
        where = f"Leg {number}: "
        leg = _leg(raw, f"leg {number}", {"symbol", "ratio_qty", "side", "position_intent"})
        try:
            symbol = symbol_text(leg.get("symbol"))
            if not _OPTION_SYMBOL.match(symbol):
                raise TradingInputError("symbol must be an option contract such as AAPL260116C00250000.")
            ratio = _decimal(leg, "ratio_qty", whole=True)
            if ratio is None:
                raise TradingInputError("ratio_qty is required.")
            side = _choice(leg, "side", SIDES)
            intent = _intent(leg, side, "")
            if side is None and intent is None:
                raise TradingInputError("side or position_intent is required.")
            side = side or intent.split("_")[0]  # type: ignore[union-attr]
        except TradingInputError as exc:
            raise TradingInputError(where + str(exc)) from None
        if symbol in seen:
            raise TradingInputError(f"{where}{symbol} appears twice; use ratio_qty for more of one contract.")
        seen.add(symbol)
        body["legs"].append({"symbol": symbol, "ratio_qty": ratio, "side": side, **({"position_intent": intent} if intent else {})})
    return body


def validate_replace(payload: Any) -> dict[str, Any]:
    """The body to send to ``PATCH /v2/orders/{id}``: only what changes."""

    if not isinstance(payload, dict):
        raise TradingInputError("The change must be an object.")
    _only(payload, {"qty", "limit_price", "stop_price", "trail", "time_in_force", "client_order_id"}, "order")
    body: dict[str, Any] = {}
    qty = _decimal(payload, "qty", whole=True)
    if qty is not None:
        body["qty"] = qty
    for name in ("limit_price", "stop_price", "trail"):
        value = _decimal(payload, name)
        if value is not None:
            body[name] = value
    tif = _choice(payload, "time_in_force", TIME_IN_FORCE)
    if tif:
        body["time_in_force"] = tif
    client_id = _text(payload, "client_order_id", _CLIENT_ID_MAX)
    if client_id:
        body["client_order_id"] = client_id
    if not body:
        raise TradingInputError("Nothing to change: give a new qty, limit_price, stop_price, trail or time_in_force.")
    return body


# --- account and watchlists -----------------------------------------------------------------------

_CONFIG_BOOLEANS = ("suspend_trade", "no_shorting", "fractional_trading", "disable_overnight_trading", "ptp_no_exception_entry")


def validate_config(payload: Any) -> dict[str, Any]:
    """The body to send to ``PATCH /v2/account/configurations``."""

    if not isinstance(payload, dict):
        raise TradingInputError("The settings must be an object.")
    _only(payload, {*_CONFIG_BOOLEANS, "trade_confirm_email", "max_margin_multiplier", "max_options_trading_level"}, "setting")
    body: dict[str, Any] = {}
    for name in _CONFIG_BOOLEANS:
        value = _boolean(payload, name)
        if value is not None:
            body[name] = value
    email = _choice(payload, "trade_confirm_email", ("all", "none"))
    if email:
        body["trade_confirm_email"] = email
    multiplier = payload.get("max_margin_multiplier")
    if not _blank(multiplier):
        if str(multiplier).strip() not in ("1", "2", "4") or isinstance(multiplier, bool):
            raise TradingInputError("max_margin_multiplier must be 1, 2 or 4.")
        body["max_margin_multiplier"] = str(multiplier).strip()
    level = payload.get("max_options_trading_level")
    if level is not None:
        if isinstance(level, bool) or not isinstance(level, int) or not 0 <= level <= 3:
            raise TradingInputError("max_options_trading_level must be 0, 1, 2 or 3.")
        body["max_options_trading_level"] = level
    if not body:
        raise TradingInputError("Nothing to change.")
    return body


def validate_watchlist(payload: Any, *, creating: bool) -> dict[str, Any]:
    """A watchlist's name and symbols. Creating needs a name; updating needs a name or symbols."""

    if not isinstance(payload, dict):
        raise TradingInputError("The watchlist must be an object.")
    _only(payload, {"name", "symbols"}, "watchlist")
    body: dict[str, Any] = {}
    name = _text(payload, "name", 64)
    if name:
        body["name"] = name
    symbols = payload.get("symbols")
    if symbols is not None:
        if not isinstance(symbols, list) or len(symbols) > 200:
            raise TradingInputError("symbols must be a list of at most 200 symbols.")
        body["symbols"] = list(dict.fromkeys(symbol_text(s, "symbols") for s in symbols))
    if creating and "name" not in body:
        raise TradingInputError("A watchlist needs a name.")
    if not body:
        raise TradingInputError("Nothing to change: give a name or symbols.")
    return body


# --- queries --------------------------------------------------------------------------------------

Spec = Mapping[str, tuple]


def clean_query(params: Mapping[str, str], spec: Spec) -> list[tuple[str, str]]:
    """The query string for Alpaca: only the parameters ``spec`` names, each checked by its kind.

Kinds: ``("enum", values)``, ``("int", low, high)``, ``("bool",)``, ``("date",)``, ``("moment",)``
    (a date or an RFC-3339 timestamp), ``("number",)``, ``("list", pattern, most)`` (comma separated),
    ``("regex", pattern, hint)`` and ``("text", limit)``. An enum is matched without regard to case and sent
    as it is written in ``values``. Empty values are dropped.
    """

    clean: list[tuple[str, str]] = []
    for name, raw in params.items():
        if name not in spec:
            raise TradingInputError(f"Unknown parameter {name!r}.")
        value = str(raw).strip()
        if not value:
            continue
        kind = spec[name]
        clean.append((name, _query_value(name, value, kind)))
    return clean


def _query_value(name: str, value: str, kind: tuple) -> str:
    tag = kind[0]
    if tag == "enum":
        canonical = {option.lower(): option for option in kind[1]}
        if value.lower() not in canonical:
            raise TradingInputError(f"{name} must be one of: {', '.join(kind[1])}.")
        return canonical[value.lower()]
    if tag == "int":
        if not re.fullmatch(r"-?\d+", value) or not kind[1] <= int(value) <= kind[2]:
            raise TradingInputError(f"{name} must be a whole number from {kind[1]} to {kind[2]}.")
        return value
    if tag == "bool":
        if value.lower() not in ("true", "false"):
            raise TradingInputError(f"{name} must be true or false.")
        return value.lower()
    if tag == "date":
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) or not valid_moment(value):
            raise TradingInputError(f"{name} must be a date in YYYY-MM-DD format.")
        return value
    if tag == "moment":
        if not valid_moment(value):
            raise TradingInputError(f"{name} must be a date (YYYY-MM-DD) or an RFC-3339 timestamp such as 2026-09-29T13:30:00Z.")
        return value
    if tag == "number":
        try:
            number = Decimal(value)
        except InvalidOperation:
            raise TradingInputError(f"{name} must be a number.") from None
        if not number.is_finite():
            raise TradingInputError(f"{name} must be a number.")
        return format(number, "f")
    if tag == "list":
        items = [item.strip() for item in value.split(",") if item.strip()]
        if not items or len(items) > kind[2] or not all(re.fullmatch(kind[1], item) for item in items):
            raise TradingInputError(f"{name} must be a comma-separated list of at most {kind[2]} valid values.")
        return ",".join(items)
    if tag == "regex":
        if not re.fullmatch(kind[1], value):
            raise TradingInputError(f"{name} must be {kind[2]}.")
        return value
    if len(value) > kind[1]:
        raise TradingInputError(f"{name} is too long (limit {kind[1]} characters).")
    return value
