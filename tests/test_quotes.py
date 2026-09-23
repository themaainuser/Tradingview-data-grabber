import json
import pathlib
import sys
import unittest
from datetime import datetime, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from tradingview_data.protocol import create_message
from tradingview_data.quotes import QuoteStreamConfig, QuoteStreamer, QuoteUpdate, format_quote, iter_quote_updates


class QuoteTests(unittest.TestCase):
    def test_parses_qsd_quote_update(self):
        wire = create_message(
            "qsd",
            [
                "qs_example",
                {
                    "n": "BINANCE:BTCUSDT",
                    "s": "ok",
                    "v": {"lp": 101.25, "bid": 101.2, "ask": 101.3, "volume": 7},
                },
            ],
        )
        updates = list(iter_quote_updates(wire))
        self.assertEqual(len(updates), 1)
        self.assertEqual(updates[0].symbol, "BINANCE:BTCUSDT")
        self.assertEqual(updates[0].values["lp"], 101.25)
        self.assertEqual(json.loads(format_quote(updates[0], "json"))["bid"], 101.2)

    def test_decodes_encoded_quote_symbol_names(self):
        wire = create_message(
            "qsd",
            [
                "qs_example",
                {
                    "n": '={"adjustment":"splits","symbol":"CRYPTO:BTCUSD"}',
                    "v": {"lp": 100.25},
                },
            ],
        )

        updates = list(iter_quote_updates(wire))

        self.assertEqual(len(updates), 1)
        self.assertEqual(updates[0].symbol, "CRYPTO:BTCUSD")

    def test_streamer_merges_partial_updates_without_losing_prior_values(self):
        config = QuoteStreamConfig(symbols=("BINANCE:BTCUSDT",), once=True)
        streamer = QuoteStreamer(config, connect=lambda: None)
        first = streamer._merge(
            QuoteUpdate("BINANCE:BTCUSDT", {"lp": 100, "bid": 99}, datetime.now(timezone.utc))
        )
        second = streamer._merge(
            QuoteUpdate("BINANCE:BTCUSDT", {"ask": 101}, datetime.now(timezone.utc))
        )
        self.assertEqual(first.values, {"lp": 100, "bid": 99})
        self.assertEqual(second.values, {"lp": 100, "bid": 99, "ask": 101})
        self.assertEqual(format_quote(second, price_only=True), "100")

    def test_ignores_non_quote_frames_and_missing_values(self):
        self.assertEqual(list(iter_quote_updates(create_message("du", ["x", {}]))), [])
        self.assertEqual(list(iter_quote_updates(create_message("qsd", ["x", {"n": "BTC"}]))), [])

    def test_config_rejects_duplicate_symbols(self):
        with self.assertRaises(ValueError):
            QuoteStreamConfig(symbols=("BINANCE:BTCUSDT", "BINANCE:BTCUSDT"))


if __name__ == "__main__":
    unittest.main()
