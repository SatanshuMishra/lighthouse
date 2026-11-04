import os
import shlex
import shutil
import unittest

from tests import accept_support as support
from tests import scratch

MISSING_SEAM = '#/criteria/0 required: lacks required property "seam"'


def plain_profile():
    return scratch.sample_profile(suite={"command": "true", "junit": None})


def loose_record():
    record = support.record_with([support.exact_line("C2.1", "true")])
    return {**record, "criteria": ["loose", *record["criteria"]]}


def seamless_record(command):
    record = support.record_with([support.exact_line("C2.1", command)])
    criterion = {key: value for key, value in record["criteria"][0].items() if key != "seam"}
    return {**record, "criteria": [criterion]}


def lines_of(record):
    return [
        line
        for criterion in record["criteria"]
        if isinstance(criterion, dict)
        for line in criterion.get("acceptance", [])
    ]


class Prepared:
    def __init__(self, test):
        self.test = test
        self.repo, _ = support.feature_repo(test)
        self.stubs = support.Stubs(test)
        self.env = support.environment(test, self.stubs.folder)
        self.inputs = support.folder(test, "lh-inputs-")
        self.profile = support.write_json(os.path.join(self.inputs, "profile.json"), plain_profile())

    def results(self):
        results = support.results_folder(self.test)
        support.worktrees(self.test, self.repo, results, self.env)
        return results

    def record_file(self, name, record):
        return support.write_json(os.path.join(self.inputs, name + ".json"), record)

    def execute(self, results, *flags):
        return support.lighthouse(["execute", "--results", results, *flags, "--profile", self.profile], self.env)

    def verdict_on(self, results, record_path):
        shutil.copyfile(record_path, os.path.join(results, "record.json"))
        support.write_json(os.path.join(results, "suite.json"), dict(support.PASSED_SUITE))
        support.write_text(os.path.join(results, "evidence", "one.log"), "one\n")
        support.write_json(os.path.join(results, "findings.json"), support.valid_findings())
        return support.lighthouse(["verdict", "--results", results], self.env)


class Consumers(unittest.TestCase):
    def test_verdict_refuses_findings_with_a_key_h14_does_not_define(self):
        findings = support.with_path(support.valid_findings(), note="x")
        self.assertNotEqual(support.referee_errors(support.H14, findings), ())
        results = support.judged_results(self, findings)

        code, stdout, stderr = support.lighthouse(["verdict", "--results", results], support.environment(self))

        self.assertEqual(code, 2, stdout + stderr)
        error = support.last_json(stdout)["error"]
        self.assertIn(support.H14, error)
        self.assertIn("note", error)
        self.assertFalse(os.path.exists(os.path.join(results, "verdict.json")))

    def test_a_criterion_that_is_not_an_object_is_refused(self):
        prepared = Prepared(self)
        record = loose_record()
        self.assertNotEqual(support.referee_errors(support.H11, record), ())
        for line in lines_of(record):
            self.assertEqual(support.referee_errors(support.K1, line), ())
        record_path = prepared.record_file("record", record)
        results = prepared.results()

        code, stdout, stderr = prepared.execute(results, "--record", record_path)

        self.assertEqual(code, 2, stdout + stderr)
        error = support.last_json(stdout)["error"]
        self.assertIn(support.H11, error)
        self.assertIn("#/criteria/0", error)
        self.assertTrue(support.no_line_in(os.path.join(results, "checks.jsonl")))

        code, stdout, stderr = prepared.verdict_on(results, record_path)

        self.assertEqual(code, 2, stdout + stderr)
        error = support.last_json(stdout)["error"]
        self.assertIn("record", error)
        self.assertIn(support.H11, error)

    def test_a_repeated_check_id_in_the_plan_is_refused(self):
        results = support.judged_results(self, support.valid_findings())
        support.write_json(
            os.path.join(results, "plan.json"),
            {
                "checks": [{"id": "C1.1", "kind": "exact", "trials": 1}, {"id": "C1.1", "kind": "judged", "trials": 3}],
                "neighbours": [],
                "reach": {},
            },
        )

        code, stdout, stderr = support.lighthouse(["verdict", "--results", results], support.environment(self))

        self.assertEqual(code, 2, stdout + stderr)
        self.assertIn("C1.1", support.last_json(stdout)["error"])
        self.assertFalse(os.path.exists(os.path.join(results, "verdict.json")))

    def test_launch_keeps_a_cost_it_cannot_read(self):
        usage = {"claude-opus": {"costUSD": 1.5}, "claude-haiku": {"costUSD": "unknown"}}

        run = support.launched(
            self, [{"envelope": support.envelope(support.blocked_line("stub reason"), modelUsage=usage)}]
        )

        child = support.read_json(os.path.join(run["results"], "child.json"))
        self.assertEqual(child["cost"], {"claude-opus": 1.5}, child)
        self.assertEqual(child["unpriced"], ["claude-haiku"], child)
        self.assertIn("claude-haiku", run["stderr"])

    def test_a_record_failing_h11_only_is_refused(self):
        prepared = Prepared(self)
        marker = os.path.join(support.folder(self, "lh-marker-"), "ran.txt")
        record = seamless_record("touch " + shlex.quote(marker))
        self.assertEqual(support.referee_errors(support.H11, record), (MISSING_SEAM,))
        for line in lines_of(record):
            self.assertEqual(support.referee_errors(support.K1, line), ())
        record_path = prepared.record_file("record", record)
        results = prepared.results()

        code, stdout, stderr = prepared.execute(results, "--record", record_path)

        self.assertEqual(code, 2, stdout + stderr)
        error = support.last_json(stdout)["error"]
        self.assertIn(support.H11, error)
        self.assertIn(MISSING_SEAM, error)
        self.assertFalse(os.path.exists(marker))
        self.assertTrue(support.no_line_in(os.path.join(results, "checks.jsonl")))

        code, stdout, stderr = prepared.verdict_on(results, record_path)

        self.assertEqual(code, 2, stdout + stderr)
        error = support.last_json(stdout)["error"]
        self.assertIn(support.H11, error)
        self.assertIn("seam", error)
        self.assertFalse(os.path.exists(os.path.join(results, "verdict.json")))

    def test_a_record_is_read_only_when_it_exists_and_passes_h11(self):
        prepared = Prepared(self)
        valid = support.record_with([support.exact_line("C2.1", "true")])
        repeated = support.record_with([support.exact_line("C2.1", "true"), support.exact_line("C2.1", "true")])
        marker = os.path.join(support.folder(self, "lh-marker-"), "ran.txt")
        failing = seamless_record("touch " + shlex.quote(marker))
        self.assertEqual(support.referee_errors(support.H11, valid), ())
        self.assertEqual(support.referee_errors(support.H11, repeated), ())
        self.assertNotEqual(support.referee_errors(support.H11, failing), ())

        with self.subTest(record="none"):
            results = prepared.results()
            code, stdout, stderr = prepared.execute(results)
            self.assertEqual(code, 0, stdout + stderr)
            self.assertTrue(support.no_line_in(os.path.join(results, "checks.jsonl")))

        with self.subTest(record="passes h11"):
            results = prepared.results()
            code, stdout, stderr = prepared.execute(results, "--record", prepared.record_file("valid", valid))
            self.assertEqual(code, 0, stdout + stderr)
            checks = support.json_lines(os.path.join(results, "checks.jsonl"))
            self.assertEqual(len(checks), 1, checks)
            self.assertEqual(checks[0]["check_id"], "C2.1")
            self.assertEqual(checks[0]["status"], "pass", checks[0])

        with self.subTest(record="repeated id"):
            results = prepared.results()
            code, stdout, stderr = prepared.execute(results, "--record", prepared.record_file("repeated", repeated))
            self.assertEqual(code, 2, stdout + stderr)
            error = support.last_json(stdout)["error"]
            self.assertIn("C2.1", error)
            self.assertNotIn(support.H11, error)
            self.assertTrue(support.no_line_in(os.path.join(results, "checks.jsonl")))

        with self.subTest(record="fails h11"):
            results = prepared.results()
            code, stdout, stderr = prepared.execute(results, "--record", prepared.record_file("failing", failing))
            self.assertEqual(code, 2, stdout + stderr)
            self.assertIn(support.H11, support.last_json(stdout)["error"])
            self.assertTrue(support.no_line_in(os.path.join(results, "checks.jsonl")))
            self.assertFalse(os.path.exists(marker))


if __name__ == "__main__":
    unittest.main()
