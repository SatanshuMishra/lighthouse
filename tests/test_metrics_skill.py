import json
import os
import re
import unittest

from tests import scratch
from tests.test_skills import frontmatter, frontmatter_name

CATALOGUE = os.path.join(scratch.ROOT, "lighthouse_tool", "catalogue.json")
EXCLUDES_CALLER = re.compile(
    r"\b(usd|spend)\b.*\b(never includes?|does not include|not including|excludes?|leaves? out|without)\b[^.]{0,60}"
    r"\b(caller|calling session|session that called)",
    re.IGNORECASE,
)
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

    def test_skill_states_usd_counts_the_callers_span(self):
        body = scratch.read_text(scratch.skill_path("metrics"))
        rule = next(line for line in body.splitlines() if line.startswith("- usd"))
        for phrase in ("caller", "run.start", "run.end"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, rule)
        self.assertIsNone(EXCLUDES_CALLER.search(rule))
        with open(CATALOGUE, encoding="utf-8") as handle:
            measured = json.load(handle)["summary"]["fields"]["usd"]["measured_from"]
        self.assertIn("the caller's transcript inside the run's span", measured)

    def test_skill_keeps_the_store_path_and_names_out_of_the_shell(self):
        body = scratch.read_text(scratch.skill_path("metrics"))
        self.assertEqual(re.findall(r'duckdb[^\n`]*-c "', body), [])
        self.assertIn("<<'SQL'", body)
        self.assertIn("every ' doubled", body)


if __name__ == "__main__":
    unittest.main()
