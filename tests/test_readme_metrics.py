import os
import re
import unittest

from tests import scratch

REQUIRED = (
    "~/.plugin-metrics",
    "PLUGIN_METRICS_DIR",
    "run.start",
    "run.end",
    "run summary",
    "price_date",
    "--parent",
    "lighthouse metrics import",
    "skills/metrics",
)


class ReadmeMetricsTest(unittest.TestCase):
    def test_readme_describes_the_store(self):
        text = scratch.read_text(os.path.join(scratch.ROOT, "README.md"))
        for phrase in REQUIRED:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)
        verdict_rows = [line for line in text.splitlines() if line.startswith("| `verdict` |")]
        self.assertEqual(len(verdict_rows), 1)
        self.assertNotIn("--repo", verdict_rows[0])
        paragraphs = [block for block in re.split(r"\n\s*\n", text) if "runs.jsonl" in block]
        self.assertEqual(len(paragraphs), 1)
        self.assertIn("lighthouse metrics import", paragraphs[0])


if __name__ == "__main__":
    unittest.main()
