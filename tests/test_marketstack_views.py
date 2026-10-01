"""Marketstack view builders: one fixture per response family, valid output for every endpoint, garbage never raising."""

from __future__ import annotations

import copy
import json
from datetime import datetime, timezone

import pytest

from tradingview_data.providers.marketstack import Marketstack
from tradingview_data.providers.marketstack_views import build_views, moment, num, stamp

from marketstack_support import EOD_ROWS, SAMPLES, TICK_ROWS, bar
from providers_support import FakeHttp

IDS = [e["id"] for e in Marketstack(http_get=FakeHttp()).catalog()["endpoints"]]


def build(endpoint_id, payload=None):
    return build_views(endpoint_id, SAMPLES[endpoint_id] if payload is None else payload, endpoint_id)


def kinds(views):
    return [v["kind"] for v in views]


def one(views, kind, index=0):
    return [v for v in views if v["kind"] == kind][index]


def facts(view):
    return {i["key"]: i for g in view["groups"] for i in g["items"]}


def utc(seconds):
    return datetime.fromtimestamp(seconds, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def check_valid(views):
    ids = [v["id"] for v in views]
    assert len(ids) == len(set(ids))
    for v in views:
        if v["kind"] == "series":
            assert all(len(s["values"]) == len(v["time"]) for s in v["series"]) and v["time"] == sorted(v["time"]) and len(v["time"]) >= 2
        if v["kind"] == "table":
            assert all(len(r) == len(v["columns"]) for r in v["rows"])
            assert all(not isinstance(c, (bool, dict, list)) for r in v["rows"] for c in r)
        if v["kind"] == "bars":
            assert len(v["labels"]) == len(v["values"])
        if v["kind"] == "facts":
            assert v["groups"] and all(g["items"] for g in v["groups"])
    json.dumps(views, allow_nan=False)


# --- time and numbers --------------------------------------------------------------------------------


def test_timestamps_become_utc_and_say_whether_they_carry_a_time_of_day():
    assert moment("2026-09-29T00:00:00+0000") == (1790640000, False)
    assert moment("2026-09-29") == (1790640000, False)
    assert moment("2026-09-29T09:30:00-0400") == (1790640000 + 13 * 3600 + 30 * 60, True)
    assert moment("2026-09-29T15:30:00+05:30")[0] == moment("2026-09-29T10:00:00Z")[0]
    assert moment("2026-09-29 10:00:00.123456")[1] is True
    assert [moment(x) for x in ("nope", "", None, "2026-13-40")] == [None, None, None, None]
    assert stamp("2026-09-29T15:30:00+0000", True) == "2026-09-29 15:30:00" and stamp("2026-09-29T00:00:00+0000", False) == "2026-09-29"
    assert stamp(None, False) is None and stamp("n/a", False) == "n/a"


@pytest.mark.parametrize(("raw", "expected"), [("1,234.5", 1234.5), ("-0.52%", -0.52), (" 4.2% ", 4.2), (7, 7.0), ("", None), ("x", None), (None, None), (True, None)])
def test_numbers_accept_thousands_separators_and_percent_signs(raw, expected):
    assert num(raw) == expected


# --- prices -------------------------------------------------------------------------------------------


def test_end_of_day_bars_are_a_candle_series_in_ascending_utc_with_a_checkable_summary_and_a_full_table():
    views, notes = build("ticker_eod")
    chart = one(views, "series")
    assert [s["role"] for s in chart["series"]] == ["open", "high", "low", "close", "volume", "value"]
    assert [s["key"] for s in chart["series"]][-1] == "adj_close" and chart["intraday"] is False
    assert [utc(t) for t in chart["time"]] == ["2026-09-25T00:00:00", "2026-09-28T00:00:00", "2026-09-29T00:00:00"]
    assert chart["series"][3]["values"] == [218.0, 220.0, 221.0] and chart["title"] == "AAPL end of day" and chart["subtitle"] == "Apple Inc · XNAS · usd"
    table = one(views, "table")
    assert table["rows"][0][0] == "2026-09-29" and table["total_rows"] == 3
    assert [c["key"] for c in table["columns"]][:4] == ["date", "symbol", "exchange", "open"]
    summary = facts(next(v for v in views if v["kind"] == "facts" and v["id"] == "summary"))
    assert summary["latest"]["value"] == 221.0 and summary["change"]["value"] == 1.0
    assert next(v for v in views if v["id"] == "eod-ticker")["title"] == "Apple Inc" and views[0]["id"] == "summary" and notes == []
    check_valid(views)


def test_several_symbols_get_one_chart_each_and_one_table():
    views, _ = build("eod")
    charts = [v for v in views if v["kind"] == "series"]
    assert [c["title"] for c in charts] == ["AAPL end of day", "MSFT end of day"] and one(views, "table")["total_rows"] == 5
    check_valid(views)


def test_a_single_latest_bar_is_a_set_of_facts_and_a_table_with_no_chart():
    views, _ = build("ticker_eod_latest")
    assert "series" not in kinds(views)
    latest = facts(next(v for v in views if v["id"].endswith("latest")))
    assert latest["close"]["value"] == 221.0 and latest["symbol"]["value"] == "AAPL" and latest["date"]["value"] == "2026-09-29"
    check_valid(views)


def test_a_flat_ticker_bar_and_a_wrapped_one_both_work():
    assert kinds(build("ticker_eod_latest")[0]) == kinds(build("ticker_eod_latest", {"data": EOD_ROWS[0]})[0])


def test_the_exchange_around_exchange_prices_is_described_first():
    views, _ = build("exchange_eod")
    head = next(v for v in views if v["id"] == "eod-exchange")
    assert head["kind"] == "facts" and head["title"] == "NASDAQ Stock Market" and head["subtitle"] == "XNAS"
    assert [g["title"] for g in head["groups"]] == ["Exchange", "Location", "Legal", "Dates"]


def test_intraday_bars_keep_their_clock_in_utc_and_say_why_bid_and_ask_are_empty():
    views, notes = build("ticker_intraday")
    chart = one(views, "series")
    assert chart["intraday"] is True and [utc(t) for t in chart["time"]] == ["2026-09-29T13:30:00", "2026-09-29T14:30:00", "2026-09-29T15:30:00"]
    assert [s["key"] for s in chart["series"]] == ["open", "high", "low", "close", "volume"]
    assert all(s["key"] not in ("bid_price", "ask_price", "last", "mid") for s in chart["series"])
    table = one(views, "table")
    assert table["rows"][0][0] == "2026-09-29 15:30:00"
    assert any("IEX" in n for n in notes)
    check_valid(views)


def test_filled_bid_and_ask_remove_the_note_and_chart_the_mid_price():
    rows = [{**t, "bid_price": t["close"] - 0.1, "ask_price": t["close"] + 0.1, "last": t["close"], "mid": t["close"]} for t in TICK_ROWS]
    views, notes = build("intraday", {"pagination": {}, "data": rows})
    assert notes == [] and {"mid", "last"} <= {s["key"] for s in one(views, "series")["series"]}


def test_a_bar_with_a_missing_price_stays_a_gap_not_a_zero():
    rows = [bar("AAPL", "2026-09-25", 218.0), {**bar("AAPL", "2026-09-26", 219.0), "close": None}, bar("AAPL", "2026-09-29", 221.0)]
    chart = one(build("ticker_eod", {"data": {"symbol": "AAPL", "eod": rows}})[0], "series")
    assert chart["series"][3]["values"] == [218.0, None, 221.0]


def test_charts_are_capped_per_symbol_and_the_table_keeps_everything():
    rows = [bar(f"S{i}", day, 10.0 + i) for i in range(9) for day in ("2026-09-28", "2026-09-29")]
    views, notes = build("eod", {"pagination": {}, "data": rows})
    assert len([v for v in views if v["kind"] == "series"]) == 6 and one(views, "table")["total_rows"] == 18
    assert any("first 6 of 9 symbols" in n for n in notes)


# --- reference data ------------------------------------------------------------------------------------


def test_booleans_are_yes_no_and_nested_dates_are_flattened_in_tickers():
    views, _ = build("exchange_tickers")
    table = one(views, "table")
    assert [r[2:] for r in table["rows"]] == [["Yes", "Yes"], ["Yes", "No"]]
    ticker = build("ticker")[0]
    exchange = facts(ticker[1])
    assert exchange["date_creation"]["value"] == "2005-01-01 00:00:00.000000" and "date_expiry" not in exchange
    assert facts(ticker[0])["isin"]["value"] == "US0378331005"
    listing = one(build("tickerslist")[0], "table")
    assert [c["key"] for c in listing["columns"]] == ["name", "ticker", "has_eod", "has_intraday", "exchange", "mic", "country", "city"]
    check_valid(ticker)


def test_one_exchange_is_facts_and_several_are_a_table_whether_a_list_or_an_object_comes_back():
    assert kinds(build("exchange")[0]) == ["facts"] == kinds(build("exchange", {"data": [SAMPLES["exchange"]["data"]]})[0])
    assert kinds(build("exchanges")[0]) == ["table"]


def test_actions_chart_the_amounts_and_keep_the_table():
    views, _ = build("ticker_dividends")
    chart = one(views, "series")
    assert chart["series"][0]["values"] == [0.24, 0.25] and chart["title"] == "AAPL dividends"
    assert one(views, "table")["rows"][0][:3] == ["2026-08-11", "AAPL", 0.25]
    assert "series" not in kinds(build("splits")[0]) and one(build("splits")[0], "table")["total_rows"] == 2


def test_a_dividend_without_dates_is_still_listed():
    table = one(build("dividends")[0], "table")
    assert table["total_rows"] == 2 and table["rows"][1][3:] == ["quarterly", None, None, None]


@pytest.mark.parametrize("endpoint", ["timezones", "currencies", "indexlist", "bondlist", "etflist", "cik_code"])
def test_plain_lists_are_one_table(endpoint):
    views, _ = build(endpoint)
    assert kinds(views) == ["table"] and views[0]["total_rows"] >= 1


def test_company_details_have_facts_addresses_executives_and_listings():
    views, _ = build("tickerinfo")
    assert {v["id"] for v in views} == {"company", "company-address", "company-post_address", "executives", "listings", "previous-names"}
    assert facts(views[0])["full_time_employees"]["value"] == 164000


# --- indices, bonds, ETFs, prices, commodities ----------------------------------------------------------------


def test_index_and_bond_changes_are_signed_percent_bars():
    bars = one(build("indexinfo")[0], "bars")
    assert bars["labels"] == ["Day", "Week", "Month", "Year"] and bars["values"] == [0.2, -0.5, 2.1, 18.4] and bars["sign_colors"] is True and bars["format"] == "percent"
    assert one(build("bond")[0], "bars")["values"] == [1.0, -2.0, 5.0]
    assert facts(build("indexinfo")[0][0])["price"]["value"] == 5123.45


def test_etf_holdings_rank_the_largest_positions_and_flatten_the_securities():
    views, _ = build("etfholdings")
    assert facts(views[0])["fund_name"]["value"] == "Example ETF" and facts(views[0])["final_filing"]["value"] == "No"
    bars = one(views, "bars")
    assert bars["labels"] == ["Apple Inc", "Microsoft"] and bars["values"] == [7.5, 6.8]
    table = one(views, "table")
    assert table["total_rows"] == 2 and [c["key"] for c in table["columns"]][:2] == ["name", "title"]
    check_valid(views)


def test_a_real_time_price_is_facts_and_a_table():
    views, _ = build("stockprice")
    assert kinds(views) == ["facts", "table"] and facts(views[0])["price"]["value"] == 221.5


def test_commodities_have_facts_signed_change_bars_and_a_table():
    views, _ = build("commodities")
    assert kinds(views) == ["facts", "bars", "table"]
    assert one(views, "bars")["values"] == [0.47, -1.2, 3.4, 8.1]
    price = facts(views[0])
    assert price["commodity_price"]["value"] == 2650.5
    assert [g["title"] for g in views[0]["groups"]] == ["Price", "Change", "Quarterly"]


def test_commodity_history_is_a_priced_line_with_its_unit_and_frequency():
    views, _ = build("commoditieshistory")
    chart = one(views, "series")
    assert chart["series"][0]["values"] == [2600.0, 2620.5, 2650.0] and chart["series"][0]["unit"] == "usd/t" and chart["subtitle"] == "usd/t · day"
    assert one(views, "table")["total_rows"] == 3


# --- company data and EDGAR -------------------------------------------------------------------------------


def test_analyst_ratings_show_the_consensus_the_split_and_each_analyst():
    views, _ = build("companyratings")
    assert one(views, "bars")["labels"] == ["Buy", "Hold", "Sell"] and one(views, "bars")["values"] == [20.0, 8.0, 2.0]
    consensus = facts(views[0])
    assert consensus["consensus_conclusion"]["value"] == "Buy" and consensus["analyst_average"]["value"] == 250.0 and views[0]["title"] == "Apple Inc consensus"
    analyst = one(views, "table")
    assert analyst["total_rows"] == 1 and "price_target" in [c["key"] for c in analyst["columns"]]


def test_a_company_by_cik_has_facts_and_both_addresses():
    views, _ = build("company_name")
    assert [v["id"] for v in views] == ["company", "address-mailing", "address-business"]
    assert facts(views[1])["zip_code"]["value"] == "95051"


def test_company_facts_list_every_concept_and_unit_with_its_latest_value():
    views, _ = build("company_facts")
    summary = facts(views[0])
    assert summary["concepts"]["value"] == 2 and summary["taxonomies"]["value"] == "dei, us-gaap"
    table = one(views, "table")
    row = dict(zip([c["key"] for c in table["columns"]], next(r for r in table["rows"] if "AccountsPayableCurrent" in r)))
    assert row["latest_end"] == "2021-12-31" and row["latest_value"] == 120 and row["observations"] == 2 and row["unit"] == "USD"


def test_a_concept_is_charted_by_period_end_with_the_unit():
    views, _ = build("concept_accounts_payable")
    chart = one(views, "series")
    assert chart["series"][0]["values"] == [100.0, 120.0] and chart["series"][0]["unit"] == "USD" and chart["title"] == "AccountsPayableCurrent (USD)"
    assert one(views, "table")["total_rows"] == 2


def test_submissions_zip_the_column_arrays_into_filing_rows():
    views, _ = build("submissions")
    filings = next(v for v in views if v["id"] == "filings")
    keys = [c["key"] for c in filings["columns"]]
    assert filings["total_rows"] == 2 and filings["rows"][0][keys.index("form")] == "10-Q" and filings["rows"][1][keys.index("filing_date")] == "2026-05-02"
    assert facts(views[0])["tickers"]["value"] == "NVDA" and {"filing-files", "former-names"} <= {v["id"] for v in views}


def test_frames_rank_the_largest_entities():
    views, _ = build("frames_accounts_payable")
    bars = one(views, "bars")
    assert bars["labels"] == ["Beta", "Alpha"] and bars["values"] == [900.0, 500.0] and bars["value_label"] == "USD"
    assert facts(views[0])["entries"]["value"] == 2


# --- every endpoint, and bad input ------------------------------------------------------------------------


@pytest.mark.parametrize("endpoint", IDS)
def test_every_endpoint_builds_valid_json_safe_views(endpoint):
    views, notes = build(endpoint)
    assert views, endpoint
    check_valid(views)
    assert all(isinstance(n, str) for n in notes)


def test_the_samples_cover_exactly_the_catalog():
    assert sorted(IDS) == sorted(SAMPLES)


GARBAGE = [None, 0, "x" * 50_000, [], {}, [1, "a", None, {"a": 1}, [2]], {"data": 5}, {"data": {"eod": "oops"}}, {"data": [None, 3]}, {"result": {"data": [None]}}, {"a": {"b": {"c": {"d": {"e": {"f": 1}}}}}},
           {"data": [{"date": "bad", "symbol": None, "close": "x"}]}, {"data": [{"date": "2026-01-01"}, {"date": "2026-01-02"}]}, {"data": {"facts": 5}}, {"data": {"filings": {"recent": {"form": "x"}}}},
           [{"a": float("nan")}], {"a": float("inf")}, {"output": {"holdings": [{"investment_security": None}]}}, {"result": {"output": {"analysts": [{"rating": 5}]}}}]


@pytest.mark.parametrize("endpoint", IDS)
def test_an_unfamiliar_shape_never_raises_and_stays_valid_json(endpoint):
    for payload in GARBAGE:
        views, notes = build_views(endpoint, copy.deepcopy(payload), endpoint)
        json.dumps(views, allow_nan=False)
        assert isinstance(notes, list)


def test_an_unknown_endpoint_falls_back_to_generic_views():
    views, _ = build_views("something_new", {"data": [{"date": "2026-01-01", "value": 1}, {"date": "2026-01-02", "value": 2}]}, "Something new")
    assert "table" in kinds(views)
