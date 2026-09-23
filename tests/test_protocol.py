import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from tradingview_data.protocol import (
    create_message,
    frame_payload,
    filter_raw_message,
    generate_chart_session,
    generate_quote_session,
    is_heartbeat,
    iter_frames,
)


class ProtocolTests(unittest.TestCase):
    def test_round_trips_concatenated_frames_without_splitting_payload_content(self):
        first = create_message("note", ["literal ~m~ marker", "café"])
        second = create_message("next", [2])

        frames = list(iter_frames(first + second))

        self.assertEqual(
            frames,
            [
                {"m": "note", "p": ["literal ~m~ marker", "café"]},
                {"m": "next", "p": [2]},
            ],
        )

    def test_uses_utf8_byte_lengths_for_unicode_payloads(self):
        payload = json.dumps({"m": "note", "p": ["café ~m~ 東京"]}, ensure_ascii=False, separators=(",", ":"))
        wire = frame_payload(payload)
        declared = int(wire.split("~m~")[1])

        self.assertEqual(declared, len(payload.encode("utf-8")))
        self.assertEqual(list(iter_frames(wire)), [{"m": "note", "p": ["café ~m~ 東京"]}])

    def test_skips_malformed_leading_frame_and_recovers_next_valid_frame(self):
        wire = "~m~999~m~not-json" + create_message("valid", [True])

        self.assertEqual(list(iter_frames(wire)), [{"m": "valid", "p": [True]}])

    def test_heartbeats_accept_bytes_and_raw_message_stays_compact(self):
        self.assertTrue(is_heartbeat(b"~m~3~m~~h~1"))
        message, payload = filter_raw_message(create_message("quote", ["BTC", 1]))
        self.assertEqual(message, "quote")
        self.assertEqual(payload, json.dumps(["BTC", 1], separators=(",", ":")))

    def test_session_identifiers_have_expected_prefix_and_entropy_length(self):
        quote = generate_quote_session()
        chart = generate_chart_session()
        self.assertRegex(quote, r"^qs_[a-z]{12}$")
        self.assertRegex(chart, r"^cs_[a-z]{12}$")
        self.assertNotEqual(quote, chart)


if __name__ == "__main__":
    unittest.main()
