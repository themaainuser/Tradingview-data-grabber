import pathlib
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from tradingview_data.research import (
    build_research,
    performance_metrics,
    request_model_notes,
    strategy_permutations,
    strategy_positions,
    write_research_dashboard,
)


def make_data(rows=240):
    index = pd.date_range("2024-01-01", periods=rows, freq="D", tz="UTC")
    steps = np.sin(np.arange(rows) / 5) * 1.5 + np.cos(np.arange(rows) / 13) * 0.8 + 0.15
    close = 100 + np.cumsum(steps)
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": np.full(rows, 100.0),
        },
        index=index,
    )


class ResearchTests(unittest.TestCase):
    def test_permutations_are_repeatable_and_positions_execute_on_next_bar(self):
        strategies = strategy_permutations()
        self.assertEqual(len(strategies), 16)
        data = pd.DataFrame(
            {"close": [1.0, 2.0, 3.0, 2.0, 1.0]},
            index=pd.date_range("2024-01-01", periods=5, tz="UTC"),
        )
        strategy = {
            "family": "SMA crossover",
            "parameters": {"fast": 1, "slow": 2},
        }
        self.assertEqual(strategy_positions(data, strategy).tolist(), [0.0, 0.0, 1.0, 1.0, 0.0])

    def test_metrics_report_drawdown_as_negative_and_count_trade_episodes(self):
        returns = pd.Series([0.1, -0.1, 0.05, 0.0])
        positions = pd.Series([1.0, 1.0, 0.0, 0.0])
        metrics = performance_metrics(returns, positions, periods_per_year=1)
        self.assertAlmostEqual(metrics["total_return_pct"], 3.95)
        self.assertAlmostEqual(metrics["max_drawdown_pct"], -10.0)
        self.assertEqual(metrics["trades"], 1)
        self.assertEqual(metrics["win_rate_pct"], 100.0)
        self.assertAlmostEqual(metrics["sortino"], 0.25)
        open_metrics = performance_metrics(pd.Series([0.1, 0.1]), pd.Series([1.0, 1.0]), periods_per_year=1)
        self.assertEqual(open_metrics["trades"], 0)
        carried_metrics = performance_metrics(
            pd.Series([0.1, -0.01]),
            pd.Series([1.0, 0.0]),
            periods_per_year=1,
            initially_active=True,
        )
        self.assertEqual(carried_metrics["trades"], 0)

    def test_research_contains_full_in_sample_forward_folds_and_costs(self):
        data = make_data()
        before = list(data.columns)
        free = build_research([("TEST", "bars.csv", data)], fee_bps=0)
        charged = build_research([("TEST", "bars.csv", data)], fee_bps=20)
        self.assertEqual(len(free["results"]), 16)
        self.assertEqual(len(free["results"][0]["forward_folds"]), 4)
        self.assertIn("full_sample", free["results"][0]["metrics"])
        self.assertIn("in_sample", free["results"][0]["metrics"])
        self.assertIn("forward", free["results"][0]["metrics"])
        free_return = free["results"][0]["metrics"]["full_sample"]["total_return_pct"]
        charged_return = charged["results"][0]["metrics"]["full_sample"]["total_return_pct"]
        self.assertLess(charged_return, free_return)
        self.assertEqual(list(data.columns), before)

    def test_single_bar_capture_has_explicitly_empty_forward_metrics(self):
        report = build_research([("SHORT", "one-row.csv", make_data(1))])
        self.assertEqual(report["results"][0]["metrics"]["in_sample"]["bars"], 1)
        self.assertEqual(report["results"][0]["metrics"]["forward"]["bars"], 0)
        self.assertEqual(report["results"][0]["forward_folds"], [])

    def test_dashboard_escapes_untrusted_text_and_writes_json_data(self):
        data = make_data(80)
        report = build_research([("</script><b>unsafe", "/private/home/user/capture.csv", data)])
        self.assertEqual(report["assets"][0]["source"], "capture.csv")
        self.assertEqual(report["assets"][0]["quality"]["source"], "capture.csv")
        with tempfile.TemporaryDirectory() as directory:
            dashboard = write_research_dashboard(report, directory)
            html = dashboard.read_text()
            self.assertIn("<\\/script>", html)
            self.assertNotIn("</script><b>unsafe", html)
            self.assertTrue((pathlib.Path(directory) / "research.json").exists())

    @patch("tradingview_data.research.requests.post")
    def test_model_notes_can_call_multiple_models_without_exposing_credentials(self, post):
        response = Mock()
        response.json.return_value = {"choices": [{"message": {"content": "Cautious summary."}}]}
        post.return_value = response
        report = build_research([("TEST", "bars.csv", make_data(80))])
        with patch.dict("os.environ", {"TVDATA_TEST_KEY": "private", "TVDATA_DEFAULT_KEY": ""}):
            notes = request_model_notes(
                report,
                ["frontier-model", "local-model"],
                base_url="http://localhost:11434/v1",
                api_key_env="TVDATA_DEFAULT_KEY",
                model_endpoints={"frontier-model": "https://api.example.test/v1"},
                model_api_key_envs={"frontier-model": "TVDATA_TEST_KEY"},
            )
        self.assertEqual([note["model"] for note in notes], ["frontier-model", "local-model"])
        self.assertTrue(all(note["status"] == "ok" for note in notes))
        self.assertNotIn("private", repr(notes))
        self.assertEqual(post.call_count, 2)
        self.assertEqual(post.call_args_list[0].args[0], "https://api.example.test/v1/chat/completions")
        self.assertEqual(post.call_args_list[0].kwargs["headers"]["Authorization"], "Bearer private")
        self.assertEqual(post.call_args_list[1].args[0], "http://localhost:11434/v1/chat/completions")
        self.assertNotIn("Authorization", post.call_args_list[1].kwargs["headers"])


if __name__ == "__main__":
    unittest.main()
