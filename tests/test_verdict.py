import json
import os
import shutil
import unittest

from tests import scratch


def results_folder(test, files=()):
    results = scratch.temporary_folder(test, "lh-results-")
    os.makedirs(os.path.join(results, "evidence"))
    for name in files:
        os.makedirs(os.path.dirname(os.path.join(results, name)), exist_ok=True)
        with open(os.path.join(results, name), "w", encoding="utf-8") as handle:
            handle.write(name + "\n")
    return results


def lighthouse_verdict(test, findings, plan=None, files=()):
    return verdict_in(test, results_folder(test, files), findings, plan)


def verdict_in(test, results, findings, plan=None):
    with open(os.path.join(results, "findings.json"), "w", encoding="utf-8") as handle:
        handle.write(json.dumps(findings, indent=2) + "\n")
    if plan is not None:
        with open(os.path.join(results, "retest.json"), "w", encoding="utf-8") as handle:
            handle.write(json.dumps(plan, indent=2) + "\n")
    env = scratch.environment(scratch.make_home(test))
    code, stdout, stderr = scratch.run_lighthouse(["verdict", "--results", results], env)
    return code, stdout, stderr, results


def verdict_line(test, stdout, results):
    line = json.loads(stdout.strip().splitlines()[-1])
    test.assertEqual(
        sorted(line), ["dollars", "failures", "flaky", "minutes", "pr", "tokens", "unproven", "verdict"]
    )
    with open(os.path.join(results, "verdict.json"), encoding="utf-8") as handle:
        test.assertEqual(json.load(handle), line)
    with open(os.path.join(results, "report.md"), encoding="utf-8") as handle:
        report = handle.read()
    for title in ("Verdict", "Suite", "New behaviour", "Neighbours", "Unproven", "Flaky", "Pre-existing", "Spend"):
        test.assertIn("## " + title + "\n", report)
    return line, report


DIRECT_CHECK = {"kind": "direct", "why": "the command prints the outcome"}


RETEST_PLAN = {"full": False, "changed": ["src/importer.py"], "retest": ["import reads the csv back"], "surfaces": ["cli"], "carried": [], "carried_paths": []}


def retest_findings(evidence):
    return {
        "version": 1,
        "suite": {"result": "passed", "reason": None, "failures": [], "pre_existing": [], "flaky": [], "core": None, "feature": None},
        "build": {"result": "ok", "reason": None},
        "paths": [
            {"name": "export writes a csv", "kind": "new", "surface": "cli", "expected": "a csv with a header row", "evidence": ["evidence/export.txt"], "status": "passed", "retry": None, "core": None, "check": DIRECT_CHECK, "trials": None},
            {"name": "import reads the csv back", "kind": "new", "surface": "cli", "expected": "the same rows", "evidence": evidence, "status": "passed", "retry": None, "core": None, "check": DIRECT_CHECK, "trials": None},
        ],
        "spend": {"tokens": 6000, "minutes": 2},
    }


def ledger_findings(spend):
    return {
        "version": 1,
        "suite": {"result": "passed", "reason": None, "failures": [], "pre_existing": [], "flaky": [], "core": None, "feature": None},
        "build": {"result": "ok", "reason": None},
        "paths": [
            {"name": "export writes a csv", "kind": "new", "surface": "cli", "expected": "a csv with a header row", "evidence": ["evidence/export.txt"], "status": "passed", "retry": None, "core": None, "check": DIRECT_CHECK, "trials": None},
        ],
        "spend": spend,
    }


def write_json(folder, name, value):
    with open(os.path.join(folder, name), "w", encoding="utf-8") as handle:
        handle.write(json.dumps(value) + "\n")


def ledger_lines(home):
    path = os.path.join(home, ".lighthouse", "work", "runs.jsonl")
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle.read().splitlines()]


def verdict_with_repo(test, results, home, repo, findings):
    write_json(results, "findings.json", findings)
    env = scratch.environment(home)
    code, stdout, stderr = scratch.run_lighthouse(["verdict", "--results", results, "--repo", repo], env)
    test.assertEqual(code, 0, stderr)
    return json.loads(stdout.strip().splitlines()[-1])


class LedgerTest(unittest.TestCase):
    def test_a_blocked_stop_with_its_results_folder_records_that_run(self):
        home = scratch.make_home(self)
        repo, _ = scratch.make_repo(self)
        results = scratch.temporary_folder(self, "lh-results-")
        code, stdout, stderr = scratch.run_lighthouse(
            ["verdict", "--blocked", "the profile is broken", "--results", results, "--repo", repo], scratch.environment(home)
        )
        self.assertEqual(code, 0, stderr)
        self.assertEqual(json.loads(stdout.strip().splitlines()[-1])["verdict"], "blocked")
        self.assertEqual([(line["run"], line["reason"]) for line in ledger_lines(home)], [(results, "the profile is broken")])
        self.assertEqual(os.listdir(results), [])

    def test_an_append_after_a_torn_ledger_line_starts_its_own_line(self):
        home = scratch.make_home(self)
        repo, _ = scratch.make_repo(self)
        folder = os.path.join(home, ".lighthouse", "work")
        os.makedirs(folder)
        with open(os.path.join(folder, "runs.jsonl"), "w", encoding="utf-8") as handle:
            handle.write('{"run": "/results/one", "kind": "verd')
        code, _, stderr = scratch.run_lighthouse(["verdict", "--blocked", "stopped", "--repo", repo], scratch.environment(home))
        self.assertEqual(code, 0, stderr)
        with open(os.path.join(folder, "runs.jsonl"), encoding="utf-8") as handle:
            lines = handle.read().splitlines()
        self.assertEqual(lines[0], '{"run": "/results/one", "kind": "verd')
        self.assertEqual(json.loads(lines[1])["reason"], "stopped")

    def test_verdict_appends_one_ledger_line(self):
        home = scratch.make_home(self)
        repo, _ = scratch.make_repo(self)
        results = results_folder(self, ["evidence/export.txt"])
        spend = {"tokens": 6000, "minutes": 2, "dollars": 0.75, "input": 6000}
        write_json(results, "spend.json", spend)
        write_json(results, "commits.json", {"core": "a" * 40, "feature": "b" * 40})
        verdict_with_repo(self, results, home, repo, ledger_findings({"tokens": 6000, "minutes": 2}))
        lines = ledger_lines(home)
        self.assertEqual(len(lines), 1)
        line = lines[0]
        self.assertEqual(line["verdict"], "green")
        self.assertEqual(line["commits"], {"core": "a" * 40, "feature": "b" * 40})
        self.assertEqual(line["spend"], spend)
        self.assertEqual(line["paths"], [{"name": "export writes a csv", "kind": "new", "status": "passed", "check": DIRECT_CHECK}])
        self.assertEqual(line["run"], results)

    def test_ledger_survives_removing_the_results_folder(self):
        home = scratch.make_home(self)
        repo, _ = scratch.make_repo(self)
        results = results_folder(self, ["evidence/export.txt"])
        verdict_with_repo(self, results, home, repo, ledger_findings({"tokens": 6000, "minutes": 2}))
        shutil.rmtree(results)
        lines = ledger_lines(home)
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["run"], results)

    def test_blocked_verdict_appends_a_ledger_line(self):
        home = scratch.make_home(self)
        repo, _ = scratch.make_repo(self)
        env = scratch.environment(home)
        code, stdout, stderr = scratch.run_lighthouse(["verdict", "--blocked", "profile", "--repo", repo], env)
        self.assertEqual(code, 0, stderr)
        self.assertEqual(json.loads(stdout.strip().splitlines()[-1])["verdict"], "blocked")
        lines = ledger_lines(home)
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["verdict"], "blocked")
        self.assertEqual(lines[0]["reason"], "profile")
        self.assertIsNone(lines[0]["run"])

    def test_verdict_line_adds_dollars_and_keeps_every_key(self):
        code, stdout, stderr, results = lighthouse_verdict(
            self, ledger_findings({"tokens": 10, "minutes": 2, "dollars": 0.5}), files=["evidence/export.txt"]
        )
        self.assertEqual(code, 0, stderr)
        line = json.loads(stdout.strip().splitlines()[-1])
        self.assertEqual(sorted(line), ["dollars", "failures", "flaky", "minutes", "pr", "tokens", "unproven", "verdict"])
        self.assertEqual(line["tokens"], 10)
        self.assertEqual(line["dollars"], 0.5)

    def test_findings_without_dollars_still_judged(self):
        code, stdout, stderr, results = lighthouse_verdict(
            self, ledger_findings({"tokens": 10, "minutes": 2}), files=["evidence/export.txt"]
        )
        self.assertEqual(code, 0, stderr)
        line, _ = verdict_line(self, stdout, results)
        self.assertEqual(line["verdict"], "green")
        self.assertIsNone(line["dollars"])

    def test_ledger_line_carries_suite_phase_minutes(self):
        home = scratch.make_home(self)
        repo, _ = scratch.make_repo(self)
        results = results_folder(self, ["evidence/export.txt"])
        write_json(
            results,
            "suite.json",
            {
                "result": "passed",
                "core": {"exit": 0, "log": "suite-core.log", "prepare_minutes": 3, "suite_minutes": 10},
                "feature": {"exit": 0, "log": "suite-feature.log", "prepare_minutes": 2, "suite_minutes": 9, "rerun_minutes": None},
            },
        )
        verdict_with_repo(self, results, home, repo, ledger_findings({"tokens": 6000, "minutes": 2}))
        line = ledger_lines(home)[0]
        self.assertEqual(line["suite"]["core"]["prepare_minutes"], 3)
        self.assertEqual(line["suite"]["core"]["suite_minutes"], 10)

    def test_refuses_negative_dollars(self):
        code, stdout, _, _ = lighthouse_verdict(
            self, ledger_findings({"tokens": 10, "minutes": 2, "dollars": -1}), files=["evidence/export.txt"]
        )
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(stdout)["key"], "spend.dollars")


def checked_path(check, kind="new", name="export writes a csv"):
    path = {"name": name, "kind": kind, "surface": "cli", "expected": "a csv with a header row", "evidence": ["evidence/export.txt"], "status": "passed", "retry": None, "core": None, "trials": None}
    return path if check is None else {**path, "check": check}


def check_findings(paths, suite=None):
    return {
        "version": 1,
        "suite": suite or {"result": "passed", "reason": None, "failures": [], "pre_existing": [], "flaky": [], "core": None, "feature": None},
        "build": {"result": "ok", "reason": None},
        "paths": paths,
        "spend": {"tokens": 6000, "minutes": 2},
    }


def suite_record(feature_tests, core_tests=None):
    return {
        "result": "passed",
        "reason": None,
        "failures": [],
        "pre_existing": [],
        "flaky": [],
        "core": {"exit": 0, "log": "suite-core.log", "prepare_minutes": 0, "suite_minutes": 1, "tests": core_tests},
        "feature": {"exit": 0, "log": "suite-feature.log", "prepare_minutes": 0, "suite_minutes": 1, "rerun_minutes": None, "tests": feature_tests},
    }


def judged_with_suite(test, findings, suite):
    results = results_folder(test, ["evidence/export.txt"])
    write_json(results, "suite.json", suite)
    return verdict_in(test, results, findings)


class CheckTest(unittest.TestCase):
    def test_path_without_check_is_refused(self):
        code, stdout, _, results = lighthouse_verdict(self, check_findings([checked_path(None)]), files=["evidence/export.txt"])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(stdout)["key"], "paths[0].check")
        self.assertFalse(os.path.exists(os.path.join(results, "verdict.json")))

    def test_check_kind_outside_the_three_is_refused(self):
        code, stdout, _, _ = lighthouse_verdict(
            self, check_findings([checked_path({"kind": "glance", "why": "it looked right"})]), files=["evidence/export.txt"]
        )
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(stdout)["key"], "paths[0].check.kind")

    def test_suite_check_naming_no_test_is_refused(self):
        code, stdout, _, _ = lighthouse_verdict(
            self,
            check_findings([checked_path({"kind": "suite", "why": "the export test asserts the header", "tests": []})]),
            files=["evidence/export.txt"],
        )
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(stdout)["key"], "paths[0].check.tests")

    def test_empty_why_is_refused(self):
        code, stdout, _, _ = lighthouse_verdict(
            self, check_findings([checked_path({"kind": "drive", "why": " "})]), files=["evidence/export.txt"]
        )
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(stdout)["key"], "paths[0].check.why")

    def test_suite_check_whose_tests_passed_proves_the_path(self):
        check = {"kind": "suite", "why": "test_export asserts the header row", "tests": ["tests.T.test_export"]}
        code, stdout, stderr, results = judged_with_suite(
            self,
            check_findings([checked_path(check)]),
            suite_record({"passed": ["tests.T.test_export"], "failed": []}),
        )
        self.assertEqual(code, 0, stderr)
        line, _ = verdict_line(self, stdout, results)
        self.assertEqual(line["verdict"], "green")
        self.assertEqual(line["unproven"], [])

    def test_suite_check_with_a_named_test_not_passing_is_unproven(self):
        check = {"kind": "suite", "why": "test_export asserts the header row", "tests": ["tests.T.test_export"]}
        code, stdout, stderr, results = judged_with_suite(
            self,
            check_findings([checked_path(check)]),
            suite_record({"passed": [], "failed": ["tests.T.test_export"]}),
        )
        self.assertEqual(code, 0, stderr)
        line, report = verdict_line(self, stdout, results)
        self.assertEqual(line["unproven"], ["export writes a csv"])
        unproven = report.split("## Unproven\n", 1)[1].split("\n## ", 1)[0]
        self.assertIn("export writes a csv", unproven)
        self.assertIn("tests.T.test_export did not pass on FEATURE's first run", unproven)

    def test_suite_check_without_junit_is_unproven(self):
        check = {"kind": "suite", "why": "test_export asserts the header row", "tests": ["tests.T.test_export"]}
        code, stdout, stderr, results = judged_with_suite(self, check_findings([checked_path(check)]), suite_record(None))
        self.assertEqual(code, 0, stderr)
        line, report = verdict_line(self, stdout, results)
        self.assertEqual(line["verdict"], "unproven")
        self.assertEqual(line["unproven"], ["export writes a csv"])
        self.assertIn("records no test ids", report)

    def test_neighbour_suite_check_needs_core_to_pass(self):
        check = {"kind": "suite", "why": "test_totals asserts the totals", "tests": ["tests.T.test_totals"]}
        paths = [
            checked_path(DIRECT_CHECK),
            {**checked_path(check, kind="neighbour", name="report totals match"), "core": "passed"},
        ]
        code, stdout, stderr, results = judged_with_suite(
            self,
            check_findings(paths),
            suite_record(
                {"passed": ["tests.T.test_totals"], "failed": []},
                {"passed": [], "failed": ["tests.T.test_totals"]},
            ),
        )
        self.assertEqual(code, 0, stderr)
        line, report = verdict_line(self, stdout, results)
        self.assertEqual(line["unproven"], ["report totals match"])
        self.assertIn("tests.T.test_totals did not pass on core's first run", report)

    def test_carried_path_without_check_is_accepted(self):
        carried = {"name": "import reads the csv back", "kind": "new", "surface": "cli", "expected": "the same rows", "evidence": ["previous/evidence/import.txt"], "status": "passed", "retry": None, "core": None, "trials": None}
        plan = {"full": False, "changed": ["src/exporter.py"], "retest": [], "surfaces": ["cli"], "carried": ["import reads the csv back"], "carried_paths": [carried]}
        code, stdout, stderr, results = lighthouse_verdict(
            self,
            check_findings([checked_path(DIRECT_CHECK), carried]),
            plan,
            files=["evidence/export.txt", "previous/evidence/import.txt"],
        )
        self.assertEqual(code, 0, stderr)
        line, _ = verdict_line(self, stdout, results)
        self.assertEqual(line["verdict"], "green")

    def test_report_lists_each_path_check(self):
        code, stdout, stderr, results = lighthouse_verdict(
            self,
            check_findings([checked_path({"kind": "drive", "why": "the outcome is on screen"})]),
            files=["evidence/export.txt"],
        )
        self.assertEqual(code, 0, stderr)
        _, report = verdict_line(self, stdout, results)
        path_lines = [line for line in report.splitlines() if line.startswith("- export writes a csv")]
        self.assertEqual(len(path_lines), 1)
        self.assertIn("drive", path_lines[0])
        self.assertIn("the outcome is on screen", path_lines[0])

    def test_a_flaky_test_cannot_prove_a_path(self):
        check = {"kind": "suite", "why": "test_export asserts the header row", "tests": ["tests.T.test_export"]}
        suite = suite_record({"passed": [], "failed": ["tests.T.test_export"]})
        suite = {**suite, "flaky": ["tests.T.test_export"], "feature": {**suite["feature"], "rerun_minutes": 1}}
        code, stdout, stderr, results = judged_with_suite(self, check_findings([checked_path(check)]), suite)
        self.assertEqual(code, 0, stderr)
        line, _ = verdict_line(self, stdout, results)
        self.assertEqual(line["verdict"], "unproven")
        self.assertEqual(line["unproven"], ["export writes a csv"])

    def test_passed_ids_come_from_suite_json_not_findings(self):
        check = {"kind": "suite", "why": "test_export asserts the header row", "tests": ["tests.T.test_export"]}
        claimed = {
            "result": "passed",
            "reason": None,
            "failures": [],
            "pre_existing": [],
            "flaky": [],
            "passed": ["tests.T.test_export"],
            "core": None,
            "feature": {"tests": {"passed": ["tests.T.test_export"], "failed": []}},
        }
        code, stdout, stderr, results = judged_with_suite(
            self,
            check_findings([checked_path(check)], claimed),
            suite_record({"passed": [], "failed": ["tests.T.test_export"]}),
        )
        self.assertEqual(code, 0, stderr)
        line, _ = verdict_line(self, stdout, results)
        self.assertEqual(line["unproven"], ["export writes a csv"])

    def test_suite_check_never_hides_a_confirmed_failure(self):
        check = {"kind": "suite", "why": "test_export asserts the header row", "tests": ["tests.T.test_export"]}
        failing = {**checked_path(check), "status": "failed", "retry": "failed"}
        code, stdout, stderr, results = judged_with_suite(
            self,
            check_findings([checked_path(DIRECT_CHECK, name="import reads the csv back"), failing]),
            suite_record(None),
        )
        self.assertEqual(code, 0, stderr)
        line, _ = verdict_line(self, stdout, results)
        self.assertEqual(line["verdict"], "failures")
        self.assertEqual(line["failures"], ["export writes a csv"])


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
        for arguments in ([], ["--blocked", " "]):
            code, _, _ = scratch.run_lighthouse(["verdict", *arguments], env)
            self.assertEqual(code, 2, arguments)

    def test_green(self):
        findings = {
            "version": 1,
            "suite": {"result": "passed", "reason": None, "failures": [], "pre_existing": [], "flaky": [], "core": None, "feature": None},
            "build": {"result": "ok", "reason": None},
            "paths": [
                {"name": "export writes a csv", "kind": "new", "surface": "cli", "expected": "a csv with a header row", "evidence": ["evidence/export.txt"], "status": "passed", "retry": None, "core": None, "check": DIRECT_CHECK, "trials": None},
                {"name": "import reads the csv back", "kind": "new", "surface": "cli", "expected": "the same rows", "evidence": ["evidence/import.txt"], "status": "passed", "retry": None, "core": None, "check": DIRECT_CHECK, "trials": None},
                {"name": "settings page loads", "kind": "neighbour", "surface": "web page", "expected": "the page renders", "evidence": [], "status": "unproven", "retry": None, "core": None, "check": DIRECT_CHECK, "trials": None},
                {"name": "sync api lists items", "kind": "neighbour", "surface": "HTTP API", "expected": "the same list on both builds", "evidence": [], "status": "unproven", "retry": None, "core": None, "check": DIRECT_CHECK, "trials": None},
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
                {"name": "export writes a csv", "kind": "new", "surface": "cli", "expected": "a csv with a header row", "evidence": ["evidence/export.txt"], "status": "passed", "retry": None, "core": None, "check": DIRECT_CHECK, "trials": None},
                {"name": "report totals match", "kind": "neighbour", "surface": "cli", "expected": "the same totals on both builds", "evidence": ["evidence/totals-feature.txt", "evidence/totals-core.txt"], "status": "failed", "retry": "failed", "core": "passed", "check": DIRECT_CHECK, "trials": None},
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
                {"name": "export writes a csv", "kind": "new", "surface": "cli", "expected": "a csv with a header row", "evidence": [], "status": "passed", "retry": None, "core": None, "check": DIRECT_CHECK, "trials": None},
                {"name": "model names the file", "kind": "neighbour", "surface": "skill", "expected": "a file name", "evidence": [], "status": "failed", "retry": None, "core": "failed", "check": DIRECT_CHECK, "trials": {"count": 3, "feature_passed": 0, "core_passed": 0}},
                {"name": "model sums the rows", "kind": "neighbour", "surface": "skill", "expected": "the total", "evidence": [], "status": "failed", "retry": None, "core": None, "check": DIRECT_CHECK, "trials": {"count": 3, "feature_passed": 0, "core_passed": None}},
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
                {"name": "export writes a csv", "kind": "new", "surface": "cli", "expected": "a csv with a header row", "evidence": ["evidence/export-1.txt", "evidence/export-2.txt"], "status": "failed", "retry": "passed", "core": None, "check": DIRECT_CHECK, "trials": None},
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
                {"name": "export writes a csv", "kind": "new", "surface": "cli", "expected": "a csv with a header row", "evidence": ["evidence/export.txt"], "status": "passed", "retry": None, "core": None, "check": DIRECT_CHECK, "trials": None},
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
                {"name": "camera captures a photo", "kind": "new", "surface": "device", "expected": "a saved photo", "evidence": [], "status": "unproven", "retry": None, "core": None, "check": DIRECT_CHECK, "trials": None},
                {"name": "gallery lists photos", "kind": "neighbour", "surface": "web page", "expected": "the same list on both builds", "evidence": ["evidence/gallery.png"], "status": "passed", "retry": None, "core": "passed", "check": DIRECT_CHECK, "trials": None},
                {"name": "upload api accepts a file", "kind": "neighbour", "surface": "HTTP API", "expected": "201 on both builds", "evidence": ["evidence/upload.json"], "status": "passed", "retry": None, "core": "passed", "check": DIRECT_CHECK, "trials": None},
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
                {"name": "dashboard shows totals", "kind": "new", "surface": "web page", "expected": "the totals panel", "evidence": [], "status": "unproven", "retry": None, "core": None, "check": DIRECT_CHECK, "trials": None},
            ],
            "spend": {"tokens": 4000, "minutes": 1.5},
        }

        code, stdout, stderr, results = lighthouse_verdict(self, findings)

        self.assertEqual(code, 0, stderr)
        line, report = verdict_line(self, stdout, results)
        self.assertEqual(line["verdict"], "blocked")
        self.assertIn("start: port never opened", report)

    def test_missing_retest_path_is_unproven(self):
        plan = {"full": False, "changed": ["src/importer.py"], "retest": ["import reads the csv back"], "surfaces": ["cli"], "carried": [], "carried_paths": []}
        findings = {
            "version": 1,
            "suite": {"result": "passed", "reason": None, "failures": [], "pre_existing": [], "flaky": [], "core": None, "feature": None},
            "build": {"result": "ok", "reason": None},
            "paths": [
                {"name": "export writes a csv", "kind": "new", "surface": "cli", "expected": "a csv with a header row", "evidence": ["evidence/export.txt"], "status": "passed", "retry": None, "core": None, "check": DIRECT_CHECK, "trials": None},
                {"name": "gallery lists photos", "kind": "neighbour", "surface": "web page", "expected": "the same list on both builds", "evidence": ["evidence/gallery.png"], "status": "passed", "retry": None, "core": "passed", "check": DIRECT_CHECK, "trials": None},
            ],
            "spend": {"tokens": 6000, "minutes": 2},
        }

        code, stdout, stderr, results = lighthouse_verdict(self, findings, plan)

        self.assertEqual(code, 0, stderr)
        line, _ = verdict_line(self, stdout, results)
        self.assertEqual(line["verdict"], "unproven")
        self.assertEqual(line["unproven"], ["import reads the csv back"])

    def test_retest_path_with_only_copied_evidence_is_unproven(self):
        plan = {"full": False, "changed": ["src/importer.py"], "retest": ["import reads the csv back"], "surfaces": ["cli"], "carried": [], "carried_paths": []}
        findings = {
            "version": 1,
            "suite": {"result": "passed", "reason": None, "failures": [], "pre_existing": [], "flaky": [], "core": None, "feature": None},
            "build": {"result": "ok", "reason": None},
            "paths": [
                {"name": "export writes a csv", "kind": "new", "surface": "cli", "expected": "a csv with a header row", "evidence": ["evidence/export.txt"], "status": "passed", "retry": None, "core": None, "check": DIRECT_CHECK, "trials": None},
                {"name": "import reads the csv back", "kind": "new", "surface": "cli", "expected": "the same rows", "evidence": ["previous/evidence/import.txt"], "status": "passed", "retry": None, "core": None, "check": DIRECT_CHECK, "trials": None},
            ],
            "spend": {"tokens": 6000, "minutes": 2},
        }

        code, stdout, stderr, results = lighthouse_verdict(self, findings, plan)

        self.assertEqual(code, 0, stderr)
        line, _ = verdict_line(self, stdout, results)
        self.assertEqual(line["verdict"], "unproven")
        self.assertEqual(line["unproven"], ["import reads the csv back"])

    def test_retest_path_driven_again_counts(self):
        plan = {"full": False, "changed": ["src/importer.py"], "retest": ["import reads the csv back"], "surfaces": ["cli"], "carried": [], "carried_paths": []}
        findings = {
            "version": 1,
            "suite": {"result": "passed", "reason": None, "failures": [], "pre_existing": [], "flaky": [], "core": None, "feature": None},
            "build": {"result": "ok", "reason": None},
            "paths": [
                {"name": "export writes a csv", "kind": "new", "surface": "cli", "expected": "a csv with a header row", "evidence": ["evidence/export.txt"], "status": "passed", "retry": None, "core": None, "check": DIRECT_CHECK, "trials": None},
                {"name": "import reads the csv back", "kind": "new", "surface": "cli", "expected": "the same rows", "evidence": ["evidence/import.txt"], "status": "passed", "retry": None, "core": None, "check": DIRECT_CHECK, "trials": None},
            ],
            "spend": {"tokens": 6000, "minutes": 2},
        }

        code, stdout, stderr, results = lighthouse_verdict(self, findings, plan, files=["evidence/import.txt"])

        self.assertEqual(code, 0, stderr)
        line, _ = verdict_line(self, stdout, results)
        self.assertEqual(line["verdict"], "green")

    def test_no_plan_judges_as_before(self):
        findings = {
            "version": 1,
            "suite": {"result": "passed", "reason": None, "failures": [], "pre_existing": [], "flaky": [], "core": None, "feature": None},
            "build": {"result": "ok", "reason": None},
            "paths": [
                {"name": "export writes a csv", "kind": "new", "surface": "cli", "expected": "a csv with a header row", "evidence": ["evidence/export.txt"], "status": "passed", "retry": None, "core": None, "check": DIRECT_CHECK, "trials": None},
                {"name": "import reads the csv back", "kind": "new", "surface": "cli", "expected": "the same rows", "evidence": ["evidence/import.txt"], "status": "passed", "retry": None, "core": None, "check": DIRECT_CHECK, "trials": None},
            ],
            "spend": {"tokens": 6000, "minutes": 2},
        }

        code, stdout, stderr, results = lighthouse_verdict(self, findings)

        self.assertEqual(code, 0, stderr)
        self.assertFalse(os.path.exists(os.path.join(results, "retest.json")))
        line, _ = verdict_line(self, stdout, results)
        self.assertEqual(line["verdict"], "green")

    def assert_retest_not_driven(self, results, evidence):
        code, stdout, stderr, _ = verdict_in(self, results, retest_findings(evidence), RETEST_PLAN)

        self.assertEqual(code, 0, stderr)
        line, report = verdict_line(self, stdout, results)
        self.assertEqual(line["verdict"], "unproven")
        self.assertEqual(line["unproven"], ["import reads the csv back"])
        self.assertIn("import reads the csv back: planned for retest but not driven again", report)

    def test_retest_path_passed_with_no_evidence_is_unproven(self):
        self.assert_retest_not_driven(results_folder(self, ["evidence/export.txt"]), [])

    def test_retest_path_with_copied_evidence_spelled_from_dot_is_unproven(self):
        results = results_folder(self, ["evidence/export.txt", "previous/evidence/import.txt"])
        self.assert_retest_not_driven(results, ["./previous/evidence/import.txt"])

    def test_retest_path_with_copied_evidence_spelled_absolute_is_unproven(self):
        results = results_folder(self, ["evidence/export.txt", "previous/evidence/import.txt"])
        self.assert_retest_not_driven(results, [os.path.join(results, "previous", "evidence", "import.txt")])

    def test_retest_path_whose_evidence_is_not_in_the_results_folder_is_unproven(self):
        self.assert_retest_not_driven(results_folder(self, ["evidence/export.txt"]), ["evidence/import.txt"])

    def test_retest_path_with_evidence_linked_into_previous_is_unproven(self):
        results = results_folder(self, ["evidence/export.txt", "previous/evidence/import.txt"])
        os.symlink(os.path.join(results, "previous", "evidence", "import.txt"), os.path.join(results, "evidence", "import.txt"))
        self.assert_retest_not_driven(results, ["evidence/import.txt"])

    @unittest.skipUnless(os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), "TEST_VERDICT.PY")), "the file system tells letter case apart")
    def test_retest_path_with_copied_evidence_spelled_in_capitals_is_unproven(self):
        results = results_folder(self, ["evidence/export.txt", "previous/evidence/import.txt"])
        self.assert_retest_not_driven(results, ["PREVIOUS/evidence/import.txt"])


if __name__ == "__main__":
    unittest.main()
