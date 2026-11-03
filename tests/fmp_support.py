"""Hand-made Financial Modeling Prep payloads in the shapes the live stable API returns, and a fake HTTP layer that records headers."""

from __future__ import annotations

import json
from typing import Any

from providers_support import FakeHttp as _FakeHttp
from tradingview_data.providers.common import HttpResult


class FakeHttp(_FakeHttp):
    """Like the shared fake, but ``FMP`` sends its key in a header, so the calls record headers too."""

    def __init__(self, *script: Any, **kwargs: Any) -> None:
        super().__init__(*script, **kwargs)
        self.headers: list[dict[str, str]] = []

    def __call__(self, url: str, params: list[tuple[str, str]], headers: "dict[str, str] | None" = None) -> HttpResult:
        self.headers.append(dict(headers or {}))
        return super().__call__(url, params)


def raw(status: int, body: str) -> HttpResult:
    """A response whose body is not JSON, as FMP's 400 and 402 answers are."""

    return HttpResult(status, body.encode(), "application/json; charset=utf-8")


RESTRICTED = raw(402, "Restricted Endpoint: This endpoint is not available under your current subscription please visit our subscription page to upgrade your plan at https://financialmodelingprep.com/")
PREMIUM_PARAMETER = raw(402, "Premium Query Parameter: 'Special Endpoint : This value set for 'symbol' is not available under your current subscription please visit our subscription page to upgrade your plan at https://financialmodelingprep.com/")
INVALID_KEY = raw(401, json.dumps({"Error Message": "Invalid API KEY. Feel free to create a Free API Key or visit https://site.financialmodelingprep.com/faqs?search=why-is-my-api-key-invalid for more information."}))
MISSING_PARAMETER = raw(400, "Query Error: Invalid or missing query parameter - symbol")
LIMIT_REACHED = raw(429, json.dumps({"Error Message": "Limit Reach . Please upgrade your plan or visit our documentation for more details at https://site.financialmodelingprep.com/"}))
LIMIT_BEYOND_PLAN = raw(402, "Premium Query Parameter: 'Special Parameters : The values for 'limit' must be between 0 and 5 based on your current subscription. Please visit our subscription page")

QUOTE = [
    {
        "symbol": "AAPL", "name": "Apple Inc.", "price": 338.0688, "changePercentage": -1.90384, "change": -6.5612, "volume": 22953697,
        "dayLow": 336.5206, "dayHigh": 343.78, "yearHigh": 351.73, "yearLow": 243.42, "marketCap": 4933836919584, "priceAvg50": 333.0408,
        "priceAvg200": 296.55606, "exchange": "NASDAQ", "open": 342.67, "previousClose": 344.63, "timestamp": 1793642472,
    }
]
AFTERMARKET_TRADE = [{"symbol": "AAPL", "price": 337.9561, "tradeSize": 8, "timestamp": 1793643102000}]
PRICE_CHANGE = [{"symbol": "AAPL", "1D": -1.97, "5D": -2.62, "1M": 1.25, "3M": 9.37, "6M": 20.6, "ytd": 24.27, "1Y": 25.57, "3Y": 80.1, "5Y": 210.2, "10Y": 1190.4, "max": 180000.5}]
PROFILE = [
    {
        "symbol": "AAPL", "price": 338.13, "marketCap": 4933836919584, "beta": 1.094, "lastDividend": 1.02, "range": "243.42-351.73", "change": -6.5, "changePercentage": -1.9,
        "volume": 22953697, "averageVolume": 48000000, "companyName": "Apple Inc.", "currency": "USD", "cik": "0000320193", "isin": "US0378331005", "cusip": "037833100",
        "exchangeFullName": "NASDAQ Global Select", "exchange": "NASDAQ", "industry": "Consumer Electronics", "website": "https://www.apple.com", "description": "Apple Inc. designs <b>smartphones</b>.\n\nIt also sells services.",
        "ceo": "Timothy D. Cook", "sector": "Technology", "country": "US", "fullTimeEmployees": "166000", "phone": "(408) 996-1010", "address": "One Apple Park Way", "city": "Cupertino",
        "state": "CA", "zip": "95014", "image": "https://images.financialmodelingprep.com/symbol/AAPL.png", "ipoDate": "1980-12-12", "defaultImage": False, "isEtf": False, "isActivelyTrading": True, "isAdr": False, "isFund": False,
    }
]


def statement(year: int, period: str = "FY", **fields: Any) -> dict[str, Any]:
    return {"date": f"{year}-09-27", "symbol": "AAPL", "reportedCurrency": "USD", "cik": "0000320193", "filingDate": f"{year}-11-01", "acceptedDate": f"{year}-11-01 06:01:36", "fiscalYear": str(year), "period": period, **fields}


INCOME = [
    statement(2025, revenue=416161000000, grossProfit=195201000000, operatingIncome=133050000000, netIncome=112010000000, epsDiluted=7.46),
    statement(2024, revenue=391035000000, grossProfit=180683000000, operatingIncome=123216000000, netIncome=93736000000, epsDiluted=6.08),
    statement(2023, revenue=383285000000, grossProfit=169148000000, operatingIncome=114301000000, netIncome=96995000000, epsDiluted=6.13),
]
RATIOS = [statement(2025, grossProfitMargin=0.469, operatingProfitMargin=0.32, netProfitMargin=0.269), statement(2024, grossProfitMargin=0.462, operatingProfitMargin=0.315, netProfitMargin=0.24)]
SEGMENTS = [
    {"symbol": "AAPL", "fiscalYear": 2025, "period": "FY", "reportedCurrency": "USD", "date": "2025-09-27", "data": {"iPhone": 209586000000, "Mac": 33708000000, "Service": 109158000000}},
    {"symbol": "AAPL", "fiscalYear": 2024, "period": "FY", "reportedCurrency": "USD", "date": "2024-09-28", "data": {"iPhone": 201183000000, "Mac": 29984000000, "Service": 96169000000}},
]


def bar(day: str, close: float, **fields: Any) -> dict[str, Any]:
    return {"symbol": "AAPL", "date": day, "open": close - 1, "high": close + 2, "low": close - 2, "close": close, "volume": 1000000, "change": 1.0, "changePercent": 0.3, "vwap": close - 0.5, **fields}


EOD = [bar("2026-10-09", 336.64), bar("2026-10-08", 340.42), bar("2026-10-07", 338.0)]
EOD_LIGHT = [{"symbol": "AAPL", "date": "2026-10-09", "price": 336.64, "volume": 37881200}, {"symbol": "AAPL", "date": "2026-10-08", "price": 340.42, "volume": 35332449}]
EOD_ADJUSTED = [{"symbol": "AAPL", "date": "2026-10-09", "adjOpen": 335.0, "adjHigh": 338.0, "adjLow": 334.0, "adjClose": 336.64, "volume": 37881200}, {"symbol": "AAPL", "date": "2026-10-08", "adjOpen": 339.0, "adjHigh": 342.0, "adjLow": 338.0, "adjClose": 340.42, "volume": 35332449}]
INTRADAY = [bar("2026-10-09 15:55:00", 336.6), bar("2026-10-09 15:50:00", 336.4), bar("2026-10-09 15:45:00", 336.1)]
RSI = [{k: v for k, v in bar(day, close).items() if k not in ("symbol", "change", "changePercent", "vwap")} | {"rsi": rsi} for day, close, rsi in (("2026-10-09", 336.64, 61.2), ("2026-10-08", 340.42, 64.8), ("2026-10-07", 338.0, 63.0))]

NEWS = [
    {"symbol": "AAPL", "publishedDate": "2026-10-22 19:06:41", "publisher": "Benzinga", "title": "Apple unveils a new chip", "image": "https://example.com/i.png", "site": "benzinga.com", "text": "<p>Apple said <b>today</b> that it has a new chip.</p>", "url": "https://example.com/apple-chip"},
    {"symbol": "MSFT", "publishedDate": "2026-10-22 18:00:00", "publisher": "Reuters", "title": "Microsoft raises its dividend", "image": "", "site": "reuters.com", "text": "Microsoft raised its quarterly dividend.", "url": "javascript:alert(1)"},
]
ARTICLES = [{"title": "Randstad (OTC: RANJY) Stock Analysis", "date": "2026-10-22 19:06:41", "content": "<ul><li>Revenue beat</li></ul>", "tickers": "OTC:RANJY, NASDAQ:AAPL", "image": "https://example.com/i.png", "link": "https://financialmodelingprep.com/market-news/randstad", "author": "Stuart Mooney", "site": "Financial Modeling Prep"}]

GAINERS = [
    {"symbol": "ABC", "price": 12.3, "name": "ABC Corp", "change": 3.1, "changesPercentage": 33.7, "exchange": "NASDAQ"},
    {"symbol": "XYZ", "price": 4.5, "name": "XYZ Inc", "change": 0.9, "changesPercentage": 25.0, "exchange": "NYSE"},
]
SECTORS = [
    {"date": "2026-10-30", "sector": "Technology", "exchange": "NASDAQ", "averageChange": 1.2},
    {"date": "2026-10-30", "sector": "Energy", "exchange": "NASDAQ", "averageChange": -0.8},
]
SECTOR_PE = [{"date": "2026-10-30", "sector": "Technology", "exchange": "NASDAQ", "pe": 31.5}, {"date": "2026-10-30", "sector": "Energy", "exchange": "NASDAQ", "pe": 12.1}]
TREASURY = [
    {"date": "2026-10-30", "month1": 4.06, "month2": 4.16, "month3": 4.16, "month6": 4.25, "year1": 4.36, "year2": 4.56, "year3": 4.65, "year5": 4.71, "year7": 4.8, "year10": 4.94, "year20": 5.34, "year30": 5.31},
    {"date": "2026-10-29", "month1": 4.05, "month2": 4.15, "month3": 4.17, "month6": 4.24, "year1": 4.35, "year2": 4.55, "year3": 4.64, "year5": 4.7, "year7": 4.79, "year10": 4.93, "year20": 5.33, "year30": 5.3},
]
TRANSCRIPT = [{"symbol": "AAPL", "period": "Q4", "year": 2024, "date": "2024-10-31", "content": "Operator: Good day.\n\nTim Cook: Thank you.\n\n"}]
EARNINGS = [
    {"symbol": "AAPL", "date": "2026-07-30", "epsActual": 1.8, "epsEstimated": 1.7, "revenueActual": 100000000000, "revenueEstimated": 98000000000, "lastUpdated": "2026-08-01"},
    {"symbol": "AAPL", "date": "2026-04-30", "epsActual": 1.6, "epsEstimated": 1.5, "revenueActual": 95000000000, "revenueEstimated": 94000000000, "lastUpdated": "2026-05-01"},
]

EXECUTIVES = [
    {"title": "Chief Executive Officer", "name": "Timothy D. Cook", "pay": 16520856, "currencyPay": "USD", "gender": "male", "yearBorn": 1961, "titleSince": None, "active": True},
    {"title": "Former CFO", "name": "Luca Maestri", "pay": 7000000, "currencyPay": "USD", "gender": "male", "yearBorn": 1964, "titleSince": None, "active": False},
]
INSIDER = [
    {"symbol": "AAPL", "filingDate": "2026-10-30", "transactionDate": "2026-10-28", "reportingCik": "0001214156", "companyCik": "0000320193", "transactionType": "S-Sale", "formType": "4", "securitiesTransacted": 1000, "price": 330.1, "reportingName": "Cook Timothy D"},
    {"symbol": "AAPL", "filingDate": "2026-10-29", "transactionDate": "2026-10-27", "reportingCik": "0001214155", "companyCik": "0000320193", "transactionType": "P-Purchase", "formType": "3/A", "securitiesTransacted": 10, "price": 0, "reportingName": "Parekh Kevan"},
]
FILINGS = [
    {"symbol": "AAPL", "cik": "0000320193", "filingDate": "2026-10-31 00:00:00", "acceptedDate": "2026-10-31 06:01:36", "formType": "8-K", "hasFinancials": True, "link": "https://www.sec.gov/a", "finalLink": "https://www.sec.gov/b"},
    {"symbol": "MSFT", "cik": "0000789019", "filingDate": "2026-10-30 00:00:00", "acceptedDate": "2026-10-30 06:01:36", "formType": "10-Q", "hasFinancials": False, "link": "https://www.sec.gov/c", "finalLink": "https://www.sec.gov/d"},
]
SEC_PROFILE = [{"symbol": "AAPL", "cik": "0000320193", "registrantName": "Apple Inc.", "sicCode": "3571", "sicDescription": "Electronic Computers", "postalCode": "95014", "phone": "4089961010", "employees": "166000", "isEtf": False}]
