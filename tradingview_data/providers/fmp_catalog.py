"""The Financial Modeling Prep (FMP) endpoint catalog, written by hand from the stable API documentation.

Unlike Alpha Vantage and Marketstack, FMP publishes no machine-readable spec: its documentation
pages list an endpoint and an example request but not the parameters. The table below therefore
holds each endpoint's path and parameters directly, and every path was checked against the live API.
Endpoints that differ only by a path segment (the price-history variants, the intraday intervals, the
technical indicators) are one endpoint with that segment as an ``enum`` parameter.

FMP does not say which subscription plan an endpoint needs either. ``Basic`` (the free plan) was
verified by calling every endpoint with a free key: a refusal is HTTP 402. The paid tier of a refused
endpoint follows the feature groups on https://site.financialmodelingprep.com/pricing-plans and is
only a lower bound: the API is the authority, and a key whose plan lacks an endpoint is refused and
reported as premium.

Not covered: the bulk CSV downloads, partner endpoints and the 10-K workbook download, which return
files rather than JSON, and (to keep the table checkable against a free key's daily quota) government
trading, ESG, Commitment of Traders, fundraisers, the as-reported statements, the statement-growth
variants and the 13F endpoints beyond the first four.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Optional

DOCS_ROOT = "https://site.financialmodelingprep.com/developer/docs/stable/"
PLAN_NAMES = ("Basic", "Starter", "Premium", "Ultimate")

# Placeholders for examples that need a recent date; replaced when the catalog is served so an
# example never ages out.
DAY, WEEK_AGO, MONTH_AGO, YEAR_AGO, WEEK_AHEAD = "@day", "@week_ago", "@month_ago", "@year_ago", "@week_ahead"


def sample_day(today: date) -> date:
    """The latest weekday before ``today``: a day the exchanges were normally open."""

    day = today - timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def fill_dates(value: Any, today: date) -> Any:
    """``value`` (any nesting of lists, dicts and strings) with the date placeholders replaced."""

    if isinstance(value, str):
        if "@" not in value:
            return value
        day = sample_day(today)
        for token, moment in ((DAY, day), (WEEK_AGO, day - timedelta(days=7)), (MONTH_AGO, day - timedelta(days=30)), (YEAR_AGO, day - timedelta(days=365)), (WEEK_AHEAD, today + timedelta(days=7))):
            value = value.replace(token, moment.isoformat())
        return value
    if isinstance(value, list):
        return [fill_dates(v, today) for v in value]
    if isinstance(value, dict):
        return {k: fill_dates(v, today) for k, v in value.items()}
    return value


CATEGORIES: list[dict[str, str]] = [
    {"id": "search", "title": "Search", "summary": "Find symbols by ticker, company name, CIK, CUSIP or ISIN, and screen the market with filters."},
    {"id": "directory", "title": "Directory", "summary": "Lists of symbols, exchanges, sectors, industries and countries FMP covers."},
    {"id": "company", "title": "Company", "summary": "Company profiles, peers, executives, market capitalisation, share float and mergers."},
    {"id": "quote", "title": "Quote", "summary": "Real-time quotes, aftermarket trades and price changes for stocks, ETFs, indices, forex, crypto and commodities."},
    {"id": "statements", "title": "Financial statements", "summary": "Income statements, balance sheets, cash flows, key metrics, ratios, growth and revenue segments."},
    {"id": "chart", "title": "Charts", "summary": "End-of-day and intraday price history."},
    {"id": "technical-indicators", "title": "Technical indicators", "summary": "Moving averages, RSI, ADX, Williams %R and standard deviation computed by FMP."},
    {"id": "analyst", "title": "Analyst", "summary": "Analyst estimates, ratings, price targets and rating changes."},
    {"id": "calendar", "title": "Calendars", "summary": "Dividends, earnings, IPOs and stock splits, per company and market-wide."},
    {"id": "economics", "title": "Economics", "summary": "Treasury rates, economic indicators, the economic calendar and the market risk premium."},
    {"id": "market-performance", "title": "Market performance", "summary": "Sector and industry performance and valuation, plus the biggest gainers, losers and most active stocks."},
    {"id": "news", "title": "News", "summary": "Stock, crypto, forex and general news, press releases and FMP's own articles."},
    {"id": "transcripts", "title": "Earnings transcripts", "summary": "Earnings call transcripts by company, year and quarter."},
    {"id": "etf-funds", "title": "ETFs and funds", "summary": "ETF holdings, exposure and weightings, and mutual fund disclosures."},
    {"id": "institutional", "title": "Institutional ownership", "summary": "Form 13F filings: what institutions hold and how their positions changed."},
    {"id": "insider", "title": "Insider trades", "summary": "Insider transactions, their statistics and beneficial ownership filings."},
    {"id": "sec-filings", "title": "SEC filings", "summary": "Latest and searchable SEC filings, company filing profiles and industry classification codes."},
    {"id": "indexes", "title": "Indexes", "summary": "Market indices and the current and historical members of the S&P 500, Nasdaq and Dow Jones."},
    {"id": "markets", "title": "Markets", "summary": "Exchange trading hours and holidays, and the forex, crypto and commodity symbol lists."},
    {"id": "valuation", "title": "Discounted cash flow", "summary": "Discounted cash flow valuations, unlevered and levered."},
]


def param(
    name: str,
    description: str,
    kind: str = "text",
    *,
    required: bool = False,
    where: str = "query",
    enum: tuple[str, ...] = (),
    premium_values: tuple[str, ...] = (),
    premium_note: Optional[str] = None,
    example: Optional[str] = None,
    default: Optional[str] = None,
    suggestions: tuple[str, ...] = (),
    minimum: Optional[float] = None,
    maximum: Optional[float] = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "in": where,
        "required": required or where == "path",
        "type": "enum" if enum else kind,
        "description": description,
        "enum": list(enum),
        "enum_labels": {},
        "suggestions": list(suggestions),
        "default": default,
        "example": example,
        "multiple": False,
        "premium_note": premium_note,
        "premium_values": list(premium_values),
        "minimum": minimum,
        "maximum": maximum,
    }


def _symbol(description: str = "Ticker symbol.", example: str = "AAPL") -> dict[str, Any]:
    return param("symbol", description, required=True, example=example)


def _symbols(description: str = "Comma-separated ticker symbols.", example: str = "AAPL,MSFT") -> dict[str, Any]:
    return param("symbols", description, required=True, example=example)


def _limit(description: str = "Maximum number of rows to return.", example: Optional[str] = None, maximum: Optional[float] = None) -> dict[str, Any]:
    return param("limit", description, "integer", example=example, minimum=1, maximum=maximum)


def _page(description: str = "Page number, starting at 0.") -> dict[str, Any]:
    return param("page", description, "integer", minimum=0)


def _from(description: str = "Start date, YYYY-MM-DD.", example: Optional[str] = None, required: bool = False) -> dict[str, Any]:
    return param("from", description, "date", example=example, required=required)


def _to(description: str = "End date, YYYY-MM-DD.", example: Optional[str] = None, required: bool = False) -> dict[str, Any]:
    return param("to", description, "date", example=example, required=required)


def _period(description: str = "Annual or quarterly figures.") -> dict[str, Any]:
    return param("period", description, enum=("annual", "quarter"), default="annual")


def _short(description: str = "Return the short form of each quote (symbol, price, change and volume only).") -> dict[str, Any]:
    return param("short", description, "boolean")


def _year(description: str = "Year.", required: bool = False, example: Optional[str] = None) -> dict[str, Any]:
    return param("year", description, "integer", required=required, example=example, minimum=1900, maximum=2100)


def _quarter(required: bool = False, example: Optional[str] = None) -> dict[str, Any]:
    return param("quarter", "Fiscal quarter.", enum=("1", "2", "3", "4"), required=required, example=example)


def _cik(description: str = "SEC Central Index Key.", required: bool = True, example: Optional[str] = "0000320193") -> dict[str, Any]:
    return param("cik", description, required=required, example=example)


def _dated(description: str, example_day: str = DAY) -> dict[str, Any]:
    return param("date", description, "date", required=True, example=example_day)


def _exchange(description: str = "Exchange code, for example NASDAQ or NYSE.", required: bool = False, example: Optional[str] = None) -> dict[str, Any]:
    return param("exchange", description, required=required, example=example, suggestions=("NASDAQ", "NYSE", "AMEX", "LSE", "TSX", "XETRA"))


def _example(caption: str, **params: str) -> dict[str, Any]:
    return {"caption": caption, "params": params}


ENDPOINTS: list[dict[str, Any]] = []


def endpoint(
    id_: str,
    path: str,
    category: str,
    title: str,
    description: str,
    params: tuple[dict[str, Any], ...] = (),
    *,
    slug: str,
    examples: tuple[dict[str, Any], ...] = (),
    trending: bool = False,
    utility: bool = False,
) -> None:
    base = {p["name"]: (p["example"] or p["default"]) for p in params if p["required"] or p["in"] == "path"}
    first = []
    if all(v is not None for v in base.values()):
        caption = "Required parameters only" if base else "No parameters"
        first = [{"caption": f"{caption}: " + ", ".join(f"{k}={v}" for k, v in base.items()) if base else caption, "params": base}]
    dates = {p["name"]: p["example"] for p in params if p["type"] == "date" and not p["required"] and p["example"]}
    if dates and len(first) == 1 and not any(set(dates) <= set(e["params"]) for e in examples):
        first.append({"caption": "With a date range: " + ", ".join(f"{k}={v}" for k, v in dates.items()), "params": {**base, **dates}})
    ENDPOINTS.append(
        {
            "id": id_,
            "path": path,
            "category": category,
            "title": title,
            "description": description,
            "params": list(params),
            "examples": [*first, *examples],
            "slug": slug,
            "trending": trending,
            "utility": utility,
        }
    )


# --- search -------------------------------------------------------------------------------------------

endpoint("search_symbol", "/search-symbol", "search", "Search by symbol", "Finds symbols and companies whose ticker matches a query, across stocks, ETFs and other instruments.", (param("query", "Part of a ticker symbol.", required=True, example="AAPL"), _limit(maximum=None), _exchange()), slug="search-symbol", trending=True)
endpoint("search_name", "/search-name", "search", "Search by company name", "Finds symbols and companies whose name matches a query.", (param("query", "Part of a company name.", required=True, example="Apple"), _limit(), _exchange()), slug="search-name", trending=True)
endpoint("search_cik", "/search-cik", "search", "Search by CIK", "Looks up companies by SEC Central Index Key.", (_cik(example="320193"), _limit()), slug="search-cik")
endpoint("search_cusip", "/search-cusip", "search", "Search by CUSIP", "Looks up a security by its CUSIP identifier.", (param("cusip", "CUSIP identifier.", required=True, example="037833100"),), slug="search-cusip")
endpoint("search_isin", "/search-isin", "search", "Search by ISIN", "Looks up a security by its ISIN identifier.", (param("isin", "ISIN identifier.", required=True, example="US0378331005"),), slug="search-isin")
endpoint(
    "company_screener",
    "/company-screener",
    "search",
    "Stock screener",
    "Filters the market by market capitalisation, price, beta, dividend, volume, sector, industry, exchange and country.",
    (
        param("marketCapMoreThan", "Minimum market capitalisation, in dollars.", "number", example="1000000000"),
        param("marketCapLowerThan", "Maximum market capitalisation, in dollars.", "number"),
        param("sector", "Sector name, for example Technology.", suggestions=("Technology", "Healthcare", "Financial Services", "Energy", "Consumer Cyclical", "Industrials", "Utilities", "Real Estate", "Basic Materials", "Communication Services", "Consumer Defensive")),
        param("industry", "Industry name, for example Consumer Electronics."),
        param("betaMoreThan", "Minimum beta.", "number"),
        param("betaLowerThan", "Maximum beta.", "number"),
        param("priceMoreThan", "Minimum share price.", "number"),
        param("priceLowerThan", "Maximum share price.", "number"),
        param("dividendMoreThan", "Minimum annual dividend per share.", "number"),
        param("dividendLowerThan", "Maximum annual dividend per share.", "number"),
        param("volumeMoreThan", "Minimum trading volume.", "number"),
        param("volumeLowerThan", "Maximum trading volume.", "number"),
        _exchange(),
        param("country", "Two-letter country code, for example US."),
        param("isEtf", "Only ETFs (true) or no ETFs (false).", "boolean"),
        param("isFund", "Only funds (true) or no funds (false).", "boolean"),
        param("isActivelyTrading", "Only actively trading (true) or not (false) securities.", "boolean"),
        param("includeAllShareClasses", "Include every share class of a company.", "boolean"),
        _limit(),
    ),
    slug="search-company-screener",
    examples=(_example("Large technology companies on Nasdaq", marketCapMoreThan="1000000000", sector="Technology", exchange="NASDAQ", limit="10"),),
    trending=True,
)
endpoint("search_exchange_variants", "/search-exchange-variants", "search", "Exchange variants", "Lists every exchange a company's stock is listed on, with the symbol used on each.", (_symbol(),), slug="search-exchange-variants")

# --- directory ----------------------------------------------------------------------------------------

endpoint("stock_list", "/stock-list", "directory", "Stock list", "Every stock symbol FMP covers, with its company name.", slug="company-symbols-list", utility=True)
endpoint("financial_statement_symbols", "/financial-statement-symbol-list", "directory", "Symbols with financial statements", "Symbols FMP has financial statements for, with their reporting currency and fiscal-year window.", slug="financial-symbols-list", utility=True)
endpoint("cik_list", "/cik-list", "directory", "CIK list", "Companies with their SEC Central Index Keys.", (_page(), _limit()), slug="cik-list", utility=True)
endpoint("symbol_changes", "/symbol-change", "directory", "Symbol changes", "Ticker symbol changes caused by mergers, acquisitions, splits and name changes.", (param("invalid", "Include changes that were later invalidated.", "boolean"), _limit()), slug="symbol-changes-list", utility=True)
endpoint("etf_list", "/etf-list", "directory", "ETF list", "Every ETF symbol FMP covers, with its name.", slug="etfs-list", utility=True)
endpoint("actively_trading", "/actively-trading-list", "directory", "Actively trading list", "Symbols that are currently trading, with their names and exchanges.", slug="actively-trading-list", utility=True)
endpoint("available_exchanges", "/available-exchanges", "directory", "Available exchanges", "Exchanges FMP covers, with their codes, countries and currencies.", slug="available-exchanges", utility=True)
endpoint("available_sectors", "/available-sectors", "directory", "Available sectors", "Sector names, as accepted by the screener and the sector endpoints.", slug="available-sectors", utility=True)
endpoint("available_industries", "/available-industries", "directory", "Available industries", "Industry names, as accepted by the screener and the industry endpoints.", slug="available-industries", utility=True)
endpoint("available_countries", "/available-countries", "directory", "Available countries", "Country codes, as accepted by the screener.", slug="available-countries", utility=True)

# --- company ------------------------------------------------------------------------------------------

endpoint("profile", "/profile", "company", "Company profile", "A company's profile: price, market capitalisation, sector, industry, description, headquarters, employees and identifiers.", (_symbol(),), slug="profile-symbol", trending=True, examples=(_example("Microsoft", symbol="MSFT"),))
endpoint("profile_cik", "/profile-cik", "company", "Company profile by CIK", "A company's profile looked up by SEC Central Index Key.", (_cik(),), slug="profile-cik")
endpoint("company_notes", "/company-notes", "company", "Company notes", "The notes (debt securities) a company has issued, with their CIK and exchange.", (_symbol(),), slug="company-notes")
endpoint("stock_peers", "/stock-peers", "company", "Stock peers", "Companies similar to a stock by sector, industry and market capitalisation.", (_symbol(),), slug="peers")
endpoint("delisted_companies", "/delisted-companies", "company", "Delisted companies", "Companies that were delisted, with their exchange and delisting date.", (_page(), _limit()), slug="delisted-companies")
endpoint("employee_count", "/employee-count", "company", "Employee count", "The number of employees a company reported in its filings.", (_symbol(), _limit()), slug="employee-count")
endpoint("historical_employee_count", "/historical-employee-count", "company", "Historical employee count", "A company's reported employee count over time.", (_symbol(), _limit()), slug="historical-employee-count")
endpoint("market_cap", "/market-capitalization", "company", "Market capitalisation", "The current market capitalisation of a company.", (_symbol(),), slug="market-cap")
endpoint("batch_market_cap", "/market-capitalization-batch", "company", "Market capitalisation, several symbols", "The current market capitalisation of several companies in one request.", (_symbols(),), slug="batch-market-cap")
endpoint("historical_market_cap", "/historical-market-capitalization", "company", "Historical market capitalisation", "A company's market capitalisation over time.", (_symbol(), _limit(), _from(example=YEAR_AGO), _to(example=DAY)), slug="historical-market-cap")
endpoint("shares_float", "/shares-float", "company", "Share float", "The shares a company has outstanding and freely tradable.", (_symbol(),), slug="shares-float")
endpoint("shares_float_all", "/shares-float-all", "company", "Share float, all companies", "Share float for every company, page by page.", (_page(), _limit()), slug="all-shares-float")
endpoint("latest_mergers", "/mergers-acquisitions-latest", "company", "Latest mergers and acquisitions", "The most recently announced mergers and acquisitions.", (_page(), _limit()), slug="latest-mergers-acquisitions")
endpoint("search_mergers", "/mergers-acquisitions-search", "company", "Search mergers and acquisitions", "Mergers and acquisitions that involve a company, found by name.", (param("name", "Company name.", required=True, example="Apple"),), slug="search-mergers-acquisitions")
endpoint("key_executives", "/key-executives", "company", "Key executives", "A company's executives with their titles, pay and when they started.", (_symbol(), param("active", "Only current (true) or former (false) executives.", "boolean")), slug="company-executives")
endpoint("executive_compensation", "/governance-executive-compensation", "company", "Executive compensation", "What a company paid its executives, from its proxy filings.", (_symbol(),), slug="executive-compensation")
endpoint("executive_compensation_benchmark", "/executive-compensation-benchmark", "company", "Executive compensation benchmark", "Average executive pay by industry for a year.", (_year(example="2024"),), slug="executive-compensation-benchmark")

# --- quote --------------------------------------------------------------------------------------------

_QUOTE_EXAMPLES = (
    _example("Microsoft", symbol="MSFT"),
    _example("S&P 500 index", symbol="^GSPC"),
    _example("EUR/USD", symbol="EURUSD"),
    _example("Bitcoin", symbol="BTCUSD"),
    _example("Gold", symbol="GCUSD"),
)
endpoint("quote", "/quote", "quote", "Stock quote", "A real-time quote: price, change, day and year range, volume, moving averages and market capitalisation. Works for stocks, ETFs, indices (^GSPC), forex (EURUSD), crypto (BTCUSD) and commodities (GCUSD).", (_symbol("Symbol of a stock, ETF, index, currency pair, cryptocurrency or commodity."),), slug="quote", trending=True, examples=_QUOTE_EXAMPLES)
endpoint("quote_short", "/quote-short", "quote", "Stock quote, short", "Price, change and volume only.", (_symbol("Symbol of a stock, ETF, index, currency pair, cryptocurrency or commodity."),), slug="quote-short", examples=_QUOTE_EXAMPLES[:2])
endpoint("aftermarket_trade", "/aftermarket-trade", "quote", "Aftermarket trade", "The latest trade made outside regular trading hours.", (_symbol(),), slug="aftermarket-trade")
endpoint("aftermarket_quote", "/aftermarket-quote", "quote", "Aftermarket quote", "The latest bid and ask outside regular trading hours.", (_symbol(),), slug="aftermarket-quote")
endpoint("price_change", "/stock-price-change", "quote", "Price change", "Price change over 1 day, 5 days, 1, 3 and 6 months, year to date and 1, 3, 5 and 10 years.", (_symbol(),), slug="quote-change", trending=True)
endpoint("batch_quote", "/batch-quote", "quote", "Batch quote", "Full quotes for several symbols in one request.", (_symbols(),), slug="batch-quote")
endpoint("batch_quote_short", "/batch-quote-short", "quote", "Batch quote, short", "Price, change and volume for several symbols in one request.", (_symbols(),), slug="batch-quote-short")
endpoint("exchange_quotes", "/batch-exchange-quote", "quote", "Quotes for an exchange", "Quotes for every symbol on an exchange.", (_exchange(required=True, example="NASDAQ"), _short()), slug="full-exchange-quotes")
endpoint("etf_quotes", "/batch-etf-quotes", "quote", "ETF quotes", "Quotes for every ETF.", (_short(),), slug="full-etf-quotes")
endpoint("commodity_quotes", "/batch-commodity-quotes", "quote", "Commodity quotes", "Quotes for every commodity.", (_short(),), slug="full-commodities-quotes")
endpoint("crypto_quotes", "/batch-crypto-quotes", "quote", "Cryptocurrency quotes", "Quotes for every cryptocurrency.", (_short(),), slug="full-cryptocurrency-quotes")
endpoint("forex_quotes", "/batch-forex-quotes", "quote", "Forex quotes", "Quotes for every currency pair.", (_short(),), slug="full-forex-quotes")
endpoint("index_quotes", "/batch-index-quotes", "quote", "Index quotes", "Quotes for every market index.", (_short(),), slug="full-index-quotes")

# --- financial statements ---------------------------------------------------------------------------------

_STATEMENT = (_symbol(), param("limit", "Number of periods to return, most recent first.", "integer", example="5", minimum=1, premium_note="Basic keys accept a limit of at most 5."), _period())
_TTM = (_symbol(), _limit("Number of periods to return.", example="1"))
endpoint("income_statement", "/income-statement", "statements", "Income statement", "Revenue, costs, operating income, net income and earnings per share for each fiscal period.", _STATEMENT, slug="income-statement", trending=True)
endpoint("balance_sheet", "/balance-sheet-statement", "statements", "Balance sheet", "Assets, liabilities and equity for each fiscal period.", _STATEMENT, slug="balance-sheet-statement", trending=True)
endpoint("cash_flow", "/cash-flow-statement", "statements", "Cash flow statement", "Operating, investing and financing cash flows and free cash flow for each fiscal period.", _STATEMENT, slug="cashflow-statement", trending=True)
endpoint("latest_financial_statements", "/latest-financial-statements", "statements", "Latest financial statements", "The most recently filed statements across all companies.", (_page(), _limit()), slug="latest-financial-statements")
endpoint("income_statement_ttm", "/income-statement-ttm", "statements", "Income statement, trailing twelve months", "The income statement summed over the last four quarters.", _TTM, slug="income-statements-ttm")
endpoint("balance_sheet_ttm", "/balance-sheet-statement-ttm", "statements", "Balance sheet, trailing twelve months", "The balance sheet as of the latest quarter.", _TTM, slug="balance-sheet-statements-ttm")
endpoint("cash_flow_ttm", "/cash-flow-statement-ttm", "statements", "Cash flow, trailing twelve months", "The cash flow statement summed over the last four quarters.", _TTM, slug="cashflow-statements-ttm")
endpoint("key_metrics", "/key-metrics", "statements", "Key metrics", "Enterprise value, margins, return on capital, working capital, per-share values and yields for each fiscal period.", _STATEMENT, slug="key-metrics", trending=True)
endpoint("ratios", "/ratios", "statements", "Financial ratios", "Profitability, liquidity, leverage, efficiency and valuation ratios for each fiscal period.", _STATEMENT, slug="metrics-ratios", trending=True)
endpoint("key_metrics_ttm", "/key-metrics-ttm", "statements", "Key metrics, trailing twelve months", "Key metrics over the last four quarters.", (_symbol(),), slug="key-metrics-ttm")
endpoint("ratios_ttm", "/ratios-ttm", "statements", "Financial ratios, trailing twelve months", "Financial ratios over the last four quarters.", (_symbol(),), slug="metrics-ratios-ttm")
endpoint("financial_scores", "/financial-scores", "statements", "Financial scores", "Altman Z-score and Piotroski score, with the inputs behind them.", (_symbol(),), slug="financial-scores")
endpoint("owner_earnings", "/owner-earnings", "statements", "Owner earnings", "Net income adjusted for depreciation and maintenance capital spending, per period.", (_symbol(), _limit()), slug="owner-earnings")
endpoint("enterprise_values", "/enterprise-values", "statements", "Enterprise value", "Market capitalisation, debt, cash and the resulting enterprise value per period.", _STATEMENT, slug="enterprise-values")
endpoint("financial_growth", "/financial-growth", "statements", "Financial growth", "Growth of revenue, profit, cash flow, assets and per-share values, per period.", _STATEMENT, slug="financial-statement-growth")
endpoint("financial_reports_dates", "/financial-reports-dates", "statements", "Financial report dates", "The fiscal years and periods a company has full reports for.", (_symbol(),), slug="financial-reports-dates")
endpoint("revenue_product_segmentation", "/revenue-product-segmentation", "statements", "Revenue by product", "Revenue split by product or service line.", (_symbol(), _period(), param("structure", "Layout of the response.", enum=("flat",), default="flat")), slug="revenue-product-segmentation")
endpoint("revenue_geographic_segmentation", "/revenue-geographic-segmentation", "statements", "Revenue by region", "Revenue split by geographic region.", (_symbol(), _period(), param("structure", "Layout of the response.", enum=("flat",), default="flat")), slug="revenue-geographic-segments")

# --- charts ------------------------------------------------------------------------------------------------

endpoint(
    "historical_eod",
    "/historical-price-eod/{variant}",
    "chart",
    "End-of-day prices",
    "Daily prices for a stock, ETF, index, currency pair, cryptocurrency or commodity. The variant sets what is returned: close and volume only (light), full OHLC with change and VWAP, prices not adjusted for splits, or prices adjusted for dividends. Without from and to, FMP returns the history your plan allows.",
    (
        param("variant", "What to return: close and volume (light), full OHLCV with change and VWAP (full), prices not adjusted for splits (non-split-adjusted) or adjusted for dividends too (dividend-adjusted).", where="path", enum=("full", "light", "non-split-adjusted", "dividend-adjusted"), default="full"),
        _symbol("Symbol of a stock, ETF, index, currency pair, cryptocurrency or commodity."),
        _from(example=MONTH_AGO),
        _to(example=DAY),
    ),
    slug="historical-price-eod-full",
    trending=True,
    examples=(_example("Light variant for the last month", variant="light", symbol="AAPL", **{"from": MONTH_AGO, "to": DAY}), _example("S&P 500 index", variant="full", symbol="^GSPC", **{"from": MONTH_AGO, "to": DAY}), _example("Bitcoin", variant="full", symbol="BTCUSD", **{"from": MONTH_AGO, "to": DAY})),
)
endpoint(
    "intraday",
    "/historical-chart/{interval}",
    "chart",
    "Intraday prices",
    "Open, high, low, close and volume at an interval from one minute to four hours, with timestamps in the exchange's local time.",
    (
        param("interval", "Bar length.", where="path", enum=("1min", "5min", "15min", "30min", "1hour", "4hour"), default="5min", premium_values=("1min",), premium_note="One-minute bars need the Ultimate plan."),
        _symbol("Symbol of a stock, ETF, index, currency pair, cryptocurrency or commodity."),
        _from(example=WEEK_AGO),
        _to(example=DAY),
        param("nonadjusted", "Return prices not adjusted for splits.", "boolean"),
    ),
    slug="intraday-5-min",
    trending=True,
)

# --- technical indicators ------------------------------------------------------------------------------------

endpoint(
    "technical_indicator",
    "/technical-indicators/{indicator}",
    "technical-indicators",
    "Technical indicator",
    "A technical indicator computed over a symbol's price history, returned with each bar's open, high, low, close and volume.",
    (
        param("indicator", "Which indicator to compute.", where="path", enum=("sma", "ema", "wma", "dema", "tema", "rsi", "standarddeviation", "williams", "adx"), default="sma"),
        _symbol(),
        param("periodLength", "Number of bars the indicator looks back over.", "integer", required=True, example="14", minimum=1),
        param("timeframe", "Bar length.", required=True, enum=("1min", "5min", "15min", "30min", "1hour", "4hour", "1day"), default="1day", example="1day"),
        _from(example=MONTH_AGO),
        _to(example=DAY),
    ),
    slug="simple-moving-average",
    examples=(_example("14-day RSI", indicator="rsi", symbol="AAPL", periodLength="14", timeframe="1day"), _example("50-day exponential moving average", indicator="ema", symbol="AAPL", periodLength="50", timeframe="1day")),
)

# --- analyst -----------------------------------------------------------------------------------------------------

endpoint("analyst_estimates", "/analyst-estimates", "analyst", "Analyst estimates", "Analysts' estimates of revenue, EBITDA, EBIT, net income and earnings per share, with the number of analysts behind each.", (_symbol(), param("period", "Annual or quarterly estimates.", enum=("annual", "quarter"), required=True, default="annual", example="annual"), _page(), _limit()), slug="financial-estimates", trending=True)
endpoint("ratings_snapshot", "/ratings-snapshot", "analyst", "Ratings snapshot", "FMP's current rating and the scores behind it: discounted cash flow, return on equity, return on assets, debt to equity, price to earnings and price to book.", (_symbol(),), slug="ratings-snapshot")
endpoint("ratings_historical", "/ratings-historical", "analyst", "Historical ratings", "How FMP's rating of a stock changed over time.", (_symbol(), _limit()), slug="historical-ratings")
endpoint("price_target_summary", "/price-target-summary", "analyst", "Price target summary", "Average analyst price targets over the last month, quarter, year and all time.", (_symbol(),), slug="price-target-summary")
endpoint("price_target_consensus", "/price-target-consensus", "analyst", "Price target consensus", "The high, low, median and consensus analyst price target.", (_symbol(),), slug="price-target-consensus")
endpoint("grades", "/grades", "analyst", "Analyst grades", "Each analyst firm's upgrades, downgrades and reiterated ratings.", (_symbol(), _limit()), slug="grades")
endpoint("grades_historical", "/grades-historical", "analyst", "Historical grades", "How many analysts rate a stock strong buy, buy, hold, sell and strong sell, over time.", (_symbol(), _limit()), slug="historical-grades")
endpoint("grades_consensus", "/grades-consensus", "analyst", "Grades consensus", "The current count of analyst ratings by grade and the consensus.", (_symbol(),), slug="grades-summary")

# --- calendars ------------------------------------------------------------------------------------------------------

endpoint("dividends", "/dividends", "calendar", "Dividends", "A company's dividend history: record, payment and declaration dates, amount and yield.", (_symbol(), _limit()), slug="dividends-company")
endpoint("dividends_calendar", "/dividends-calendar", "calendar", "Dividends calendar", "Upcoming and recent dividends across all companies.", (_from(example=DAY), _to(example=WEEK_AHEAD)), slug="dividends-calendar")
endpoint("earnings", "/earnings", "calendar", "Earnings", "A company's earnings reports: date, estimated and actual earnings per share and revenue.", (_symbol(), _limit()), slug="earnings-company", trending=True)
endpoint("earnings_calendar", "/earnings-calendar", "calendar", "Earnings calendar", "Upcoming and recent earnings reports across all companies.", (_from(example=DAY), _to(example=WEEK_AHEAD)), slug="earnings-calendar", trending=True)
endpoint("ipos_calendar", "/ipos-calendar", "calendar", "IPO calendar", "Upcoming and recent initial public offerings.", (_from(example=DAY), _to(example=WEEK_AHEAD)), slug="ipos-calendar")
endpoint("ipos_disclosure", "/ipos-disclosure", "calendar", "IPO disclosures", "SEC disclosure filings related to IPOs.", (_from(example=MONTH_AGO), _to(example=DAY)), slug="ipos-disclosure")
endpoint("ipos_prospectus", "/ipos-prospectus", "calendar", "IPO prospectuses", "IPO prospectus filings with the offering price and proceeds.", (_from(example=MONTH_AGO), _to(example=DAY)), slug="ipos-prospectus")
endpoint("splits", "/splits", "calendar", "Stock splits", "A company's stock split history.", (_symbol(), _limit()), slug="splits-company")
endpoint("splits_calendar", "/splits-calendar", "calendar", "Splits calendar", "Upcoming and recent stock splits across all companies.", (_from(example=WEEK_AGO), _to(example=WEEK_AHEAD)), slug="splits-calendar")

# --- economics --------------------------------------------------------------------------------------------------------

endpoint("treasury_rates", "/treasury-rates", "economics", "Treasury rates", "US Treasury yields from one month to thirty years.", (_from(example=MONTH_AGO), _to(example=DAY)), slug="treasury-rates", trending=True)
endpoint(
    "economic_indicators",
    "/economic-indicators",
    "economics",
    "Economic indicators",
    "A US economic indicator over time, such as GDP, CPI, unemployment or the federal funds rate.",
    (
        param("name", "Indicator name.", required=True, example="CPI", suggestions=("GDP", "realGDP", "CPI", "inflationRate", "federalFunds", "unemploymentRate", "retailSales", "consumerSentiment", "durableGoods", "totalNonfarmPayroll", "initialClaims", "industrialProductionTotalIndex", "totalVehicleSales", "30YearFixedRateMortgageAverage", "15YearFixedRateMortgageAverage")),
        _from(example=YEAR_AGO),
        _to(example=DAY),
    ),
    slug="economics-indicators",
    examples=(_example("Consumer price index over a year", name="CPI", **{"from": YEAR_AGO, "to": DAY}), _example("Unemployment rate", name="unemploymentRate", **{"from": YEAR_AGO, "to": DAY}), _example("Real GDP", name="realGDP", **{"from": YEAR_AGO, "to": DAY})),
)
endpoint("economic_calendar", "/economic-calendar", "economics", "Economic calendar", "Scheduled economic releases with their previous, estimated and actual values.", (_from(example=DAY), _to(example=WEEK_AHEAD)), slug="economics-calendar")
endpoint("market_risk_premium", "/market-risk-premium", "economics", "Market risk premium", "The market risk premium and country risk premium for each country.", slug="market-risk-premium")

# --- market performance --------------------------------------------------------------------------------------------------

_SECTOR = param("sector", "Sector name, for example Technology.", suggestions=("Technology", "Healthcare", "Financial Services", "Energy", "Consumer Cyclical", "Industrials", "Utilities", "Real Estate", "Basic Materials", "Communication Services", "Consumer Defensive"))
_INDUSTRY = param("industry", "Industry name, for example Biotechnology.", suggestions=("Biotechnology", "Software - Infrastructure", "Semiconductors", "Banks - Diversified", "Oil & Gas E&P"))
endpoint("sector_performance", "/sector-performance-snapshot", "market-performance", "Sector performance", "The average price change of each sector on a day.", (_dated("Trading day."), _exchange(), _SECTOR), slug="sector-performance-snapshot")
endpoint("industry_performance", "/industry-performance-snapshot", "market-performance", "Industry performance", "The average price change of each industry on a day.", (_dated("Trading day."), _exchange(), _INDUSTRY), slug="industry-performance-snapshot")
endpoint("historical_sector_performance", "/historical-sector-performance", "market-performance", "Historical sector performance", "A sector's average daily price change over time.", (param("sector", "Sector name.", required=True, example="Technology"), _from(example=MONTH_AGO), _to(example=DAY), _exchange()), slug="historical-sector-performance")
endpoint("historical_industry_performance", "/historical-industry-performance", "market-performance", "Historical industry performance", "An industry's average daily price change over time.", (param("industry", "Industry name.", required=True, example="Biotechnology"), _from(example=MONTH_AGO), _to(example=DAY), _exchange()), slug="historical-industry-performance")
endpoint("sector_pe", "/sector-pe-snapshot", "market-performance", "Sector price to earnings", "The average price-to-earnings ratio of each sector on a day.", (_dated("Trading day."), _exchange(), _SECTOR), slug="sector-pe-snapshot")
endpoint("industry_pe", "/industry-pe-snapshot", "market-performance", "Industry price to earnings", "The average price-to-earnings ratio of each industry on a day.", (_dated("Trading day."), _exchange(), _INDUSTRY), slug="industry-pe-snapshot")
endpoint("historical_sector_pe", "/historical-sector-pe", "market-performance", "Historical sector price to earnings", "A sector's average price-to-earnings ratio over time.", (param("sector", "Sector name.", required=True, example="Technology"), _from(example=MONTH_AGO), _to(example=DAY), _exchange()), slug="historical-sector-pe")
endpoint("historical_industry_pe", "/historical-industry-pe", "market-performance", "Historical industry price to earnings", "An industry's average price-to-earnings ratio over time.", (param("industry", "Industry name.", required=True, example="Biotechnology"), _from(example=MONTH_AGO), _to(example=DAY), _exchange()), slug="historical-industry-pe")
endpoint("biggest_gainers", "/biggest-gainers", "market-performance", "Biggest gainers", "The stocks with the largest price gains today.", slug="biggest-gainers", trending=True)
endpoint("biggest_losers", "/biggest-losers", "market-performance", "Biggest losers", "The stocks with the largest price losses today.", slug="biggest-losers", trending=True)
endpoint("most_actives", "/most-actives", "market-performance", "Most active", "The stocks with the highest trading volume today.", slug="most-active", trending=True)

# --- news -------------------------------------------------------------------------------------------------------------------

_NEWS = (_page(), _limit())
_NEWS_DATES = (_from(example=WEEK_AGO), _to(example=DAY))
endpoint("fmp_articles", "/fmp-articles", "news", "FMP articles", "Articles FMP's own writers publish.", _NEWS, slug="fmp-articles")
endpoint("general_news", "/news/general-latest", "news", "General news", "The latest general market and business news.", (*_NEWS, *_NEWS_DATES), slug="general-news", trending=True)
endpoint("press_releases_latest", "/news/press-releases-latest", "news", "Latest press releases", "The latest company press releases.", (*_NEWS, *_NEWS_DATES), slug="press-releases")
endpoint("stock_news_latest", "/news/stock-latest", "news", "Latest stock news", "The latest news about stocks.", (*_NEWS, *_NEWS_DATES), slug="stock-news", trending=True)
endpoint("crypto_news_latest", "/news/crypto-latest", "news", "Latest crypto news", "The latest news about cryptocurrencies.", (*_NEWS, *_NEWS_DATES), slug="crypto-news")
endpoint("forex_news_latest", "/news/forex-latest", "news", "Latest forex news", "The latest news about currencies.", (*_NEWS, *_NEWS_DATES), slug="forex-news")
endpoint("press_releases_search", "/news/press-releases", "news", "Press releases by symbol", "Press releases of the given companies.", (_symbols(), *_NEWS_DATES, *_NEWS), slug="search-press-releases")
endpoint("stock_news_search", "/news/stock", "news", "Stock news by symbol", "News about the given stocks.", (_symbols(), *_NEWS_DATES, *_NEWS), slug="search-stock-news", trending=True)
endpoint("crypto_news_search", "/news/crypto", "news", "Crypto news by symbol", "News about the given cryptocurrencies.", (_symbols(example="BTCUSD"), *_NEWS_DATES, *_NEWS), slug="search-crypto-news")
endpoint("forex_news_search", "/news/forex", "news", "Forex news by symbol", "News about the given currency pairs.", (_symbols(example="EURUSD"), *_NEWS_DATES, *_NEWS), slug="search-forex-news")

# --- earnings transcripts ------------------------------------------------------------------------------------------------

endpoint("transcripts_latest", "/earning-call-transcript-latest", "transcripts", "Latest transcripts", "The most recent earnings call transcripts.", (_limit(), _page()), slug="latest-transcripts")
endpoint("transcript", "/earning-call-transcript", "transcripts", "Earnings call transcript", "The full text of one earnings call.", (_symbol(), _year(required=True, example="2024"), _quarter(required=True, example="4"), _limit()), slug="search-transcripts")
endpoint("transcript_dates", "/earning-call-transcript-dates", "transcripts", "Transcript dates", "The fiscal years, quarters and dates of a company's earnings calls.", (_symbol(),), slug="transcripts-dates-by-symbol")
endpoint("transcript_symbols", "/earnings-transcript-list", "transcripts", "Companies with transcripts", "Companies that have earnings call transcripts, with how many.", slug="available-transcript-symbols", utility=True)

# --- ETFs and funds ---------------------------------------------------------------------------------------------------------

endpoint("etf_holdings", "/etf/holdings", "etf-funds", "ETF holdings", "What an ETF holds: each asset with its weight and market value.", (_symbol("ETF symbol.", "SPY"),), slug="holdings")
endpoint("etf_info", "/etf/info", "etf-funds", "ETF information", "An ETF's expense ratio, assets under management, inception date, holdings count and description.", (_symbol("ETF symbol.", "SPY"),), slug="information")
endpoint("etf_country_weightings", "/etf/country-weightings", "etf-funds", "ETF country weightings", "How an ETF's assets are split by country.", (_symbol("ETF symbol.", "SPY"),), slug="country-weighting")
endpoint("etf_asset_exposure", "/etf/asset-exposure", "etf-funds", "ETF asset exposure", "Which ETFs hold a given stock, and how much.", (_symbol(),), slug="etf-asset-exposure")
endpoint("etf_sector_weightings", "/etf/sector-weightings", "etf-funds", "ETF sector weightings", "How an ETF's assets are split by sector.", (_symbol("ETF symbol.", "SPY"),), slug="sector-weighting")
endpoint("funds_disclosure_latest", "/funds/disclosure-holders-latest", "etf-funds", "Latest fund holders", "The funds that most recently disclosed holding a stock.", (_symbol(),), slug="latest-disclosures")
endpoint("funds_disclosure", "/funds/disclosure", "etf-funds", "Fund disclosure", "A mutual fund's or ETF's disclosed holdings for a quarter.", (_symbol("Fund symbol.", "VWO"), _year(required=True, example="2023"), _quarter(required=True, example="4")), slug="mutual-fund-disclosures")
endpoint("funds_disclosure_search", "/funds/disclosure-holders-search", "etf-funds", "Search fund holders", "Finds funds by name in the disclosure filings.", (param("name", "Fund name.", required=True, example="Vanguard"),), slug="disclosures-name-search")
endpoint("funds_disclosure_dates", "/funds/disclosure-dates", "etf-funds", "Fund disclosure dates", "The dates a fund filed its holdings disclosure.", (_symbol("Fund symbol.", "VWO"),), slug="disclosures-dates")

# --- institutional ownership (Form 13F) ------------------------------------------------------------------------------

endpoint("institutional_latest", "/institutional-ownership/latest", "institutional", "Latest 13F filings", "The most recently filed Form 13F reports.", (_page(), _limit()), slug="latest-filings")
endpoint("institutional_extract", "/institutional-ownership/extract", "institutional", "13F holdings", "The securities an institution reported holding in a quarter.", (_cik(), _year(required=True, example="2023"), _quarter(required=True, example="3")), slug="filings-extract")
endpoint("institutional_holder_analytics", "/institutional-ownership/extract-analytics/holder", "institutional", "Institutional holders of a stock", "The institutions holding a stock with how their positions changed in a quarter.", (_symbol(), _year(required=True, example="2023"), _quarter(required=True, example="3"), _page(), _limit()), slug="filings-extract-with-analytics-by-holder")
endpoint("institutional_positions", "/institutional-ownership/symbol-positions-summary", "institutional", "Institutional positions in a stock", "Total institutional holders and shares of a stock in a quarter, and the change from the previous one.", (_symbol(), _year(required=True, example="2023"), _quarter(required=True, example="3")), slug="positions-summary")

# --- insider trades --------------------------------------------------------------------------------------------------------------

endpoint("insider_latest", "/insider-trading/latest", "insider", "Latest insider trades", "The most recently reported insider transactions.", (_page(), _limit(), param("date", "Only trades on this day.", "date")), slug="latest-insider-trade")
endpoint("insider_search", "/insider-trading/search", "insider", "Search insider trades", "Insider transactions filtered by company, insider and transaction type.", (param("symbol", "Ticker symbol."), _page(), _limit(), param("reportingCik", "CIK of the insider."), param("companyCik", "CIK of the company."), param("transactionType", "Transaction type code, for example P-Purchase.")), slug="search-insider-trades", trending=True, examples=(_example("Apple insiders", symbol="AAPL"),))
endpoint("insider_by_name", "/insider-trading/reporting-name", "insider", "Insiders by name", "Finds insiders by name, with their CIKs.", (param("name", "Insider name.", required=True, example="Zuckerberg"),), slug="search-reporting-name")
endpoint("insider_transaction_types", "/insider-trading-transaction-type", "insider", "Insider transaction types", "The transaction type codes insiders report.", slug="all-transaction-types", utility=True)
endpoint("insider_statistics", "/insider-trading/statistics", "insider", "Insider trading statistics", "Quarterly counts of insider purchases and sales, and the ratio between them.", (_symbol(),), slug="insider-trade-statistics")
endpoint("beneficial_ownership", "/acquisition-of-beneficial-ownership", "insider", "Beneficial ownership", "Filings in which a holder crossed 5% ownership of a company (Schedules 13D and 13G).", (_symbol(),), slug="acquisition-ownership")

# --- SEC filings ------------------------------------------------------------------------------------------------------------------

_FILING_DATES = (_from("Start date, YYYY-MM-DD.", WEEK_AGO), _to("End date, YYYY-MM-DD.", DAY))
_FILING_RANGE = (_from("Start date, YYYY-MM-DD.", WEEK_AGO, required=True), _to("End date, YYYY-MM-DD.", DAY, required=True))
endpoint("sec_8k_latest", "/sec-filings-8k", "sec-filings", "Latest 8-K filings", "The latest Form 8-K current reports.", (*_FILING_DATES, _page(), _limit()), slug="8k-latest")
endpoint("sec_financials_latest", "/sec-filings-financials", "sec-filings", "Latest financial filings", "The latest 10-K and 10-Q reports.", (*_FILING_DATES, _page(), _limit()), slug="financials-latest")
endpoint("sec_by_form_type", "/sec-filings-search/form-type", "sec-filings", "Filings by form type", "Filings of one form type, such as 10-K or 8-K.", (param("formType", "SEC form type.", required=True, example="8-K"), *_FILING_RANGE, _page(), _limit()), slug="search-by-form-type")
endpoint("sec_by_symbol", "/sec-filings-search/symbol", "sec-filings", "Filings by symbol", "A company's SEC filings, found by ticker.", (_symbol(), *_FILING_RANGE, _page(), _limit()), slug="search-by-symbol")
endpoint("sec_by_cik", "/sec-filings-search/cik", "sec-filings", "Filings by CIK", "A company's SEC filings, found by CIK.", (_cik(), *_FILING_RANGE, _page(), _limit()), slug="search-by-cik")
endpoint("sec_profile", "/sec-profile", "sec-filings", "SEC company profile", "A company's SEC registration: SIC code, state of incorporation, fiscal year end, addresses and phone.", (_symbol(),), slug="sec-company-full-profile")

# --- indexes ---------------------------------------------------------------------------------------------------------------------

endpoint("index_list", "/index-list", "indexes", "Index list", "Market indices FMP covers, with their exchange and currency.", slug="indexes-list", utility=True)
endpoint("sp500_constituents", "/sp500-constituent", "indexes", "S&P 500 members", "The companies in the S&P 500, with their sector, headquarters and date added.", slug="sp-500", trending=True)
endpoint("nasdaq_constituents", "/nasdaq-constituent", "indexes", "Nasdaq-100 members", "The companies in the Nasdaq-100.", slug="nasdaq")
endpoint("dowjones_constituents", "/dowjones-constituent", "indexes", "Dow Jones members", "The companies in the Dow Jones Industrial Average.", slug="dow-jones")

# --- markets ---------------------------------------------------------------------------------------------------------------------

endpoint("exchange_market_hours", "/exchange-market-hours", "markets", "Exchange trading hours", "When an exchange opens and closes, and whether it is open now.", (_exchange(required=True, example="NASDAQ"),), slug="exchange-market-hours")
endpoint("exchange_holidays", "/holidays-by-exchange", "markets", "Exchange holidays", "Days an exchange is closed.", (_exchange(required=True, example="NASDAQ"), _from(), _to()), slug="holidays-by-exchange")
endpoint("all_exchange_market_hours", "/all-exchange-market-hours", "markets", "Trading hours of all exchanges", "Opening hours and open or closed status of every exchange.", slug="all-exchange-market-hours")
endpoint("forex_list", "/forex-list", "markets", "Currency pairs", "Every currency pair FMP covers.", slug="forex-list", utility=True)
endpoint("crypto_list", "/cryptocurrency-list", "markets", "Cryptocurrencies", "Every cryptocurrency FMP covers.", slug="cryptocurrency-list", utility=True)
endpoint("commodities_list", "/commodities-list", "markets", "Commodities", "Every commodity FMP covers.", slug="commodities-list", utility=True)

# --- valuation ---------------------------------------------------------------------------------------------------------------------

endpoint("dcf", "/discounted-cash-flow", "valuation", "Discounted cash flow", "FMP's estimate of a stock's intrinsic value from projected free cash flows, next to the current price.", (_symbol(),), slug="dcf-advanced")
endpoint("levered_dcf", "/levered-discounted-cash-flow", "valuation", "Levered discounted cash flow", "Intrinsic value estimated from free cash flow to equity, after debt payments.", (_symbol(),), slug="dcf-levered")






# --- plans ---------------------------------------------------------------------------------------------------------------------------------

# The endpoints a free key is refused, each with the cheapest plan the pricing page names for its
# feature group, or None where the page does not say which paid plan adds it. Every endpoint not
# listed is on Basic.
PAID_PLANS: dict[str, Optional[str]] = {
    **{id_: None for id_ in ("search_cusip", "search_isin", "search_exchange_variants", "company_screener", "search_mergers", "executive_compensation_benchmark", "stock_list", "financial_statement_symbols", "cik_list", "symbol_changes", "etf_list", "actively_trading", "available_exchanges", "available_sectors", "available_industries", "available_countries", "latest_financial_statements", "income_statement_ttm", "balance_sheet_ttm", "cash_flow_ttm", "economic_calendar", "insider_search", "insider_by_name", "insider_statistics", "beneficial_ownership", "sp500_constituents", "nasdaq_constituents", "dowjones_constituents")},
    **{id_: "Starter" for id_ in ("general_news", "press_releases_latest", "stock_news_latest", "crypto_news_latest", "forex_news_latest", "press_releases_search", "stock_news_search", "crypto_news_search", "forex_news_search")},
    **{id_: "Premium" for id_ in ("intraday", "technical_indicator", "ipos_calendar", "ipos_disclosure", "ipos_prospectus")},
    **{id_: "Ultimate" for id_ in ("batch_quote", "batch_quote_short", "exchange_quotes", "etf_quotes", "crypto_quotes", "forex_quotes", "commodity_quotes", "index_quotes", "transcripts_latest", "transcript", "transcript_dates", "transcript_symbols", "etf_holdings", "etf_info", "etf_country_weightings", "etf_asset_exposure", "etf_sector_weightings", "funds_disclosure_latest", "funds_disclosure", "funds_disclosure_search", "funds_disclosure_dates", "institutional_latest", "institutional_extract", "institutional_holder_analytics", "institutional_positions")},
}


def plan_of(endpoint_id: str) -> Optional[str]:
    return PAID_PLANS.get(endpoint_id, PLAN_NAMES[0])


# --- what a Basic (free) key may do with the endpoints it can reach -----------------------------------------------------
#
# FMP's Market Data page marks each endpoint Full, Limited or No access on the free plan but documents nothing about
# what "Limited" is. This is what calling the live API with a free key showed (November 2026). A request beyond a limit
# is refused with HTTP 402 "Premium Query Parameter ...", which the provider reports as ``premium_required``.
#
# 1. Which symbols. On SYMBOL_LIMITED a free key may query only BASIC_SYMBOLS (plus a few indices, currency pairs,
#    cryptocurrencies and commodities, BASIC_OTHER_SYMBOLS); anything else is refused, even a large US company
#    (ORCL, PLUG, GME). Endpoints that list or calendar many symbols (earnings and dividends calendars, All Shares
#    Float) are not refused: they quietly return only the rows of those symbols.
# 2. How many rows. ``limit`` is capped per endpoint (ROW_CAPS), so a statement reaches back five periods.
# 3. How far back. A start date (``from``, or ``date`` for the sector and industry snapshots) must be within 30 days on
#    RECENT_30 and within a year on RECENT_YEAR. Price history, treasury rates and sector history are not limited this way.
# Full-access endpoints (search, profile by CIK, stock peers, SEC profile, movers, market hours...) take any symbol.

# The symbols "All Shares Float" returns on a free key. All 31 of the ones tried on the endpoints below were accepted and
# none of the 13 that are not on the list.
BASIC_SYMBOLS = (
    "AAL", "AAPL", "ABBV", "ADBE", "AMD", "AMZN", "ATVI", "BA", "BABA", "BAC", "BIDU", "BILI", "C", "CARR", "CCL",
    "COIN", "COST", "CPRX", "CSCO", "CVX", "DAL", "DIS", "DOCU", "ET", "ETSY", "F", "FDX", "FUBO", "GE", "GM",
    "GOOGL", "GS", "HCA", "HOOD", "INTC", "JNJ", "JPM", "KO", "LCID", "LMT", "META", "MGM", "MRNA", "MRO", "MSFT",
    "NFLX", "NIO", "NKE", "NOK", "NVDA", "PEP", "PFE", "PINS", "PLTR", "PYPL", "RBLX", "RIOT", "RIVN", "RKT", "ROKU",
    "SBUX", "SHOP", "SIRI", "SNAP", "SOFI", "SONY", "SPY", "SPYG", "SQ", "T", "TGT", "TLRY", "TSLA", "TSM", "TWTR",
    "UAL", "UBER", "UNH", "V", "VIAC", "VWO", "VZ", "WBA", "WFC", "WMT", "XOM", "ZM",
)
# Seen accepted on a free key (the list of other asset classes is not published); CLUSD (WTI crude) was refused.
BASIC_OTHER_SYMBOLS = ("^GSPC", "^DJI", "^IXIC", "EURUSD", "GBPUSD", "BTCUSD", "ETHUSD", "GCUSD", "SIUSD")

# Endpoints that refuse a symbol outside the list above (every one was called with ORCL, which is not on it).
SYMBOL_LIMITED = (
    "employee_count", "historical_employee_count", "market_cap", "historical_market_cap", "shares_float",
    "key_executives", "executive_compensation", "quote", "quote_short", "aftermarket_trade", "aftermarket_quote",
    "price_change", "income_statement", "balance_sheet", "cash_flow", "key_metrics", "ratios", "key_metrics_ttm",
    "ratios_ttm", "financial_scores", "owner_earnings", "enterprise_values", "financial_growth",
    "revenue_product_segmentation", "revenue_geographic_segmentation", "historical_eod", "analyst_estimates",
    "ratings_snapshot", "ratings_historical", "price_target_summary", "price_target_consensus", "grades",
    "grades_historical", "grades_consensus", "dividends", "earnings", "splits", "dcf", "levered_dcf",
)
# ``profile`` takes any US-traded symbol, OTC included (ORCL, PLUG, GME, BRK-B, ASML, RANJY) but not one on another exchange.
US_SYMBOL_ONLY = ("profile",)

# The ``limit`` a free key may ask for: the refusal says "must be between 0 and N". Not capped: the three searches, delisted
# companies, historical market capitalisation, All Shares Float, analyst grades and FMP articles.
ROW_CAPS: dict[str, int] = {
    **dict.fromkeys(("employee_count", "historical_employee_count", "latest_mergers", "income_statement", "balance_sheet", "cash_flow", "key_metrics", "ratios", "owner_earnings", "enterprise_values", "financial_growth", "dividends", "earnings", "splits"), 5),
    **dict.fromkeys(("analyst_estimates", "grades_historical"), 10),
    "ratings_historical": 1,
    **dict.fromkeys(("sec_8k_latest", "sec_financials_latest", "sec_by_symbol", "sec_by_cik"), 20),
    "insider_latest": 100,
}

# Endpoints whose start date a free key may not set further back than 30 days (the date parameter is named), or a year.
RECENT_30: dict[str, str] = {
    **dict.fromkeys(("earnings_calendar", "dividends_calendar", "splits_calendar", "sec_8k_latest", "sec_financials_latest", "sec_by_form_type"), "from"),
    **dict.fromkeys(("sector_performance", "industry_performance", "sector_pe", "industry_pe"), "date"),
}
RECENT_YEAR: dict[str, str] = dict.fromkeys(("sec_by_symbol", "sec_by_cik"), "from")

# Shown beside the symbol field of the endpoints above; the examples are the first picks of the list.
SYMBOL_NOTE = (
    f"A Basic key can query only a fixed list of well-known symbols ({len(BASIC_SYMBOLS)} stocks and ETFs, such as AAPL, MSFT, NVDA, TSLA and SPY, "
    "plus a few indices, currency pairs, cryptocurrencies and commodities). Any other symbol is refused."
)
US_SYMBOL_NOTE = "A Basic key can query US-traded symbols, OTC included. A symbol on another exchange, such as SAP.DE or RY.TO, is refused."
SYMBOL_SUGGESTIONS = ("AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "NFLX", "JPM", "V", "WMT", "DIS", "KO", "PEP", "INTC", "AMD", "BA", "NKE", "XOM", "SPY")
# Added to the description of an endpoint that returns many symbols at once.
SUBSET_NOTE = "A Basic key sees only the rows of its fixed symbol list, so this is a part of the market, not all of it."
SUBSET_ENDPOINTS = ("earnings_calendar", "dividends_calendar", "splits_calendar", "shares_float_all")


def _note_param(item: dict[str, Any], name: str, note: str, suggestions: tuple[str, ...] = ()) -> None:
    for p in item["params"]:
        if p["name"] == name:
            p["premium_note"] = note
            if suggestions and not p["suggestions"]:
                p["suggestions"] = list(suggestions)
            return
    raise ValueError(f"{item['id']} has no {name} parameter to describe a limit on")


def apply_basic_limits() -> None:
    """Writes what a free key may not do next to the parameter it concerns, so the form says so before a fetch."""

    for item in ENDPOINTS:
        id_ = item["id"]
        if id_ in SYMBOL_LIMITED:
            _note_param(item, "symbol", SYMBOL_NOTE, SYMBOL_SUGGESTIONS)
        if id_ in US_SYMBOL_ONLY:
            _note_param(item, "symbol", US_SYMBOL_NOTE)
        if id_ in ROW_CAPS:
            cap = ROW_CAPS[id_]
            _note_param(item, "limit", f"A Basic key can ask for at most {cap} {'row' if cap == 1 else 'rows'} at a time.")
        if id_ in RECENT_30:
            _note_param(item, RECENT_30[id_], f"A Basic key can only use a {'start date' if RECENT_30[id_] == 'from' else 'date'} from the last 30 days.")
        if id_ in RECENT_YEAR:
            _note_param(item, RECENT_YEAR[id_], "A Basic key can only start up to a year (365 days) back.")
        if id_ in SUBSET_ENDPOINTS:
            item["description"] += " " + SUBSET_NOTE


apply_basic_limits()
