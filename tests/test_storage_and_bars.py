import csv
import pathlib
import sys
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from tradingview_data.bars import BarStreamConfig, BarStreamer, collect_bars, parse_bar, parse_symbols
from tradingview_data.protocol import create_message, iter_frames
from tradingview_data.storage import CSV_TIME_FORMAT, CsvBarStore, safe_filename


IST = ZoneInfo("Asia/Kolkata")


def csv_row(timestamp, close):
    rendered = datetime.fromtimestamp(timestamp, IST).strftime(CSV_TIME_FORMAT)
    return ["[1]", rendered, "100", "105", "95", str(close), "20"]


class FakeSocket:
    def __init__(self):
        self.sent = []

    def send(self, value):
        self.sent.append(value)


class ReceivingSocket(FakeSocket):
    def __init__(self, messages):
        super().__init__()
        self.messages = iter(messages)
        self.closed = False

    def recv(self):
        return next(self.messages)

    def close(self):
        self.closed = True


class TrackingStore:
    def __init__(self, *, fail_on_open=False):
        self.symbol = "BINANCE:BTCUSDT"
        self.fail_on_open = fail_on_open
        self.closed = False

    def open(self):
        if self.fail_on_open:
            raise ValueError("metadata mismatch")

    def close(self):
        self.closed = True


class StorageAndBarTests(unittest.TestCase):
    def test_store_rewrites_forming_candle_and_restores_state_after_restart(self):
        timestamp = 1704067200
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "BTC" / "1.csv"
            store = CsvBarStore(path, symbol="BINANCE:BTCUSDT", timeframe="1")
            store.open()
            self.assertTrue(store.write_bar(timestamp, csv_row(timestamp, 101)))
            self.assertTrue(store.write_bar(timestamp + 60, csv_row(timestamp + 60, 102)))
            self.assertTrue(store.write_bar(timestamp + 60, csv_row(timestamp + 60, 103)))
            self.assertTrue(store.write_bar(timestamp, csv_row(timestamp, 999)))
            store.close()

            with path.open(newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["close"], "999")
            self.assertEqual(rows[-1]["close"], "103")

            restarted = CsvBarStore(path, symbol="BINANCE:BTCUSDT", timeframe="1")
            restarted.open()
            self.assertTrue(restarted.write_bar(timestamp + 60, csv_row(timestamp + 60, 104)))
            restarted.close()
            with path.open(newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[-1]["close"], "104")
            self.assertTrue(path.with_suffix(".csv.meta.json").exists())

    def test_store_rejects_metadata_collision(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "data.csv"
            with CsvBarStore(path, symbol="BINANCE:BTCUSDT", timeframe="1"):
                pass
            mismatched = CsvBarStore(path, symbol="BINANCE:BTCUSDT", timeframe="5")
            with self.assertRaises(ValueError):
                mismatched.open()
            self.assertIsNone(mismatched.file)
            mismatched.close()

    def test_store_discards_an_incomplete_trailing_row_after_a_crash(self):
        timestamp = 1704067200
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "data.csv"
            with CsvBarStore(path) as store:
                store.write_bar(timestamp, csv_row(timestamp, 101))
            with path.open("a", encoding="utf-8") as handle:
                handle.write("[partial],Mon Jan")
            reopened = CsvBarStore(path)
            reopened.open()
            reopened.close()
            with path.open(newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["close"], "101")

    def test_store_inserts_late_bars_without_staling_the_forming_candle(self):
        timestamp = 1704067200
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "data.csv"
            with CsvBarStore(path) as store:
                store.write_bar(timestamp, csv_row(timestamp, 101))
                store.write_bar(timestamp + 120, csv_row(timestamp + 120, 103))
                store.write_bar(timestamp + 60, csv_row(timestamp + 60, 102))
                store.write_bar(timestamp + 120, csv_row(timestamp + 120, 104))
            with path.open(newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual([row["close"] for row in rows], ["101", "102", "104"])

    def test_streamer_closes_already_opened_stores_when_later_open_fails(self):
        config = BarStreamConfig(symbols=("BINANCE:BTCUSDT",), output=pathlib.Path("unused"))
        streamer = BarStreamer(config)
        first = TrackingStore()
        second = TrackingStore(fail_on_open=True)
        with patch.object(streamer, "build_stores", return_value={"first": first, "second": second}):
            with self.assertRaisesRegex(ValueError, "metadata mismatch"):
                streamer.run()
        self.assertTrue(first.closed)
        self.assertTrue(second.closed)

    def test_once_waits_for_a_persisted_batch_from_each_symbol(self):
        timestamp = 1704067200
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            stores = {
                "cs_one": CsvBarStore(root / "one.csv", symbol="BINANCE:BTCUSDT", timeframe="1"),
                "cs_two": CsvBarStore(root / "two.csv", symbol="BINANCE:ETHUSDT", timeframe="1"),
            }

            def update(session, index):
                return create_message(
                    "du",
                    [
                        session,
                        {
                            "sds_1": {
                                "s": [
                                    {
                                        "i": index,
                                        "v": [timestamp + index * 60, 100, 105, 95, 102, 50],
                                    }
                                ]
                            }
                        },
                    ],
                )

            socket = ReceivingSocket([update("cs_one", 0), update("cs_two", 1)])
            config = BarStreamConfig(
                symbols=("BINANCE:BTCUSDT", "BINANCE:ETHUSDT"),
                output=root,
                once=True,
                silent=True,
            )
            streamer = BarStreamer(config, connect=lambda: socket)
            with patch.object(streamer, "build_stores", return_value=stores):
                streamer.run()
            self.assertTrue(socket.closed)
            for path in (root / "one.csv", root / "two.csv"):
                with path.open(newline="") as handle:
                    self.assertEqual(len(list(csv.DictReader(handle))), 1)

    def test_bar_parsing_and_collection_ignore_malformed_values(self):
        good = {"i": 7, "v": [1704067200, 100, 105, 95, 102, 50]}
        self.assertIsNone(parse_bar({"v": [1704067200, 100]}))
        self.assertIsNone(parse_bar({"v": [1704067200, 100, "nan", 95, 102, 50]}))
        self.assertIsNone(parse_bar({"v": [1704067200, 100, 105, 95, 102, -1]}))
        self.assertEqual(parse_bar(good).close, 102.0)  # type: ignore[union-attr]
        payload = {
            "m": "du",
            "p": ["cs_example", {"sds_1": {"s": [good, {"v": ["bad"]}]}}],
        }
        bars = list(collect_bars(create_message(payload["m"], payload["p"])))
        self.assertEqual(len(bars), 1)
        self.assertEqual(bars[0][0], "cs_example")
        self.assertEqual(bars[0][1].volume, 50.0)

    def test_stream_subscriptions_use_requested_symbols_timeframe_and_history(self):
        config = BarStreamConfig(
            symbols=parse_symbols("BINANCE:BTCUSDT, BINANCE:ETHUSDT, BINANCE:BTCUSDT"),
            timeframe="5",
            history_bars=120,
            output=pathlib.Path("unused"),
        )
        streamer = BarStreamer(config)
        stores = streamer.build_stores()
        socket = FakeSocket()
        streamer.subscribe(socket, stores)
        frames = [next(iter_frames(message)) for message in socket.sent]
        methods = [frame["m"] for frame in frames]
        self.assertEqual(methods.count("create_series"), 2)
        series = [frame["p"] for frame in frames if frame["m"] == "create_series"]
        self.assertTrue(all(values[-2:] == ["5", 120] for values in series))
        self.assertEqual(safe_filename("../BINANCE:BTC/USDT"), "BINANCE_BTC_USDT")

    def test_stream_config_rejects_duplicate_symbols_and_filename_collisions(self):
        with self.assertRaises(ValueError):
            BarStreamConfig(symbols=("BINANCE:BTCUSDT", "BINANCE:BTCUSDT"))
        config = BarStreamConfig(
            symbols=("EXCHANGE:A/B", "EXCHANGE:A:B"),
            output=pathlib.Path("unused"),
        )
        with self.assertRaisesRegex(ValueError, "same output path"):
            BarStreamer(config).build_stores()


if __name__ == "__main__":
    unittest.main()
