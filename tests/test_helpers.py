import importlib
import sys
import pathlib
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))


class FilterRawMessageTests(unittest.TestCase):
    def test_filter_raw_message_returns_message_and_payload(self):
        module = importlib.import_module("helpers")
        text = '~m~35~m~{"m":"test_message","p":[1,2,3]}'
        message, payload = module.filter_raw_message(text)
        self.assertEqual(message, "test_message")
        self.assertIn("[1,2,3]", payload)

    def test_filter_raw_message_returns_none_on_invalid_frame(self):
        module = importlib.import_module("helpers")
        message, payload = module.filter_raw_message("garbage")
        self.assertIsNone(message)
        self.assertIsNone(payload)

    def test_is_heartbeat(self):
        module = importlib.import_module("helpers")
        self.assertTrue(module.is_heartbeat("~m~3~m~~h~1"))
        self.assertFalse(module.is_heartbeat(
            '~m~35~m~{"m":"test_message","p":[1,2,3]}'))


if __name__ == "__main__":
    unittest.main()
