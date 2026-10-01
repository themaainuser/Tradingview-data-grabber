"""View builders: one hand-made fixture per response family, caps, and garbage never raising."""

from __future__ import annotations

import glob
import json
import os
from datetime import datetime, timezone

import pytest

from tradingview_data.providers import views as V
from tradingview_data.providers.alphavantage_views import build_views

from providers_support import DAILY


def kinds(views):
    return [v["kind"] for v in views]


def by_kind(views, kind):
    return [v for v in views if v["kind"] == kind]


def facts(view):
    return {i["key"]: i for g in view["groups"] for i in g["items"]}


def utc(seconds):
    return datetime.fromtimestamp(seconds, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


# --- scalars -----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("raw", "expected"), [("1.5", 1.5), (3, 3.0), (".", None), ("None", None), ("", None), ("abc", None), ("nan", None), ("inf", None), (None, None), (True, None)])
def test_to_number(raw, expected):
    assert V.to_number(raw) == expected


@pytest.mark.parametrize(("key", "label"), [("1. open", "Open"), ("PERatio", "PE Ratio"), ("52WeekHigh", "52 Week High"), ("eps_estimate_average", "Eps estimate average"), ("6.1: Deviation multiplier", "Deviation multiplier"), ("fiscalDateEnding", "Fiscal Date Ending")])
def test_humanize(key, label):
    assert V.humanize(key) == label


# --- time series -------------------------------------------------------------------------------------------------


def test_a_daily_series_has_roles_ascending_utc_midnight_times_and_a_hand_checkable_summary():
    views, notes = build_views("TIME_SERIES_DAILY", DAILY, "Daily")
    assert kinds(views) == ["facts", "series", "table"] and notes == []
    series = views[1]
    assert series["title"] == "Price history" and series["subtitle"] == "IBM · Daily Prices"
    assert [utc(t) for t in series["time"]] == ["2026-09-25T00:00:00", "2026-09-28T00:00:00", "2026-09-29T00:00:00"]
    assert [(c["label"], c["role"]) for c in series["series"]] == [("open", "open"), ("high", "high"), ("low", "low"), ("close", "close"), ("volume", "volume")]
    assert next(c for c in series["series"] if c["role"] == "close")["values"] == [218.0, 220.0, 221.0]
    summary = facts(views[0])
    assert summary["latest"]["value"] == 221.0 and summary["change"]["value"] == 1.0 and summary["change"]["tone"] == "positive"
    assert summary["period"]["value"] == pytest.approx((221 / 218 - 1) * 100)
    assert summary["high"]["value"] == 223.0 and summary["low"]["value"] == 214.0
    assert summary["avg_volume"]["value"] == 2000.0 and summary["points"]["value"] == 3
    assert summary["range"]["value"] == "2026-09-25 to 2026-09-29"
    table = views[2]
    assert table["rows"][0][0] == "2026-09-29" and table["columns"][1]["type"] == "number"


def test_intraday_times_are_converted_from_the_providers_zone_across_both_daylight_saving_changes():
    keyed = {
        "2026-03-06 12:00:00": {"1. open": "1", "4. close": "1"},  # EST, UTC-5
        "2026-03-09 12:00:00": {"1. open": "2", "4. close": "2"},  # EDT, UTC-4
        "2026-10-30 12:00:00": {"1. open": "3", "4. close": "3"},  # EDT
        "2026-11-02 12:00:00": {"1. open": "4", "4. close": "4"},  # EST
    }
    payload = {"Meta Data": {"1. Information": "Intraday", "2. Symbol": "IBM", "6. Time Zone": "US/Eastern"}, "Time Series (5min)": keyed}
    views, notes = build_views("TIME_SERIES_INTRADAY", payload, "Intraday")
    series = by_kind(views, "series")[0]
    assert [utc(t) for t in series["time"]] == ["2026-03-06T17:00:00", "2026-03-09T16:00:00", "2026-10-30T16:00:00", "2026-11-02T17:00:00"]
    assert series["intraday"] is True and "US/Eastern" in series["time_note"] and notes == []


def test_an_unknown_time_zone_is_read_as_utc_and_says_so():
    payload = {"Meta Data": {"6. Time Zone": "Mars/Olympus"}, "Time Series (5min)": {"2026-03-06 12:00:00": {"1. open": "1", "4. close": "1"}, "2026-03-06 12:05:00": {"1. open": "2", "4. close": "2"}}}
    views, notes = build_views("TIME_SERIES_INTRADAY", payload, "x")
    series = by_kind(views, "series")[0]
    assert utc(series["time"][0]) == "2026-03-06T12:00:00" and "unknown" in series["time_note"] and notes


def test_an_indicator_with_several_outputs_is_one_series_with_a_line_per_output():
    payload = {
        "Meta Data": {"1: Symbol": "IBM", "2: Indicator": "Bollinger Bands (BBANDS)", "6.1: Deviation multiplier for upper band": 2},
        "Technical Analysis: BBANDS": {"2026-09-29": {"Real Upper Band": "3", "Real Middle Band": "2", "Real Lower Band": "1"}, "2026-09-28": {"Real Upper Band": "3.5", "Real Middle Band": "2.5", "Real Lower Band": "1.5"}},
    }
    views, _ = build_views("BBANDS", payload, "BBANDS")
    series = by_kind(views, "series")[0]
    assert series["title"] == "Bollinger Bands (BBANDS)" and [c["label"] for c in series["series"]] == ["Real Upper Band", "Real Middle Band", "Real Lower Band"]
    assert {c["role"] for c in series["series"]} == {"value"}
    assert "Deviation multiplier for upper band" in {i["label"] for g in views[0]["groups"] for i in g["items"]}


def test_economic_data_keeps_its_unit_name_and_turns_missing_values_into_nulls():
    payload = {"name": "Consumer Price Index", "interval": "monthly", "unit": "index 1982-1984=100", "data": [{"date": "2026-03-01", "value": "."}, {"date": "2026-02-01", "value": "330.5"}, {"date": "2026-01-01", "value": "329"}]}
    views, _ = build_views("CPI", payload, "Consumer Price Index")
    series = by_kind(views, "series")[0]
    assert series["title"] == "Consumer Price Index" and series["series"][0]["unit"] == "index 1982-1984=100"
    assert series["series"][0]["values"] == [329.0, 330.5, None]
    assert not any("." == str(c) for row in by_kind(views, "table")[0]["rows"] for c in row)


# --- facts families -------------------------------------------------------------------------------------------------


def test_a_quote_has_typed_values_and_tones_for_the_change_fields():
    payload = {"Global Quote": {"01. symbol": "IBM", "05. price": "219.99", "06. volume": "3766484", "07. latest trading day": "2026-09-29", "09. change": "-0.6800", "10. change percent": "-0.3082%"}}
    (view,), _ = build_views("GLOBAL_QUOTE", payload, "Quote")
    f = facts(view)
    assert f["01. symbol"]["value"] == "IBM" and f["05. price"]["value"] == 219.99
    assert f["06. volume"]["format"] == "integer" and f["07. latest trading day"]["format"] == "date"
    assert f["09. change"]["tone"] == "negative" and f["10. change percent"]["format"] == "percent" and f["10. change percent"]["value"] == -0.3082


def test_an_overview_is_grouped_and_fractions_become_percentages_while_ids_stay_text():
    payload = {"Symbol": "IBM", "Name": "International Business Machines", "CIK": "0000051143", "MarketCapitalization": "207260156000", "PERatio": "19.61", "DividendYield": "0.0305", "ProfitMargin": "0.155", "Beta": "0.7", "Note": "x"}
    (view,), _ = build_views("OVERVIEW", payload, "Overview")
    assert [g["title"] for g in view["groups"]] == ["Company", "Valuation", "Financials", "Dividends", "Technicals", "Other"]
    f = facts(view)
    assert f["CIK"]["format"] == "text" and f["CIK"]["value"] == "0000051143"
    assert f["DividendYield"]["value"] == pytest.approx(3.05) and f["DividendYield"]["format"] == "percent"
    assert f["MarketCapitalization"]["format"] == "integer" and f["PERatio"]["value"] == 19.61


def test_statements_are_transposed_with_periods_as_columns_and_a_year_over_year_summary():
    payload = {
        "symbol": "IBM",
        "annualReports": [
            {"fiscalDateEnding": "2025-12-31", "reportedCurrency": "USD", "totalRevenue": "110", "netIncome": "11", "grossProfit": "None"},
            {"fiscalDateEnding": "2024-12-31", "reportedCurrency": "USD", "totalRevenue": "100", "netIncome": "10", "grossProfit": "None"},
        ],
        "quarterlyReports": [{"fiscalDateEnding": "2026-06-30", "reportedCurrency": "USD", "totalRevenue": "30", "netIncome": "3"}],
    }
    views, _ = build_views("INCOME_STATEMENT", payload, "Income statement")
    annual = next(v for v in views if v["id"] == "annual-table")
    assert [c["label"] for c in annual["columns"]] == ["Metric", "2025-12-31", "2024-12-31"]
    assert [r[0] for r in annual["rows"]] == ["Total Revenue", "Net Income", "Gross Profit"] and annual["rows"][0][1:] == [110.0, 100.0]
    assert annual["rows"][2][1:] == [None, None]
    chart = by_kind(views, "series")[0]
    assert [utc(t)[:10] for t in chart["time"]] == ["2024-12-31", "2025-12-31"] and chart["series"][0]["unit"] == "USD"
    revenue = facts(views[0])["totalRevenue"]
    assert revenue["value"] == 110.0 and revenue["tone"] == "positive" and "+10.0%" in revenue["hint"]
    assert any(v["id"] == "quarterly-table" for v in views)


def test_earnings_chart_compares_reported_with_estimated_and_charts_the_surprise():
    payload = {"symbol": "IBM", "annualEarnings": [{"fiscalDateEnding": "2025-12-31", "reportedEPS": "10"}], "quarterlyEarnings": [
        {"fiscalDateEnding": "2026-03-31", "reportedEPS": "1.6", "estimatedEPS": "1.5", "surprisePercentage": "6.67"},
        {"fiscalDateEnding": "2026-06-30", "reportedEPS": "2.9", "estimatedEPS": "3.0", "surprisePercentage": "-3.33"}]}
    views, _ = build_views("EARNINGS", payload, "Earnings")
    series, bars = by_kind(views, "series")[0], by_kind(views, "bars")[0]
    assert [c["label"] for c in series["series"]] == ["Reported EPS", "Estimated EPS"] and series["series"][0]["values"] == [1.6, 2.9]
    assert bars["values"] == [6.67, -3.33] and bars["sign_colors"] is True and bars["format"] == "percent"


def test_news_becomes_a_feed_with_sentiment_and_a_distribution_in_canonical_order():
    article = lambda label, score: {"title": f"{label} story", "url": "https://example.test/a", "time_published": "20260930T100224", "source": "Wire", "summary": "s",
        "overall_sentiment_score": score, "overall_sentiment_label": label, "topics": [{"topic": "financial_markets", "relevance_score": "0.9"}],
        "ticker_sentiment": [{"ticker": "IBM", "relevance_score": "1.0", "ticker_sentiment_score": "-0.36", "ticker_sentiment_label": "Bearish"}]}
    payload = {"items": "3", "feed": [article("Bullish", 0.4), article("Bearish", -0.4), article("Bullish", 0.5)]}
    views, _ = build_views("NEWS_SENTIMENT", payload, "News")
    feed, bars = by_kind(views, "feed")[0], by_kind(views, "bars")[0]
    assert utc(feed["items"][0]["published"]) == "2026-09-30T10:02:24" and feed["items"][0]["tags"] == ["Financial Markets"]
    assert feed["items"][0]["tickers"][0] == {"symbol": "IBM", "relevance": 1.0, "score": -0.36, "label": "Bearish"}
    assert bars["labels"] == ["Bearish", "Bullish"] and bars["values"] == [1.0, 2.0] and bars["sign_colors"] is False
    assert facts(views[0])["average"]["value"] == pytest.approx(0.1666667, rel=1e-4)


def test_news_urls_that_are_not_http_are_dropped():
    payload = {"feed": [{"title": "x", "url": "javascript:alert(1)", "time_published": "20260930T100224"}]}
    feed = by_kind(build_views("NEWS_SENTIMENT", payload, "News")[0], "feed")[0]
    assert feed["items"][0]["url"] is None


def test_top_movers_make_three_tables_and_a_signed_bar_chart():
    row = lambda t, p: {"ticker": t, "price": "1.0", "change_amount": "0.1", "change_percentage": p, "volume": "100"}
    payload = {"last_updated": "2026-09-29 16:15:59", "top_gainers": [row("UP", "193.9%")], "top_losers": [row("DN", "-79.1%")], "most_actively_traded": [row("AC", "5.0%")]}
    views, _ = build_views("TOP_GAINERS_LOSERS", payload, "Movers")
    assert kinds(views).count("table") == 3
    bars = by_kind(views, "bars")[0]
    assert bars["labels"] == ["UP", "DN"] and bars["values"] == [193.9, -79.1] and bars["sign_colors"] is True
    assert by_kind(views, "table")[0]["columns"][3]["type"] == "percent"


def test_analytics_correlation_is_a_full_symmetric_heatmap_and_scalar_metrics_a_table():
    payload = {"meta_data": {"symbols": "A,B,C"}, "payload": {"RETURNS_CALCULATIONS": {
        "MEAN": {"A": 0.1, "B": 0.2, "C": 0.3},
        "CORRELATION": {"index": ["A", "B", "C"], "correlation": [[1.0], [0.5, 1.0], [0.25, -0.5, 1.0]]}}}}
    views, _ = build_views("ANALYTICS_FIXED_WINDOW", payload, "Analytics")
    heat = by_kind(views, "heatmap")[0]
    assert heat["rows"] == heat["cols"] == ["A", "B", "C"] and heat["domain"] == [-1.0, 1.0]
    assert heat["values"] == [[1.0, 0.5, 0.25], [0.5, 1.0, -0.5], [0.25, -0.5, 1.0]]
    metrics = by_kind(views, "table")[0]
    assert [c["label"] for c in metrics["columns"]] == ["Symbol", "Mean"] and metrics["rows"][1] == ["B", 0.2]


def test_a_sliding_window_is_a_series_with_a_line_per_symbol():
    payload = {"meta_data": {"window_size": 20}, "payload": {"RETURNS_CALCULATIONS": {"MEAN": {"RUNNING_MEAN": {"IBM": {"2026-08-26": 0.1, "2026-08-27": 0.2}, "AAPL": {"2026-08-26": 0.3, "2026-08-27": 0.4}}, "window_start": {"2026-08-26": "2026-07-29"}}}}}
    series = by_kind(build_views("ANALYTICS_SLIDING_WINDOW", payload, "Sliding")[0], "series")[0]
    assert [c["label"] for c in series["series"]] == ["IBM", "AAPL"] and series["series"][1]["values"] == [0.3, 0.4]


def test_a_transcript_is_text_blocks_with_a_sentiment_badge():
    payload = {"symbol": "IBM", "quarter": "2024Q1", "transcript": [{"speaker": "A", "title": "CEO", "content": "Hello", "sentiment": "0.6"}, {"speaker": "B", "title": "CFO", "content": "Hi", "sentiment": "-0.25"}]}
    views, _ = build_views("EARNINGS_CALL_TRANSCRIPT", payload, "Transcript")
    text = by_kind(views, "text")[0]
    assert [b["badge"] for b in text["blocks"]] == ["Sentiment +0.60", "Sentiment -0.25"] and text["blocks"][0]["heading"] == "A"
    assert facts(views[0])["segments"]["value"] == 2


def test_etf_profile_has_sector_bars_in_percent_and_a_holdings_table():
    payload = {"net_assets": "489000000000", "net_expense_ratio": "0.0018", "sectors": [{"sector": "INFORMATION TECHNOLOGY", "weight": "0.577"}], "holdings": [{"symbol": "NVDA", "description": "NVIDIA", "weight": "0.0826"}]}
    views, _ = build_views("ETF_PROFILE", payload, "ETF")
    assert by_kind(views, "bars")[0]["values"] == [pytest.approx(57.7)]
    holdings = by_kind(views, "table")[0]
    assert holdings["rows"][0][2] == pytest.approx(8.26) and holdings["columns"][2]["type"] == "percent"
    assert facts(views[0])["net_expense_ratio"]["value"] == pytest.approx(0.18)


def test_options_get_counts_and_a_contract_table():
    payload = {"endpoint": "Historical Options", "data": [{"contractID": "A1", "expiration": "2026-10-02", "strike": "100.00", "type": "call"}, {"contractID": "A2", "expiration": "2026-10-09", "strike": "120.00", "type": "put"}]}
    views, _ = build_views("HISTORICAL_OPTIONS", payload, "Options")
    f = facts(views[0])
    assert (f["contracts"]["value"], f["calls"]["value"], f["puts"]["value"], f["expirations"]["value"]) == (2, 1, 1, 2) and f["strikes"]["value"] == "100 to 120"
    assert by_kind(views, "table")[0]["columns"][0]["type"] == "text"  # contract ids stay text


def test_the_index_catalog_is_a_two_column_table():
    (view,), _ = build_views("INDEX_CATALOG", {"DJI": "Dow Jones", "SPX": "S&P 500"}, "Catalog")
    assert view["rows"] == [["DJI", "Dow Jones"], ["SPX", "S&P 500"]]


# --- caps, shape guarantees, garbage ---------------------------------------------------------------------------------


def test_a_long_series_keeps_the_most_recent_points_and_says_so():
    keyed = {f"{2000 + i // 365}-{(i % 365) // 31 + 1:02d}-{(i % 28) + 1:02d}": {"4. close": str(i)} for i in range(30)}
    times = [V.epoch(k) for k in keyed]
    view = V.series_view("s", "S", times, [{"key": "c", "label": "close", "values": list(range(30)), "role": "close", "unit": None}])
    assert view["total_points"] == len(set(times)) and view["truncated"] is False
    original = V.CAPS["series"]
    V.CAPS["series"] = 5
    try:
        capped = V.series_view("s", "S", list(range(100, 130)), [{"key": "c", "label": "close", "values": list(range(30)), "role": "close", "unit": None}])
    finally:
        V.CAPS["series"] = original
    assert capped["time"] == list(range(125, 130)) and capped["series"][0]["values"] == [25, 26, 27, 28, 29] and capped["truncated"] and capped["total_points"] == 30


def test_a_big_table_is_capped_and_flagged():
    records = [{"n": i, "name": f"row {i}"} for i in range(V.CAPS["table"] + 10)]
    view = V.table_view("t", "T", records)
    assert len(view["rows"]) == V.CAPS["table"] and view["total_rows"] == len(records) and view["truncated"] is True
    views, notes = build_views("INSIDER_TRANSACTIONS", {"data": records}, "Insiders")
    assert any("first 5,000 of 5,010 rows" in n for n in notes)


def test_every_series_and_table_is_aligned_ascending_and_finite():
    payloads = [("TIME_SERIES_DAILY", DAILY), ("CPI", {"name": "x", "unit": "u", "data": [{"date": f"2026-0{m}-01", "value": str(m)} for m in range(1, 6)]})]
    for function, payload in payloads:
        views, _ = build_views(function, payload, function)
        for v in views:
            if v["kind"] == "series":
                assert all(len(s["values"]) == len(v["time"]) for s in v["series"]) and v["time"] == sorted(v["time"])
            if v["kind"] == "table":
                assert all(len(r) == len(v["columns"]) for r in v["rows"])
        json.dumps(views, allow_nan=False)


GARBAGE = [None, 0, "x" * 100_000, [], {}, [1, "a", None, {"a": 1}, [2]], {"a": {"b": {"c": {"d": {"e": {"f": 1}}}}}}, {"Meta Data": 5, "Time Series (Daily)": 7}, {"Meta Data": {}, "Time Series (Daily)": {"not a date": {"a": 1}}},
           {"data": [{"date": "2026-01-01"}, {"date": "bad"}]}, {"feed": "oops", "items": []}, {"transcript": [1, 2]}, {"payload": {"RETURNS_CALCULATIONS": {"CORRELATION": {"index": ["A"], "correlation": "bad"}}}}, {"annualReports": [None, 5], "quarterlyReports": "x"}, [{"a": float("nan")}], {"a": float("inf")}]


@pytest.mark.parametrize("function", ["TIME_SERIES_DAILY", "NEWS_SENTIMENT", "EARNINGS", "INCOME_STATEMENT", "ANALYTICS_FIXED_WINDOW", "ANALYTICS_SLIDING_WINDOW", "EARNINGS_CALL_TRANSCRIPT", "ETF_PROFILE", "OVERVIEW", "TOP_GAINERS_LOSERS", "WHATEVER"])
def test_an_unfamiliar_shape_never_raises_and_stays_valid_json(function):
    for payload in GARBAGE:
        views, notes = build_views(function, payload, function)
        json.dumps(views, allow_nan=False)
        assert isinstance(notes, list)


SAMPLES = sorted(glob.glob("/tmp/av/samples/*.body"))


@pytest.mark.skipif(not SAMPLES, reason="real sample responses are only on the dev machine")
@pytest.mark.parametrize("path", SAMPLES, ids=[os.path.basename(p)[:-5] for p in SAMPLES])
def test_real_responses_yield_valid_views(path):
    import csv
    import io

    raw = open(path, "rb").read()
    payload = json.loads(raw) if raw[:1] in (b"{", b"[") else [dict(r) for r in csv.DictReader(io.StringIO(raw.decode("utf-8", "replace")))]
    function = os.path.basename(path)[:-5]
    views, _ = build_views(function, payload, function)
    assert views, function
    json.dumps(views, allow_nan=False)
    for v in views:
        if v["kind"] == "series":
            assert all(len(s["values"]) == len(v["time"]) for s in v["series"]) and v["time"] == sorted(v["time"])
        if v["kind"] == "table":
            assert all(len(r) == len(v["columns"]) for r in v["rows"])
