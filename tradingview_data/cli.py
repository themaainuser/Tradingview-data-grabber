"""Unified command-line interface and backwards-compatible script adapters."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Callable, Sequence

from .analytics import (
    OhlcvValidationError,
    data_quality_report,
    load_ohlcv,
    market_report,
    write_enriched_csv,
    write_report,
)
from .auth import get_auth_token
from .bars import BarStreamConfig, BarStreamer, parse_symbols
from .charts import generate_charts
from .quotes import QUOTE_FIELDS, QuoteStreamConfig, QuoteStreamer, format_quote
from .research import DEFAULT_BASE_URL, build_research, request_model_notes, write_research_dashboard


def _fields(value: str) -> tuple[str, ...]:
    fields = tuple(field.strip() for field in value.split(",") if field.strip())
    if not fields:
        raise argparse.ArgumentTypeError("provide at least one quote field")
    return fields


def _model_mapping(values: list[str] | None, option: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for value in values or []:
        model, separator, setting = value.partition("=")
        if not separator or not model.strip() or not setting.strip():
            raise ValueError(f"{option} values must use MODEL=VALUE")
        mapping[model.strip()] = setting.strip()
    return mapping


def _write_lines(path: str | None) -> tuple[Callable[[str], None], Callable[[], None]]:
    if path is None:
        return (lambda _: None), (lambda: None)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle = destination.open("a", encoding="utf-8")
    return (lambda line: handle.write(line + "\n")), handle.close


def _run_bars(args: argparse.Namespace) -> int:
    config = BarStreamConfig(
        symbols=parse_symbols(args.symbols),
        timeframe=args.timeframe,
        history_bars=args.bars,
        output=Path(args.output),
        layout=args.layout,
        timeout=args.timeout,
        max_retries=args.max_retries,
        silent=not args.verbose_protocol,
        once=args.once,
    )
    BarStreamer(config).run()
    return 0


def _run_quote(args: argparse.Namespace) -> int:
    write_line, close_output = _write_lines(args.output)

    def on_update(update: object) -> None:
        line = format_quote(update, args.format, price_only=args.price_only)  # type: ignore[arg-type]
        print(line)
        write_line(line)

    config = QuoteStreamConfig(
        symbols=parse_symbols(args.symbols),
        fields=args.fields,
        timeout=args.timeout,
        max_retries=args.max_retries,
        silent=not args.verbose_protocol,
        once=args.once,
        raw_output=Path(args.raw_output) if args.raw_output else None,
    )
    try:
        QuoteStreamer(config, on_update=on_update).run()
    finally:
        close_output()
    return 0


def _text_report(report: dict[str, object]) -> str:
    latest = report["latest"]
    performance = report["performance"]
    indicators = report["indicators"]
    signals = report["signals"]
    assert isinstance(latest, dict)
    assert isinstance(performance, dict)
    assert isinstance(indicators, dict)
    assert isinstance(signals, dict)
    return "\n".join(
        (
            f"Latest close: {latest['close']} at {latest['time']}",
            f"Period return: {performance['period_return_pct']}%",
            f"Support / resistance (20): {performance['support_20']} / {performance['resistance_20']}",
            f"RSI(14): {indicators['rsi_14']} ({signals['rsi']})",
            f"MACD: {signals['macd']}; trend: {signals['ema_trend']}",
            f"ATR(14): {indicators['atr_14']} ({indicators['atr_pct']}%)",
        )
    )


def _run_analyze(args: argparse.Namespace) -> int:
    data = load_ohlcv(args.file)
    report = market_report(data)
    if args.enriched_csv:
        write_enriched_csv(data, args.enriched_csv)
    if args.output:
        write_report(report, args.output)
    print(json.dumps(report, indent=2, sort_keys=True) if args.format == "json" else _text_report(report))
    return 0


def _run_validate(args: argparse.Namespace) -> int:
    report = data_quality_report(load_ohlcv(args.file))
    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        text_values = dict(report)
        text_values["gap_count"] = len(report["gaps"])
        print(
            "{valid_rows} valid bars from {start} to {end}; "
            "{dropped_rows} dropped, {duplicate_rows_collapsed} duplicates collapsed, {gap_count} gaps".format(**text_values)
        )
    return 0


def _run_chart(args: argparse.Namespace) -> int:
    for path in generate_charts(args.files, args.outdir, include_indicators=not args.no_indicators):
        print(f"saved {path}")
    return 0


def _run_research(args: argparse.Namespace) -> int:
    datasets = []
    for file in args.files:
        source = Path(file)
        datasets.append((source.stem, source, load_ohlcv(source)))
    report = build_research(
        datasets,
        fee_bps=args.fee_bps,
        periods_per_year=args.periods_per_year,
    )
    model_endpoints = _model_mapping(args.model_endpoint, "--model-endpoint")
    model_api_key_envs = _model_mapping(args.model_api_key_env, "--model-api-key-env")
    selected_models = set(args.model or [])
    unused_settings = (set(model_endpoints) | set(model_api_key_envs)) - selected_models
    if unused_settings:
        raise ValueError(
            f"model endpoint/key settings reference unselected model(s): {', '.join(sorted(unused_settings))}"
        )
    if args.model:
        report["model_notes"] = request_model_notes(
            report,
            args.model,
            base_url=args.base_url or os.environ.get("TVDATA_AI_BASE_URL", DEFAULT_BASE_URL),
            api_key_env=args.api_key_env,
            model_endpoints=model_endpoints,
            model_api_key_envs=model_api_key_envs,
            timeout=args.model_timeout,
        )
    dashboard = write_research_dashboard(report, args.outdir)
    print(f"saved {dashboard}")
    print(f"saved {Path(args.outdir) / 'research.json'}")
    return 0


def _run_auth(_: argparse.Namespace) -> int:
    get_auth_token()
    print("Authenticated token retrieved successfully. It was not written to disk.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the public ``tvdata`` command parser."""

    parser = argparse.ArgumentParser(
        prog="tvdata",
        description="Stream, validate, analyze, and chart TradingView OHLCV data.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    bars = commands.add_parser("bars", help="stream OHLCV bars to durable CSV files")
    bars.add_argument("-n", "--symbols", "--symbol", default="BINANCE:BTCUSDT", help="comma-separated symbols")
    bars.add_argument("-t", "--timeframe", default="1", help="TradingView interval, e.g. 1, 5, 60, 1D")
    bars.add_argument("-b", "--bars", type=int, default=300, help="history bars requested on connect")
    bars.add_argument("-o", "--output", default="data", help="output directory")
    bars.add_argument("--layout", choices=("by-timeframe", "flat"), default="by-timeframe")
    bars.add_argument("--timeout", type=int, default=30)
    bars.add_argument("--max-retries", type=int, default=5)
    bars.add_argument("--once", action="store_true", help="exit after every requested symbol has a persisted batch")
    bars.add_argument("--verbose-protocol", action="store_true", help="print raw websocket frames")
    bars.set_defaults(handler=_run_bars)

    quote = commands.add_parser("quote", help="stream parsed quote updates")
    quote.add_argument("-n", "--symbols", "--symbol", required=True, help="comma-separated symbols")
    quote.add_argument("--fields", type=_fields, default=QUOTE_FIELDS, help="comma-separated quote fields")
    quote.add_argument("--format", choices=("text", "json"), default="text")
    quote.add_argument("--price-only", action="store_true", help="print only the last price")
    quote.add_argument("-o", "--output", help="append rendered quote updates to this file")
    quote.add_argument("--raw-output", help="append raw websocket frames to this file")
    quote.add_argument("--timeout", type=int, default=30)
    quote.add_argument("--max-retries", type=int, default=5)
    quote.add_argument("--once", action="store_true", help="exit after every requested symbol has an update")
    quote.add_argument("--verbose-protocol", action="store_true", help="print raw websocket frames")
    quote.set_defaults(handler=_run_quote)

    analyze = commands.add_parser("analyze", help="calculate data-quality and technical reports")
    analyze.add_argument("file", help="OHLCV CSV created by the bars command")
    analyze.add_argument("--format", choices=("text", "json"), default="text")
    analyze.add_argument("-o", "--output", help="write the JSON report to this path")
    analyze.add_argument("--enriched-csv", help="write OHLCV rows plus indicators to this path")
    analyze.set_defaults(handler=_run_analyze)

    validate = commands.add_parser("validate", help="inspect OHLCV schema, duplicates, and gaps")
    validate.add_argument("file", help="OHLCV CSV created by the bars command")
    validate.add_argument("--format", choices=("text", "json"), default="text")
    validate.set_defaults(handler=_run_validate)

    chart = commands.add_parser("chart", help="create static charts and an offline gallery")
    chart.add_argument("files", nargs="+", help="one or more OHLCV CSV files")
    chart.add_argument("-o", "--outdir", default="charts")
    chart.add_argument("--no-indicators", action="store_true", help="skip the technical-indicators chart")
    chart.set_defaults(handler=_run_chart)

    research = commands.add_parser("research", help="backtest strategy permutations and build a quant dashboard")
    research.add_argument("files", nargs="+", help="one or more OHLCV CSV files")
    research.add_argument("-o", "--outdir", default="research", help="dashboard and JSON output directory")
    research.add_argument("--fee-bps", type=float, default=5, help="cost in basis points per position change")
    research.add_argument(
        "--periods-per-year",
        type=float,
        default=252,
        help="annualization factor for Sharpe, volatility, and CAGR; choose for your bar interval",
    )
    research.add_argument(
        "--model",
        action="append",
        help="optional OpenAI-compatible model ID; repeat to compare several models",
    )
    research.add_argument(
        "--base-url",
        help="model API base URL (or set TVDATA_AI_BASE_URL); defaults to local Ollama at localhost:11434",
    )
    research.add_argument(
        "--api-key-env",
        default="TVDATA_AI_API_KEY",
        help="environment variable name containing the endpoint API key (default: TVDATA_AI_API_KEY)",
    )
    research.add_argument(
        "--model-endpoint",
        action="append",
        metavar="MODEL=URL",
        help="override the API URL for one model; repeat to mix hosted and local endpoints",
    )
    research.add_argument(
        "--model-api-key-env",
        action="append",
        metavar="MODEL=ENV_VAR",
        help="select an API-key environment variable for one model; repeat as needed",
    )
    research.add_argument("--model-timeout", type=float, default=90, help="per-model request timeout in seconds")
    research.set_defaults(handler=_run_research)

    auth = commands.add_parser("auth", help="verify account credentials without writing a token")
    auth.set_defaults(handler=_run_auth)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the unified CLI and report clean user-facing data errors."""

    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except (OhlcvValidationError, ValueError, RuntimeError) as exc:
        parser.error(str(exc))
    return 2


def legacy_bars_main(argv: Sequence[str] | None = None) -> int:
    """Retain ``livestreamtest.py`` flags while delegating to the package."""

    parser = argparse.ArgumentParser(description="Stream TradingView live OHLCV bars to CSV")
    parser.add_argument("-n", "--symbols", "--symbol", default="BINANCE:BTCUSDT")
    parser.add_argument("-t", "--timeframe", default="1")
    parser.add_argument("-b", "--bars", type=int, default=300)
    parser.add_argument("-o", "--output", default="data")
    parser.add_argument("-s", "--silent", action="store_true")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--max-retries", type=int, default=5)
    args = parser.parse_args(argv)
    args.layout = "flat"
    args.timeout = 30
    args.verbose_protocol = not args.silent
    return _run_bars(args)


def legacy_quote_main(argv: Sequence[str] | None = None) -> int:
    """Retain ``main.py`` flags while using parsed quote sessions internally."""

    parser = argparse.ArgumentParser(description="Stream TradingView live quotes")
    parser.add_argument("-n", "--symbol", required=True)
    parser.add_argument("-s", "--silent", action="store_true", help="only print the latest price")
    parser.add_argument("-o", "--output", help="append raw frames to a file")
    parser.add_argument("-q", "--quit", action="store_true", help="exit after initial price updates")
    parser.add_argument("--max-retries", type=int, default=5)
    args = parser.parse_args(argv)

    def on_update(update: object) -> None:
        if args.silent:
            print(format_quote(update, price_only=True))  # type: ignore[arg-type]

    config = QuoteStreamConfig(
        symbols=parse_symbols(args.symbol),
        max_retries=args.max_retries,
        silent=args.silent,
        once=args.quit,
        require_price_for_once=True,
        raw_output=Path(args.output) if args.output else None,
    )
    QuoteStreamer(config, on_update=on_update).run()
    return 0


def legacy_charts_main(argv: Sequence[str] | None = None) -> int:
    """Retain ``visuals.py`` usage while gaining safe multi-file outputs."""

    parser = argparse.ArgumentParser(description="Turn captured OHLCV CSVs into charts and a dashboard")
    parser.add_argument("files", nargs="+", help="captured CSV files")
    parser.add_argument("-o", "--outdir", default="charts")
    parser.add_argument("--no-indicators", action="store_true")
    args = parser.parse_args(argv)
    return _run_chart(args)


def legacy_auth_main(argv: Sequence[str] | None = None) -> int:
    """Retain the old authentication script without displaying the token."""

    parser = argparse.ArgumentParser(
        description="Retrieve a TradingView session token without printing or storing it"
    )
    parser.parse_args(argv)
    try:
        get_auth_token()
    except (ValueError, RuntimeError) as exc:
        parser.error(str(exc))
    print("Authenticated token retrieved successfully. Set TV_AUTH_TOKEN before streaming.")
    return 0
