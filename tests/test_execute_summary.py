import unittest

from tests import test_k1_execute as k1

FAIL_THEN_PASS = "test -f first-run.done && exit 0; touch first-run.done; exit 1"


class ExecuteSummaryTest(unittest.TestCase):
    def summary_for(self, line):
        prepared = k1.default_setup(self)
        code, stdout, stderr = prepared.execute_record(line)
        self.assertEqual(code, 0, stdout + stderr)
        return k1.last_json(stdout)["checks"], prepared

    def test_check_that_failed_then_passed_prints_both_runs(self):
        checks, prepared = self.summary_for(k1.exact_line("C1.1", FAIL_THEN_PASS))
        self.assertEqual(checks, [{"id": "C1.1", "runs": ["fail", "pass"]}])
        self.assertEqual([result["status"] for result in prepared.checks()], ["fail", "pass"])

    def test_check_that_passed_at_once_prints_one_run(self):
        checks, _ = self.summary_for(k1.exact_line("C1.1", "exit 0"))
        self.assertEqual(checks, [{"id": "C1.1", "runs": ["pass"]}])

    def test_judged_check_prints_every_trial(self):
        checks, _ = self.summary_for(k1.judged_line("C1.1", "exit 0"))
        self.assertEqual(checks, [{"id": "C1.1", "runs": ["pass", "pass", "pass"]}])


if __name__ == "__main__":
    unittest.main()
