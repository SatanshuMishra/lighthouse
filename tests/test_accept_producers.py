import json
import os
import unittest

from tests import accept_support as support
from tests import scratch

BROKEN_ID = "broken\nid"


def failing_suite():
    return {**support.PASSED_SUITE, "result": "failures", "failures": [BROKEN_ID]}


def draft_folder(test, draft):
    results = support.folder(test, "lh-results-")
    support.write_text(os.path.join(results, "evidence", "one.log"), "one\n")
    support.write_json(os.path.join(results, "findings.draft.json"), draft)
    return results


def origin_heads(repo):
    return scratch.run_git(repo, "ls-remote", "--heads", "origin", "feature")


class Producers(unittest.TestCase):
    def test_verdict_refuses_a_blocked_line_that_breaks_h13(self):
        results = support.folder(self, "lh-results-")

        code, stdout, stderr = support.lighthouse(
            ["verdict", "--blocked", "first line\nsecond line", "--results", results], support.environment(self)
        )

        self.assertEqual(code, 2, stdout + stderr)
        self.assertIn(support.H13, support.last_json(stdout)["error"])
        self.assertFalse(os.path.exists(os.path.join(results, "verdict.json")))

    def test_verdict_refuses_a_verdict_line_that_breaks_h13(self):
        findings = support.valid_findings(
            suite=failing_suite(), paths=[], spend={"tokens": 0, "minutes": 0, "dollars": None}
        )
        self.assertEqual(support.referee_errors(support.H14, findings), ())
        results = support.judged_results(self, findings, failing_suite())

        code, stdout, stderr = support.lighthouse(["verdict", "--results", results], support.environment(self))

        self.assertEqual(code, 2, stdout + stderr)
        self.assertIn(support.H13, support.last_json(stdout)["error"])
        self.assertFalse(os.path.exists(os.path.join(results, "verdict.json")))
        self.assertFalse(os.path.exists(os.path.join(results, "report.md")))

    def test_findings_writes_a_draft_that_meets_h14(self):
        draft = support.valid_findings()
        self.assertEqual(support.referee_errors(support.H14, draft), ())
        results = draft_folder(self, draft)

        code, stdout, stderr = support.lighthouse(["findings", "--results", results], support.environment(self))

        self.assertEqual(code, 0, stdout + stderr)
        written = support.read_json(os.path.join(results, "findings.json"))
        self.assertEqual(written, draft)
        self.assertEqual(support.referee_errors(support.H14, written), ())

    def test_findings_refuses_a_draft_that_breaks_h14(self):
        draft = support.with_path(support.valid_findings(), status="skipped")
        self.assertNotEqual(support.referee_errors(support.H14, draft), ())
        results = draft_folder(self, draft)

        code, stdout, stderr = support.lighthouse(["findings", "--results", results], support.environment(self))

        self.assertEqual(code, 2, stdout + stderr)
        printed = json.dumps(support.last_json(stdout))
        self.assertIn(support.H14, printed)
        self.assertIn("/paths/0/status", printed)
        self.assertFalse(os.path.exists(os.path.join(results, "findings.json")))

    def test_measure_and_publish_refuse_to_write_a_broken_profile(self):
        base = scratch.sample_profile()
        surface = {**base["surfaces"][0], "trials": 0}
        profile = scratch.sample_profile(suite={"command": "true", "junit": None}, surfaces=[surface])
        text = json.dumps(profile, indent=2) + "\n"
        repo, _ = support.feature_repo(self, {".lighthouse/profile.json": text})
        copy = support.write_text(os.path.join(support.folder(self, "lh-inputs-"), "profile.json"), text)
        before = support.read_bytes(copy)
        feature_before = scratch.run_git(repo, "rev-parse", "feature").strip()
        origin_before = origin_heads(repo)
        stubs = support.Stubs(self)
        env = support.environment(self, stubs.folder)

        measure_code, measure_out, measure_err = support.lighthouse(
            ["profile", "measure", "--repo", repo, "--profile", copy], env
        )

        self.assertEqual(measure_code, 2, measure_out + measure_err)
        self.assertIn("trials", json.dumps(support.last_json(measure_out)))
        self.assertEqual(support.read_bytes(copy), before)

        publish_code, publish_out, publish_err = support.lighthouse(
            ["profile", "publish", "--repo", repo, "--feature", "feature", "--profile", copy], env
        )

        self.assertEqual(publish_code, 2, publish_out + publish_err)
        self.assertIn("trials", json.dumps(support.last_json(publish_out)))
        self.assertEqual(scratch.run_git(repo, "rev-parse", "feature").strip(), feature_before)
        self.assertEqual(origin_heads(repo), origin_before)


if __name__ == "__main__":
    unittest.main()
