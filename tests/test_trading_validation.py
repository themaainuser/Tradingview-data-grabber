"""Every trading request is checked before it leaves: the order rules, replace, settings, watchlists and queries."""

from __future__ import annotations

import pytest

from tradingview_data.trading.validation import (
    TradingInputError,
    asset_kind,
    clean_query,
    symbol_text,
    validate_config,
    validate_order,
    validate_replace,
    validate_watchlist,
)

BASE = {"symbol": "AAPL", "side": "buy", "type": "market", "time_in_force": "day", "qty": "10"}
CALL = "AAPL260116C00250000"
PUT = "AAPL260116P00240000"


def order(**changes):
    payload = {**BASE, **changes}
    return {name: value for name, value in payload.items() if value is not None}


def refused(payload, words):
    with pytest.raises(TradingInputError) as raised:
        validate_order(payload)
    assert words.lower() in str(raised.value).lower(), str(raised.value)


# --- orders that are fine --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload, sent",
    [
        (order(), BASE),
        (order(symbol="aapl", side="BUY", type="Market"), BASE),
        (order(qty=10), BASE),
        (order(qty=1.5, type="limit", limit_price=220.5), {**BASE, "qty": "1.5", "type": "limit", "limit_price": "220.5"}),
        (order(qty=None, notional="500.75"), {"symbol": "AAPL", "side": "buy", "type": "market", "time_in_force": "day", "notional": "500.75"}),
        (order(qty="0.000000001"), {**BASE, "qty": "0.000000001"}),
        (order(qty="10.00"), {**BASE, "qty": "10.00"}),
        (order(type="limit", limit_price="1e2"), {**BASE, "type": "limit", "limit_price": "100"}),
        (order(type="stop", stop_price="210"), {**BASE, "type": "stop", "stop_price": "210"}),
        (order(type="stop_limit", stop_price="210", limit_price="209.5", time_in_force="gtc"), {**BASE, "type": "stop_limit", "stop_price": "210", "limit_price": "209.5", "time_in_force": "gtc"}),
        (order(side="sell", type="trailing_stop", trail_percent="2.5"), {**BASE, "side": "sell", "type": "trailing_stop", "trail_percent": "2.5"}),
        (order(side="sell", type="trailing_stop", trail_price="3", time_in_force="gtc"), {**BASE, "side": "sell", "type": "trailing_stop", "trail_price": "3", "time_in_force": "gtc"}),
        (order(type="limit", limit_price="1", time_in_force="opg"), {**BASE, "type": "limit", "limit_price": "1", "time_in_force": "opg"}),
        (order(time_in_force="cls"), {**BASE, "time_in_force": "cls"}),
        (order(time_in_force="ioc"), {**BASE, "time_in_force": "ioc"}),
        (order(time_in_force="fok", type="limit", limit_price="9"), {**BASE, "time_in_force": "fok", "type": "limit", "limit_price": "9"}),
        (order(type="limit", limit_price="9", extended_hours=True), {**BASE, "type": "limit", "limit_price": "9", "extended_hours": True}),
        (order(type="limit", limit_price="9", time_in_force="gtc", extended_hours=True), {**BASE, "type": "limit", "limit_price": "9", "time_in_force": "gtc", "extended_hours": True}),
        (order(extended_hours=False), BASE),
        (order(client_order_id="my-id-1"), {**BASE, "client_order_id": "my-id-1"}),
        (order(order_class="simple"), BASE),
        (order(order_class=""), BASE),
        (order(order_class=None, client_order_id=" "), BASE),
    ],
)
def test_orders_that_follow_the_rules_are_sent_as_strings_and_nothing_is_added(payload, sent):
    assert validate_order(payload) == sent


@pytest.mark.parametrize(
    "payload, sent",
    [
        (order(order_class="bracket", take_profit={"limit_price": "240"}, stop_loss={"stop_price": "200"}), {**BASE, "order_class": "bracket", "take_profit": {"limit_price": "240"}, "stop_loss": {"stop_price": "200"}}),
        (order(order_class="bracket", type="limit", limit_price="220", time_in_force="gtc", take_profit={"limit_price": 240}, stop_loss={"stop_price": 200, "limit_price": 199.5}),
         {**BASE, "type": "limit", "limit_price": "220", "time_in_force": "gtc", "order_class": "bracket", "take_profit": {"limit_price": "240"}, "stop_loss": {"stop_price": "200", "limit_price": "199.5"}}),
        (order(order_class="oto", type="limit", limit_price="220", stop_loss={"stop_price": "200"}), {**BASE, "type": "limit", "limit_price": "220", "order_class": "oto", "stop_loss": {"stop_price": "200"}}),
        (order(order_class="oto", take_profit={"limit_price": "240"}), {**BASE, "order_class": "oto", "take_profit": {"limit_price": "240"}}),
        (order(order_class="oco", side="sell", type="limit", limit_price="240", time_in_force="gtc", take_profit={"limit_price": "240"}, stop_loss={"stop_price": "200"}),
         {**BASE, "side": "sell", "type": "limit", "limit_price": "240", "time_in_force": "gtc", "order_class": "oco", "take_profit": {"limit_price": "240"}, "stop_loss": {"stop_price": "200"}}),
    ],
)
def test_bracket_oto_and_oco_orders_carry_their_exit_legs(payload, sent):
    assert validate_order(payload) == sent


@pytest.mark.parametrize(
    "payload, sent",
    [
        (order(symbol=CALL, qty="2", type="limit", limit_price="4.15"), {"symbol": CALL, "side": "buy", "type": "limit", "time_in_force": "day", "qty": "2", "limit_price": "4.15"}),
        (order(symbol=CALL, qty="1", position_intent="buy_to_open", time_in_force="gtc"), {"symbol": CALL, "side": "buy", "type": "market", "time_in_force": "gtc", "qty": "1", "position_intent": "buy_to_open"}),
        (order(symbol=CALL, side="sell", qty="1", type="stop", stop_price="3", position_intent="sell_to_close"), {"symbol": CALL, "side": "sell", "type": "stop", "time_in_force": "day", "qty": "1", "stop_price": "3", "position_intent": "sell_to_close"}),
        (order(symbol="BTC/USD", qty="0.01", type="limit", limit_price="80000", time_in_force="gtc"), {"symbol": "BTC/USD", "side": "buy", "type": "limit", "time_in_force": "gtc", "qty": "0.01", "limit_price": "80000"}),
        (order(symbol="btc/usd", qty="0.01", time_in_force="ioc"), {"symbol": "BTC/USD", "side": "buy", "type": "market", "time_in_force": "ioc", "qty": "0.01"}),
        (order(symbol="ETH/USD", qty=None, notional="100", time_in_force="gtc"), {"symbol": "ETH/USD", "side": "buy", "type": "market", "time_in_force": "gtc", "notional": "100"}),
        (order(symbol="BTC/USD", qty="0.01", type="stop_limit", stop_price="79000", limit_price="78900", time_in_force="gtc"), {"symbol": "BTC/USD", "side": "buy", "type": "stop_limit", "time_in_force": "gtc", "qty": "0.01", "stop_price": "79000", "limit_price": "78900"}),
    ],
)
def test_option_and_crypto_orders_follow_their_own_rules(payload, sent):
    assert validate_order(payload) == sent


def test_a_multi_leg_order_has_its_legs_a_net_price_and_no_top_level_symbol():
    sent = validate_order(
        {
            "order_class": "mleg", "qty": 1, "type": "limit", "limit_price": "-0.35", "time_in_force": "day",
            "legs": [
                {"symbol": CALL.lower(), "ratio_qty": 1, "side": "buy", "position_intent": "buy_to_open"},
                {"symbol": PUT, "ratio_qty": "2", "position_intent": "sell_to_open"},
            ],
        }
    )
    assert sent == {
        "order_class": "mleg", "type": "limit", "time_in_force": "day", "qty": "1", "limit_price": "-0.35",
        "legs": [
            {"symbol": CALL, "ratio_qty": "1", "side": "buy", "position_intent": "buy_to_open"},
            {"symbol": PUT, "ratio_qty": "2", "side": "sell", "position_intent": "sell_to_open"},  # the side follows the intent
        ],
    }
    assert validate_order({"order_class": "mleg", "qty": "1", "type": "market", "time_in_force": "gtc", "legs": [{"symbol": CALL, "ratio_qty": 1, "side": "buy"}, {"symbol": PUT, "ratio_qty": 1, "side": "buy"}]})["type"] == "market"
    assert validate_order({"order_class": "mleg", "qty": "1", "type": "limit", "limit_price": "0", "time_in_force": "day", "legs": [{"symbol": CALL, "ratio_qty": 1, "side": "buy"}, {"symbol": PUT, "ratio_qty": 1, "side": "sell"}]})["limit_price"] == "0"


# --- orders that are not ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload, words",
    [
        ([], "must be an object"),
        ("AAPL", "must be an object"),
        (order(quantity="10"), "Unknown order field 'quantity'"),
        (order(symbol=None), "symbol must be a symbol"),
        (order(symbol="AAPL?x=1"), "symbol must be a symbol"),
        (order(symbol="../account"), "symbol must be a symbol"),
        (order(symbol=7), "symbol must be a symbol"),
        (order(side=None), "side is required"),
        (order(side="hold"), "side must be one of"),
        (order(type=None), "type is required"),
        (order(type="iceberg"), "type must be one of"),
        (order(time_in_force=None), "time_in_force is required"),
        (order(time_in_force="forever"), "time_in_force must be one of"),
        (order(order_class="chain"), "order_class must be one of"),
        (order(qty=None), "Give a qty"),
        (order(qty="10", notional="500"), "either qty or notional"),
        (order(qty="0"), "greater than zero"),
        (order(qty="-5"), "greater than zero"),
        (order(qty="abc"), "must be a number"),
        (order(qty="NaN"), "must be a number"),
        (order(qty="Infinity"), "must be a number"),
        (order(qty="0.0000000001"), "at most 9 decimal places"),
        (order(qty=True), "must be a number"),
        (order(qty=["1"]), "must be a number"),
        (order(qty=None, notional="500", type="limit", limit_price="1"), "notional orders must be market"),
        (order(qty=None, notional="500", time_in_force="gtc"), "notional orders must use time_in_force day"),
        (order(qty=None, notional="0"), "greater than zero"),
        (order(qty="1.5", time_in_force="gtc"), "Fractional quantities need time_in_force day"),
        (order(qty="1.5", side="sell", type="trailing_stop", trail_percent="1"), "Fractional quantities are not available for trailing stops"),
        (order(type="limit"), "limit_price is required"),
        (order(type="limit", limit_price="0"), "greater than zero"),
        (order(type="limit", limit_price="-1"), "greater than zero"),
        (order(limit_price="220"), "limit_price does not apply to a market order"),
        (order(type="stop"), "stop_price is required"),
        (order(type="stop_limit", stop_price="1"), "limit_price is required"),
        (order(type="limit", limit_price="9", stop_price="8"), "stop_price does not apply to a limit order"),
        (order(type="trailing_stop"), "exactly one of trail_price or trail_percent"),
        (order(type="trailing_stop", trail_price="1", trail_percent="1"), "exactly one of trail_price or trail_percent"),
        (order(trail_percent="1"), "only for trailing_stop"),
        (order(type="stop", stop_price="1", time_in_force="opg"), "only for market and limit orders"),
        (order(type="stop_limit", stop_price="1", limit_price="1", time_in_force="ioc"), "only for market and limit orders"),
        (order(extended_hours=True), "extended_hours works only with limit"),
        (order(type="limit", limit_price="9", time_in_force="ioc", extended_hours=True), "extended_hours works only with limit"),
        (order(extended_hours="yes"), "must be true or false"),
        (order(client_order_id="x" * 129), "too long"),
        (order(client_order_id=7), "must be text"),
        (order(position_intent="buy_to_open"), "only for options"),
        (order(symbol=CALL, position_intent="sell_to_open"), "does not match side buy"),
        (order(symbol=CALL, position_intent="open"), "position_intent must be one of"),
        (order(legs=[{"symbol": CALL}]), "legs are only for order_class mleg"),
        (order(take_profit={"limit_price": "9"}), "need order_class bracket"),
        (order(stop_loss={"stop_price": "9"}), "need order_class bracket"),
    ],
)
def test_a_mistake_that_is_certain_is_refused_in_plain_words(payload, words):
    refused(payload, words)


@pytest.mark.parametrize(
    "payload, words",
    [
        (order(symbol=CALL, qty="1.5"), "whole contracts"),
        (order(symbol=CALL, qty=None, notional="100"), "notional is not available for options"),
        (order(symbol=CALL, type="trailing_stop", trail_percent="1"), "trailing_stop orders are not available for options"),
        (order(symbol=CALL, time_in_force="ioc"), "time_in_force ioc is not available for options"),
        (order(symbol=CALL, time_in_force="opg", type="limit", limit_price="1"), "time_in_force opg is not available for options"),
        (order(symbol=CALL, order_class="bracket", take_profit={"limit_price": "9"}, stop_loss={"stop_price": "1"}), "order_class bracket is not available for options"),
        (order(symbol="BTC/USD", time_in_force="day"), "time_in_force day is not available for crypto"),
        (order(symbol="BTC/USD", time_in_force="gtc", type="stop", stop_price="1"), "stop orders are not available for crypto"),
        (order(symbol="BTC/USD", time_in_force="gtc", type="trailing_stop", trail_percent="1"), "trailing_stop orders are not available for crypto"),
        (order(symbol="BTC/USD", time_in_force="fok"), "time_in_force fok is not available for crypto"),
        (order(symbol="BTC/USD", time_in_force="gtc", order_class="oto", stop_loss={"stop_price": "1"}), "order_class oto is not available for crypto"),
    ],
)
def test_option_and_crypto_orders_are_refused_what_alpaca_does_not_offer_them(payload, words):
    refused(payload, words)


@pytest.mark.parametrize(
    "changes, words",
    [
        ({"order_class": "bracket", "take_profit": {"limit_price": "9"}}, "needs both take_profit and stop_loss"),
        ({"order_class": "bracket", "stop_loss": {"stop_price": "9"}}, "needs both take_profit and stop_loss"),
        ({"order_class": "bracket"}, "needs both take_profit and stop_loss"),
        ({"order_class": "oto"}, "exactly one of take_profit or stop_loss"),
        ({"order_class": "oto", "take_profit": {"limit_price": "9"}, "stop_loss": {"stop_price": "1"}}, "exactly one of take_profit or stop_loss"),
        ({"order_class": "oco", "take_profit": {"limit_price": "9"}, "stop_loss": {"stop_price": "1"}}, "use type limit"),
        ({"order_class": "bracket", "type": "stop", "stop_price": "5", "take_profit": {"limit_price": "9"}, "stop_loss": {"stop_price": "1"}}, "must be a market or limit order"),
        ({"order_class": "bracket", "take_profit": {}, "stop_loss": {"stop_price": "1"}}, "take_profit.limit_price is required"),
        ({"order_class": "bracket", "take_profit": {"limit_price": "9", "stop_price": "1"}, "stop_loss": {"stop_price": "1"}}, "Unknown take_profit field 'stop_price'"),
        ({"order_class": "bracket", "take_profit": {"limit_price": "0"}, "stop_loss": {"stop_price": "1"}}, "greater than zero"),
        ({"order_class": "bracket", "take_profit": {"limit_price": "9"}, "stop_loss": {"limit_price": "1"}}, "stop_loss.stop_price is required"),
        ({"order_class": "bracket", "take_profit": "9", "stop_loss": {"stop_price": "1"}}, "take_profit must be an object"),
    ],
)
def test_exit_legs_must_be_complete_and_only_where_they_belong(changes, words):
    refused(order(**changes), words)


def multileg(**changes):
    payload = {
        "order_class": "mleg", "qty": "1", "type": "limit", "limit_price": "1.00", "time_in_force": "day",
        "legs": [{"symbol": CALL, "ratio_qty": "1", "side": "buy"}, {"symbol": PUT, "ratio_qty": "1", "side": "sell"}],
    }
    return {name: value for name, value in {**payload, **changes}.items() if value is not None}


@pytest.mark.parametrize(
    "payload, words",
    [
        (multileg(symbol="AAPL"), "symbol does not apply to a multi-leg order"),
        (multileg(side="buy"), "side does not apply to a multi-leg order"),
        (multileg(notional="5"), "notional does not apply"),
        (multileg(stop_price="5"), "stop_price does not apply"),
        (multileg(take_profit={"limit_price": "1"}), "take_profit does not apply"),
        (multileg(extended_hours=True), "extended_hours does not apply"),
        (multileg(type="stop"), "type must be one of: market, limit"),
        (multileg(time_in_force="ioc"), "time_in_force must be one of: day, gtc"),
        (multileg(qty=None), "qty is required"),
        (multileg(qty="1.5"), "qty must be a whole number"),
        (multileg(qty="0"), "greater than zero"),
        (multileg(limit_price=None), "limit_price is required for a limit order"),
        (multileg(type="market"), "limit_price does not apply to a market order"),
        (multileg(limit_price="free"), "must be a number"),
        (multileg(legs=None), "two to four legs"),
        (multileg(legs=[{"symbol": CALL, "ratio_qty": "1", "side": "buy"}]), "two to four legs"),
        (multileg(legs=[{"symbol": CALL, "ratio_qty": "1", "side": "buy"}] * 5), "two to four legs"),
        (multileg(legs="x"), "two to four legs"),
        (multileg(legs=[{"symbol": "AAPL", "ratio_qty": "1", "side": "buy"}, {"symbol": PUT, "ratio_qty": "1", "side": "buy"}]), "Leg 1: symbol must be an option contract"),
        (multileg(legs=[{"symbol": CALL, "side": "buy"}, {"symbol": PUT, "ratio_qty": "1", "side": "buy"}]), "Leg 1: ratio_qty is required"),
        (multileg(legs=[{"symbol": CALL, "ratio_qty": "0", "side": "buy"}, {"symbol": PUT, "ratio_qty": "1", "side": "buy"}]), "Leg 1: ratio_qty must be greater than zero"),
        (multileg(legs=[{"symbol": CALL, "ratio_qty": "1.5", "side": "buy"}, {"symbol": PUT, "ratio_qty": "1", "side": "buy"}]), "Leg 1: ratio_qty must be a whole number"),
        (multileg(legs=[{"symbol": CALL, "ratio_qty": "1", "side": "buy"}, {"symbol": PUT, "ratio_qty": "1"}]), "Leg 2: side or position_intent is required"),
        (multileg(legs=[{"symbol": CALL, "ratio_qty": "1", "side": "buy"}, {"symbol": PUT, "ratio_qty": "1", "side": "buy", "position_intent": "sell_to_open"}]), "Leg 2: position_intent sell_to_open does not match side buy"),
        (multileg(legs=[{"symbol": CALL, "ratio_qty": "1", "side": "buy"}, {"symbol": CALL, "ratio_qty": "1", "side": "sell"}]), "Leg 2: " + CALL + " appears twice"),
        (multileg(legs=[{"symbol": CALL, "ratio_qty": "1", "side": "buy", "price": "1"}, {"symbol": PUT, "ratio_qty": "1", "side": "buy"}]), "Unknown leg 1 field 'price'"),
        (multileg(legs=["x", {"symbol": PUT, "ratio_qty": "1", "side": "buy"}]), "leg 1 must be an object"),
    ],
)
def test_multi_leg_orders_need_two_to_four_option_legs_and_one_net_price(payload, words):
    refused(payload, words)


def test_kinds_of_asset_are_told_apart_by_their_symbol():
    assert [asset_kind(s) for s in ("AAPL", "BRK.B", "BTC/USD", "AAPL260116C00250000", "SPXW250117P05000000", "AAPL1260116C00250000", "BTCUSD")] == [
        "us_equity", "us_equity", "crypto", "us_option", "us_option", "us_option", "us_equity",
    ]
    assert symbol_text(" brk.b ") == "BRK.B" and symbol_text("btc/usd") == "BTC/USD"
    for bad in ("", " ", "A B", "AAPL;", "../x", "A" * 40, None, 5, "-AAPL"):
        with pytest.raises(TradingInputError):
            symbol_text(bad)


# --- changing an order, settings, watchlists ---------------------------------------------------------


def test_a_replacement_carries_only_what_changes():
    assert validate_replace({"qty": 5, "limit_price": "205.5", "stop_price": 200, "trail": "1.5", "time_in_force": "GTC", "client_order_id": "new-1"}) == {
        "qty": "5", "limit_price": "205.5", "stop_price": "200", "trail": "1.5", "time_in_force": "gtc", "client_order_id": "new-1",
    }
    assert validate_replace({"limit_price": "9", "qty": ""}) == {"limit_price": "9"}


@pytest.mark.parametrize(
    "payload, words",
    [
        ([], "must be an object"),
        ({}, "Nothing to change"),
        ({"qty": ""}, "Nothing to change"),
        ({"symbol": "TSLA"}, "Unknown order field 'symbol'"),
        ({"notional": "5"}, "Unknown order field 'notional'"),
        ({"qty": "1.5"}, "does not let the quantity of a fractional order change"),
        ({"qty": "0"}, "greater than zero"),
        ({"limit_price": "-1"}, "greater than zero"),
        ({"time_in_force": "later"}, "time_in_force must be one of"),
        ({"client_order_id": "x" * 129}, "too long"),
    ],
)
def test_a_bad_replacement_is_refused(payload, words):
    with pytest.raises(TradingInputError) as raised:
        validate_replace(payload)
    assert words.lower() in str(raised.value).lower()


def test_settings_are_checked_one_by_one():
    assert validate_config({"suspend_trade": True, "no_shorting": False, "trade_confirm_email": "NONE", "max_margin_multiplier": 4, "max_options_trading_level": 3, "fractional_trading": True, "disable_overnight_trading": False, "ptp_no_exception_entry": False}) == {
        "suspend_trade": True, "no_shorting": False, "fractional_trading": True, "disable_overnight_trading": False, "ptp_no_exception_entry": False,
        "trade_confirm_email": "none", "max_margin_multiplier": "4", "max_options_trading_level": 3,
    }
    assert validate_config({"max_margin_multiplier": "2"}) == {"max_margin_multiplier": "2"}
    assert validate_config({"max_options_trading_level": 0}) == {"max_options_trading_level": 0}
    for payload, words in (
        ([], "must be an object"), ({}, "Nothing to change"), ({"suspend_trade": "yes"}, "must be true or false"), ({"suspend_trade": 1}, "must be true or false"),
        ({"trade_confirm_email": "some"}, "must be one of: all, none"), ({"max_margin_multiplier": "3"}, "must be 1, 2 or 4"), ({"max_margin_multiplier": True}, "must be 1, 2 or 4"),
        ({"max_options_trading_level": 4}, "must be 0, 1, 2 or 3"), ({"max_options_trading_level": "2"}, "must be 0, 1, 2 or 3"), ({"max_options_trading_level": True}, "must be 0, 1, 2 or 3"),
        ({"account_blocked": False}, "Unknown setting field 'account_blocked'"),
    ):
        with pytest.raises(TradingInputError, match=words):
            validate_config(payload)


def test_watchlists_need_a_name_to_be_created_and_something_to_change_to_be_updated():
    assert validate_watchlist({"name": " Tech ", "symbols": ["aapl", "AAPL", "tsla"]}, creating=True) == {"name": "Tech", "symbols": ["AAPL", "TSLA"]}
    assert validate_watchlist({"name": "Tech"}, creating=True) == {"name": "Tech"}
    assert validate_watchlist({"symbols": []}, creating=False) == {"symbols": []}
    assert validate_watchlist({"name": "New"}, creating=False) == {"name": "New"}
    for payload, creating, words in (
        ([], True, "must be an object"), ({}, True, "needs a name"), ({"symbols": ["AAPL"]}, True, "needs a name"), ({}, False, "Nothing to change"),
        ({"name": "x" * 65}, True, "too long"), ({"name": "a", "symbols": "AAPL"}, True, "list of at most 200"), ({"name": "a", "symbols": ["A"] * 201}, True, "list of at most 200"),
        ({"name": "a", "symbols": ["../x"]}, True, "symbols must be a symbol"), ({"name": "a", "extra": 1}, True, "Unknown watchlist field 'extra'"),
    ):
        with pytest.raises(TradingInputError, match=words):
            validate_watchlist(payload, creating=creating)


def test_queries_pass_only_known_parameters_each_checked_by_its_kind():
    spec = {
        "status": ("enum", ("open", "closed")), "kind": ("enum", ("TRADING", "SETTLEMENT")), "limit": ("int", 1, 500), "nested": ("bool",), "day": ("date",),
        "after": ("moment",), "price": ("number",), "symbols": ("list", r"[A-Z]{1,5}", 3), "period": ("regex", r"\d[DW]", "like 1D"), "token": ("text", 5),
    }
    assert clean_query({"status": "OPEN", "kind": "settlement", "limit": "50", "nested": "TRUE", "day": "2026-09-30", "after": "2026-09-30T13:30:00Z", "price": "1e1", "symbols": "AAPL, TSLA", "period": "1D", "token": "abc"}, spec) == [
        ("status", "open"), ("kind", "SETTLEMENT"), ("limit", "50"), ("nested", "true"), ("day", "2026-09-30"), ("after", "2026-09-30T13:30:00Z"), ("price", "10"), ("symbols", "AAPL,TSLA"), ("period", "1D"), ("token", "abc"),
    ]
    assert clean_query({"status": " ", "limit": ""}, spec) == []
    for params, words in (
        ({"bogus": "1"}, "Unknown parameter 'bogus'"), ({"status": "all"}, "must be one of: open, closed"), ({"limit": "0"}, "from 1 to 500"), ({"limit": "501"}, "from 1 to 500"), ({"limit": "5.5"}, "from 1 to 500"),
        ({"nested": "maybe"}, "true or false"), ({"day": "2026-13-01"}, "YYYY-MM-DD"), ({"day": "2026-9-1"}, "YYYY-MM-DD"), ({"after": "yesterday"}, "RFC-3339"), ({"price": "abc"}, "must be a number"), ({"price": "NaN"}, "must be a number"),
        ({"symbols": "AAPL,tsla"}, "at most 3 valid"), ({"symbols": "A,B,C,D"}, "at most 3 valid"), ({"period": "10D"}, "must be like 1D"), ({"token": "abcdefg"}, "too long"),
    ):
        with pytest.raises(TradingInputError, match=words):
            clean_query(params, spec)
