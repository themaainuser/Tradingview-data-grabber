"""Hand-made Marketstack payloads in the shapes the OpenAPI document declares, one per endpoint."""

from __future__ import annotations

from typing import Any

PAGE = {"limit": 100, "offset": 0, "count": 3, "total": 3}


def bar(symbol: str, day: str, close: float, **extra: Any) -> dict[str, Any]:
    return {
        "open": close - 1, "high": close + 2, "low": close - 2, "close": close, "volume": 1000.0 + close,
        "adj_high": close + 2, "adj_low": close - 2, "adj_close": close, "adj_open": close - 1, "adj_volume": 1000.0,
        "split_factor": 1.0, "dividend": 0.0, "name": "Apple Inc", "exchange_code": "NASDAQ", "asset_type": "Stock",
        "price_currency": "usd", "symbol": symbol, "exchange": "XNAS", "date": f"{day}T00:00:00+0000", **extra,
    }


def tick(symbol: str, when: str, close: float, **extra: Any) -> dict[str, Any]:
    return {
        "open": close - 0.5, "high": close + 1, "low": close - 1, "mid": None, "last_size": None, "bid_size": None,
        "bid_price": None, "ask_price": None, "ask_size": None, "last": None, "close": close, "volume": 500.0,
        "marketstack_last": close, "symbol": symbol, "exchange": "IEXG", "date": when, **extra,
    }


EOD_ROWS = [bar("AAPL", "2026-09-29", 221.0), bar("AAPL", "2026-09-28", 220.0), bar("AAPL", "2026-09-25", 218.0)]
TICK_ROWS = [tick("AAPL", "2026-09-29T15:30:00+0000", 221.5), tick("AAPL", "2026-09-29T14:30:00+0000", 220.5), tick("AAPL", "2026-09-29T13:30:00+0000", 219.5)]

EXCHANGE = {
    "name": "NASDAQ Stock Market", "acronym": "NASDAQ", "mic": "XNAS", "country": "USA", "country_code": "US", "city": "New York",
    "website": "www.nasdaq.com", "operating_mic": "XNAS", "oprt_sgmt": "OPRT", "legal_entity_name": "NASDAQ STOCK MARKET LLC",
    "exchange_lei": "549300L7MZFMZ6RPQM71", "market_category_code": "SRSP", "exchange_status": "ACTIVE",
    "date_creation": "2005-01-01", "date_last_update": "2024-02-01", "date_last_validation": "2024-02-01", "date_expiry": None, "comments": None,
}
TICKER_EXCHANGE = {**EXCHANGE, "date_creation": {"date": "2005-01-01 00:00:00.000000", "timezone_type": 3, "timezone": "UTC"}, "date_expiry": {"date": None}}

COMMODITY = {
    "commodity_name": "aluminum", "commodity_unit": "usd/t", "commodity_price": "2,650.5", "price_change_day": "12.5", "percentage_day": "0.47%",
    "percentage_week": "-1.2%", "percentage_month": "3.4%", "percentage_year": "8.1%", "quarter1_25": "2500", "quarter2_25": "2550",
    "quarter3_25": "2600", "quarter4_25": "2650", "datetime": "2026-09-29 15:00:00",
}
FILING = {"accession_number": ["0001-26-000001", "0001-26-000002"], "filing_date": ["2026-08-01", "2026-05-02"], "report_date": ["2026-06-30", "2026-03-31"],
          "form": ["10-Q", "10-Q"], "size": [1000, 2000], "primary_document": ["a.htm", "b.htm"], "primary_doc_description": ["10-Q", "10-Q"]}

SAMPLES: dict[str, Any] = {
    "exchanges": {"pagination": PAGE, "data": [EXCHANGE, {**EXCHANGE, "name": "NYSE", "mic": "XNYS", "acronym": "NYSE"}]},
    "exchange": {"data": EXCHANGE},
    "exchange_eod": {"pagination": PAGE, "data": {**EXCHANGE, "eod": EOD_ROWS}},
    "exchange_eod_latest": {"pagination": PAGE, "data": {**EXCHANGE, "eod": EOD_ROWS[:1]}},
    "exchange_eod_date": {"pagination": PAGE, "data": {**EXCHANGE, "eod": EOD_ROWS[:1]}},
    "exchange_intraday": {"pagination": PAGE, "data": TICK_ROWS},
    "exchange_intraday_latest": {"pagination": PAGE, "data": TICK_ROWS[:1]},
    "exchange_intraday_date": {"pagination": PAGE, "data": TICK_ROWS},
    "exchange_tickers": {"pagination": PAGE, "data": {**EXCHANGE, "tickers": [{"name": "Apple Inc", "symbol": "AAPL", "has_intraday": True, "has_eod": True}, {"name": "Microsoft", "symbol": "MSFT", "has_intraday": False, "has_eod": True}]}},
    "ticker": {"name": "Apple Inc", "symbol": "AAPL", "cik": "0000320193", "isin": "US0378331005", "cusip": "037833100", "ein_employer_id": "942404110", "lei": None, "series_id": None, "item_type": "equity", "sector": "Technology", "industry": "Consumer Electronics", "sic_code": "3571", "sic_name": "Electronic Computers", "stock_exchange": TICKER_EXCHANGE},
    "ticker_eod": {"pagination": PAGE, "data": {"name": "Apple Inc", "symbol": "AAPL", "has_intraday": True, "has_eod": True, "country": "USA", "eod": EOD_ROWS}},
    "ticker_eod_latest": EOD_ROWS[0],
    "ticker_eod_date": EOD_ROWS[0],
    "ticker_intraday": {"pagination": PAGE, "data": {"name": "Apple Inc", "symbol": "AAPL", "has_intraday": True, "has_eod": True, "country": "USA", "intraday": TICK_ROWS}},
    "ticker_intraday_latest": TICK_ROWS[0],
    "ticker_intraday_date": {"pagination": PAGE, "data": {"name": "Apple Inc", "symbol": "AAPL", "intraday": TICK_ROWS}},
    "ticker_splits": {"pagination": PAGE, "data": [{"date": "2020-08-31", "split_factor": 4.0, "stock_split": "4-for-1", "symbol": "AAPL"}, {"date": "2014-06-09", "split_factor": 7.0, "stock_split": "7-for-1", "symbol": "AAPL"}]},
    "ticker_dividends": {"pagination": PAGE, "data": [{"date": "2026-08-11", "dividend": 0.25, "payment_date": "2026-08-14", "record_date": "2026-08-11", "declaration_date": "2026-07-31", "distr_freq": "quarterly", "symbol": "AAPL"}, {"date": "2026-05-12", "dividend": 0.24, "payment_date": "2026-05-15", "record_date": "2026-05-12", "declaration_date": "2026-05-01", "distr_freq": "quarterly", "symbol": "AAPL"}]},
    "eod": {"pagination": PAGE, "data": EOD_ROWS + [bar("MSFT", "2026-09-29", 450.0), bar("MSFT", "2026-09-28", 448.0)]},
    "eod_latest": {"pagination": PAGE, "data": [bar("AAPL", "2026-09-29", 221.0), bar("MSFT", "2026-09-29", 450.0)]},
    "eod_date": {"pagination": PAGE, "data": [bar("AAPL", "2026-09-29", 221.0)]},
    "intraday": {"pagination": PAGE, "data": TICK_ROWS},
    "intraday_latest": {"pagination": PAGE, "data": TICK_ROWS[:1]},
    "intraday_date": {"pagination": PAGE, "data": TICK_ROWS},
    "timezones": {"pagination": PAGE, "data": [{"timezone": "America/New_York", "abbr": "EST", "abbr_dst": "EDT"}, {"timezone": "Europe/London", "abbr": "GMT", "abbr_dst": "BST"}]},
    "currencies": {"pagination": PAGE, "data": [{"code": "USD", "name": "US Dollar", "symbol": "$", "symbol_native": "$"}, {"code": "EUR", "name": "Euro", "symbol": "€", "symbol_native": "€"}]},
    "splits": {"pagination": PAGE, "data": [{"date": "2020-08-31", "split_factor": 4.0, "stock_split": "4-for-1", "symbol": "AAPL"}, {"date": "2022-08-25", "split_factor": 3.0, "stock_split": "3-for-1", "symbol": "TSLA"}]},
    "dividends": {"pagination": PAGE, "data": [{"date": "2026-08-11", "dividend": 0.25, "payment_date": "2026-08-14", "record_date": "2026-08-11", "declaration_date": "2026-07-31", "distr_freq": "quarterly", "symbol": "AAPL"}, {"date": "2026-05-12", "dividend": 0.24, "payment_date": None, "record_date": None, "declaration_date": None, "distr_freq": "quarterly", "symbol": "AAPL"}]},
    "tickerslist": {"pagination": PAGE, "data": [{"name": "Apple Inc", "ticker": "AAPL", "has_intraday": True, "has_eod": True, "stock_exchange": TICKER_EXCHANGE}]},
    "tickerinfo": {"data": {"name": "Apple Inc", "ticker": "AAPL", "item_type": "equity", "sector": "Technology", "industry": "Consumer Electronics", "exchange_code": "NASDAQ", "full_time_employees": "164000", "ipo_date": "1980-12-12", "date_founded": "1976", "key_executives": [{"name": "Tim Cook", "salary": "3000000", "function": "CEO", "exercised": "0", "birth_year": "1960"}], "incorporation": "CA", "incorporation_description": "California", "start_fiscal": "0101", "end_fiscal": "1231", "mission": None, "vision": None, "previous_names": ["Apple Computer Inc"], "post_address": {"city": "Cupertino", "street1": "One Apple Park Way", "postal_code": "95014"}, "stock_exchanges": [{"exchange_name": "NASDAQ", "acronym1": "NASDAQ", "exchange_mic": "XNAS", "alpha2_code": "US", "country": "USA", "city": "New York", "website": "www.nasdaq.com"}], "reporting_currency": "USD", "address": {"city": "Cupertino", "street1": "One Apple Park Way"}, "phone": "408-996-1010", "website": "https://www.apple.com", "about": "Designs consumer electronics."}},
    "companyratings": {"status": {"code": 200, "message": "ok", "details": ""}, "result": {"basics": {"company_name": "Apple Inc", "ticker": "AAPL"}, "output": {"analyst_consensus": {"consensus_conclusion": "Buy", "stock_price": "221", "analyst_average": "250", "analyst_highest": "300", "analyst_lowest": "180", "analysts_number": "30", "buy": "20", "hold": "8", "sell": "2", "consensus_date": "2026-09-29"}, "analysts": [{"analyst_name": "Jane Doe", "analyst_firm": "Bank", "analyst_role": "Analyst", "rating": {"date_rating": "2026-09-01", "target_date": "2027-09-01", "price_target": "260", "rated": "buy", "conclusion": "Buy"}}]}}},
    "indexlist": {"pagination": PAGE, "data": [{"benchmark": "sp500"}, {"benchmark": "dowjones"}]},
    "indexinfo": [{"benchmark": "sp500", "region": "North America", "country": "United States", "price": "5,123.45", "price_change_day": "10.2", "percentage_day": "0.2%", "percentage_week": "-0.5%", "percentage_month": "2.1%", "percentage_year": "18.4%", "date": "2026-09-29"}],
    "bondlist": {"pagination": PAGE, "data": [{"country": "united states"}, {"country": "germany"}]},
    "bond": {"pagination": PAGE, "data": [{"region": "North America", "country": "united states", "type": "10Y", "yield": "4.2%", "price_change_day": "0.02", "percentage_week": "1.0%", "percentage_month": "-2.0%", "percentage_year": "5.0%", "date": "2026-09-29"}]},
    "etflist": {"pagination": PAGE, "data": [{"ticker": "SPY"}, {"ticker": "QQQ"}]},
    "etfholdings": {"basics": {"fund_name": "Example ETF", "file_number": "811-1", "cik": "0000001", "reg_lei": "LEI1"}, "output": {"attributes": {"series_name": "Example", "series_id": "S1", "series_lei": "L1", "ticker": "EXM", "isin": "US0000000001", "date_report_period": "2026-06-30", "end_report_period": "2026-12-31", "final_filing": False}, "signature": {"date_signed": "2026-08-01", "name_of_applicant": "Example Trust", "signature": "A. Person", "signer_name": "A. Person", "title": "Treasurer"}, "holdings": [{"investment_security": {"name": "Apple Inc", "title": "Common", "currency": "USD", "value_usd": "1000000", "percent_value": "7.5", "balance": "5000", "units": "NS", "asset_category": "EC", "invested_country": "US", "isin": "US0378331005"}}, {"investment_security": {"name": "Microsoft", "title": "Common", "currency": "USD", "value_usd": "900000", "percent_value": "6.8", "balance": "2000", "units": "NS", "asset_category": "EC", "invested_country": "US"}}]}},
    "stockprice": {"data": [{"exchange_code": "XNAS", "exchange_name": "NASDAQ", "country": "USA", "ticker": "AAPL", "price": "221.5", "currency": "USD", "trade_last": "2026-09-29 20:00:00"}]},
    "commodities": {"data": [COMMODITY]},
    "commoditieshistory": {"result": {"basics": {"frequency": "day"}, "data": [{"commodity_name": "aluminum", "commodity_unit": "usd/t", "commodity_prices": [{"commodity_price": "2600", "date": "2026-09-25"}, {"commodity_price": "2620.5", "date": "2026-09-26"}, {"commodity_price": "2650", "date": "2026-09-29"}]}]}},
    "company_name": {"data": {"cik_code": "0001045810", "company_name": "NVIDIA", "ein": "943177549", "sic": "3674", "sic_description": "Semiconductors", "phone": "9899990001", "incorporation_state": "DE", "addresses": {"mailing": {"street1": "2788 SAN TOMAS EXPRESSWAY", "street2": None, "city": "SANTA CLARA", "state_or_country": "CA", "zip_code": "95051"}, "business": {"street1": "2788 SAN TOMAS EXPRESSWAY", "city": "SANTA CLARA", "state_or_country": "CA", "zip_code": "95051"}}}},
    "cik_code": {"pagination": PAGE, "data": [{"cik_code": "1045810", "company_name": "NVIDIA", "ein": "943177549", "sic": "3674", "sic_description": "Semiconductors"}]},
    "company_facts": {"data": {"cik": 1467858, "company_name": "GENERAL MOTORS", "facts": {"dei": {"EntityCommonStockSharesOutstanding": {"label": "Shares outstanding", "description": "d", "units": {"shares": [{"end": "2009-08-17", "val": 547800000, "accn": "a", "fy": 2009, "fp": "Q2", "form": "10-Q", "filed": "2009-08-20"}]}}}, "us-gaap": {"AccountsPayableCurrent": {"label": "Accounts Payable", "units": {"USD": [{"end": "2020-12-31", "val": 100, "fy": 2020, "fp": "FY", "form": "10-K", "filed": "2021-02-01"}, {"end": "2021-12-31", "val": 120, "fy": 2021, "fp": "FY", "form": "10-K", "filed": "2022-02-01"}]}}}}}},
    "concept_accounts_payable": {"data": {"cik": 1467858, "company_name": "GENERAL MOTORS", "us-gaap": {"AccountsPayableCurrent": {"label": "Accounts Payable, Current", "description": "d", "units": {"USD": [{"end": "2020-12-31", "val": 100, "accn": "a", "fy": 2020, "fp": "FY", "form": "10-K", "filed": "2021-02-01", "frame": "CY2020Q4I"}, {"end": "2021-12-31", "val": 120, "accn": "b", "fy": 2021, "fp": "FY", "form": "10-K", "filed": "2022-02-01", "frame": "CY2021Q4I"}]}}}}},
    "submissions": {"data": {"cik_code": "0001045810", "company_name": "NVIDIA CORP", "entity_type": "operating", "ein": "943177549", "sic": "3674", "sic_description": "Semiconductors", "owner_org": "04 Manufacturing", "tickers": ["NVDA"], "exchanges": ["Nasdaq"], "description": "", "website": "", "fiscal_year_end": "0131", "phone": "408", "addresses": {"mailing": {"street1": "2788 SAN TOMAS", "city": "SANTA CLARA", "state_or_country_desc": "CA", "zip_code": "95051"}}, "former_names": [{"name": "NVIDIA", "from": "1993", "to": "1999"}], "filings": {"recent": FILING, "files": [{"name": "CIK-submissions-001.json", "filing_count": 100, "filing_from": "1999-01-01", "filing_to": "2020-01-01"}]}}},
    "frames_accounts_payable": {"pagination": PAGE, "data": {"taxonomy": "us-gaap", "tag": "AccountsPayableCurrent", "ccp": "CY2023Q1I", "uom": "USD", "label": "Accounts Payable, Current", "description": "d", "frame_data": [{"accn": "a", "cik": 1, "entityName": "Alpha", "end": "2023-03-31", "val": 500}, {"accn": "b", "cik": 2, "entityName": "Beta", "end": "2023-03-31", "val": 900}]}},
}


def error(type_: str, code: Any, info: str) -> dict[str, Any]:
    return {"success": False, "error": {"code": code, "type": type_, "info": info}}
