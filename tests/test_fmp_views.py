"""Financial Modeling Prep view builders: one fixture per response family, garbage never raising."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from tradingview_data.providers.fmp_catalog import ENDPOINTS
from tradingview_data.providers.fmp_views import build_views, clean, fact_of, rows_of

import fmp_support as fx

IDS = [e["id"] for e in ENDPOINTS]


def build(endpoint_id, payload):
    return build_views(endpoint_id, payload, endpoint_id.replace("_", " ").title())


def one(views, kind, index=0):
    return [v for v in views if v["kind"] == kind][index]


def facts(view):
    return {i["key"]: i for g in view["groups"] for i in g["items"]}


def utc(seconds):
    return datetime.fromtimestamp(seconds, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


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


# --- one company: facts ---------------------------------------------------------------------------------


def test_a_quote_is_facts_with_percentages_a_tone_and_a_readable_time():
    views, notes = build("quote", fx.QUOTE)
    assert [v["kind"] for v in views] == ["facts"] and views[0]["title"] == "Apple Inc." and views[0]["subtitle"] == "AAPL" and notes == []
    assert [g["title"] for g in views[0]["groups"]] == ["Price", "Ranges", "Market"]
    items = facts(views[0])
    assert (items["changePercentage"]["format"], items["changePercentage"]["tone"], items["changePercentage"]["label"]) == ("percent", "negative", "Change (%)")
    assert items["timestamp"]["value"] == utc(1793642472) and items["priceAvg50"]["label"] == "50-day average"
    assert items["marketCap"]["value"] == 4933836919584
    check_valid(views)


def test_a_quote_for_several_symbols_is_a_table():
    views, _ = build("quote", [*fx.QUOTE, {**fx.QUOTE[0], "symbol": "MSFT"}])
    assert [v["kind"] for v in views] == ["table"] and views[0]["total_rows"] == 2
    check_valid(views)


def test_a_millisecond_timestamp_is_read_as_milliseconds():
    views, _ = build("aftermarket_trade", fx.AFTERMARKET_TRADE)
    assert facts(one(views, "facts"))["timestamp"]["value"] == utc(1793643102)
    assert fact_of("timestamp", 1793642472)["value"] == utc(1793642472)


def test_price_changes_are_percentages_with_plain_labels():
    items = facts(build("price_change", fx.PRICE_CHANGE)[0][0])
    assert items["ytd"]["label"] == "Year to date" and items["1D"]["format"] == "percent" and items["1D"]["tone"] == "negative" and items["1M"]["tone"] == "positive"


def test_a_profile_is_grouped_facts_plus_the_description_as_clean_text():
    views, _ = build("profile", fx.PROFILE)
    assert [v["id"] for v in views] == ["profile", "about"] and views[0]["title"] == "Apple Inc."
    items = facts(views[0])
    assert items["website"]["format"] == "url" and items["isEtf"]["value"] == "No" and items["isActivelyTrading"]["value"] == "Yes" and items["cik"]["value"] == "0000320193"
    assert "image" not in items and "description" not in items
    assert views[1]["blocks"][0]["body"] == "Apple Inc. designs smartphones. It also sells services."
    check_valid(views)


def test_other_single_records_become_facts_and_nested_values_are_left_out():
    views, _ = build("dcf", [{"symbol": "AAPL", "date": "2026-10-09", "dcf": 141.3, "Stock Price": 338.1}])
    assert [v["kind"] for v in views] == ["facts"] and facts(views[0])["Stock Price"]["value"] == 338.1
    nested, _ = build("sec_profile", [{"symbol": "AAPL", "sicCode": "3571", "extra": {"a": 1}, "list": [1, 2]}])
    assert set(facts(nested[0])) == {"symbol", "sicCode"}


# --- statements: periods across, fields down -----------------------------------------------------------------


def test_a_statement_is_a_chart_of_the_headline_lines_and_a_table_with_a_column_per_period():
    views, notes = build("income_statement", fx.INCOME)
    assert [v["kind"] for v in views] == ["facts", "series", "table"] and notes == []
    chart = one(views, "series")
    assert [s["key"] for s in chart["series"]] == ["revenue", "grossProfit", "operatingIncome", "netIncome"] and chart["subtitle"] == "AAPL \u00b7 USD"
    assert chart["series"][0]["values"] == [383285000000, 391035000000, 416161000000] and utc(chart["time"][-1]) == "2025-09-27 00:00:00"
    table = one(views, "table")
    assert [c["label"] for c in table["columns"]] == ["Item", "2025 FY", "2024 FY", "2023 FY"] and table["columns"][0]["type"] == "text"
    revenue = next(r for r in table["rows"] if r[0] == "Revenue")
    assert revenue[1:] == [416161000000, 391035000000, 383285000000]
    assert not any(r[0] in ("Symbol", "Reported Currency", "Cik", "Fiscal Year", "Period") for r in table["rows"])
    check_valid(views)


def test_a_quarterly_statement_labels_its_columns_by_year_and_quarter_and_disambiguates_repeats():
    rows = [fx.statement(2025, "Q4", revenue=1.0), fx.statement(2025, "Q3", revenue=2.0), fx.statement(2025, "Q3", revenue=3.0)]
    table = one(build("income_statement", rows)[0], "table")
    assert [c["label"] for c in table["columns"]] == ["Item", "2025 Q4", "2025 Q3", "2025 Q3 (2025-09-27)"]


def test_a_single_period_is_still_a_table_and_never_a_blank_chart():
    views, _ = build("balance_sheet", [fx.statement(2025, totalAssets=3.5e11, totalLiabilities=2.8e11)])
    assert [v["kind"] for v in views] == ["table"]
    check_valid(views)


def test_ratio_endpoints_chart_same_scale_lines_and_long_histories_are_capped_with_a_note():
    views, notes = build("ratios", fx.RATIOS)
    assert [s["key"] for s in one(views, "series")["series"]] == ["grossProfitMargin", "operatingProfitMargin", "netProfitMargin"]
    long = [fx.statement(2025 - i, revenue=float(i + 1)) for i in range(25)]
    table = one(build("income_statement", long)[0], "table")
    assert len(table["columns"]) == 21 and any("latest 20 of 25 periods" in n for n in build("income_statement", long)[1])


def test_revenue_segments_are_a_table_of_segments_by_period():
    views, _ = build("revenue_product_segmentation", fx.SEGMENTS)
    table = one(views, "table")
    assert [c["label"] for c in table["columns"]] == ["Item", "2025 FY", "2024 FY"]
    assert sorted(table["rows"], key=lambda r: r[0]) == [["I Phone", 209586000000, 201183000000], ["Mac", 33708000000, 29984000000], ["Service", 109158000000, 96169000000]]
    check_valid(views)


# --- prices -------------------------------------------------------------------------------------------------------


def test_end_of_day_prices_are_a_candle_series_in_ascending_utc_with_a_summary_and_the_full_table():
    views, _ = build("historical_eod", fx.EOD)
    chart = one(views, "series")
    assert [s["role"] for s in chart["series"]] == ["open", "high", "low", "close", "volume"] and chart["title"] == "AAPL historical eod" and chart["intraday"] is False and chart["time_note"] is None
    assert chart["series"][3]["values"] == [338.0, 340.42, 336.64] and [utc(t) for t in chart["time"]][0] == "2026-10-07 00:00:00"
    summary = facts(next(v for v in views if v["id"] == "summary"))
    assert summary["latest"]["value"] == 336.64
    table = one(views, "table")
    assert table["total_rows"] == 3 and [c["key"] for c in table["columns"]][:3] == ["symbol", "date", "open"]
    check_valid(views)


def test_the_light_and_adjusted_variants_chart_what_they_have():
    light = one(build("historical_eod", fx.EOD_LIGHT)[0], "series")
    assert [(s["key"], s["role"]) for s in light["series"]] == [("close", "close"), ("volume", "volume")] and light["series"][0]["values"] == [340.42, 336.64]
    adjusted = one(build("historical_eod", fx.EOD_ADJUSTED)[0], "series")
    assert [s["role"] for s in adjusted["series"]] == ["open", "high", "low", "close", "volume"] and adjusted["series"][3]["values"] == [340.42, 336.64]


def test_intraday_bars_keep_the_exchange_local_time_and_say_so():
    views, _ = build("intraday", fx.INTRADAY)
    chart = one(views, "series")
    assert chart["intraday"] is True and "local time" in chart["time_note"] and utc(chart["time"][0]) == "2026-10-09 15:45:00"
    check_valid(views)


def test_a_technical_indicator_adds_its_own_chart_next_to_the_prices():
    views, _ = build("technical_indicator", fx.RSI)
    indicator = next(v for v in views if v["id"] == "indicator")
    assert indicator["title"] == "Rsi" and indicator["series"][0]["values"] == [63.0, 64.8, 61.2] and indicator["series"][0]["role"] == "value"
    assert len([v for v in views if v["kind"] == "series"]) == 2
    check_valid(views)


def test_prices_without_dates_fall_back_to_the_generic_views():
    views, _ = build("historical_eod", [{"symbol": "AAPL", "close": 1.0}])
    assert [v["kind"] for v in views] == ["facts"]


# --- movers, snapshots, rates -----------------------------------------------------------------------------------------


def test_movers_are_bars_of_the_percentage_change_and_a_table():
    views, _ = build("biggest_gainers", fx.GAINERS)
    bars = one(views, "bars")
    assert bars["labels"] == ["ABC", "XYZ"] and bars["values"] == [33.7, 25.0] and bars["format"] == "percent" and bars["sign_colors"] is True
    assert [c["key"] for c in one(views, "table")["columns"]] == ["symbol", "name", "price", "change", "changesPercentage", "exchange"]
    check_valid(views)


def test_sector_snapshots_are_bars_by_sector_and_pe_snapshots_use_plain_numbers():
    performance, _ = build("sector_performance", fx.SECTORS)
    assert one(performance, "bars")["labels"] == ["Technology", "Energy"] and one(performance, "bars")["values"] == [1.2, -0.8]
    pe, _ = build("sector_pe", fx.SECTOR_PE)
    assert one(pe, "bars")["format"] == "number" and one(pe, "bars")["values"] == [31.5, 12.1]
    check_valid(performance)
    check_valid(pe)


def test_treasury_rates_are_one_line_per_maturity_and_a_yield_curve_of_the_latest_day():
    views, _ = build("treasury_rates", fx.TREASURY)
    chart = one(views, "series")
    assert [s["label"] for s in chart["series"]] == ["1M", "2M", "3M", "6M", "1Y", "2Y", "3Y", "5Y", "7Y", "10Y", "20Y", "30Y"]
    curve = one(views, "bars")
    assert curve["title"] == "Yield curve on 2026-10-30" and curve["values"][0] == 4.06 and len(curve["labels"]) == 12
    check_valid(views)


# --- news and transcripts ----------------------------------------------------------------------------------------------


def test_news_is_a_feed_with_plain_text_a_safe_link_and_the_symbols():
    views, _ = build("stock_news_latest", fx.NEWS)
    feed = one(views, "feed")
    first, second = feed["items"]
    assert first["title"] == "Apple unveils a new chip" and first["url"] == "https://example.com/apple-chip" and first["source"] == "Benzinga \u00b7 benzinga.com"
    assert first["summary"] == "Apple said today that it has a new chip." and [t["symbol"] for t in first["tickers"]] == ["AAPL"] and first["sentiment"] is None
    assert utc(first["published"]) == "2026-10-22 19:06:41" and second["url"] is None
    assert facts(one(views, "facts"))["articles"]["value"] == 2 and feed["total_items"] == 2 and feed["truncated"] is False
    check_valid(views)


def test_fmp_articles_use_link_author_and_exchange_prefixed_tickers():
    item = one(build("fmp_articles", fx.ARTICLES)[0], "feed")["items"][0]
    assert item["url"].endswith("/randstad") and item["source"] == "Stuart Mooney \u00b7 Financial Modeling Prep" and item["summary"] == "Revenue beat"
    assert [t["symbol"] for t in item["tickers"]] == ["RANJY", "AAPL"]


def test_news_without_titles_falls_back_to_the_generic_table():
    views, _ = build("stock_news_latest", [{"symbol": "AAPL", "text": "x"}])
    assert [v["kind"] for v in views] == ["facts"]


def test_a_transcript_is_one_text_block_per_paragraph():
    views, _ = build("transcript", fx.TRANSCRIPT)
    text = one(views, "text")
    assert [b["body"] for b in text["blocks"]] == ["Operator: Good day.", "Tim Cook: Thank you."] and text["subtitle"] == "AAPL Q4 2024"
    check_valid(views)


# --- the generic path and garbage ---------------------------------------------------------------------------------------


def test_dated_records_become_a_chart_and_a_table_through_the_generic_analyzer():
    views, _ = build("earnings", fx.EARNINGS)
    assert [v["kind"] for v in views] == ["facts", "series", "table"] and one(views, "table")["total_rows"] == 2
    check_valid(views)


def test_records_helpers():
    assert rows_of([{"a": 1}, 3, None]) == [{"a": 1}] and rows_of({"a": 1}) == [{"a": 1}] and rows_of("x") == [] and rows_of(None) == []
    assert clean("<p>Tom &amp; Jerry&nbsp;<b>world</b></p>  ok") == "Tom & Jerry world ok" and clean(None) is None and clean("x" * 700).endswith("\u2026") and len(clean("x" * 700)) == 600


@pytest.mark.parametrize("payload", [None, 5, "text", [], {}, [1, 2, 3], [{}], [[{"a": 1}]], {"a": {"b": {"c": {"d": {"e": 1}}}}}, [{"date": "2026-01-01", "x": float("nan")}], [{"date": "not a date", "close": "abc"}], [{"data": "not a mapping", "date": "2026-01-01"}]])
@pytest.mark.parametrize("endpoint_id", IDS)
def test_garbage_never_raises_and_always_yields_valid_views(endpoint_id, payload):
    views, notes = build(endpoint_id, payload)
    assert isinstance(views, list) and isinstance(notes, list)
    json.dumps(views, allow_nan=False)
