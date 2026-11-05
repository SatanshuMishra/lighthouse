import json
import os
import unittest

from tests import scratch

H14 = "h14-lighthouse-findings"
DRAFT_FINDINGS = {
    "version": 1,
    "suite": {"result": "passed", "reason": None, "failures": [], "pre_existing": [], "flaky": [], "core": None, "feature": None},
    "build": {"result": "ok", "reason": None},
    "paths": [
        {
            "name": "export writes a csv",
            "kind": "new",
            "surface": "cli",
            "expected": "a csv with a header row",
            "evidence": ["evidence/export.txt"],
            "status": "passed",
            "retry": None,
            "core": None,
            "trials": None,
            "check": {"kind": "direct", "why": "the command prints the outcome"},
        }
    ],
    "spend": {"tokens": 6000, "minutes": 2, "dollars": None},
}
BROKEN_PATH = {
    "name": "export writes a csv",
    "kind": "new",
    "surface": "cli",
    "expected": "a csv with a header row",
    "evidence": ["evidence/export.txt"],
    "status": "skipped",
    "retry": None,
    "core": None,
    "trials": None,
    "check": {"kind": "direct", "why": "the command prints the outcome"},
    "note": "seen twice",
}
EARLIER_FINDINGS = "{\"version\": 1, \"written\": \"by an earlier run\"}\n"


def results_with(test, draft_text=None):
    results = scratch.temporary_folder(test, "lh-results-")
    if draft_text is not None:
        with open(os.path.join(results, "findings.draft.json"), "w", encoding="utf-8") as handle:
            handle.write(draft_text)
    return results


def findings_command(test, results):
    env = scratch.environment(scratch.make_home(test))
    code, stdout, stderr = scratch.run_lighthouse(["findings", "--results", results], env)
    return code, json.loads(stdout.strip().splitlines()[-1]), stderr


def read_text(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


class FindingsTest(unittest.TestCase):
    def test_a_draft_that_meets_h14_becomes_findings_json(self):
        results = results_with(self, json.dumps(DRAFT_FINDINGS))

        code, printed, stderr = findings_command(self, results)

        self.assertEqual(code, 0, stderr)
        target = os.path.join(os.path.realpath(results), "findings.json")
        self.assertEqual(printed, {"written": target})
        self.assertEqual(json.loads(read_text(target)), DRAFT_FINDINGS)
        self.assertEqual(sorted(os.listdir(results)), ["findings.draft.json", "findings.json"])

    def test_a_passing_draft_replaces_an_earlier_findings_file(self):
        results = results_with(self, json.dumps(DRAFT_FINDINGS))
        with open(os.path.join(results, "findings.json"), "w", encoding="utf-8") as handle:
            handle.write(EARLIER_FINDINGS)

        code, _, stderr = findings_command(self, results)

        self.assertEqual(code, 0, stderr)
        self.assertEqual(json.loads(read_text(os.path.join(results, "findings.json"))), DRAFT_FINDINGS)

    def test_a_failing_draft_names_every_error_and_writes_nothing(self):
        results = results_with(self, json.dumps({**DRAFT_FINDINGS, "paths": [BROKEN_PATH]}))
        with open(os.path.join(results, "findings.json"), "w", encoding="utf-8") as handle:
            handle.write(EARLIER_FINDINGS)

        code, printed, stderr = findings_command(self, results)

        self.assertEqual(code, 2, stderr)
        self.assertEqual(sorted(printed), ["error", "errors", "schema"])
        self.assertEqual(printed["schema"], H14)
        self.assertEqual(len(printed["errors"]), 2, printed)
        self.assertTrue(printed["errors"][0].startswith("#/paths/0/status enum"), printed)
        self.assertTrue(printed["errors"][1].startswith("#/paths/0/note additionalProperties"), printed)
        self.assertIn("findings.draft.json", printed["error"])
        self.assertIn(H14, printed["error"])
        for error in printed["errors"]:
            self.assertIn(error, printed["error"])
        self.assertEqual(read_text(os.path.join(results, "findings.json")), EARLIER_FINDINGS)

    def test_a_missing_draft_is_refused(self):
        results = results_with(self)

        code, printed, stderr = findings_command(self, results)

        self.assertEqual(code, 2, stderr)
        self.assertEqual(printed["schema"], H14)
        self.assertEqual(len(printed["errors"]), 1, printed)
        self.assertIn("findings.draft.json does not exist", printed["errors"][0])
        self.assertEqual(os.listdir(results), [])

    def test_a_draft_that_is_not_json_is_refused(self):
        results = results_with(self, "{\"version\": 1,")

        code, printed, stderr = findings_command(self, results)

        self.assertEqual(code, 2, stderr)
        self.assertEqual(printed["schema"], H14)
        self.assertIn("findings.draft.json is not JSON", printed["errors"][0])
        self.assertFalse(os.path.exists(os.path.join(results, "findings.json")))

    def test_a_results_folder_that_does_not_exist_is_refused(self):
        missing = os.path.join(scratch.temporary_folder(self, "lh-results-"), "absent")

        code, printed, stderr = findings_command(self, missing)

        self.assertEqual(code, 2, stderr)
        self.assertIn("is not a folder", printed["error"])
        self.assertFalse(os.path.exists(missing))

    def test_results_flag_is_required(self):
        env = scratch.environment(scratch.make_home(self))

        code, stdout, stderr = scratch.run_lighthouse(["findings"], env)

        self.assertEqual(code, 2, stderr)
        self.assertIn("--results", json.loads(stdout)["error"])


if __name__ == "__main__":
    unittest.main()
