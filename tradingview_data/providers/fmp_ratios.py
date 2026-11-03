"""Ratio and growth fields FMP sends as plain fractions (``0.469``), and what each one is a share of.

The Providers page shows them as a percentage that names its base, with FMP's own figure in brackets:
``46.91% of revenue (0.4691)``, ``+6.43% vs prior period (0.0643)``. Multiples (price to earnings, turnover, coverage,
days, per-share amounts) are not shares of anything and stay numbers.

A field is listed only when its definition is settled; an unlisted ratio is shown as FMP sent it rather than guessed at.
"""

from __future__ import annotations

from decimal import Decimal
from typing import NamedTuple, Optional


class Ratio(NamedTuple):
    label: str
    phrase: str  # what the percentage is a share of ("of revenue") or a change against ("vs prior period")
    signed: bool  # a change shows its sign
    scale: float  # 100 for a fraction; 1 for a field FMP already sends as a percentage


def _share(label: str, base: str, scale: float = 100.0) -> Ratio:
    return Ratio(label, f"of {base}", False, scale)


def _change(label: str, against: str = "vs prior period") -> Ratio:
    return Ratio(label, against, True, 100.0)


_SPEC: dict[str, Ratio] = {
    # margins
    "grossProfitMargin": _share("Gross profit margin", "revenue"),
    "ebitMargin": _share("EBIT margin", "revenue"),
    "ebitdaMargin": _share("EBITDA margin", "revenue"),
    "operatingProfitMargin": _share("Operating profit margin", "revenue"),
    "pretaxProfitMargin": _share("Pre-tax profit margin", "revenue"),
    "continuousOperationsProfitMargin": _share("Continuing operations margin", "revenue"),
    "netProfitMargin": _share("Net profit margin", "revenue"),
    "bottomLineProfitMargin": _share("Bottom-line margin", "revenue"),
    "operatingCashFlowSalesRatio": _share("Operating cash flow to sales", "revenue"),
    # liquidity and leverage
    "currentRatio": _share("Current ratio", "current liabilities"),
    "quickRatio": _share("Quick ratio", "current liabilities"),
    "cashRatio": _share("Cash ratio", "current liabilities"),
    "operatingCashFlowRatio": _share("Operating cash flow ratio", "current liabilities"),
    "debtToAssetsRatio": _share("Debt to assets", "total assets"),
    "debtToEquityRatio": _share("Debt to equity", "shareholders' equity"),
    "debtToCapitalRatio": _share("Debt to capital", "total capital"),
    "longTermDebtToCapitalRatio": _share("Long-term debt to capital", "total capital"),
    "debtToMarketCap": _share("Debt to market cap", "market cap"),
    "freeCashFlowOperatingCashFlowRatio": _share("Free cash flow to operating cash flow", "operating cash flow"),
    # payouts, yields, tax
    "dividendPayoutRatio": _share("Dividend payout", "net income"),
    "dividendYield": _share("Dividend yield", "share price"),
    "dividendYieldPercentage": _share("Dividend yield, FMP's percentage field", "share price", scale=1.0),
    "effectiveTaxRate": _share("Effective tax rate", "pre-tax income"),
    # returns and cost shares
    "returnOnAssets": _share("Return on assets", "total assets"),
    "operatingReturnOnAssets": _share("Operating return on assets", "total assets"),
    "returnOnTangibleAssets": _share("Return on tangible assets", "tangible assets"),
    "returnOnEquity": _share("Return on equity", "shareholders' equity"),
    "returnOnInvestedCapital": _share("Return on invested capital", "invested capital"),
    "returnOnCapitalEmployed": _share("Return on capital employed", "capital employed"),
    "earningsYield": _share("Earnings yield", "market cap"),
    "freeCashFlowYield": _share("Free cash flow yield", "market cap"),
    "capexToOperatingCashFlow": _share("Capex to operating cash flow", "operating cash flow"),
    "capexToRevenue": _share("Capex to revenue", "revenue"),
    "salesGeneralAndAdministrativeToRevenue": _share("SG&A to revenue", "revenue"),
    "researchAndDevelopementToRevenue": _share("R&D to revenue", "revenue"),
    "stockBasedCompensationToRevenue": _share("Stock-based compensation to revenue", "revenue"),
    "intangiblesToTotalAssets": _share("Intangibles to total assets", "total assets"),
    # growth against the previous period
    "revenueGrowth": _change("Revenue growth"),
    "grossProfitGrowth": _change("Gross profit growth"),
    "ebitgrowth": _change("EBIT growth"),
    "ebitdaGrowth": _change("EBITDA growth"),
    "operatingIncomeGrowth": _change("Operating income growth"),
    "netIncomeGrowth": _change("Net income growth"),
    "epsgrowth": _change("EPS growth"),
    "epsdilutedGrowth": _change("Diluted EPS growth"),
    "weightedAverageSharesGrowth": _change("Share count growth"),
    "weightedAverageSharesDilutedGrowth": _change("Diluted share count growth"),
    "dividendsPerShareGrowth": _change("Dividend per share growth"),
    "operatingCashFlowGrowth": _change("Operating cash flow growth"),
    "freeCashFlowGrowth": _change("Free cash flow growth"),
    "receivablesGrowth": _change("Receivables growth"),
    "inventoryGrowth": _change("Inventory growth"),
    "assetGrowth": _change("Asset growth"),
    "bookValueperShareGrowth": _change("Book value per share growth"),
    "debtGrowth": _change("Debt growth"),
    "rdexpenseGrowth": _change("R&D expense growth"),
    "sgaexpensesGrowth": _change("SG&A expense growth"),
    "growthCapitalExpenditure": _change("Capital expenditure growth"),
}

_YEARS = {"three": 3, "five": 5, "ten": 10}
_PER_SHARE = {"Revenue": "Revenue", "OperatingCF": "Operating cash flow", "NetIncome": "Net income", "ShareholdersEquity": "Shareholders' equity", "DividendperShare": "Dividend", "BottomLineNetIncome": "Bottom-line net income"}
for _word, _years in _YEARS.items():
    for _name, _label in _PER_SHARE.items():
        _key = f"{_word}Y{_name}GrowthPerShare" if _name != "DividendperShare" else f"{_word}YDividendperShareGrowthPerShare"
        _SPEC[_key] = _change(f"{_label} growth per share", f"over {_years} years")


def lookup(field: str) -> Optional[Ratio]:
    """The spec of a field, with or without FMP's ``TTM`` suffix."""

    spec = _SPEC.get(field)
    if spec is None and field.endswith("TTM"):
        spec = _SPEC.get(field[:-3])
    return spec


def original(value: float) -> str:
    """FMP's figure with every digit it sent, never in exponent form: ``repr`` is the shortest text that reads back as the same number."""

    return "0" if value == 0 else format(Decimal(repr(float(value))).normalize(), "f")


def percent(field: str, value: float) -> Optional[float]:
    spec = lookup(field)
    return None if spec is None else value * spec.scale


def short_text(field: str, value: float) -> Optional[str]:
    """``46.91% (0.4691)``: the percentage, then FMP's own figure."""

    spec = lookup(field)
    if spec is None:
        return None
    shown = value * spec.scale
    return f"{shown:+.2f}% ({original(value)})" if spec.signed else f"{shown:.2f}% ({original(value)})"


def text(field: str, value: float) -> Optional[str]:
    """``46.91% of revenue (0.4691)``: the same with what it is a share of."""

    spec = lookup(field)
    short = short_text(field, value)
    if spec is None or short is None:
        return None
    head, _, tail = short.partition(" ")
    return f"{head} {spec.phrase} {tail}"


def item_label(field: str) -> str:
    """``Gross profit margin (% of revenue)``: the row heading of a table that holds the percentages."""

    spec = lookup(field)
    return field if spec is None else f"{spec.label} (% {spec.phrase})"
