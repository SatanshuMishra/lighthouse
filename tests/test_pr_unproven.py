import json
import unittest

from tests import test_pr as pull_requests

UNPROVEN_DRAFT = {
    "problem": ["The executor needs proof before it merges."],
    "change": ["Add the executor."],
    "impact": ["No user-visible change."],
    "tradeoffs": ["Unproven: C2.1 could not be reached."],
}
UNPROVEN_TESTING = "\n".join(
    [
        "## Testing",
        "| Check | Result |",
        "|---|---|",
        "| Lighthouse verdict | unproven |",
        "| Project suite | passed |",
        "| Failures | 0 |",
        "| Unproven | 1 |",
        "| Flaky | 0 |",
    ]
)


class PrUnprovenTest(unittest.TestCase):
    def test_unproven_verdict_composes_a_draft_without_final(self):
        run = pull_requests.Run(self, pull_requests.verdict_line("unproven", unproven=["C2.1"]), draft=UNPROVEN_DRAFT)

        code, stdout, stderr = run.pr()

        self.assertEqual(code, 0, stdout + stderr)
        composed = json.loads(stdout)
        self.assertIs(composed.get("draft"), True)
        self.assertIn("- Unproven: C2.1 could not be reached.", composed["body"].splitlines())
        self.assertTrue(composed["body"].endswith(UNPROVEN_TESTING), composed["body"])

    def test_green_verdict_composes_a_ready_pull_request(self):
        run = pull_requests.Run(self, pull_requests.verdict_line("green"), draft=pull_requests.PLAIN_DRAFT)

        code, stdout, stderr = run.pr()

        self.assertEqual(code, 0, stdout + stderr)
        self.assertIs(json.loads(stdout).get("draft"), False)

    def test_an_unproven_name_no_tradeoffs_sentence_holds_is_counted(self):
        draft = {**UNPROVEN_DRAFT, "tradeoffs": ["Nothing is left open."]}
        run = pull_requests.Run(self, pull_requests.verdict_line("unproven", unproven=["C2.1"]), draft=draft)

        code, stdout, stderr = run.pr()

        self.assertEqual(code, 0, stdout + stderr)
        lines = json.loads(stdout)["body"].splitlines()
        self.assertIn("- Nothing is left open.", lines)
        self.assertIn("- " + pull_requests.REST_OF_ONE, lines)


if __name__ == "__main__":
    unittest.main()
