"""Ratios and growth shown as percentages that name their base, with FMP's own figure in brackets."""

from __future__ import annotations

import json

import pytest

from tradingview_data.providers import fmp_ratios as R
from tradingview_data.providers.fmp_views import build_views

import fmp_support as fx


def build(endpoint_id, payload):
    return build_views(endpoint_id, payload, endpoint_id.replace("_", " ").title())


def one(views, view_id):
    return next(v for v in views if v["id"] == view_id)


def cells(view):
    return {row[0]: row[1:] for row in view["rows"]}


def facts(view):
    return {i["key"]: i for g in view["groups"] for i in g["items"]}


# --- the formatting -------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("field", "value", "short", "full", "label"),
    [
        ("grossProfitMargin", 0.469052, "46.91% (0.469052)", "46.91% of revenue (0.469052)", "Gross profit margin (% of revenue)"),
        ("returnOnEquity", 1.5191, "151.91% (1.5191)", "151.91% of shareholders' equity (1.5191)", "Return on equity (% of shareholders' equity)"),
        ("currentRatio", 0.893293, "89.33% (0.893293)", "89.33% of current liabilities (0.893293)", "Current ratio (% of current liabilities)"),
        ("debtToEquityRatio", 1.52, "152.00% (1.52)", "152.00% of shareholders' equity (1.52)", "Debt to equity (% of shareholders' equity)"),
        ("revenueGrowth", 0.0642551, "+6.43% (0.0642551)", "+6.43% vs prior period (0.0642551)", "Revenue growth (% vs prior period)"),
        ("freeCashFlowGrowth", -0.0923, "-9.23% (-0.0923)", "-9.23% vs prior period (-0.0923)", "Free cash flow growth (% vs prior period)"),
        ("tenYRevenueGrowthPerShare", 1.7413, "+174.13% (1.7413)", "+174.13% over 10 years (1.7413)", "Revenue growth per share (% over 10 years)"),
        ("threeYDividendperShareGrowthPerShare", 0.2, "+20.00% (0.2)", "+20.00% over 3 years (0.2)", "Dividend growth per share (% over 3 years)"),
        ("returnOnAssetsTTM", 0.336398, "33.64% (0.336398)", "33.64% of total assets (0.336398)", "Return on assets (% of total assets)"),
        ("effectiveTaxRate", -0.02, "-2.00% (-0.02)", "-2.00% of pre-tax income (-0.02)", "Effective tax rate (% of pre-tax income)"),
        ("dividendYieldPercentage", 0.31, "0.31% (0.31)", "0.31% of share price (0.31)", "Dividend yield, FMP's percentage field (% of share price)"),
    ],
)
def test_a_fraction_is_a_percentage_that_names_its_base_with_the_original_figure_in_brackets(field, value, short, full, label):
    assert R.short_text(field, value) == short and R.text(field, value) == full and R.item_label(field) == label
    assert R.percent(field, value) == pytest.approx(value * R.lookup(field).scale)


def test_a_field_already_sent_as_a_percentage_is_not_multiplied_again():
    assert R.percent("dividendYieldPercentage", 0.31) == 0.31 and R.percent("dividendYield", 0.0031) == pytest.approx(0.31)


@pytest.mark.parametrize("field", ["priceToEarningsRatio", "interestCoverageRatio", "assetTurnover", "daysOfSalesOutstanding", "revenuePerShare", "marketCap", "symbol", "evToSales", "incomeQuality", "taxBurden"])
def test_multiples_amounts_and_unknown_fields_are_left_alone(field):
    assert R.lookup(field) is None and R.text(field, 1.0) is None and R.short_text(field, 1.0) is None and R.percent(field, 1.0) is None and R.item_label(field) == field


def test_every_listed_field_has_a_label_a_base_and_a_unique_row_heading():
    headings = [R.item_label(f) for f in R._SPEC]
    assert len(headings) == len(set(headings)) > 60
    for field, spec in R._SPEC.items():
        assert spec.label and spec.phrase.split()[0] in ("of", "vs", "over") and spec.scale in (1.0, 100.0), field
        assert spec.signed == (spec.phrase.split()[0] != "of"), field


# --- ratios, key metrics and growth by period --------------------------------------------------------------------


def test_ratios_split_into_a_percentage_table_that_names_each_base_and_a_table_of_the_other_figures():
    views, notes = build("ratios", fx.RATIOS)
    assert [v["id"] for v in views] == ["summary", "ratios-chart", "ratios-percent-table", "ratios-table"]
    percentages = cells(one(views, "ratios-percent-table"))
    assert percentages["Gross profit margin (% of revenue)"] == ["46.90% (0.469)", "46.20% (0.462)"]
    assert percentages["Debt to equity (% of shareholders' equity)"] == ["152.00% (1.52)", "187.00% (1.87)"]
    assert set(percentages) == {"Gross profit margin (% of revenue)", "Operating profit margin (% of revenue)", "Net profit margin (% of revenue)", "Debt to equity (% of shareholders' equity)"}
    others = one(views, "ratios-table")
    assert cells(others) == {"Price To Earnings Ratio": [34.11, 28.9], "Receivables Turnover": [5.7, 6.1]}
    assert [c["type"] for c in others["columns"]] == ["text", "number", "number"] and [c["label"] for c in one(views, "ratios-percent-table")["columns"]] == ["Item", "2025 FY", "2024 FY"]
    assert len(notes) == 1 and "times 100" in notes[0] and "figure in brackets" in notes[0]


def test_the_summary_is_in_percent_and_counts_the_change_in_percentage_points():
    summary = facts(one(build("ratios", fx.RATIOS)[0], "summary"))
    assert (summary["latest"]["label"], summary["latest"]["format"], summary["latest"]["value"]) == ("Latest gross profit margin (% of revenue)", "percent", pytest.approx(46.9))
    assert summary["change"]["label"] == "Change vs previous (percentage points)" and summary["change"]["value"] == pytest.approx(0.7) and summary["change"]["tone"] == "positive"
    assert (summary["high"]["format"], summary["low"]["format"]) == ("percent", "percent") and summary["high"]["value"] == pytest.approx(46.9) and summary["low"]["value"] == pytest.approx(46.2)
    assert summary["points"]["value"] == 2 and summary["range"]["value"] == "2024-09-27 to 2025-09-27"
    falling = facts(one(build("financial_growth", [fx.statement(2025, revenueGrowth=0.01), fx.statement(2024, revenueGrowth=0.05)])[0], "summary"))
    assert falling["latest"]["label"] == "Latest revenue growth (% vs prior period)" and falling["change"]["value"] < 0 and falling["change"]["tone"] == "negative"


def test_the_chart_plots_percent_and_the_legend_names_the_base():
    chart = one(build("ratios", fx.RATIOS)[0], "ratios-chart")
    assert [s["label"] for s in chart["series"]] == ["Gross profit margin (% of revenue)", "Operating profit margin (% of revenue)", "Net profit margin (% of revenue)"]
    assert [s["key"] for s in chart["series"]][0] == "grossProfitMargin" and chart["series"][0]["values"] == [pytest.approx(46.2), pytest.approx(46.9)] and chart["series"][0]["unit"] == "%"


def test_key_metrics_show_returns_as_percent_and_leave_amounts_and_days_as_numbers():
    views, _ = build("key_metrics", fx.KEY_METRICS)
    percentages = cells(one(views, "key-metrics-percent-table"))
    assert percentages["Return on equity (% of shareholders' equity)"] == ["151.91% (1.5191)", "164.59% (1.6459)"]
    assert percentages["Return on assets (% of total assets)"][0] == "31.18% (0.311796)" and percentages["Current ratio (% of current liabilities)"][0] == "89.33% (0.893293)"
    assert percentages["Earnings yield (% of market cap)"] == ["2.62% (0.0262)", "2.75% (0.0275)"]
    others = cells(one(views, "key-metrics-table"))
    assert others["Cash Conversion Cycle"] == [-42.0, -45.0] and others["Market Cap"] == [3.8e12, 3.4e12] and "Return On Equity" not in others
    assert one(views, "key-metrics-chart")["series"][0]["label"] == "Return on equity (% of shareholders' equity)"


def test_growth_shows_its_sign_and_what_it_is_measured_against_and_has_no_other_table():
    views, _ = build("financial_growth", fx.GROWTH)
    assert [v["id"] for v in views] == ["summary", "financial-growth-chart", "financial-growth-percent-table"]
    rows = cells(one(views, "financial-growth-percent-table"))
    assert rows["Revenue growth (% vs prior period)"] == ["+6.43% (0.0642551)", "+2.02% (0.0202199)"]
    assert rows["Net income growth (% vs prior period)"] == ["+19.50% (0.195)", "-3.36% (-0.0336)"]
    assert rows["Free cash flow growth (% vs prior period)"] == ["-9.23% (-0.0923)", "+0.00% (0)"]
    assert rows["Revenue growth per share (% over 10 years)"][0] == "+174.13% (1.7413)" and rows["Revenue growth per share (% over 5 years)"][1] == "+70.00% (0.7)"


def test_a_single_period_is_a_percentage_table_without_a_chart():
    views, _ = build("ratios", fx.RATIOS[:1])
    assert [v["id"] for v in views] == ["ratios-percent-table", "ratios-table"]


# --- trailing twelve months: one card per figure ----------------------------------------------------------------------


def test_ttm_ratios_are_cards_with_the_base_in_the_value_and_the_other_figures_after_them():
    views, notes = build("ratios_ttm", fx.RATIOS_TTM)
    view = views[0]
    assert [g["title"] for g in view["groups"]] == ["Percentages and what each is a share of", "Other figures"] and view["subtitle"] == "AAPL" and len(notes) == 1
    items = facts(view)
    assert items["grossProfitMarginTTM"]["value"] == "48.65% of revenue (0.486529)" and items["grossProfitMarginTTM"]["label"] == "Gross profit margin" and items["grossProfitMarginTTM"]["format"] == "text"
    assert items["currentRatioTTM"]["value"] == "100.33% of current liabilities (1.00329)" and items["dividendYieldTTM"]["value"] == "0.31% of share price (0.00313721)"
    assert items["dividendYieldPercentageTTM"]["value"] == "0.31% of share price (0.31)"
    assert items["effectiveTaxRateTTM"]["value"] == "-2.00% of pre-tax income (-0.02)" and items["effectiveTaxRateTTM"]["tone"] == "negative" and items["grossProfitMarginTTM"]["tone"] is None
    assert [i["key"] for i in view["groups"][1]["items"]] == ["priceToEarningsRatioTTM"]
    assert "interestCoverageRatioTTM" not in items and "symbol" not in items


def test_ttm_key_metrics_use_the_same_cards():
    items = facts(build("key_metrics_ttm", [{"symbol": "AAPL", "marketCap": 4.9e12, "returnOnEquityTTM": 1.37184, "returnOnAssetsTTM": 0.336398, "cashConversionCycleTTM": -35.3}])[0][0])
    assert items["returnOnEquityTTM"]["value"] == "137.18% of shareholders' equity (1.37184)" and items["returnOnAssetsTTM"]["value"] == "33.64% of total assets (0.336398)"
    assert items["cashConversionCycleTTM"]["format"] == "number" and items["marketCap"]["format"] in ("integer", "number")


def test_growth_cards_are_green_or_red_by_sign():
    items = facts(build_views("ratios_ttm", [{"symbol": "AAPL", "revenueGrowth": 0.1, "freeCashFlowGrowth": -0.1, "debtGrowth": 0.0}], "x")[0][0])
    assert (items["revenueGrowth"]["tone"], items["freeCashFlowGrowth"]["tone"], items["debtGrowth"]["tone"]) == ("positive", "negative", None)


def test_several_ttm_records_fall_back_to_a_table_and_everything_is_valid_json():
    views, _ = build("ratios_ttm", [*fx.RATIOS_TTM, *fx.RATIOS_TTM])
    assert [v["kind"] for v in views] == ["table"]
    for endpoint_id, payload in (("ratios", fx.RATIOS), ("key_metrics", fx.KEY_METRICS), ("financial_growth", fx.GROWTH), ("ratios_ttm", fx.RATIOS_TTM)):
        json.dumps(build(endpoint_id, payload)[0], allow_nan=False)


@pytest.mark.parametrize("payload", [None, [], {}, [{}], [{"date": "2026-01-01", "grossProfitMargin": "n/a"}], [{"fiscalYear": 2025, "grossProfitMargin": float("nan")}], [{"date": "x", "revenueGrowth": True}]])
@pytest.mark.parametrize("endpoint_id", ["ratios", "key_metrics", "financial_growth", "ratios_ttm", "key_metrics_ttm"])
def test_garbage_in_a_ratio_endpoint_never_raises(endpoint_id, payload):
    views, notes = build(endpoint_id, payload)
    assert isinstance(views, list) and isinstance(notes, list)
    json.dumps(views, allow_nan=False)
