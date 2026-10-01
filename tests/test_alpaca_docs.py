"""The Alpaca catalog generator: reading the embedded OpenAPI definitions, tier labels, examples, offline mode."""

from __future__ import annotations

import json
from datetime import date

import pytest

from tradingview_data.providers import alpaca_docs as docs


def definition(paths, parameters=None, schemas=None):
    return {"openapi": "3.1.2", "paths": paths, "components": {"parameters": parameters or {}, "schemas": schemas or {}}}


PARAMETERS = {
    "symbols": {"name": "symbols", "in": "query", "required": True, "description": "A comma-separated list of stock symbols.", "example": "AAPL,TSLA", "schema": {"type": "string"}},
    "timeframe": {"name": "timeframe", "in": "query", "required": True, "example": "1Min", "schema": {"type": "string"}},
    "start": {"name": "start", "in": "query", "schema": {"type": "string", "format": "date-time"}},
    "end": {"name": "end", "in": "query", "description": "The inclusive end. Default: now.", "schema": {"type": "string", "format": "date-time"}},
    "limit": {"name": "limit", "in": "query", "schema": {"type": "integer", "default": 1000, "minimum": 1, "maximum": 10000}},
    "feed": {"name": "feed", "in": "query", "description": "The source feed.\n - `sip`: everything\n - `iex`: one exchange", "schema": {"$ref": "#/components/schemas/feed"}},
    "sort": {"name": "sort", "in": "query", "schema": {"allOf": [{"type": "string"}, {"$ref": "#/components/schemas/sort"}]}},
    "symbol": {"name": "symbol", "in": "path", "required": True, "example": "AAPL", "schema": {"type": "string"}},
    "include": {"name": "include_content", "in": "query", "schema": {"type": "boolean", "default": False}},
    "asof": {"name": "asof", "in": "query", "schema": {"type": "string", "format": "date"}},
    "price": {"name": "strike_price_gte", "in": "query", "schema": {"type": "number", "format": "double"}},
}
SCHEMAS = {"feed": {"type": "string", "enum": ["iex", "otc", "sip", "boats"], "default": "sip"}, "sort": {"enum": ["asc", "desc"], "default": "asc"}}


def ref(name):
    return {"$ref": f"#/components/parameters/{name}"}


BARS = definition(
    {
        "/v2/stocks/bars": {
            "get": {
                "summary": "Historical bars",
                "description": "Bars for [the symbols](https://docs.example/symbols).\n\n> ⚠️ Warning\n>\n> **Careful** with `limit`.",
                "parameters": [ref(n) for n in ("symbols", "timeframe", "start", "end", "limit", "feed", "sort", "include", "asof", "price")] + [{"name": "APCA-API-KEY-ID", "in": "header", "schema": {"type": "string"}}],
            }
        }
    },
    PARAMETERS,
    SCHEMAS,
)
LATEST = definition({"/v2/stocks/{symbol}/trades/latest": {"get": {"summary": "Latest trade", "description": "The latest trade.", "parameters": [ref("symbol"), ref("feed")]}}}, PARAMETERS, {"feed": {"enum": ["iex", "sip"]}})
LOGO = definition({"/v1beta1/logos/{symbol}": {"get": {"summary": "Logos", "parameters": [ref("symbol")]}}}, PARAMETERS)


def endpoints(*pages):
    catalog = docs.build_catalog([(f"https://docs.alpaca.markets/us/reference/page{i}.md", spec) for i, spec in enumerate(pages)])
    return catalog, {e["id"]: e for e in catalog["endpoints"]}


def test_markdown_in_descriptions_becomes_plain_text():
    assert docs.clean_text("Bars for [the symbols](https://x.test/a). **Bold** and `code`.\n\n> ⚠️ Warning\n>\n> Careful.") == "Bars for the symbols. Bold and code. ⚠️ Warning Careful."
    assert docs.clean_text("See [this](#/components/schemas/x) ,  now ;") == "See this, now;"


def test_the_embedded_definition_is_found_and_bad_pages_are_refused():
    page = "# Title\n\nText\n\n# OpenAPI definition\n\n```json\n" + json.dumps(BARS) + "\n```\n"
    assert docs.definition_of(page)["paths"].keys() == BARS["paths"].keys()
    assert docs.definition_of("# Title\n\nno code here") is None
    assert docs.definition_of("```json\n{not json}\n```") is None
    assert docs.definition_of('```json\n{"info": {}}\n```') is None
    assert docs.definition_of("```json\n[1, 2]\n```") is None


def test_only_the_market_data_reference_pages_are_listed():
    index = "\n".join(
        [
            "# Alpaca US Documentation",
            "## Documentation: Market Data API",
            "- [About](https://docs.alpaca.markets/us/docs/about-market-data-api.md): text",
            "## API Reference: Trading API",
            "- [Orders](https://docs.alpaca.markets/us/reference/postorder.md): text",
            "## API Reference: Market Data API",
            "- [Historical bars](https://docs.alpaca.markets/us/reference/stockbars.md): The historical stock bars API",
            "  - [Nested](https://docs.alpaca.markets/us/reference/nested-1.md)",
            "- [Elsewhere](https://example.com/us/reference/other.md)",
            "## API Reference: Broker API",
            "- [Accounts](https://docs.alpaca.markets/us/reference/getaccounts.md)",
        ]
    )
    assert docs.reference_urls(index) == ["https://docs.alpaca.markets/us/reference/stockbars.md", "https://docs.alpaca.markets/us/reference/nested-1.md"]


def test_parameters_are_typed_from_their_schemas_with_references_and_allof_followed():
    catalog, found = endpoints(BARS)
    bars = found["stock_bars"]
    types = {p["name"]: p["type"] for p in bars["params"]}
    assert types == {"symbols": "text", "timeframe": "text", "start": "datetime", "end": "datetime", "limit": "integer", "feed": "enum", "sort": "enum", "include_content": "boolean", "asof": "date", "strike_price_gte": "number"}
    by_name = {p["name"]: p for p in bars["params"]}
    assert by_name["limit"]["default"] == "1000" and (by_name["limit"]["minimum"], by_name["limit"]["maximum"]) == (1, 10000)
    assert by_name["include_content"]["default"] == "false" and by_name["sort"]["enum"] == ["asc", "desc"] and by_name["sort"]["default"] == "asc"
    assert by_name["symbols"]["example"] == "AAPL,TSLA" and by_name["timeframe"]["example"] == "1Day"  # the page's own example is replaced for a better first chart
    assert "APCA-API-KEY-ID" not in by_name and all(p["multiple"] is False for p in bars["params"])
    assert bars["description"] == "Bars for the symbols. ⚠️ Warning Careful with limit."
    assert bars["doc_url"] == "https://docs.alpaca.markets/us/reference/page0" and bars["path"] == "/v2/stocks/bars"
    assert bars["plan"] == "Basic" and bars["premium"] is False
    assert catalog["plans"] == ["Basic", "Algo Trader Plus"] and [c["title"] for c in catalog["categories"]][:3] == ["Stocks", "Options", "Crypto"]
    assert [p["name"] for p in bars["params"]][:2] == ["symbols", "timeframe"]
    assert next(p for p in bars["params"] if p["name"] == "timeframe")["suggestions"][0] == "1Min"


def test_path_parameters_come_first_as_in_the_url():
    _, found = endpoints(LATEST)
    assert [p["name"] for p in found["stock_latest_trade_single"]["params"]] == ["symbol", "feed"]
    assert found["stock_latest_trade_single"]["params"][0]["in"] == "path"


def test_tier_rules_label_the_feed_and_the_end_of_the_range():
    _, found = endpoints(BARS, LATEST)
    history = {p["name"]: p for p in found["stock_bars"]["params"]}
    assert history["feed"]["premium_values"] == ["otc"] and history["feed"]["enum_labels"]["iex"] == "IEX · Basic" and history["feed"]["default"] == "sip"
    assert history["end"]["premium_note"] == docs.HISTORY_END_NOTE and history["start"]["premium_note"] is None
    latest = {p["name"]: p for p in found["stock_latest_trade_single"]["params"]}
    assert latest["feed"]["premium_values"] == ["sip"]  # otc is not offered by this definition, so it is not listed
    assert latest["feed"]["enum_labels"]["sip"] == "SIP, all US exchanges · Algo Trader Plus"
    assert found["stock_latest_trade_single"]["premium_notes"] == docs._TIER_NOTES["stock_latest"] and found["stock_bars"]["tier_rule"] == "stock_history"


def test_documented_bullets_label_enum_choices_unless_a_tier_label_replaces_them():
    parameters = {"loc": {"name": "loc", "in": "path", "required": True, "description": "Where from.\n - us: Alpaca US\n - `eu-1`: Kraken EU\n - bs-1: a very long explanation that does not fit in a dropdown at all, really", "schema": {"type": "string", "enum": ["us", "eu-1", "bs-1"]}}}
    spec = definition({"/v1beta3/crypto/{loc}/latest/bars": {"get": {"summary": "Latest", "parameters": [ref("loc")]}}}, parameters)
    _, found = endpoints(spec)
    loc = found["crypto_latest_bars"]["params"][0]
    assert loc["enum_labels"] == {"us": "Alpaca US", "eu-1": "Kraken EU"}
    assert loc["description"] == "Where from."  # the bullets became the dropdown labels, so they are not repeated as text


def test_stock_feeds_are_offered_in_a_readable_order_not_the_alphabetical_one_the_api_lists():
    parameters = {**PARAMETERS, "feed": {"name": "feed", "in": "query", "schema": {"enum": ["delayed_sip", "iex", "otc", "sip", "boats", "overnight"]}}}
    spec = definition({"/v2/stocks/quotes/latest": {"get": {"summary": "Latest quotes", "parameters": [ref("symbols"), ref("feed")]}}}, parameters)
    _, found = endpoints(spec)
    feed = next(p for p in found["stock_latest_quotes"]["params"] if p["name"] == "feed")
    assert feed["enum"] == ["iex", "sip", "delayed_sip", "boats", "overnight", "otc"] and feed["premium_values"] == ["sip", "otc"]


def test_examples_are_complete_requests_with_a_sample_period_for_bars():
    _, found = endpoints(BARS, LATEST)
    bars = found["stock_bars"]["examples"]
    assert bars[0] == {"caption": "1Day bars for the last month", "params": {"symbols": "AAPL", "timeframe": "1Day", "start": docs.SAMPLE_START, "end": docs.SAMPLE_DAY}}
    assert bars[1]["params"] == {"symbols": "AAPL", "timeframe": "1Day"}
    assert found["stock_latest_trade_single"]["examples"] == [{"caption": "Required parameters only: symbol=AAPL", "params": {"symbol": "AAPL"}}]


def test_no_example_is_offered_when_a_required_value_is_unknown_or_known_to_have_expired():
    spec = definition({"/v1beta1/options/bars": {"get": {"summary": "Bars", "parameters": [ref("symbols"), ref("timeframe")]}}, "/v1beta1/news": {"get": {"summary": "News", "parameters": [{"name": "symbols", "in": "query", "required": True, "schema": {"type": "string"}}]}}}, PARAMETERS)
    _, found = endpoints(spec)
    assert found["option_bars"]["examples"] == [] and found["news"]["examples"] == []
    assert found["option_bars"]["params"][0]["example"] == "AAPL,TSLA"  # still shown as the placeholder


def test_operations_that_cannot_be_a_request_and_an_answer_are_left_out_without_a_warning():
    catalog, found = endpoints(BARS, LOGO)
    assert list(found) == ["stock_bars"] and catalog["warnings"][0].endswith("no longer in the documentation")
    assert {s["path"] for s in catalog["skipped"]} == {"/v1beta1/logos/{symbol}", "/v1beta1/events/corporate-actions"}
    assert not any("logos" in w for w in catalog["warnings"])


def test_a_documented_path_without_an_entry_is_reported_and_so_is_one_that_went_away():
    unknown = definition({"/v9/brand-new": {"get": {"summary": "New", "parameters": []}}})
    catalog, found = endpoints(BARS, unknown)
    assert list(found) == ["stock_bars"]
    assert "/v9/brand-new is in the documentation but has no entry in OPERATIONS (skipped)" in catalog["warnings"]
    assert sum(1 for w in catalog["warnings"] if w.endswith("no longer in the documentation")) == len(docs.OPERATIONS) - 1


def test_endpoints_keep_the_order_of_the_operations_table_whatever_order_the_pages_came_in():
    _, found = endpoints(LATEST, BARS)
    assert list(found) == ["stock_bars", "stock_latest_trade_single"]


def test_the_sample_period_is_a_recent_weekday_and_a_month_before_it():
    assert docs.sample_day(date(2026, 9, 30)) == "2026-09-29" and docs.sample_start(date(2026, 9, 30)) == "2026-08-30"
    assert docs.sample_day(date(2026, 9, 28)) == "2026-09-25"  # Monday -> the Friday before
    assert docs.sample_day(date(2026, 9, 27)) == "2026-09-25"  # Sunday
    nested = {"a": [docs.SAMPLE_DAY, {"b": docs.SAMPLE_START}], "n": 3}
    assert docs.fill_samples(nested, date(2026, 9, 30)) == {"a": ["2026-09-29", {"b": "2026-08-30"}], "n": 3}


def test_running_the_generator_from_saved_pages_writes_the_catalog(tmp_path, capsys):
    pages = tmp_path / "pages"
    pages.mkdir()
    (pages / "stockbars.md").write_text("# Bars\n\n```json\n" + json.dumps(BARS) + "\n```\n", encoding="utf-8")
    (pages / "empty.md").write_text("# No definition here\n", encoding="utf-8")
    output = tmp_path / "catalog.json"
    assert docs.main(["--pages", str(pages), "--output", str(output)]) == 0
    catalog = json.loads(output.read_text(encoding="utf-8"))
    assert [e["id"] for e in catalog["endpoints"]] == ["stock_bars"] and catalog["endpoints"][0]["doc_url"].endswith("/us/reference/stockbars")
    captured = capsys.readouterr()
    assert "1 endpoints from 1 pages" in captured.out and "no OpenAPI definition in" in captured.err


def test_the_committed_catalog_matches_the_operations_table():
    committed = json.loads(docs.CATALOG_PATH.read_text(encoding="utf-8"))
    assert [e["path"] for e in committed["endpoints"]] == list(docs.OPERATIONS)
    assert committed["warnings"] == [] and committed["plans"] == list(docs.PLANS)
    assert all(e["id"] == docs.OPERATIONS[e["path"]][0] and e["tier_rule"] == docs.OPERATIONS[e["path"]][3] for e in committed["endpoints"])
    assert {e["category"] for e in committed["endpoints"]} == {c["id"] for c in committed["categories"]}


@pytest.mark.parametrize("rule", ["stock_latest", "stock_history", "option_latest", "option_history"])
def test_every_tier_rule_has_a_plain_language_note(rule):
    assert rule in docs._TIER_NOTES and "Basic" in docs._TIER_NOTES[rule][0] and "Algo Trader Plus" in docs._TIER_NOTES[rule][0]
