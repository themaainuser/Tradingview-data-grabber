import csv
import importlib
import pathlib
import sys
import tempfile
import unittest
from argparse import Namespace
from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from tradingview_data.protocol import create_message, iter_frames
from tradingview_data.storage import CSV_COLUMNS, CSV_TIME_FORMAT


class FakeSocket:
    def __init__(self):
        self.sent = []

    def send(self, value):
        self.sent.append(value)


def csv_capture(path):
    start = datetime(2024, 1, 1, 9, 15, tzinfo=ZoneInfo("Asia/Kolkata"))
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_COLUMNS)
        for index in range(2):
            writer.writerow(
                [
                    f"[{index}]",
                    (start + timedelta(minutes=index)).strftime(CSV_TIME_FORMAT),
                    100 + index,
                    102 + index,
                    99 + index,
                    101 + index,
                    10,
                ]
            )


class LegacyAdapterTests(unittest.TestCase):
    def test_helpers_keep_legacy_keyword_arguments(self):
        helpers = importlib.import_module("helpers")
        websocket = FakeSocket()

        helpers.sendMessage(ws=websocket, func="test", args=["value"])

        self.assertEqual(next(iter_frames(websocket.sent[0])), {"m": "test", "p": ["value"]})
        self.assertEqual(helpers.constructMessage(func="test", paramList=[]), '{"m":"test","p":[]}')
        self.assertTrue(helpers.prependHeader(st="é").startswith("~m~2~m~"))

    def test_main_adapter_subscribes_with_its_legacy_ws_keyword(self):
        legacy_main = importlib.import_module("main")
        websocket = FakeSocket()

        legacy_main.subscribe(ws=websocket, symbol="BINANCE:BTCUSDT", silent=False)

        frames = [next(iter_frames(message)) for message in websocket.sent]
        additions = [frame["p"] for frame in frames if frame["m"] == "quote_add_symbols"]
        self.assertEqual(len(additions), 1)
        self.assertEqual(additions[0][-1], "BINANCE:BTCUSDT")
        self.assertIn("chart_create_session", [frame["m"] for frame in frames])
        self.assertIn("create_series", [frame["m"] for frame in frames])

    def test_livestream_adapter_preserves_tuple_helpers_and_stream_sessions(self):
        legacy_bars = importlib.import_module("livestreamtest")
        raw_bar = {"i": 4, "v": [1704067200, 100, 104, 99, 102, 7]}
        parsed = legacy_bars.parse_bar(raw_bar)
        self.assertIsNotNone(parsed)
        timestamp, row = parsed
        self.assertEqual(timestamp, 1704067200)
        self.assertEqual(row[0], "[4]")

        message = create_message(
            "timescale_update",
            ["cs_example", {"s1": {"s": [raw_bar]}}],
        )
        self.assertEqual(list(legacy_bars.collect_bars(message)), [("cs_example", timestamp, row)])

        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            stream = legacy_bars.SymbolStream("BINANCE:BTCUSDT", root / "bars.csv", timeframe="5")
            stream.last_row_pos = 19
            self.assertEqual(stream.last_row_position, 19)
            self.assertEqual(stream.csv_path, str(root / "bars.csv"))

            args = Namespace(
                symbols="NASDAQ:AAPL",
                timeframe="5",
                bars=120,
                output=str(root),
                silent=True,
            )
            websocket = FakeSocket()
            legacy_bars.subscribe(ws=websocket, streams={"old-key": stream}, args=args)

        frames = [next(iter_frames(message)) for message in websocket.sent]
        additions = [frame["p"][-1] for frame in frames if frame["m"] == "quote_add_symbols"]
        series = [frame["p"] for frame in frames if frame["m"] == "create_series"]
        self.assertEqual(additions, ["BINANCE:BTCUSDT"])
        self.assertEqual(series, [[stream.chart_session, "s1", "s1", "symbol_1", "5", 120]])

    def test_livestream_build_streams_retains_flat_paths_and_metadata_context(self):
        legacy_bars = importlib.import_module("livestreamtest")
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory) / "data"
            streams = legacy_bars.build_streams(
                Namespace(
                    symbols="BINANCE:BTCUSDT",
                    timeframe="60",
                    bars=10,
                    output=str(root),
                    silent=True,
                )
            )

            stream = next(iter(streams.values()))
            self.assertTrue(root.is_dir())
            self.assertEqual(stream.path, root / "BINANCE_BTCUSDT.csv")
            self.assertEqual(stream.timeframe, "60")

    def test_livestream_run_reuses_the_legacy_stream_mapping(self):
        legacy_bars = importlib.import_module("livestreamtest")
        args = Namespace(
            symbols="BINANCE:BTCUSDT",
            timeframe="1",
            bars=10,
            output="data",
            silent=True,
        )
        streams = {"cs_example": object()}
        with patch.object(legacy_bars, "build_streams", return_value=streams) as build_streams:
            with patch.object(legacy_bars, "BarStreamer") as streamer:
                legacy_bars.run(args)

        build_streams.assert_called_once_with(args)
        streamer.return_value.run.assert_called_once_with(stores=streams)

    def test_visuals_chart_correlation_accepts_legacy_csv_paths(self):
        visuals = importlib.import_module("visuals")
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            first = root / "btc.csv"
            second = root / "eth.csv"
            csv_capture(first)
            csv_capture(second)
            expected = root / "correlation.png"

            with patch.object(visuals, "_chart_correlation", return_value=expected) as chart:
                self.assertEqual(visuals.chart_correlation([first, second], root), expected)

            datasets, outdir = chart.call_args.args
            self.assertEqual([label for label, _ in datasets], ["btc", "eth"])
            self.assertEqual(outdir, root)
            self.assertTrue(hasattr(visuals, "_time_grid"))
            self.assertIs(visuals.time_grid, visuals._time_grid)
            self.assertEqual(visuals.load_csv(first).iloc[0]["index"], "0")
            self.assertEqual(visuals.GREEN, "#26a69a")

    def test_get_auth_token_entry_point_delegates_without_exposing_a_token(self):
        legacy_auth = importlib.import_module("getAuthToken")
        with patch.object(legacy_auth, "legacy_auth_main", return_value=0) as command:
            self.assertEqual(legacy_auth.main(), 0)
        command.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
