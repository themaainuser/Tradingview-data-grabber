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

    def test_legacy_auth_adapter_does_not_print_the_token(self):
        output = io.StringIO()
        with patch("tradingview_data.cli.get_auth_token", return_value="sensitive-token"):
            with redirect_stdout(output):
                self.assertEqual(legacy_auth_main([]), 0)
        self.assertIn("retrieved successfully", output.getvalue())
        self.assertNotIn("sensitive-token", output.getvalue())


if __name__ == "__main__":
    unittest.main()
