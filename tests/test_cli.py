import argparse
import csv
import io
import json
import pathlib
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from tradingview_data.cli import build_parser, legacy_auth_main, main
from tradingview_data.storage import CSV_COLUMNS, CSV_TIME_FORMAT


class CliTests(unittest.TestCase):
    def _csv(self, path):
        with path.open("w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(CSV_COLUMNS)
            for index in range(25):
                time = datetime.fromtimestamp(1704067200 + index * 60, ZoneInfo("Asia/Kolkata"))
                writer.writerow([f"[{index}]", time.strftime(CSV_TIME_FORMAT), 100 + index, 102 + index, 99 + index, 101 + index, 10])

    def test_parser_has_modular_subcommands_and_bar_defaults(self):
        parser = build_parser()
        args = parser.parse_args(["bars"])
        self.assertEqual(args.symbols, "BINANCE:BTCUSDT")
        self.assertEqual(args.layout, "by-timeframe")
        self.assertEqual(args.timeframe, "1")
        subcommands = next(action for action in parser._actions if isinstance(action, argparse._SubParsersAction))
        self.assertIn(
            "every requested symbol has a persisted batch",
            " ".join(subcommands.choices["bars"].format_help().split()),
        )

    def test_research_parser_accepts_model_specific_endpoints_and_keys(self):
        args = build_parser().parse_args(
            [
                "research",
                "bars.csv",
                "--model",
                "local-model",
                "--model",
                "hosted-model",
                "--model-endpoint",
                "local-model=http://localhost:11434/v1",
                "--model-endpoint",
                "hosted-model=https://api.example.test/v1",
                "--model-api-key-env",
                "hosted-model=HOSTED_API_KEY",
            ]
        )
        self.assertEqual(args.model, ["local-model", "hosted-model"])
        self.assertEqual(len(args.model_endpoint), 2)
        self.assertEqual(args.model_api_key_env, ["hosted-model=HOSTED_API_KEY"])

    def test_validate_and_analyze_commands_emit_machine_readable_reports(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "bars.csv"
            report_path = pathlib.Path(directory) / "report.json"
            enriched_path = pathlib.Path(directory) / "enriched.csv"
            self._csv(path)

            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(main(["validate", str(path), "--format", "json"]), 0)
            self.assertEqual(json.loads(output.getvalue())["valid_rows"], 25)

            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(
                    main(
                        [
                            "analyze",
                            str(path),
                            "--format",
                            "json",
                            "--output",
                            str(report_path),
                            "--enriched-csv",
                            str(enriched_path),
                        ]
                    ),
                    0,
                )
            self.assertIn("indicators", json.loads(output.getvalue()))
            self.assertTrue(report_path.exists())
            self.assertTrue(enriched_path.exists())

    def test_research_command_writes_dashboard_and_permutation_report(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "bars.csv"
            outdir = pathlib.Path(directory) / "research"
            self._csv(path)
            self.assertEqual(main(["research", str(path), "-o", str(outdir)]), 0)
            report = json.loads((outdir / "research.json").read_text())
            self.assertEqual(len(report["results"]), 16)
            self.assertEqual(report["results"][0]["metrics"]["in_sample"]["bars"], 17)
            self.assertEqual(report["results"][0]["metrics"]["forward"]["bars"], 8)
            dashboard = (outdir / "dashboard.html").read_text()
            self.assertIn("Quant Research Lab", dashboard)
            self.assertIn("sharpe-filter", dashboard)
            self.assertIn("research.json", dashboard)

    def test_legacy_auth_adapter_does_not_print_the_token(self):
        output = io.StringIO()
        with patch("tradingview_data.cli.get_auth_token", return_value="sensitive-token"):
            with redirect_stdout(output):
                self.assertEqual(legacy_auth_main([]), 0)
        self.assertIn("retrieved successfully", output.getvalue())
        self.assertNotIn("sensitive-token", output.getvalue())


if __name__ == "__main__":
    unittest.main()
