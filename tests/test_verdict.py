import json
import os
import unittest

from tests import scratch


def lighthouse_verdict(test, findings):
    results = scratch.temporary_folder(test, "lh-results-")
    os.makedirs(os.path.join(results, "evidence"))
    with open(os.path.join(results, "findings.json"), "w", encoding="utf-8") as handle:
        handle.write(json.dumps(findings, indent=2) + "\n")
    env = scratch.environment(scratch.make_home(test))
    code, stdout, stderr = scratch.run_lighthouse(["verdict", "--results", results], env)
    return code, stdout, stderr, results


def verdict_line(test, stdout, results):
    line = json.loads(stdout.strip().splitlines()[-1])
    test.assertEqual(
        sorted(line), ["failures", "flaky", "minutes", "pr", "tokens", "unproven", "verdict"]
    )
    with open(os.path.join(results, "verdict.json"), encoding="utf-8") as handle:
        test.assertEqual(json.load(handle), line)
    with open(os.path.join(results, "report.md"), encoding="utf-8") as handle:
        report = handle.read()
    for title in ("Verdict", "Suite", "New behaviour", "Neighbours", "Unproven", "Flaky", "Pre-existing", "Spend"):
        test.assertIn("## " + title + "\n", report)
    return line, report


class VerdictTest(unittest.TestCase):
    def test_blocked_line_needs_no_results_folder(self):
        env = scratch.environment(scratch.make_home(self))
        code, stdout, stderr = scratch.run_lighthouse(["verdict", "--blocked", "the results folder is inside the checkout"], env)
        self.assertEqual(code, 0, stderr)
        self.assertEqual(
            json.loads(stdout.strip().splitlines()[-1]),
            {"verdict": "blocked", "failures": [], "unproven": [], "flaky": [], "tokens": 0, "minutes": 0, "pr": None},
        )
        self.assertIn("the results folder is inside the checkout", stderr)

    def test_takes_a_results_folder_or_a_blocked_reason(self):
        env = scratch.environment(scratch.make_home(self))
        results = scratch.temporary_folder(self, "lh-results-")
        for arguments in ([], ["--results", results, "--blocked", "why"], ["--blocked", " "]):
            code, _, _ = scratch.run_lighthouse(["verdict", *arguments], env)
            self.assertEqual(code, 2, arguments)

    def test_green(self):
        findings = {
            "version": 1,
            "suite": {"result": "passed", "reason": None, "failures": [], "pre_existing": [], "flaky": [], "core": None, "feature": None},
            "build": {"result": "ok", "reason": None},
            "paths": [
                {"name": "export writes a csv", "kind": "new", "surface": "cli", "expected": "a csv with a header row", "evidence": ["evidence/export.txt"], "status": "passed", "retry": None, "core": None, "trials": None},
                {"name": "import reads the csv back", "kind": "new", "surface": "cli", "expected": "the same rows", "evidence": ["evidence/import.txt"], "status": "passed", "retry": None, "core": None, "trials": None},
                {"name": "settings page loads", "kind": "neighbour", "surface": "web page", "expected": "the page renders", "evidence": [], "status": "unproven", "retry": None, "core": None, "trials": None},
                {"name": "sync api lists items", "kind": "neighbour", "surface": "HTTP API", "expected": "the same list on both builds", "evidence": [], "status": "unproven", "retry": None, "core": None, "trials": None},
            ],
            "spend": {"tokens": 12000, "minutes": 4.5},
        }

        code, stdout, stderr, results = lighthouse_verdict(self, findings)

        self.assertEqual(code, 0, stderr)
        line, report = verdict_line(self, stdout, results)
        self.assertEqual(line["verdict"], "green")
        self.assertEqual(line["unproven"], ["settings page loads", "sync api lists items"])
        self.assertEqual(line["failures"], [])
        self.assertEqual((line["tokens"], line["minutes"], line["pr"]), (12000, 4.5, None))
        self.assertIn("evidence/export.txt", report)
        self.assertIn("a csv with a header row", report)

    def test_failures(self):
        findings = {
            "version": 1,
            "suite": {"result": "passed", "reason": None, "failures": [], "pre_existing": [], "flaky": [], "core": None, "feature": None},
            "build": {"result": "ok", "reason": None},
            "paths": [
                {"name": "export writes a csv", "kind": "new", "surface": "cli", "expected": "a csv with a header row", "evidence": ["evidence/export.txt"], "status": "passed", "retry": None, "core": None, "trials": None},
                {"name": "report totals match", "kind": "neighbour", "surface": "cli", "expected": "the same totals on both builds", "evidence": ["evidence/totals-feature.txt", "evidence/totals-core.txt"], "status": "failed", "retry": "failed", "core": "passed", "trials": None},
            ],
            "spend": {"tokens": 9000, "minutes": 3},
        }

        code, stdout, stderr, results = lighthouse_verdict(self, findings)

        self.assertEqual(code, 0, stderr)
        line, report = verdict_line(self, stdout, results)
        self.assertEqual(line["verdict"], "failures")
        self.assertEqual(line["failures"], ["report totals match"])
        self.assertIn("evidence/totals-core.txt", report)

    def test_a_neighbour_failing_every_trial_on_both_builds_is_pre_existing(self):
        findings = {
            "version": 1,
            "suite": {"result": "passed", "reason": None, "failures": [], "pre_existing": [], "flaky": [], "core": None, "feature": None},
            "build": {"result": "ok", "reason": None},
            "paths": [
                {"name": "export writes a csv", "kind": "new", "surface": "cli", "expected": "a csv with a header row", "evidence": [], "status": "passed", "retry": None, "core": None, "trials": None},
                {"name": "model names the file", "kind": "neighbour", "surface": "skill", "expected": "a file name", "evidence": [], "status": "failed", "retry": None, "core": "failed", "trials": {"count": 3, "feature_passed": 0, "core_passed": 0}},
                {"name": "model sums the rows", "kind": "neighbour", "surface": "skill", "expected": "the total", "evidence": [], "status": "failed", "retry": None, "core": None, "trials": {"count": 3, "feature_passed": 0, "core_passed": None}},
            ],
            "spend": {"tokens": 5000, "minutes": 2},
        }

        code, stdout, stderr, results = lighthouse_verdict(self, findings)

        self.assertEqual(code, 0, stderr)
        line, report = verdict_line(self, stdout, results)
        self.assertEqual(line["verdict"], "green")
        self.assertEqual(line["flaky"], [])
        self.assertEqual(line["unproven"], ["model sums the rows"])
        pre_existing = report.split("## Pre-existing\n", 1)[1].split("\n## ", 1)[0]
        self.assertIn("model names the file", pre_existing)

    def test_flaky_is_not_a_failure(self):
        findings = {
            "version": 1,
            "suite": {"result": "passed", "reason": None, "failures": [], "pre_existing": [], "flaky": [], "core": None, "feature": None},
            "build": {"result": "ok", "reason": None},
            "paths": [
                {"name": "export writes a csv", "kind": "new", "surface": "cli", "expected": "a csv with a header row", "evidence": ["evidence/export-1.txt", "evidence/export-2.txt"], "status": "failed", "retry": "passed", "core": None, "trials": None},
            ],
            "spend": {"tokens": 5000, "minutes": 2},
        }

        code, stdout, stderr, results = lighthouse_verdict(self, findings)

        self.assertEqual(code, 0, stderr)
        line, _ = verdict_line(self, stdout, results)
        self.assertEqual(line["verdict"], "green")
        self.assertEqual(line["flaky"], ["export writes a csv"])
        self.assertEqual(line["failures"], [])

    def test_blocked(self):
        findings = {
            "version": 1,
            "suite": {"result": "blocked", "reason": "build: npm run build exited 1", "failures": [], "pre_existing": [], "flaky": [], "core": None, "feature": None},
            "build": {"result": "ok", "reason": None},
            "paths": [
                {"name": "export writes a csv", "kind": "new", "surface": "cli", "expected": "a csv with a header row", "evidence": ["evidence/export.txt"], "status": "passed", "retry": None, "core": None, "trials": None},
            ],
            "spend": {"tokens": 3000, "minutes": 1},
        }

        code, stdout, stderr, results = lighthouse_verdict(self, findings)

        self.assertEqual(code, 0, stderr)
        line, _ = verdict_line(self, stdout, results)
        self.assertEqual(line["verdict"], "blocked")

    def test_unproven(self):
        findings = {
            "version": 1,
            "suite": {"result": "passed", "reason": None, "failures": [], "pre_existing": [], "flaky": [], "core": None, "feature": None},
            "build": {"result": "ok", "reason": None},
            "paths": [
                {"name": "camera captures a photo", "kind": "new", "surface": "device", "expected": "a saved photo", "evidence": [], "status": "unproven", "retry": None, "core": None, "trials": None},
                {"name": "gallery lists photos", "kind": "neighbour", "surface": "web page", "expected": "the same list on both builds", "evidence": ["evidence/gallery.png"], "status": "passed", "retry": None, "core": "passed", "trials": None},
                {"name": "upload api accepts a file", "kind": "neighbour", "surface": "HTTP API", "expected": "201 on both builds", "evidence": ["evidence/upload.json"], "status": "passed", "retry": None, "core": "passed", "trials": None},
            ],
            "spend": {"tokens": 7000, "minutes": 2.5},
        }

        code, stdout, stderr, results = lighthouse_verdict(self, findings)

        self.assertEqual(code, 0, stderr)
        line, _ = verdict_line(self, stdout, results)
        self.assertEqual(line["verdict"], "unproven")
        self.assertEqual(line["unproven"], ["camera captures a photo"])

    def test_refuses_malformed_findings(self):
        findings = {
            "version": 1,
            "suite": {"result": "passed", "reason": None, "failures": [], "pre_existing": [], "flaky": [], "core": None, "feature": None},
            "build": {"result": "ok", "reason": None},
            "spend": {"tokens": 1000, "minutes": 1},
        }

        code, _, stderr, results = lighthouse_verdict(self, findings)

        self.assertEqual(code, 2)
        self.assertIn("paths", stderr)
        self.assertFalse(os.path.exists(os.path.join(results, "verdict.json")))

    def test_blocked_when_feature_does_not_start(self):
        findings = {
            "version": 1,
            "suite": {"result": "passed", "reason": None, "failures": [], "pre_existing": [], "flaky": [], "core": None, "feature": None},
            "build": {"result": "blocked", "reason": "start: port never opened"},
            "paths": [
                {"name": "dashboard shows totals", "kind": "new", "surface": "web page", "expected": "the totals panel", "evidence": [], "status": "unproven", "retry": None, "core": None, "trials": None},
            ],
            "spend": {"tokens": 4000, "minutes": 1.5},
        }

        code, stdout, stderr, results = lighthouse_verdict(self, findings)

        self.assertEqual(code, 0, stderr)
        line, report = verdict_line(self, stdout, results)
        self.assertEqual(line["verdict"], "blocked")
        self.assertIn("start: port never opened", report)


if __name__ == "__main__":
    unittest.main()
