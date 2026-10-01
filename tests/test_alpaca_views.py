"""Alpaca response shapes -> views: every documented family, the single-symbol forms, and the fallback."""

from __future__ import annotations

import json
from typing import Any

import pytest

from tradingview_data.providers import alpaca_views as A
from tradingview_data.providers import views as V
from tradingview_data.providers.alpaca import Alpaca

from alpaca_support import CONTRACT_CALL, CONTRACT_PUT, DAILY, LATER_CALL, PAYLOADS, bar


def build(endpoint_id: str, payload: Any = None) -> tuple[dict[str, dict[str, Any]], list[str]]:
    views, notes = A.build_views(endpoint_id, PAYLOADS[endpoint_id] if payload is None else payload, endpoint_id)
    return {v["id"]: v for v in views}, notes


def facts_of(view: dict[str, Any]) -> dict[str, Any]:
    return {item["key"]: item["value"] for group in view["groups"] for item in group["items"]}


def columns(view: dict[str, Any]) -> list[str]:
    return [c["key"] for c in view["columns"]]


def test_every_endpoint_has_a_sample_payload_and_a_handler():
    ids = {e["id"] for e in Alpaca().catalog()["endpoints"]}
    assert set(PAYLOADS) == ids == set(A._HANDLERS)


@pytest.mark.parametrize("endpoint_id", sorted(PAYLOADS))
def test_each_documented_shape_is_drawn_by_its_own_handler_and_serialises(endpoint_id):
    views, _ = A.build_views(endpoint_id, PAYLOADS[endpoint_id], endpoint_id)
    assert views and {v["kind"] for v in views} <= {"facts", "series", "table", "bars", "feed"}
    assert not any(v["id"].startswith(V.slug(endpoint_id) + "-") for v in views), "fell back to the generic analyzer"
    assert len({v["id"] for v in views}) == len(views)
    json.dumps(views, allow_nan=False)


# --- timestamps and contract symbols ------------------------------------------------------------------------------


def test_timestamps_read_nanoseconds_offsets_and_dates_and_refuse_nonsense():
    assert A.moment("2026-09-29T13:30:00.123456789Z") == A.moment("2026-09-29T13:30:00Z") == 1790688600
    assert A.moment("2026-09-29T09:30:00-04:00") == 1790688600
    assert A.moment("2026-09-29") == 1790640000
    assert A.moment("yesterday") is None and A.moment(None) is None and A.moment("2026-13-40T00:00:00Z") is None
    assert A.stamp("2026-09-29T13:30:00.123456789Z") == "2026-09-29 13:30:00"
    assert A.stamp("2026-09-29T13:30:00.123456789Z", True) == "2026-09-29 13:30:00.123"
    assert A.stamp("2026-09-29T13:30:00Z", True) == "2026-09-29 13:30:00"
    assert A.stamp("2026-09-29") == "2026-09-29" and A.stamp(None) is None and A.stamp("n/a") == "n/a"


def test_option_contract_symbols_are_taken_apart():
    assert A.occ("AAPL240426C00162500") == {"underlying": "AAPL", "expiration": "2024-04-26", "type": "call", "strike": 162.5}
    assert A.occ("AAPL1260116P00240000") == {"underlying": "AAPL1", "expiration": "2026-01-16", "type": "put", "strike": 240.0}
    assert A.occ("AAPL") is None


# --- bars, quotes and trades --------------------------------------------------------------------------------------


def test_bars_for_several_symbols_draw_a_candlestick_chart_each_and_one_table():
    views, notes = build("stock_bars")
    assert list(views) == ["summary", "bar-aapl-chart", "bar-tsla-chart", "bar-table"]
    chart = views["bar-aapl-chart"]
    assert chart["title"] == "AAPL bars" and chart["intraday"] is False and chart["time"] == sorted(chart["time"])
    assert [(s["label"], s["role"]) for s in chart["series"]] == [("Open", "open"), ("High", "high"), ("Low", "low"), ("Close", "close"), ("Volume", "volume"), ("VWAP", "value")]
    assert chart["series"][3]["values"] == [218.0, 220.0, 221.0]
    table = views["bar-table"]
    assert table["total_rows"] == 5 and columns(table) == ["symbol", "time", "open", "high", "low", "close", "volume", "trades", "vwap"]
    assert table["rows"][0][:2] == ["AAPL", "2026-09-25 04:00:00"]
    assert notes == []


def test_the_single_symbol_form_draws_the_same_chart():
    views, _ = build("stock_bars_single")
    assert views["bar-aapl-chart"]["series"][3]["values"] == [218.0, 220.0, 221.0]


def test_minute_bars_are_intraday_and_daily_bars_across_a_weekend_are_not():
    minutes = {"bars": {"AAPL": [bar("2026-09-29T13:30:00Z", 1.0), bar("2026-09-29T13:31:00Z", 2.0), bar("2026-09-29T13:32:00Z", 3.0)]}}
    assert build("stock_bars", minutes)[0]["bar-aapl-chart"]["intraday"] is True
    assert build("stock_bars", {"bars": {"AAPL": DAILY["AAPL"]}})[0]["bar-aapl-chart"]["intraday"] is False


def test_charts_stop_at_six_symbols_and_the_table_keeps_every_row():
    many = {"bars": {f"S{i}": [bar("2026-09-25T04:00:00Z", 1.0), bar("2026-09-28T04:00:00Z", 2.0)] for i in range(8)}}
    views, notes = build("stock_bars", many)
    assert sum(1 for v in views.values() if v["kind"] == "series") == 6 and views["bar-table"]["total_rows"] == 16
    assert any("first 6 of 8 symbols" in n for n in notes)


def test_quotes_chart_bid_and_ask_and_keep_every_tick_in_the_table():
    views, notes = build("stock_quotes")
    chart = views["quote-aapl-chart"]
    assert [s["label"] for s in chart["series"]] == ["Bid price", "Ask price"] and chart["total_points"] == 2
    assert chart["series"][0]["values"] == [221.1, 221.2]  # two ticks share 13:30:00: the last one wins
    assert any("share a second" in n and "all 3" in n for n in notes)
    table = views["quote-table"]
    assert table["total_rows"] == 3 and table["rows"][0][1] == "2026-09-29 13:30:00.123"
    assert {"bid_price", "ask_exchange", "spread", "conditions", "tape"} <= set(columns(table))
    assert table["rows"][0][columns(table).index("spread")] == pytest.approx(0.1)


def test_trades_chart_price_with_size_as_volume():
    views, _ = build("stock_trades")
    chart = views["trade-aapl-chart"]
    assert [(s["label"], s["role"]) for s in chart["series"]] == [("Price", "value"), ("Size", "volume")]
    table = views["trade-table"]
    row = dict(zip(columns(table), table["rows"][0]))
    assert row["conditions"] == "@,T" and row["trade_id"] == "1234" and row["exchange"] == "V"


def test_crypto_trade_ids_stay_text_and_columns_that_are_always_empty_are_dropped():
    table = build("crypto_trades")[0]["trade-table"]
    assert "conditions" not in columns(table) and "tape" not in columns(table)
    assert table["rows"][0][columns(table).index("trade_id")] == "5941898911247126155"
    quotes = build("crypto_quotes")[0]["quote-table"]
    assert "bid_exchange" not in columns(quotes)


# --- the latest endpoints ---------------------------------------------------------------------------------------


def test_latest_records_are_one_row_per_symbol_and_a_single_symbol_also_gets_facts():
    views, _ = build("stock_latest_quotes")
    assert list(views) == ["quote-table"] and views["quote-table"]["total_rows"] == 2
    single, _ = build("stock_latest_quote_single")
    assert list(single) == ["quote-latest", "quote-table"] and single["quote-latest"]["title"] == "AAPL latest quote"
    facts = facts_of(single["quote-latest"])
    assert facts["bid_price"] == 221.0 and facts["time"] == "2026-09-29 13:30:00.123"
    assert list(build("stock_latest_bar_single")[0]) == ["bar-latest", "bar-table"]
    assert list(build("stock_latest_trades")[0]) == ["trade-table"]


def test_snapshots_for_several_symbols_rank_the_day_change_and_give_facts_for_the_first_three():
    views, notes = build("stock_snapshots")
    assert list(views) == ["snapshot-aapl", "snapshot-tsla", "day-change", "snapshots-table"]
    change = views["day-change"]
    assert change["labels"] == ["TSLA", "AAPL"] and change["sign_colors"] and change["format"] == "percent"
    assert change["values"][0] == pytest.approx(-1.0) and change["values"][1] == pytest.approx(221 / 220 * 100 - 100)
    facts = facts_of(views["snapshot-tsla"])
    assert facts["change"] == -4.0 and facts["price"] == 396.0 and facts["prevDailyBar_close"] == 400.0
    tone = views["snapshot-tsla"]["groups"][0]["items"][0]["tone"]
    assert views["snapshot-tsla"]["groups"][0]["title"] == "Change on the day" and tone == "negative"
    assert notes == []


def test_a_single_snapshot_is_facts_only_in_either_documented_form():
    for payload in (PAYLOADS["stock_snapshot_single"], {"AAPL": PAYLOADS["stock_snapshots"]["AAPL"]}, {"snapshots": {"AAPL": PAYLOADS["stock_snapshots"]["AAPL"]}}):
        views, _ = build("stock_snapshots", payload)
        assert list(views) == ["snapshot-aapl"]
    assert [g["title"] for g in views["snapshot-aapl"]["groups"]] == ["Change on the day", "Latest trade", "Latest quote", "Today", "Previous day", "Latest minute"]


def test_many_snapshots_say_that_facts_cover_only_the_first_three():
    snaps = {f"S{i}": PAYLOADS["stock_snapshots"]["AAPL"] for i in range(5)}
    views, notes = build("stock_snapshots", snaps)
    assert sum(1 for v in views.values() if v["kind"] == "facts") == 3 and any("first 3 of 5" in n for n in notes)


# --- options ------------------------------------------------------------------------------------------------------------


def test_the_option_chain_is_sorted_parsed_and_summarised_with_an_iv_smile_for_the_nearest_expiry():
    views, _ = build("option_chain")
    assert list(views) == ["chain-summary", "iv-calls", "iv-puts", "chain-table"]
    summary = facts_of(views["chain-summary"])
    assert (summary["contracts"], summary["calls"], summary["puts"], summary["expirations"]) == (4, 3, 1, 2)
    assert (summary["first"], summary["last"], summary["low"], summary["high"]) == ("2026-01-16", "2026-02-20", 240.0, 260.0)
    table = views["chain-table"]
    cols = columns(table)
    rows = [dict(zip(cols, r)) for r in table["rows"]]
    assert [r["contract"] for r in rows] == [CONTRACT_PUT, CONTRACT_CALL, "AAPL260116C00260000", LATER_CALL]
    assert rows[1]["type"] == "call" and rows[1]["strike"] == 250.0 and rows[1]["underlying"] == "AAPL" and rows[1]["delta"] == 0.5
    calls = views["iv-calls"]
    assert calls["labels"] == ["250", "260"] and calls["values"] == [pytest.approx(33.7), pytest.approx(32.0)]
    assert views["iv-puts"]["labels"] == ["240"] and calls["title"].endswith("expiring 2026-01-16")


def test_a_single_contract_snapshot_is_facts_and_a_symbol_that_is_not_occ_does_not_break_the_chain():
    views, _ = build("option_snapshots")
    facts = facts_of(views["contract"])
    assert facts["strike"] == 250.0 and facts["type"] == "call" and facts["implied_volatility"] == 0.337 and facts["theta"] == -0.28
    odd, _ = build("option_chain", {"snapshots": {"WEIRD": PAYLOADS["option_snapshots"]["snapshots"][CONTRACT_CALL], CONTRACT_PUT: PAYLOADS["option_chain"]["snapshots"][CONTRACT_PUT]}})
    assert odd["chain-table"]["total_rows"] == 2


# --- the order book and one-off responses --------------------------------------------------------------------------


def test_the_order_book_has_best_prices_spread_depth_and_running_totals():
    views, _ = build("crypto_orderbooks")
    assert list(views) == ["book-btc-usd", "depth-bid", "depth-ask", "book-table"]
    facts = facts_of(views["book-btc-usd"])
    assert (facts["best_bid"], facts["best_ask"], facts["spread"]) == (20846, 20902, 56)
    assert facts["spread_percent"] == pytest.approx(56 / 20902 * 100) and facts["levels"] == 6
    assert views["depth-bid"]["labels"][:2] == ["20846", "20840"] and views["depth-ask"]["labels"][0] == "20902"
    table = views["book-table"]
    rows = [dict(zip(columns(table), r)) for r in table["rows"]]
    bids = [r for r in rows if r["side"] == "bid"]
    assert [r["cumulative_size"] for r in bids] == [pytest.approx(0.19), pytest.approx(2.19), pytest.approx(2.19)]


def test_order_books_for_more_than_six_symbols_keep_every_symbol_in_the_table_and_say_so():
    book = PAYLOADS["crypto_orderbooks"]["orderbooks"]["BTC/USD"]
    many = {"orderbooks": {f"S{i}/USD": book for i in range(8)}}
    views, notes = build("crypto_orderbooks", many)
    assert sum(1 for v in views.values() if v["kind"] == "facts") == 6 and "depth-bid" not in views
    table = views["book-table"]
    assert {row[columns(table).index("symbol")] for row in table["rows"]} == {f"S{i}/USD" for i in range(8)} and table["total_rows"] == 48
    assert any("first 6 of 8 symbols" in n and "every price level" in n for n in notes)
    assert build("crypto_orderbooks")[1] == []


def test_rates_for_more_than_six_pairs_keep_every_pair_in_the_table_and_say_so():
    history = PAYLOADS["forex_rates"]["rates"]["USDJPY"]
    views, notes = build("forex_rates", {"rates": {f"P{i}": history for i in range(8)}})
    assert sum(1 for v in views.values() if v["kind"] == "series") == 6 and views["rates-table"]["total_rows"] == 16
    assert any("first 6 of 8 currency pairs" in n for n in notes)
    assert build("forex_rates")[1] == [] and build("forex_latest_rates")[1] == []
    latest, latest_notes = build("forex_latest_rates", {"rates": {f"P{i}": PAYLOADS["forex_latest_rates"]["rates"]["USDJPY"] for i in range(8)}})
    assert latest["rates-table"]["total_rows"] == 8 and latest_notes == []


def test_a_capped_order_book_table_is_not_described_as_holding_every_level():
    book = {"t": "2026-09-29T08:00:14Z", "a": [{"p": 100 + i, "s": 1.0} for i in range(400)], "b": [{"p": 99 - i * 0.01, "s": 1.0} for i in range(400)]}
    views, notes = build("crypto_orderbooks", {"orderbooks": {f"S{i}/USD": book for i in range(8)}})
    table = views["book-table"]
    assert table["truncated"] and table["total_rows"] == 6400 and len(table["rows"]) == 5000
    assert any("first 6 of 8 symbols" in n and "every price level" not in n and "the table has" not in n for n in notes)
    assert any("showing the first 5,000 of 6,400 rows" in n for n in notes)  # finalize reports the cut itself


def test_a_pair_with_no_history_does_not_use_up_a_chart_slot_or_inflate_the_count():
    history = PAYLOADS["forex_rates"]["rates"]["USDJPY"]
    pairs = {"EMPTY": [], "ONE": history[:1], **{f"P{i}": history for i in range(7)}}
    views, notes = build("forex_rates", {"rates": pairs})
    charts = [v for v in views.values() if v["kind"] == "series"]
    assert len(charts) == 6 and [c["title"] for c in charts][0] == "P0 rates"
    assert views["rates-table"]["total_rows"] == 15
    assert notes == ["Charts are drawn for the first 6 of 7 currency pairs that have enough history to chart; the table has every row."]
    fits = {"EMPTY": [], **{f"P{i}": history for i in range(6)}}
    assert build("forex_rates", {"rates": fits})[1] == []  # every chart that could be drawn was drawn


def test_a_symbol_with_too_little_data_to_chart_does_not_use_up_a_chart_slot():
    two = DAILY["AAPL"][:2]
    bars = {"bars": {"LONE": DAILY["AAPL"][:1], **{f"S{i}": two for i in range(7)}}}
    views, notes = build("stock_bars", bars)
    assert sum(1 for v in views.values() if v["kind"] == "series") == 6 and views["bar-table"]["total_rows"] == 15
    assert notes == ["Charts are drawn for the first 6 of 7 symbols that have enough data to chart; the table has every row."]


def test_a_capped_history_table_is_not_described_as_listing_every_tick():
    ticks = [{"t": f"2026-09-29T13:{i // 600:02d}:{(i // 10) % 60:02d}.{(i % 10) * 100:03d}Z", "bp": 1.0 + i / 1e5, "ap": 1.1, "bs": 1, "as": 1} for i in range(6000)]
    views, notes = build("stock_quotes", {"quotes": {"AAPL": ticks}, "next_page_token": None})
    assert views["quote-table"]["truncated"] and views["quote-table"]["total_rows"] == 6000
    assert any("share a second" in n and "table lists all" not in n for n in notes)
    assert any("showing the first 5,000 of 6,000 rows" in n for n in notes)


def test_a_snapshot_with_nothing_to_show_does_not_use_up_a_facts_slot():
    snaps = {"EMPTY": {}, **{f"S{i}": PAYLOADS["stock_snapshots"]["AAPL"] for i in range(4)}}
    views, notes = build("stock_snapshots", snaps)
    assert sum(1 for v in views.values() if v["kind"] == "facts") == 3
    assert notes == ["Facts are shown for the first 3 of 4 symbols; the table has all of them."]


def test_news_becomes_a_feed_with_clean_summaries_safe_links_and_symbol_counts():
    views, _ = build("news")
    assert list(views) == ["summary", "feed", "symbols"]
    first, second = views["feed"]["items"]
    assert first["title"] == "Apple leads phone sales" and first["source"] == "benzinga · Charles Gross" and first["published"] == A.moment("2026-09-29T11:08:42Z")
    assert first["url"] == "https://example.com/a" and first["tickers"][0]["symbol"] == "AAPL" and first["sentiment"] is None
    assert second["url"] is None and second["summary"] == "Chips rallied today." and second["source"] == "benzinga"
    facts = facts_of(views["summary"])
    assert (facts["articles"], facts["symbols"], facts["sources"]) == (2, 2, 1) and facts["newest"] == "2026-09-29 11:08:42"
    assert views["symbols"]["labels"] == ["AAPL", "NVDA"] and views["symbols"]["values"] == [2.0, 1.0]


def test_the_screener_draws_volume_trade_count_and_signed_movers():
    actives, _ = build("most_actives")
    assert list(actives) == ["volume", "trades", "actives-table"] and actives["volume"]["subtitle"] == "Updated 2026-09-29 19:59:30 UTC"
    assert actives["trades"]["values"] == [90_000.0, 120_000.0]
    movers, _ = build("movers")
    assert list(movers) == ["gainers", "losers", "gainers-table", "losers-table"]
    assert movers["losers"]["values"] == [-63.07] and movers["losers"]["sign_colors"] and "Updated 2026-09-29 17:53:30 UTC" in movers["gainers"]["subtitle"]


def test_corporate_actions_get_a_count_summary_and_a_table_per_type_that_has_rows():
    views, _ = build("corporate_actions")
    assert list(views) == ["summary", "actions-cash-dividends", "actions-forward-splits"]
    assert facts_of(views["summary"]) == {"cash_dividends": 1, "forward_splits": 1}
    assert columns(views["actions-cash-dividends"])[:4] == ["symbol", "ex_date", "record_date", "payable_date"]
    assert views["actions-forward-splits"]["rows"][0][:2] == ["NVDA", "2026-06-10"]


def test_forex_rates_chart_bid_mid_and_ask_over_time():
    views, _ = build("forex_rates")
    assert [s["label"] for s in views["rates-usdjpy-chart"]["series"]] == ["Bid", "Mid", "Ask"] and views["rates-usdjpy-chart"]["intraday"]
    assert list(build("forex_latest_rates")[0]) == ["rates-table"]


def test_fixed_income_prices_rank_yields_and_quotes_list_both_sides():
    prices, _ = build("fixed_income_prices")
    assert prices["yields"]["labels"] == ["US912797KJ59", "US912797KS58"] and prices["yields"]["values"] == [4.249, 4.2245]
    one, _ = build("fixed_income_prices", {"prices": {"US912797KJ59": {"p": 99.6, "t": "2026-09-29T20:58:00Z", "ytm": 4.2}}})
    assert "yields" not in one
    quotes, _ = build("fixed_income_quotes")
    assert {"bid_price", "ask_price", "bid_yield_to_maturity", "ask_min_size"} <= set(columns(next(iter(quotes.values()))))


def test_auctions_are_flattened_to_one_row_per_print_in_either_documented_form():
    views, _ = build("stock_auctions")
    table = next(v for v in views.values() if v["kind"] == "table")
    rows = [dict(zip(columns(table), r)) for r in table["rows"]]
    assert [(r["auction"], r["price"]) for r in rows] == [("opening", 218.5), ("closing", 220.0), ("closing", 220.0)]
    assert facts_of(views["summary"]) == {"prints": 3, "symbols": 1, "days": 1}
    single, _ = build("stock_auctions_single")
    assert facts_of(single["summary"])["prints"] == 1


def test_code_tables_are_sorted_by_code():
    table = build("stock_conditions")[0]["codes-table"]
    assert table["rows"] == [["@", "Regular Sale"], ["A", "Acquisition"], ["B", "Bunched Trade"]]


# --- never raising -----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("payload", [{"bars": "oops"}, {"bars": {"AAPL": "oops"}}, [], "text", 7, {"unexpected": {"shape": [1, 2, 3]}}])
def test_a_shape_surprise_falls_back_to_the_generic_analyzer_and_never_raises(payload):
    for endpoint_id in ("stock_bars", "stock_snapshots", "news", "option_chain", "crypto_orderbooks", "movers", "corporate_actions"):
        views, notes = A.build_views(endpoint_id, payload, "Title")
        assert isinstance(views, list) and isinstance(notes, list)
        json.dumps(views, allow_nan=False)


def test_a_handler_that_raises_costs_views_not_the_response(monkeypatch):
    def boom(payload, label):
        raise RuntimeError("bad shape")

    monkeypatch.setitem(A._HANDLERS, "stock_bars", boom)
    views, _ = A.build_views("stock_bars", {"bars": {"AAPL": DAILY["AAPL"]}, "x": {"a": 1}}, "Bars")
    assert views


def test_non_finite_numbers_never_reach_the_views():
    payload = {"bars": {"AAPL": [{**bar("2026-09-25T04:00:00Z", 1.0), "c": float("nan")}, bar("2026-09-28T04:00:00Z", 2.0)]}}
    views, _ = A.build_views("stock_bars", payload, "Bars")
    json.dumps(views, allow_nan=False)
