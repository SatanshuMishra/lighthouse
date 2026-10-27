import re
import unittest

from tests import scratch
from tests.test_skills import frontmatter, frontmatter_name

BODY_PHRASES = (
    "catalogue.json",
    "read_json",
    "hive_partitioning",
    "union_by_name",
    "TimeZone",
    "started",
    "duckdb",
    "brew install duckdb",
    "usd",
    "null",
    "transcripts",
)


class MetricsSkillTest(unittest.TestCase):
    def test_skill_states_how_to_answer(self):
        text = scratch.read_text(scratch.skill_path("metrics"))
        self.assertEqual(frontmatter_name(text), "metrics")
        description = re.search(r"(?m)^description:\s*(.+)$", frontmatter(text))
        self.assertIsNotNone(description)
        self.assertIn("lighthouse", description.group(1))
        body = re.sub(r"\A---\n.*?\n---\n", "", text, count=1, flags=re.DOTALL)
        for phrase in BODY_PHRASES:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, body)


if __name__ == "__main__":
    unittest.main()
