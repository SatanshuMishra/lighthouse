import json
import os
import unittest

from tests import accept_support as support

TITLE = "feat(work): prove the feature"
UNPROVEN_LINE = {
    "verdict": "unproven",
    "failures": [],
    "unproven": ["C1.2"],
    "flaky": [],
    "tokens": 100,
    "minutes": 1,
    "dollars": None,
    "pr": None,
}
DRAFT = {
    "problem": ["The FEATURE branch needs proof before it merges."],
    "change": ["Lighthouse proved the change."],
    "impact": ["No user-visible change."],
    "tradeoffs": ["Unproven: C1.2 could not be reached."],
}
RENDERED_BODY = "\n".join(
    [
        "## Problem",
        "The FEATURE branch needs proof before it merges.",
        "",
        "## Change",
        "- Lighthouse proved the change.",
        "",
        "## Impact",
        "No user-visible change.",
        "",
        "## Trade-offs and open problems",
        "- Unproven: C1.2 could not be reached.",
        "",
        "## Testing",
        "| Check | Result |",
        "|---|---|",
        "| Suite | Passed |",
    ]
)
RENDERED = {"title": TITLE, "body": RENDERED_BODY}


class Composed:
    def __init__(self, test, draft=DRAFT, render=RENDERED):
        self.repo, _ = support.feature_repo(test)
        self.results = support.folder(test, "lh-results-")
        support.write_json(os.path.join(self.results, "verdict.json"), UNPROVEN_LINE)
        support.write_json(
            os.path.join(self.results, "findings.json"),
            support.valid_findings(paths=[], spend={"tokens": 100, "minutes": 1, "dollars": None}),
        )
        self.draft = support.write_json(os.path.join(support.folder(test, "lh-inputs-"), "fields.draft.json"), draft)
        self.stubs = support.Stubs(test)
        if render is not None:
            self.stubs.pull_request(render)
        self.env = support.environment(test, self.stubs.folder, without=("pull-request",))

    def pr(self):
        return support.lighthouse(
            [
                "pr",
                "--repo",
                self.repo,
                "--core",
                "main",
                "--feature",
                "feature",
                "--results",
                self.results,
                "--scope",
                "work",
                "--summary",
                "prove the feature",
                "--draft-fields",
                self.draft,
            ],
            self.env,
        )

    def render_calls(self):
        return self.stubs.calls("pull-request")


class PrRender(unittest.TestCase):
    def test_render_composes_the_pull_request(self):
        self.assertEqual(support.referee_errors(support.H16, RENDERED), ())
        self.assertEqual(support.referee_errors(support.H13, UNPROVEN_LINE), ())
        composed = Composed(self)

        code, stdout, stderr = composed.pr()

        self.assertEqual(code, 0, stdout + stderr)
        calls = composed.render_calls()
        self.assertEqual(len(calls), 1, stdout + stderr)
        argv = calls[0]["argv"]
        self.assertEqual(len(argv), 3, argv)
        self.assertEqual(argv[:2], ["render", "--fields"])
        self.assertEqual(os.path.realpath(argv[2]), os.path.realpath(os.path.join(composed.results, "pr-fields.json")))
        self.assertEqual(calls[0]["stdin"], "")
        self.assertEqual(calls[0]["env"]["GH_PROMPT_DISABLED"], "1")
        fields = json.loads(calls[0]["fields"])
        self.assertEqual(support.referee_errors(support.H15, fields), ())
        self.assertEqual(fields["title"], TITLE)
        printed = support.last_json(stdout)
        self.assertEqual(printed["title"], RENDERED["title"])
        self.assertEqual(printed["body"], RENDERED["body"])
        self.assertEqual(printed["base"], "main")
        self.assertEqual(printed["head"], "feature")
        self.assertIs(printed["draft"], True)

    def test_render_output_breaking_h16_is_refused(self):
        composed = Composed(self, render={"title": "Bad Title.", "body": "x"})

        code, stdout, stderr = composed.pr()

        self.assertEqual(code, 2, stdout + stderr)
        printed = support.last_json(stdout)
        self.assertIn("pull-request render", printed["error"])
        self.assertIn(support.H16, printed["error"])
        self.assertNotIn("title", printed)

    def test_without_render_the_pull_request_still_meets_h16(self):
        composed = Composed(self, render=None)

        code, stdout, stderr = composed.pr()

        self.assertEqual(code, 0, stdout + stderr)
        printed = support.last_json(stdout)
        shown = {"title": printed["title"], "body": printed["body"]}
        self.assertEqual(support.referee_errors(support.H16, shown), (), json.dumps(shown))

    def test_a_draft_breaking_h15_is_refused(self):
        composed = Composed(self, draft={**DRAFT, "problem": ["lowercase start without a period"]})

        code, stdout, stderr = composed.pr()

        self.assertEqual(code, 2, stdout + stderr)
        error = support.last_json(stdout)["error"]
        self.assertIn(support.H15, error)
        self.assertIn("/problem/0", error)
        self.assertFalse(os.path.exists(os.path.join(composed.results, "pr-fields.json")))
        self.assertEqual(composed.render_calls(), [])

    def test_every_unresolved_name_must_appear(self):
        composed = Composed(self, draft={**DRAFT, "tradeoffs": ["Nothing is left open."]})

        code, stdout, stderr = composed.pr()

        self.assertEqual(code, 2, stdout + stderr)
        self.assertIn("C1.2", support.last_json(stdout)["error"])
        self.assertEqual(composed.render_calls(), [])


if __name__ == "__main__":
    unittest.main()
