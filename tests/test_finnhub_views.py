"""Finnhub response shapes -> views: quotes and profiles as facts, news as a feed, financials as tables and charts,
candles as a candlestick chart, and everything else as tables that keep identifiers and flags as sent."""

from __future__ import annotations

import pytest

from tradingview_data.providers.finnhub_views import METRIC_NOTE, REPORTED_NOTE, build_views

import finnhub_support as fx


def views(endpoint_id, payload, label="Data"):
    built, notes = build_views(endpoint_id, payload, label)
    return {v["id"]: v for v in built}, notes


def items(view):
    return {i["key"]: i for group in view["groups"] for i in group["items"]}


def column(view, key):
    index = next(i for i, c in enumerate(view["columns"]) if c["key"] == key)
    return view["columns"][index], [row[index] for row in view["rows"]]


def test_a_quote_names_its_one_letter_fields_and_shows_the_time_in_utc():
    built, _ = views("quote", fx.QUOTE, "Quote")
    facts = items(built["quote"])
    assert [f["label"] for f in facts.values()] == ["Current price", "Change", "Change (%)", "Open", "High", "Low", "Previous close", "Updated (UTC)"]
    assert (facts["c"]["value"], facts["dp"]["format"], facts["dp"]["tone"], facts["d"]["tone"]) == (331.9, "percent", "negative", "negative")
    assert facts["t"]["value"] == "2026-11-03 21:00:00"


def test_a_profile_says_which_figures_are_in_millions_and_keeps_the_phone_as_sent():
    built, _ = views("company_profile2", fx.PROFILE2)
    profile = built["profile"]
    assert profile["title"] == "Apple Inc." and profile["subtitle"] == "AAPL" and [g["title"] for g in profile["groups"]] == ["Company", "Market"]
    facts = items(profile)
    assert facts["marketCapitalization"]["label"] == "Market capitalisation (millions)" and facts["shareOutstanding"]["label"] == "Shares outstanding (millions)"
    assert facts["phone"]["value"] == "14089961010" and facts["finnhubIndustry"]["label"] == "Industry (Finnhub)"


def test_news_is_a_feed_without_unsafe_links_and_with_its_tickers():
    built, notes = views("company_news", fx.NEWS)
    feed = built["feed"]
    first, second = feed["items"]
    assert (first["title"], first["source"], first["published"], first["url"]) == ("Why the blue wave could be good for Apple", "Yahoo", 1793786451, "https://finnhub.io/api/news?id=6d59")
    assert first["summary"] == "Apple is seen as an early winner." and first["tags"] == ["company"]
    assert second["url"] is None and [t["symbol"] for t in second["tickers"]] == ["AAPL", "MSFT"]
    assert items(built["summary"])["articles"]["value"] == 2 and notes == []


def test_company_news_at_finnhubs_row_cap_says_the_range_may_be_cut_short():
    rows = [{**fx.NEWS[0], "id": i, "datetime": 1793786451 - i * 60} for i in range(250)]
    built, notes = views("company_news", rows)
    assert len(built["feed"]["items"]) == 100 and built["feed"]["truncated"]
    assert any("at most about 250 articles" in n for n in notes) and any("showing 100 of 250" in n for n in notes)


def test_basic_financials_keep_finnhubs_figures_chart_eps_and_margins_and_table_each_frequency():
    built, notes = views("company_basic_financials", fx.METRIC)
    figures = items(built["metrics"])
    assert (figures["peTTM"]["label"], figures["peTTM"]["value"]) == ("P/E TTM", 36.6817)
    assert (figures["roeTTM"]["label"], figures["roeTTM"]["value"]) == ("ROE TTM", 127.61)  # already a percentage: not scaled
    assert figures["52WeekHighDate"]["value"] == "2026-10-23"
    assert built["eps"]["series"][0]["values"] == [6.0766, 7.465, 8.9791]
    margins = {s["key"]: s["values"] for s in built["margins"]["series"]}
    assert margins["netMargin"] == [23.97, 26.92, 27.6] and built["margins"]["title"] == "Margins (annual, % of revenue)"
    annual = built["annual-table"]
    assert [c["label"] for c in annual["columns"]] == ["Figure", "2026-09-26", "2025-09-27", "2024-09-28"]
    assert annual["rows"][0] == ["EPS", 8.9791, 7.465, 6.0766]
    assert "quarterly-table" in built and METRIC_NOTE in notes


def test_basic_financials_beyond_twenty_periods_say_how_many_are_shown():
    periods = tuple(f"{2000 + i}-12-31" for i in range(25))
    payload = {**fx.METRIC, "series": {"annual": {"eps": [{"period": p, "v": float(i)} for i, p in enumerate(periods)]}}}
    built, notes = views("company_basic_financials", payload)
    assert len(built["annual-table"]["columns"]) == 21 and built["annual-table"]["columns"][1]["label"] == "2024-12-31"
    assert any("latest 20 of 25 periods" in n for n in notes)


def test_statements_as_reported_are_a_table_per_statement_with_a_column_per_filing():
    built, notes = views("financials_reported", fx.FINANCIALS_REPORTED)
    income = built["ic-table"]
    assert income["title"] == "Income statement as reported" and income["subtitle"] == "AAPL"
    assert [c["label"] for c in income["columns"]] == ["Line", "Unit", "FY2025 10-K", "2025 Q3 10-Q"]
    assert income["rows"] == [["Net sales", "usd", 416161000000.0, 94036000000.0], ["Diluted", "usdPerShare", 7.46, None]]
    assert "bs-table" in built and "cf-table" not in built  # no cash flow lines in these filings
    access, values = column(built["filings"], "accessNumber")
    assert access["type"] == "text" and values == ["0000320193-25-000079", "0000320193-25-000073"] and REPORTED_NOTE in notes


def test_recommendations_chart_the_trend_and_bar_the_latest_month():
    built, _ = views("recommendation_trends", fx.RECOMMENDATIONS)
    trend = built["trend"]
    assert [s["label"] for s in trend["series"]] == ["Strong buy", "Buy", "Hold", "Sell", "Strong sell"] and trend["series"][0]["values"] == [10, 11]
    assert built["latest"]["title"] == "Recommendations on 2026-11-01" and built["latest"]["values"] == [11, 19, 15, 3, 1]


def test_eps_surprises_chart_actual_against_estimate_and_show_the_surprise_as_a_percentage():
    built, _ = views("company_earnings", fx.EARNINGS)
    assert [s["values"] for s in built["eps"]["series"]] == [[1.57, 2.05], [1.6, 2.0267]]
    assert built["surprise"]["format"] == "percent" and built["surprise"]["values"] == [-1.875, 1.1497]
    surprise, values = column(built["surprises"], "surprisePercent")
    assert (surprise["type"], surprise["label"], values[0]) == ("percent", "Surprise (%)", 1.1497)


def test_insider_sentiment_is_dated_by_month():
    built, notes = views("insider_sentiment", fx.INSIDER_SENTIMENT)
    assert built["mspr"]["time"] == [1767225600, 1769904000] and built["mspr"]["series"][0]["values"] == [-33.333332, 12.5]
    assert built["sentiment"]["subtitle"] == "TSLA" and any("MSPR runs from -100" in n for n in notes)


def test_insider_transactions_keep_flags_as_text_and_name_their_columns():
    built, _ = views("insider_transactions", fx.INSIDER_TRANSACTIONS)
    table = next(v for v in built.values() if v["kind"] == "table")
    flag, values = column(table, "isDerivative")
    assert (flag["type"], flag["label"], values) == ("text", "Derivative", ["No", "Yes"])
    assert column(table, "share")[0]["label"] == "Shares held after" and column(table, "id")[1] == ["000177", "000178"]
    assert table["subtitle"] == "TSLA"


def test_identifiers_keep_their_leading_zeros():
    built, _ = views("stock_visa_application", fx.VISAS)
    table = next(v for v in built.values() if v["kind"] == "table")
    assert column(table, "worksitePostalCode")[1] == ["02134"] and column(table, "year")[1] == ["2026"]


def test_identifiers_stay_in_the_table_but_are_never_charted():
    rows = [
        {"symbol": "LMT", "actionDate": "2026-09-30", "totalValue": 306376860, "performanceZipCode": "801258504", "naicsCode": "336414"},
        {"symbol": "LMT", "actionDate": "2026-08-31", "totalValue": 1200000, "performanceZipCode": "200011234", "naicsCode": "541715"},
    ]
    built, _ = views("stock_usa_spending", {"data": rows, "symbol": "LMT"}, "USA Spending")
    chart = next(v for v in built.values() if v["kind"] == "series")
    assert [s["key"] for s in chart["series"]] == ["totalValue"]
    table = next(v for v in built.values() if v["kind"] == "table")
    assert column(table, "naicsCode") == ({"key": "naicsCode", "label": "Naics Code", "type": "text"}, ["336414", "541715"])
    assert column(table, "performanceZipCode")[1] == ["801258504", "200011234"]


def test_the_earnings_calendar_spells_out_when_and_warns_at_finnhubs_row_cap():
    built, notes = views("earnings_calendar", fx.EARNINGS_CALENDAR)
    assert column(built["calendar"], "hour")[1] == ["Before market open", "After market close"] and notes == []
    many = {"earningsCalendar": fx.EARNINGS_CALENDAR["earningsCalendar"] * 750}
    assert any("at most 1,500 rows" in n for n in views("earnings_calendar", many)[1])


@pytest.mark.parametrize(("payload", "intraday"), [(fx.CANDLES, False), (fx.INTRADAY, True)])
def test_candles_are_a_candlestick_series_in_utc(payload, intraday):
    built, _ = views("stock_candles", payload, "Stock Candles")
    chart = built["candles"]
    assert [s["role"] for s in chart["series"]] == ["open", "high", "low", "close", "volume"] and chart["intraday"] is intraday
    assert chart["time"] == payload["t"] and (chart["time_note"] == "Times are UTC.") is intraday
    assert built["candles-table"]["rows"][0][0].endswith(":00") and built["candles-table"]["total_rows"] == 3


def test_an_indicator_is_its_own_series_and_a_bond_price_is_a_close_line():
    built, _ = views("technical_indicator", fx.INDICATOR)
    assert built["indicator-sma"]["series"][0]["values"] == [None, 222.0, 222.8]
    bond, _ = views("bond_price", fx.BOND_PRICE)
    assert [s["role"] for s in bond["candles"]["series"]] == ["close"]


def test_lists_of_names_become_a_one_column_table():
    built, _ = views("company_peers", fx.PEERS, "Peers")
    table = built["company-peers"]
    assert table["columns"] == [{"key": "symbol", "label": "Symbol", "type": "text"}] and table["rows"] == [["AAPL"], ["DELL"], ["HPQ"]]


def test_flat_objects_become_facts_with_readable_times():
    built, _ = views("market_status", fx.MARKET_STATUS, "Market Status")
    facts = items(built["market-status"])
    assert (facts["isOpen"]["label"], facts["isOpen"]["value"]) == ("Open now", "No")
    assert facts["t"]["value"] == "2026-11-04 11:15:36" and "holiday" not in facts


def test_the_fda_calendar_says_its_times_are_eastern():
    built, notes = views("fda_committee_meeting_calendar", fx.FDA)
    assert next(v for v in built.values() if v["kind"] == "table")["total_rows"] == 2
    assert "Meeting times are US Eastern time, as Finnhub sends them." in notes


@pytest.mark.parametrize("endpoint_id", ["quote", "company_news", "company_basic_financials", "financials_reported", "stock_candles", "recommendation_trends", "insider_sentiment"])
def test_a_surprising_shape_costs_views_not_the_response(endpoint_id):
    for payload in (["odd", 1], {"weird": {"nested": [1, 2]}}, {"t": ["x"]}, "text"):
        built, notes = build_views(endpoint_id, payload, "Data")
        assert isinstance(built, list) and isinstance(notes, list)
