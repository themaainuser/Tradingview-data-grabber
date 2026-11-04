"""The Finnhub catalog builder: plans from the spec's own premium marks, examples from the docs, parameters fixed where
the spec is wrong, and the committed catalog in the shape the provider serves."""

from __future__ import annotations

import json

from tradingview_data.providers import finnhub_docs as docs
from tradingview_data.providers.finnhub_docs import CATALOG_PATH, build_catalog, clean_html


def operation(op_id, section="Stock Fundamentals", premium=None, params=(), examples=(), free_tier=None, description="Does a thing.", summary=None):
    return {
        "operationId": op_id, "summary": summary or op_id.title(), "description": description, "urlId": op_id, "section": section, "premium": premium,
        "freeTier": free_tier, "parameters": list(params), "examples": [{"text": e} for e in examples],
    }


def p(name, required=False, type_="string", fmt=None, description=""):
    return {"in": "query", "name": name, "required": required, "type": type_, **({"format": fmt} if fmt else {}), "description": description}


SPEC = {
    "orders": ["/quote", "/company-news", "/stock/candle", "/stock/transcripts", "/stock/insider-transactions", "/indicator", "/stock/financials-reported"],
    "paths": {
        "/stock/candle": {"get": operation("stock-candles", "Stock Price", "Premium Access Required", [p("symbol", True), p("resolution", True, description="Supported resolution includes 1, 5, 15, 30, 60, D, W, M."), p("from", True, "integer", "int64", "UNIX timestamp."), p("to", True, "integer", "int64", "UNIX timestamp.")], ["/stock/candle?symbol=AAPL&resolution=D&from=1&to=2"])},
        "/quote": {"get": operation("quote", "Stock Price", None, [p("symbol", True)], ["/quote?symbol=AAPL", "/quote?symbol=RY.TO"], description="<p>Get real-time quote data for US stocks.</p><table><tr><td>noise</td></tr></table>")},
        "/company-news": {"get": operation("company-news", premium=None, params=[p("symbol", True), p("from", True, fmt="date"), p("to", True, fmt="date")], examples=["/company-news?symbol=AAPL&from=2025-05-15&to=2025-06-20"], free_tier="1 year of historical news and new updates")},
        "/stock/transcripts": {"get": operation("earnings-call-transcripts-api", "Alternative Data", "Premium required.", [p("id", True)], ["/stock/transcripts?id=AAPL_162777"])},
        "/stock/insider-transactions": {"get": operation("insider-transactions", params=[p("symbol", True), p("from", fmt="date")], examples=["/stock/insider-transactions?symbol=TSLA"])},
        "/indicator": {"get": operation("technical-indicator", "Technical Analysis", "Premium Access Required", [p("symbol", True), p("indicator", True), {"in": "query", "name": "indicator_fields", "description": "See the list."}], ["/indicator?symbol=symbol=AAPL&indicator=sma&timeperiod=3"])},
        "/stock/financials-reported": {"get": operation("financials-reported", params=[p("symbol"), p("freq", description="Frequency. Can be either annual or quarterly. Default to annual.")], examples=["/stock/financials-reported?symbol=AAPL"])},
        "/stock/revenue-breakdown2": {"get": operation("revenue-breakdown2", "Enterprise data", "Premium", [p("symbol", True)], ["/stock/revenue-breakdown2?symbol=AAPL"])},
        "/global-filings/search": {"post": operation("search", "Global Filings Search", "Premium Access Required")},
    },
}


def built():
    catalog = build_catalog(SPEC)
    return catalog, {e["id"]: e for e in catalog["endpoints"]}


def test_plans_come_from_the_specs_premium_marks_and_the_pricing_tables_exceptions():
    _, endpoints = built()
    assert (endpoints["quote"]["plan"], endpoints["quote"]["premium"]) == ("Free", False)
    assert (endpoints["stock_candles"]["plan"], endpoints["stock_candles"]["premium"]) == ("All-in-One", True)
    assert endpoints["earnings_call_transcripts_api"]["plan"] is None and endpoints["revenue_breakdown2"]["plan"] is None
    assert "sold separately" in endpoints["revenue_breakdown2"]["premium_notes"][0]


def test_endpoints_follow_the_docs_order_and_post_operations_are_left_out_with_a_warning():
    catalog, endpoints = built()
    assert list(endpoints)[:3] == ["quote", "company_news", "stock_candles"] and "search" not in endpoints
    assert "/global-filings/search has no GET operation (skipped)" in catalog["warnings"]
    assert [c["id"] for c in catalog["categories"]][:3] == ["stock-price", "stock-fundamentals", "alternative-data"]


def test_examples_are_finnhubs_with_recent_dates_where_the_free_window_needs_them():
    _, endpoints = built()
    news = endpoints["company_news"]
    assert news["examples"] == [{"caption": "Finnhub's example: symbol=AAPL, from=@week_ago, to=@day", "params": {"symbol": "AAPL", "from": "@week_ago", "to": "@day"}}]
    assert [p["example"] for p in news["params"]] == ["AAPL", "@week_ago", "@day"]
    assert "Free plan: 1 year of historical news and new updates." in news["premium_notes"]
    assert endpoints["quote"]["examples"][1]["caption"].endswith("(not US-listed: a free key is refused)")
    indicator = endpoints["technical_indicator"]
    assert indicator["examples"][0]["params"] == {"symbol": "AAPL", "indicator": "sma", "timeperiod": "3"}  # symbol=symbol=AAPL repaired
    assert [p["name"] for p in indicator["params"]] == ["symbol", "indicator", "timeperiod"]


def test_parameters_get_types_choices_and_the_specs_wrong_required_flags_fixed():
    _, endpoints = built()
    candle = {p["name"]: p for p in endpoints["stock_candles"]["params"]}
    assert candle["resolution"]["type"] == "enum" and candle["resolution"]["enum_labels"]["W"] == "Weekly"
    assert candle["from"]["type"] == "integer" and candle["from"]["minimum"] == 0
    assert next(p for p in endpoints["company_news"]["params"] if p["name"] == "from")["type"] == "date"
    assert next(p for p in endpoints["financials_reported"]["params"] if p["name"] == "freq")["enum"] == ["annual", "quarterly"]
    assert next(p for p in endpoints["insider_transactions"]["params"] if p["name"] == "symbol")["required"] is False


def test_descriptions_are_plain_text_without_tables():
    _, endpoints = built()
    assert endpoints["quote"]["description"] == "Get real-time quote data for US stocks."
    assert clean_html("<p>A &amp; B <code>x</code> .</p>") == "A & B x."
    long = clean_html("First sentence here. " + "word " * 400)
    assert long == "First sentence here." or long.endswith("\u2026")


def test_the_committed_catalog_has_what_the_provider_serves():
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    assert catalog["provider"] == "finnhub" and catalog["plans"] == list(docs.PLANS) and catalog["spec"] == docs.SPEC_URL
    keys = {"id", "path", "title", "category", "description", "doc_url", "plan", "premium", "trending", "utility", "premium_notes", "request_cost", "params", "examples"}
    assert all(set(e) == keys for e in catalog["endpoints"]) and len({e["id"] for e in catalog["endpoints"]}) == len(catalog["endpoints"])
    assert set(docs.TRENDING) | set(docs.UTILITY) <= {e["id"] for e in catalog["endpoints"]}
    assert {c["title"] for c in catalog["categories"]} == set(docs.CATEGORY_SUMMARIES)
