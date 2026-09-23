import csv
import json
import math
import pathlib
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from tradingview_data.analytics import (
    OhlcvValidationError,
    add_indicators,
    data_quality_report,
    load_ohlcv,
    market_report,
    write_enriched_csv,
    write_report,
)
from tradingview_data.storage import CSV_COLUMNS, CSV_TIME_FORMAT


def make_csv(path, rows=40):
    start = datetime(2024, 1, 1, 9, 15, tzinfo=ZoneInfo("Asia/Kolkata"))
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_COLUMNS)
        for index in range(rows):
            price = 100 + index
            writer.writerow(
                [
                    f"[{index}]",
                    (start + timedelta(minutes=index)).strftime(CSV_TIME_FORMAT),
                    price,
                    price + 2,
                    price - 1,
                    price + 1,
                    100 + index,
                ]
            )


class AnalyticsTests(unittest.TestCase):
    def test_loader_filters_invalid_rows_and_keeps_latest_duplicate(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "bars.csv"
            make_csv(path)
            with path.open("a", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["[7]", "Mon Jan 01 2024 09:22:00 GMT+0530", 107, 110, 106, 109, 400])
                writer.writerow(["[bad]", "Mon Jan 01 2024 10:30:00 GMT+0530", 10, 9, 8, 11, 1])
                writer.writerow(["[inf]", "Mon Jan 01 2024 10:31:00 GMT+0530", "inf", 12, 9, 10, 1])
            data = load_ohlcv(path)

            self.assertEqual(len(data), 40)
            self.assertEqual(data.attrs["duplicate_rows"], 1)
            self.assertEqual(data.attrs["dropped_rows"], 2)
            self.assertEqual(data.iloc[7]["close"], 109)

    def test_indicators_reports_and_exports_are_derived_without_mutating_input(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "bars.csv"
            make_csv(path)
            data = load_ohlcv(path)
            original_columns = list(data.columns)
            enriched = add_indicators(data)
            quality = data_quality_report(data)
            report = market_report(data)

            self.assertEqual(list(data.columns), original_columns)
            self.assertIn("rsi_14", enriched.columns)
            self.assertFalse(math.isnan(enriched.iloc[-1]["ema_20"]))
            self.assertEqual(quality["valid_rows"], 40)
            self.assertEqual(report["signals"]["ema_trend"], "above_ema_20")

            enriched_path = write_enriched_csv(data, pathlib.Path(directory) / "indicators.csv")
            report_path = write_report(report, pathlib.Path(directory) / "report.json")
            self.assertTrue(enriched_path.exists())
            self.assertEqual(json.loads(report_path.read_text())["latest"]["close"], 140.0)

    def test_flat_prices_produce_neutral_rsi_after_warmup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "bars.csv"
            make_csv(path, rows=20)
            data = load_ohlcv(path)
            data.loc[:, ["open", "high", "low", "close"]] = [100, 101, 99, 100]
            self.assertEqual(add_indicators(data).iloc[-1]["rsi_14"], 50.0)

    def test_empty_csv_has_a_clean_validation_error(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "empty.csv"
            path.write_text("")
            with self.assertRaises(OhlcvValidationError):
                load_ohlcv(path)


if __name__ == "__main__":
    unittest.main()
