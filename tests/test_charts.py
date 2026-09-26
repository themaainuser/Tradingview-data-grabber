import csv
import pathlib
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from tradingview_data.charts import build_dashboard, generate_charts
from tradingview_data.storage import CSV_COLUMNS, CSV_TIME_FORMAT


def make_csv(path, offset=0):
    start = datetime(2024, 1, 1, 9, 15, tzinfo=ZoneInfo("Asia/Kolkata"))
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_COLUMNS)
        for index in range(40):
            price = 100 + offset + index * 0.5
            writer.writerow(
                [
                    f"[{index}]",
                    (start + timedelta(minutes=index)).strftime(CSV_TIME_FORMAT),
                    price,
                    price + 1,
                    price - 1,
                    price + 0.25,
                    50 + index,
                ]
            )


class ChartTests(unittest.TestCase):
    def test_single_and_multi_symbol_generation_uses_non_overwriting_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            btc = root / "btc.csv"
            eth = root / "eth.csv"
            make_csv(btc)
            make_csv(eth, offset=50)

            single = root / "single"
            generated = generate_charts([btc], single)
            expected = {
                "1_candles_volume.png",
                "2_volume_profile.png",
                "3_volume_by_time_heatmap.png",
                "4_volatility_by_time_heatmap.png",
                "5_price_time_heatmap.png",
                "6_returns_atr.png",
                "7_technical_indicators.png",
                "dashboard.html",
            }
            self.assertEqual({path.name for path in generated}, expected)
            for name in expected - {"dashboard.html"}:
                self.assertTrue((single / name).read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))
            dashboard = (single / "dashboard.html").read_text()
            self.assertIn("Pinned charts", dashboard)
            self.assertIn("chart-search", dashboard)
            self.assertIn("prefers-reduced-motion", dashboard)

            multi = root / "multi"
            generate_charts([btc, eth], multi, include_indicators=False)
            self.assertTrue((multi / "btc" / "1_candles_volume.png").exists())
            self.assertTrue((multi / "eth" / "1_candles_volume.png").exists())
            self.assertTrue((multi / "8_correlation_heatmap.png").exists())

    def test_dashboard_escapes_labels_and_contains_offline_gallery_controls(self):
        with tempfile.TemporaryDirectory() as directory:
            output = pathlib.Path(directory)
            dashboard = build_dashboard(output, [(output / "chart.png", "</script><b>unsafe")])
            html = dashboard.read_text()
            self.assertIn("<\\/script>", html)
            self.assertNotIn("</script><b>unsafe", html)
            self.assertIn("chart-search", html)
            self.assertIn("pinned-count-label", html)
            self.assertIn("prefers-reduced-motion", html)


if __name__ == "__main__":
    unittest.main()
