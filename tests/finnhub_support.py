"""Hand-made Finnhub payloads in the shapes the live API returns (checked against real responses), and a fake HTTP
layer that records headers."""

from __future__ import annotations

import json
from typing import Any

from providers_support import FakeHttp as _FakeHttp
from tradingview_data.providers.common import HttpResult


class FakeHttp(_FakeHttp):
    """Like the shared fake, but Finnhub sends its key in a header, so the calls record headers too."""

    def __init__(self, *script: Any, **kwargs: Any) -> None:
        super().__init__(*script, **kwargs)
        self.headers: list[dict[str, str]] = []

    def __call__(self, url: str, params: list[tuple[str, str]], headers: "dict[str, str] | None" = None) -> HttpResult:
        self.headers.append(dict(headers or {}))
        return super().__call__(url, params)


def error(status: int, message: str) -> HttpResult:
    return HttpResult(status, json.dumps({"error": message}).encode(), "application/json; charset=utf-8")


def raw(status: int, body: str, content_type: str = "text/html; charset=utf-8") -> HttpResult:
    return HttpResult(status, body.encode(), content_type)


INVALID_KEY = error(401, "Invalid API key.")
NO_KEY = error(401, "Please use an API key.")
NO_ACCESS = error(403, "You don't have access to this resource.")
NO_ACCESS_401 = error(401, "You don't have access to this resource.")  # a non-US exchange on a free key
CFD_INDEX = error(200, "Market data subscription required for CFD indices.")
LIMIT_REACHED = error(429, "API limit reached. Please try again later. Remaining Limit: 0")
MISSING_PARAMETER = error(422, "Missing parameter symbol")
HTML_PAGE = raw(200, "<!DOCTYPE html><html><body>Finnhub</body></html>")
SERVER_ERROR = raw(502, "<html><body>Bad gateway</body></html>")

QUOTE = {"c": 331.9, "d": -6.42, "dp": -1.8976, "h": 334.5, "l": 325.33, "o": 325.58, "pc": 338.32, "t": 1793739600}
BLANK_QUOTE = {"c": 0, "d": None, "dp": None, "h": 0, "l": 0, "o": 0, "pc": 0, "t": 0}

PROFILE2 = {
    "country": "US", "currency": "USD", "estimateCurrency": "USD", "exchange": "NASDAQ NMS - GLOBAL MARKET", "finnhubIndustry": "Technology",
    "ipo": "1980-12-12", "logo": "https://static2.finnhub.io/file/publicdatany/finnhubimage/stock_logo/AAPL.png", "marketCapitalization": 4843808.343143874,
    "name": "Apple Inc.", "phone": "14089961010", "shareOutstanding": 14594.18, "ticker": "AAPL", "weburl": "https://www.apple.com/", "floatingShare": 14352.36,
}

NEWS = [
    {"category": "company", "datetime": 1793786451, "headline": "Why the blue wave could be good for Apple", "id": 143479725, "image": "https://s.yimg.com/x.png", "related": "AAPL", "source": "Yahoo", "summary": "Apple is seen as an <b>early</b> winner.", "url": "https://finnhub.io/api/news?id=6d59"},
    {"category": "company", "datetime": 1793700000, "headline": "Apple and Microsoft rally", "id": 143479700, "image": "", "related": "AAPL,MSFT", "source": "Reuters", "summary": "", "url": "javascript:alert(1)"},
]


def _points(*values: float, periods: tuple[str, ...] = ("2026-09-26", "2025-09-27", "2024-09-28")) -> list[dict[str, Any]]:
    return [{"period": p, "v": v} for p, v in zip(periods, values)]


METRIC = {
    "metric": {"10DayAverageTradingVolume": 42.13432, "52WeekHigh": 351.73, "52WeekHighDate": "2026-10-23", "peTTM": 36.6817, "roeTTM": 127.61, "grossMarginTTM": 48.79, "marketCapitalization": 4848405.5},
    "metricType": "all",
    "series": {
        "annual": {"eps": _points(8.9791, 7.465, 6.0766), "grossMargin": _points(0.4879, 0.4691, 0.4621), "operatingMargin": _points(0.3301, 0.3197, 0.3151), "netMargin": _points(0.276, 0.2692, 0.2397)},
        "quarterly": {"eps": _points(2.05, 1.65, periods=("2026-09-26", "2026-06-27"))},
    },
    "symbol": "AAPL",
}

FINANCIALS_REPORTED = {
    "cik": "320193",
    "data": [
        {
            "accessNumber": "0000320193-25-000079", "symbol": "AAPL", "cik": "320193", "year": 2025, "quarter": 0, "form": "10-K",
            "startDate": "2024-09-29 00:00:00", "endDate": "2025-09-27 00:00:00", "filedDate": "2025-10-31 00:00:00", "acceptedDate": "2025-10-31 06:01:26",
            "report": {
                "ic": [{"concept": "us-gaap_RevenueFromContractWithCustomerExcludingAssessedTax", "unit": "usd", "label": "Net sales", "value": 416161000000.0}, {"concept": "us-gaap_EarningsPerShareDiluted", "unit": "usdPerShare", "label": "Diluted", "value": 7.46}],
                "bs": [{"concept": "us-gaap_Assets", "unit": "usd", "label": "Total assets", "value": 359241000000.0}],
                "cf": [],
            },
        },
        {
            "accessNumber": "0000320193-25-000073", "symbol": "AAPL", "cik": "320193", "year": 2025, "quarter": 3, "form": "10-Q",
            "startDate": "2025-03-30 00:00:00", "endDate": "2025-06-28 00:00:00", "filedDate": "2025-08-01 00:00:00", "acceptedDate": "2025-08-01 06:02:31",
            "report": {"ic": [{"concept": "us-gaap_RevenueFromContractWithCustomerExcludingAssessedTax", "unit": "usd", "label": "Total net sales", "value": 94036000000.0}], "bs": [], "cf": []},
        },
    ],
    "symbol": "AAPL",
}

RECOMMENDATIONS = [
    {"symbol": "AAPL", "period": "2026-11-01", "strongBuy": 11, "buy": 19, "hold": 15, "sell": 3, "strongSell": 1},
    {"symbol": "AAPL", "period": "2026-10-01", "strongBuy": 10, "buy": 20, "hold": 14, "sell": 2, "strongSell": 1},
]

EARNINGS = [
    {"actual": 2.05, "estimate": 2.0267, "period": "2026-09-30", "quarter": 4, "surprise": 0.0233, "surprisePercent": 1.1497, "symbol": "AAPL", "year": 2026},
    {"actual": 1.57, "estimate": 1.6, "period": "2026-06-30", "quarter": 3, "surprise": -0.03, "surprisePercent": -1.875, "symbol": "AAPL", "year": 2026},
]

INSIDER_SENTIMENT = {
    "data": [
        {"symbol": "TSLA", "year": 2026, "month": 2, "change": 5000, "mspr": 12.5},
        {"symbol": "TSLA", "year": 2026, "month": 1, "change": -107000, "mspr": -33.333332},
    ],
    "symbol": "TSLA",
}

INSIDER_TRANSACTIONS = {
    "data": [
        {"name": "Taneja Vaibhav", "share": 25972, "change": -2606, "filingDate": "2026-09-09", "transactionDate": "2026-09-08", "transactionCode": "S", "transactionPrice": 360.134, "id": "000177", "symbol": "TSLA", "source": "sec", "isDerivative": False, "currency": "USD"},
        {"name": "Musk Elon", "share": 411062076, "change": 2500000, "filingDate": "2026-09-15", "transactionDate": "2026-09-12", "transactionCode": "P", "transactionPrice": 395.94, "id": "000178", "symbol": "TSLA", "source": "sec", "isDerivative": True, "currency": "USD"},
    ],
    "symbol": "TSLA",
}

VISAS = {"data": [{"symbol": "AAPL", "year": 2026, "quarter": 1, "caseNumber": "I-200-25356-500794", "worksitePostalCode": "02134", "wageRangeFrom": 185224, "receivedDate": "2025-12-22"}], "symbol": "AAPL"}

EARNINGS_CALENDAR = {
    "earningsCalendar": [
        {"date": "2026-11-19", "epsActual": None, "epsEstimate": -0.0612, "hour": "bmo", "quarter": 3, "revenueActual": None, "revenueEstimate": 871590, "symbol": "ARBE", "year": 2026},
        {"date": "2026-11-20", "epsActual": None, "epsEstimate": 1.2, "hour": "amc", "quarter": 3, "revenueActual": None, "revenueEstimate": 1000000, "symbol": "XYZ", "year": 2026},
    ]
}

DAY = 86400
CANDLES = {"c": [221.0, 223.0, 222.5], "h": [222.0, 224.0, 223.5], "l": [219.0, 221.0, 221.5], "o": [220.0, 221.5, 223.0], "s": "ok", "t": [1793664000, 1793664000 + DAY, 1793664000 + 2 * DAY], "v": [1000, 3000, 2000]}
INTRADAY = {**CANDLES, "t": [1793710800, 1793710800 + 300, 1793710800 + 600]}
INDICATOR = {**CANDLES, "sma": [None, 222.0, 222.8]}
BOND_PRICE = {"c": [98.1, 98.4], "s": "ok", "t": [1793664000, 1793664000 + DAY]}
NO_DATA = {"s": "no_data"}

PEERS = ["AAPL", "DELL", "HPQ"]
MARKET_STATUS = {"exchange": "US", "holiday": None, "isOpen": False, "session": "pre-market", "t": 1793790936, "timezone": "America/New_York"}
FDA = [
    {"fromDate": "2026-11-19 09:00:00", "toDate": "2026-11-19 16:00:00", "eventDescription": "Microbiology Devices Panel", "url": "https://www.fda.gov/advisory"},
    {"fromDate": "2026-12-03 10:00:00", "toDate": "2026-12-03 17:00:00", "eventDescription": "Oncologic Drugs Advisory Committee", "url": "https://www.fda.gov/odac"},
]
