"""The documentation parser, on a small page shaped like Alpha Vantage's."""

from __future__ import annotations

import json

from tradingview_data.providers.alphavantage_docs import build_catalog, parse_documentation

PAGE = """
<h2 id="time-series-data">Time Series Stock Data APIs</h2>
<p>Core stock data.</p>
<h4 id="intraday">TIME_SERIES_INTRADAY <span class="popular-label">Trending</span> <span class="premium-label">Premium</span></h4>
<p>Intraday OHLCV. Premium keys can query the full history.</p>
<h6><b>API Parameters</b></h6>
<p><b>❚ Required: <code>function</code></b></p>
<p>The time series of your choice. In this case, <code>function=TIME_SERIES_INTRADAY</code></p>
<p><b>❚ Required: <code>symbol</code></b></p>
<p>The equity of your choice. For example: <code>symbol=IBM</code></p>
<p><b>❚ Required: <code>interval</code></b></p>
<p>Time interval. The following values are supported: <code>1min</code>, <code>5min</code>, <code>60min</code></p>
<p>❚ Optional: <code>adjusted</code></p>
<p>By default, <code>adjusted=true</code>. Set <code>adjusted=false</code> for raw data.</p>
<p>❚ Optional: <code>outputsize</code></p>
<p>By default, <code>outputsize=compact</code>. Strings <code>compact</code> and <code>full</code> are accepted. The "full" outputsize is available to premium keys.</p>
<p>❚ Optional: <code>entitlement</code></p>
<p>Freshness. Setting <code>entitlement=realtime</code> or <code>entitlement=delayed</code> changes it.</p>
<p><b>❚ Required: <code>apikey</code></b></p>
<p>Your API key.</p>
<h6><b>Examples (click for JSON output)</b></h6>
<i>Most recent 100 bars</i>
<p><a href="https://www.alphavantage.co/query?function=TIME_SERIES_INTRADAY&symbol=IBM&interval=5min&apikey=demo">link</a></p>
<h6><b>Language-specific guides</b></h6>
<h4 id="daily">TIME_SERIES_DAILY</h4>
<p>Daily bars.</p>
<h6><b>API Parameters</b></h6>
<p><b>❚ Required: <code>function</code></b></p>
<p>In this case, <code>function=TIME_SERIES_DAILY</code></p>
<p><b>❚ Required: <code>symbol</code></b></p>
<p>The equity. For example: <code>symbol=IBM</code></p>
<h6><b>Example (click for JSON output)</b></h6>
<p><a href="https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol=IBM&apikey=demo">link</a></p>
<h2 id="index-data">Index Data APIs</h2>
<h4 id="index-data-dow">Dow Jones <span class="premium-label">Premium</span></h4>
<p>Dow data.</p>
<h6><b>API Parameters</b></h6>
<p><b>❚ Required: <code>function</code></b></p>
<p>In this case, <code>function=INDEX_DATA</code></p>
<p><b>❚ Required: <code>symbol</code></b></p>
<p>Index symbol.</p>
<h6><b>Example</b></h6>
<p><a href="https://www.alphavantage.co/query?function=INDEX_DATA&symbol=DJI&apikey=demo">link</a></p>
<h4 id="index-data-sp500">S&amp;P 500 <span class="premium-label">Premium</span></h4>
<p>S&amp;P data.</p>
<h6><b>API Parameters</b></h6>
<p><b>❚ Required: <code>function</code></b></p>
<p>In this case, <code>function=INDEX_DATA</code></p>
<p><b>❚ Required: <code>symbol</code></b></p>
<p>Index symbol.</p>
<p>❚ Optional: <code>interval</code></p>
<p>Strings <code>daily</code> and <code>weekly</code> are accepted.</p>
<h6><b>Example</b></h6>
<p><a href="https://www.alphavantage.co/query?function=INDEX_DATA&symbol=SPX&interval=weekly&apikey=demo">link</a></p>
<h4 id="analytics">ANALYTICS_FIXED_WINDOW</h4>
<p>Analytics.</p>
<h6><b>API Parameters</b></h6>
<p><b>❚ Required: <code>function</code></b></p>
<p>In this case, <code>function=ANALYTICS_FIXED_WINDOW</code></p>
<p><b>❚ Required: <code>RANGE</code></b></p>
<p>Date range, for example <code>RANGE=2023-07-01&amp;RANGE=2023-08-31</code></p>
<h6><b>Example</b></h6>
<p><a href="https://www.alphavantage.co/query?function=ANALYTICS_FIXED_WINDOW&RANGE=2023-07-01&RANGE=2023-08-31&apikey=demo">link</a></p>
"""


def endpoints():
    parsed = parse_documentation(PAGE)
    return parsed, {e["function"]: e for e in parsed["endpoints"]}


def test_categories_and_endpoints_are_read_in_order_with_their_category():
    parsed, by_function = endpoints()
    assert [c["id"] for c in parsed["categories"]] == ["time-series-data", "index-data"]
    assert parsed["categories"][0]["summary"] == "Core stock data."
    assert by_function["TIME_SERIES_DAILY"]["category"] == "time-series-data" and by_function["INDEX_DATA"]["category"] == "index-data"
    assert parsed["warnings"] == []


def test_the_badges_become_flags():
    _, by_function = endpoints()
    intraday = by_function["TIME_SERIES_INTRADAY"]
    assert (intraday["premium"], intraday["trending"], intraday["utility"]) == (True, True, False)
    assert by_function["TIME_SERIES_DAILY"]["premium"] is False
    assert intraday["title"] == "TIME_SERIES_INTRADAY"  # the badge text is not part of the title


def test_parameters_required_optional_function_and_apikey_handling():
    _, by_function = endpoints()
    params = {p["name"]: p for p in by_function["TIME_SERIES_INTRADAY"]["params"]}
    assert set(params) == {"symbol", "interval", "adjusted", "outputsize", "entitlement"}  # function and apikey are not user inputs
    assert params["symbol"]["required"] and not params["adjusted"]["required"]
    assert params["symbol"]["example"] == "IBM"


def test_enums_are_strict_only_where_the_docs_state_the_accepted_values_and_hints_are_suggestions():
    _, by_function = endpoints()
    params = {p["name"]: p for p in by_function["TIME_SERIES_INTRADAY"]["params"]}
    assert params["interval"]["type"] == "enum" and params["interval"]["enum"] == ["1min", "5min", "60min"]
    assert params["outputsize"]["enum"] == ["compact", "full"] and params["outputsize"]["default"] == "compact"
    assert params["adjusted"]["type"] == "boolean" and params["adjusted"]["enum"] == ["true", "false"] and params["adjusted"]["default"] == "true"
    assert params["entitlement"]["enum"] == [] and params["entitlement"]["suggestions"] == ["realtime", "delayed"]


def test_a_premium_note_is_kept_on_the_parameter_it_describes():
    _, by_function = endpoints()
    params = {p["name"]: p for p in by_function["TIME_SERIES_INTRADAY"]["params"]}
    assert "premium keys" in params["outputsize"]["premium_note"] and params["symbol"]["premium_note"] is None


def test_examples_drop_the_key_and_repeated_parameters_become_lists():
    _, by_function = endpoints()
    assert by_function["TIME_SERIES_INTRADAY"]["examples"][0]["params"] == {"function": "TIME_SERIES_INTRADAY", "symbol": "IBM", "interval": "5min"}
    assert by_function["TIME_SERIES_INTRADAY"]["examples"][0]["caption"] == "Most recent 100 bars"
    analytics = by_function["ANALYTICS_FIXED_WINDOW"]
    assert analytics["examples"][0]["params"]["RANGE"] == ["2023-07-01", "2023-08-31"]
    assert next(p for p in analytics["params"] if p["name"] == "RANGE")["multiple"] is True
    assert "apikey" not in json.dumps(parse_documentation(PAGE)["endpoints"])


def test_a_function_documented_in_several_sections_becomes_one_endpoint():
    catalog = build_catalog(PAGE)
    index = [e for e in catalog["endpoints"] if e["function"] == "INDEX_DATA"]
    assert len(index) == 1 and index[0]["title"] == "Index Data" and index[0]["premium"] is True
    assert {p["name"] for p in index[0]["params"]} == {"symbol", "interval"}
    assert len(index[0]["examples"]) == 2
    assert [e["function"] for e in catalog["endpoints"]] == ["TIME_SERIES_INTRADAY", "TIME_SERIES_DAILY", "INDEX_DATA", "ANALYTICS_FIXED_WINDOW"]


def test_html_entities_are_decoded():
    _, by_function = endpoints()
    assert "S&P" in by_function["INDEX_DATA"]["description"] or "Dow" in by_function["INDEX_DATA"]["description"]
    assert "&amp;" not in json.dumps(parse_documentation(PAGE))


def test_a_section_with_no_function_is_skipped_with_a_warning():
    page = '<h2 id="x">Group</h2><h4 id="odd">Odd</h4><p>Nothing here.</p>'
    parsed = parse_documentation(page)
    assert parsed["endpoints"] == [] and "odd" in parsed["warnings"][0]
