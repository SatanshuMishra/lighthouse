import json
import os
import re
import unittest

from tests import scratch

WITHHELD = ("CLAUDE_CODE_SESSION_ID", "SHIP", "PIPELINE_EVENTS", "PLUGIN_METRICS_DIR", "PLUGIN_METRICS_PARENT")
OPUS = {"input": 4.0, "cache_write_5m": 5.0, "cache_write_1h": 8.0, "cache_read": 0.2, "output": 20.0}
SHIPPED = os.path.join(scratch.ROOT, "lighthouse_tool", "prices.json")


def child_environment(test):
    base = scratch.environment(scratch.make_home(test))
    kept = {name: value for name, value in base.items() if name not in WITHHELD}
    return {**kept, "PLUGIN_METRICS_DIR": scratch.temporary_folder(test, "lh-metrics-")}


def write_prices(test, table):
    path = os.path.join(scratch.temporary_folder(test, "lh-prices-"), "prices.json")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(table))
    return path


def fixture_transcripts(test):
    folder = scratch.temporary_folder(test, "lh-transcripts-")
    entry = {
        "type": "assistant",
        "timestamp": "2026-10-16T10:00:00Z",
        "message": {
            "id": "msg_opus",
            "model": "claude-opus-5-5",
            "usage": {"input_tokens": 1000000, "cache_read_input_tokens": 500000, "output_tokens": 100000},
            "content": [],
        },
    }
    with open(os.path.join(folder, "session.jsonl"), "w", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")
    return folder


def spend_with(test, prices):
    return scratch.run_lighthouse(
        ["spend", "--since", "2026-10-16T09:00:00Z", "--prices", prices, "--transcripts", fixture_transcripts(test)],
        child_environment(test),
    )


def printed(stdout):
    return json.loads(stdout.strip().splitlines()[-1])


class SpendPriceDateTest(unittest.TestCase):
    def test_spend_prints_the_price_date(self):
        code, stdout, stderr = spend_with(self, write_prices(self, {"date": "2026-10-01", "claude-opus-5-5": OPUS}))
        undated_code, undated_stdout, undated_stderr = spend_with(self, write_prices(self, {"claude-opus-5-5": OPUS}))
        self.assertEqual(code, 0, stderr)
        self.assertEqual(undated_code, 0, undated_stderr)
        spend = printed(stdout)
        self.assertEqual(spend["price_date"], "2026-10-01")
        self.assertEqual(spend["dollars"], printed(undated_stdout)["dollars"])
        self.assertEqual(spend["dollars"], 6.1)

    def test_table_without_date_gives_null(self):
        code, stdout, stderr = spend_with(self, write_prices(self, {"claude-opus-5-5": OPUS}))
        self.assertEqual(code, 0, stderr)
        spend = printed(stdout)
        self.assertIn("price_date", spend)
        self.assertIsNone(spend["price_date"])

    def test_bad_date_refused(self):
        code, stdout, stderr = spend_with(self, write_prices(self, {"date": "October", "claude-opus-5-5": OPUS}))
        self.assertEqual(code, 2, stderr)
        self.assertIn("date", printed(stdout)["error"])

    def test_shipped_table_is_dated(self):
        with open(SHIPPED, encoding="utf-8") as handle:
            table = json.load(handle)
        self.assertRegex(table.get("date") or "", re.compile(r"^\d{4}-\d{2}-\d{2}$"))


if __name__ == "__main__":
    unittest.main()
