import json
import os
import subprocess
import sys
import unittest

from tests import contract_check, scratch

FEATURE_COMMIT = "0123456789abcdef0123456789abcdef01234567"
CORE_COMMIT = "fedcba9876543210fedcba9876543210fedcba98"
OTHER_COMMIT = "1111111111111111111111111111111111111111"
COMMAND_TIMEOUT_SECONDS = 60
CHECK_SURFACE = {"family": "cli", "target": "bin/lighthouse verdict"}
DIRECT_CHECK = {"kind": "direct", "why": "the command prints the written file"}
PATH_NAME = "export writes the file"
PATH_EVIDENCE = "evidence/export.txt"
LAUNCH_PR = "https://example.invalid/pr/1"


def passing_suite(failures=()):
    return {
        "result": "passed",
        "reason": None,
        "failures": list(failures),
        "pre_existing": [],
        "flaky": [],
        "core": None,
        "feature": None,
    }


def new_path(status="passed", evidence=(PATH_EVIDENCE,), surface="cli", retry=None, trials=None):
    return {
        "name": PATH_NAME,
        "kind": "new",
        "surface": surface,
        "expected": "the file holds the exported rows",
        "evidence": list(evidence),
        "status": status,
        "retry": retry,
        "core": None,
        "check": DIRECT_CHECK,
        "trials": trials,
    }


def findings_with(paths, suite=None):
    return {
        "version": 1,
        "suite": passing_suite() if suite is None else suite,
        "build": {"result": "ok", "reason": None},
        "paths": list(paths),
        "spend": {"tokens": 100, "minutes": 1},
    }


def k3_result(status, evidence, commit=FEATURE_COMMIT, check_id="C1.1"):
    return {
        "check_id": check_id,
        "commit": commit,
        "surface": dict(CHECK_SURFACE),
        "status": status,
        "evidence": list(evidence),
        "seconds": 0.25,
        "runner": "lighthouse execute",
    }


def exact_k1_line(check_id="C1.1"):
    return {
        "id": check_id,
        "kind": "exact",
        "surface": dict(CHECK_SURFACE),
        "command": "test -f feature-only.txt",
        "pass": "exit 0",
    }


def plan_with(checks, reach=None):
    return {"checks": list(checks), "neighbours": [], "changed": [], "reach": {} if reach is None else reach}


def exact_check(check_id="C1.1"):
    return {"id": check_id, "kind": "exact", "trials": 1}


def write_json(folder, name, value):
    with open(os.path.join(folder, name), "w", encoding="utf-8") as handle:
        handle.write(json.dumps(value, indent=2) + "\n")


def write_evidence(results, relative_path, text="the command ran and printed its output\n"):
    path = os.path.join(results, relative_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return relative_path


def write_checks(results, lines):
    with open(os.path.join(results, "checks.jsonl"), "w", encoding="utf-8") as handle:
        for line in lines:
            handle.write(json.dumps(line) + "\n")


def results_folder(test, paths=(), suite_file=True, findings_suite=None, suite_json=None):
    results = scratch.temporary_folder(test, "lh-k3-results-")
    os.makedirs(os.path.join(results, "evidence"))
    write_json(results, "commits.json", {"core": CORE_COMMIT, "feature": FEATURE_COMMIT})
    if suite_file:
        write_json(results, "suite.json", passing_suite() if suite_json is None else suite_json)
    write_json(results, "findings.json", findings_with(paths, findings_suite))
    return results


def run_verdict(test, results):
    env = scratch.environment(scratch.make_home(test))
    completed = subprocess.run(
        [sys.executable, scratch.LIGHTHOUSE, "verdict", "--results", results],
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=COMMAND_TIMEOUT_SECONDS,
    )
    test.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
    line = json.loads(completed.stdout.strip().splitlines()[-1])
    test.assertIn("verdict", line, completed.stdout)
    return line


def profile_with_surface(name, available):
    surface = {
        "name": name,
        "kind": "command line",
        "paths": ["README.md"],
        "driver": "the shell",
        "available": available,
        "sign_in": {"method": "none", "command": None},
        "credentials": [],
        "trials": 1,
    }
    return scratch.sample_profile(surfaces=[surface])


CLAUDE_STUB = """#!{python}
import json
import os
import shlex
import shutil
import sys

folder = os.path.dirname(os.path.realpath(__file__))
words = shlex.split(sys.argv[2])
results = words[words.index("--results") + 1]
record = os.path.join(results, "record.json")
if os.path.exists(record):
    shutil.copyfile(record, os.path.join(folder, "record-seen-by-child.json"))
verdict_file = os.path.join(folder, "verdict-to-write.json")
if os.path.exists(verdict_file):
    shutil.copyfile(verdict_file, os.path.join(results, "verdict.json"))
with open(os.path.join(folder, "claude-output.txt"), encoding="utf-8") as output:
    sys.stdout.write(output.read())
sys.exit(0)
"""

CAFFEINATE_STUB = """#!{python}
import sys
sys.exit(0)
"""

SYSTEMD_INHIBIT_STUB = """#!{python}
import os
import sys

wrapped = [argument for argument in sys.argv[1:] if not argument.startswith("--what=") and not argument.startswith("--why=")]
os.execvp(wrapped[0], wrapped)
"""


def write_stub(folder, name, text):
    path = os.path.join(folder, name)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text.format(python=sys.executable))
    os.chmod(path, 0o755)


def claude_reply(result):
    return json.dumps(
        {
            "type": "result",
            "result": result,
            "session_id": "child-session-k3",
            "duration_ms": 1000,
            "modelUsage": {},
        }
    )


def stub_folder(test, reply, verdict_to_write=None):
    folder = scratch.temporary_folder(test, "lh-k3-stubs-")
    write_stub(folder, "claude", CLAUDE_STUB)
    write_stub(folder, "caffeinate", CAFFEINATE_STUB)
    write_stub(folder, "systemd-inhibit", SYSTEMD_INHIBIT_STUB)
    with open(os.path.join(folder, "claude-output.txt"), "w", encoding="utf-8") as handle:
        handle.write(reply)
    if verdict_to_write is not None:
        write_json(folder, "verdict-to-write.json", verdict_to_write)
    return folder


def run_launch(test, stubs, extra_flags=()):
    repo, _ = scratch.make_repo(test)
    results = os.path.join(scratch.temporary_folder(test, "lh-k3-launch-"), "results")
    env = {
        **scratch.environment(scratch.make_home(test), stubs),
        "PLUGIN_METRICS_DIR": scratch.temporary_folder(test, "lh-k3-store-"),
    }
    completed = subprocess.run(
        [
            sys.executable,
            scratch.LIGHTHOUSE,
            "launch",
            "--repo",
            repo,
            "--core",
            "main",
            "--feature",
            "feat/x",
            "--results",
            results,
            *extra_flags,
        ],
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=COMMAND_TIMEOUT_SECONDS,
    )
    return completed, results


def read_bytes(path):
    with open(path, "rb") as handle:
        return handle.read()


class K3VerdictTest(unittest.TestCase):
    def test_all_checks_passing_with_evidence_is_green(self):
        results = results_folder(self)
        evidence = write_evidence(results, "evidence/checks/C1.1-1.log")
        result = k3_result("pass", [evidence])
        contract_check.assert_valid(self, result, contract_check.K3_SCHEMA)
        write_json(results, "plan.json", plan_with([exact_check()]))
        write_checks(results, [result])
        line = run_verdict(self, results)
        self.assertEqual(line["verdict"], "green", line)
        self.assertEqual(line["failures"], [])
        self.assertEqual(line["unproven"], [])
        self.assertEqual(line["flaky"], [])

    def test_passed_check_without_its_evidence_file_is_not_green(self):
        results = results_folder(self)
        result = k3_result("pass", ["evidence/checks/C1.1-1.log"])
        contract_check.assert_valid(self, result, contract_check.K3_SCHEMA)
        write_json(results, "plan.json", plan_with([exact_check()]))
        write_checks(results, [result])
        self.assertFalse(os.path.exists(os.path.join(results, "evidence", "checks", "C1.1-1.log")))
        line = run_verdict(self, results)
        self.assertNotEqual(line["verdict"], "green", line)
        self.assertIn("C1.1", line["unproven"], line)

    def test_passed_path_without_its_evidence_file_is_not_green(self):
        results = results_folder(self, paths=[new_path(status="passed")])
        self.assertFalse(os.path.exists(os.path.join(results, PATH_EVIDENCE)))
        line = run_verdict(self, results)
        self.assertNotEqual(line["verdict"], "green", line)
        self.assertIn(PATH_NAME, line["unproven"], line)

    def test_check_that_failed_once_without_a_retry_is_a_failure(self):
        results = results_folder(self)
        evidence = write_evidence(results, "evidence/checks/C1.1-1.log", "exit 1\n")
        result = k3_result("fail", [evidence])
        contract_check.assert_valid(self, result, contract_check.K3_SCHEMA)
        write_json(results, "plan.json", plan_with([exact_check()]))
        write_checks(results, [result])
        line = run_verdict(self, results)
        self.assertEqual(line["verdict"], "failures", line)
        self.assertIn("C1.1", line["failures"], line)

    def test_new_path_failed_without_a_retry_is_a_failure(self):
        results = results_folder(self, paths=[new_path(status="failed", retry=None)])
        write_evidence(results, PATH_EVIDENCE, "the file was empty\n")
        line = run_verdict(self, results)
        self.assertEqual(line["verdict"], "failures", line)
        self.assertIn(PATH_NAME, line["failures"], line)

    def test_judged_check_passing_two_of_three_runs_is_not_green(self):
        results = results_folder(self)
        statuses = ["pass", "pass", "fail"]
        lines = []
        for run_number, status in enumerate(statuses, start=1):
            evidence = write_evidence(results, "evidence/checks/C1.1-{}.log".format(run_number), status + "\n")
            result = k3_result(status, [evidence])
            contract_check.assert_valid(self, result, contract_check.K3_SCHEMA)
            lines.append(result)
        write_json(results, "plan.json", plan_with([{"id": "C1.1", "kind": "judged", "trials": 3}]))
        write_checks(results, lines)
        line = run_verdict(self, results)
        self.assertEqual(line["verdict"], "failures", line)
        self.assertIn("C1.1", line["flaky"], line)

    def test_new_path_passing_two_of_three_trials_is_not_green(self):
        trials = {"count": 3, "feature_passed": 2, "core_passed": None}
        results = results_folder(self, paths=[new_path(status="failed", retry=None, trials=trials)])
        write_evidence(results, PATH_EVIDENCE, "two of three trials passed\n")
        line = run_verdict(self, results)
        self.assertEqual(line["verdict"], "failures", line)
        self.assertIn(PATH_NAME, line["flaky"], line)

    def test_suite_failures_come_from_suite_json(self):
        failing_test = "tests.test_a.A.test_one"
        results = results_folder(
            self, suite_json=passing_suite(failures=[failing_test]), findings_suite=passing_suite()
        )
        evidence = write_evidence(results, "evidence/checks/C1.1-1.log")
        result = k3_result("pass", [evidence])
        contract_check.assert_valid(self, result, contract_check.K3_SCHEMA)
        write_json(results, "plan.json", plan_with([exact_check()]))
        write_checks(results, [result])
        line = run_verdict(self, results)
        self.assertNotEqual(line["verdict"], "green", line)
        self.assertIn("suite: " + failing_test, line["failures"], line)

    def test_missing_suite_json_is_not_green(self):
        results = results_folder(self, paths=[new_path(status="passed")], suite_file=False)
        write_evidence(results, PATH_EVIDENCE, "the exported rows\n")
        self.assertFalse(os.path.exists(os.path.join(results, "suite.json")))
        line = run_verdict(self, results)
        self.assertNotEqual(line["verdict"], "green", line)
        self.assertIn("suite: suite.json is missing", line["unproven"], line)

    def test_invalid_check_result_is_ignored(self):
        results = results_folder(self)
        evidence = write_evidence(results, "evidence/checks/C1.1-1.log")
        result = k3_result("pass", [evidence])
        del result["runner"]
        self.assertNotEqual(contract_check.errors(result, contract_check.K3_SCHEMA), [])
        write_json(results, "plan.json", plan_with([exact_check()]))
        write_checks(results, [result])
        line = run_verdict(self, results)
        self.assertNotEqual(line["verdict"], "green", line)
        self.assertIn("C1.1", line["unproven"], line)

    def test_result_at_another_commit_is_ignored(self):
        results = results_folder(self)
        evidence = write_evidence(results, "evidence/checks/C1.1-1.log")
        result = k3_result("pass", [evidence], commit=OTHER_COMMIT)
        contract_check.assert_valid(self, result, contract_check.K3_SCHEMA)
        write_json(results, "plan.json", plan_with([exact_check()]))
        write_checks(results, [result])
        line = run_verdict(self, results)
        self.assertNotEqual(line["verdict"], "green", line)
        self.assertIn("C1.1", line["unproven"], line)

    def test_passed_path_with_no_evidence_is_not_green(self):
        results = results_folder(self, paths=[new_path(status="passed", evidence=())])
        line = run_verdict(self, results)
        self.assertNotEqual(line["verdict"], "green", line)
        self.assertIn(PATH_NAME, line["unproven"], line)

    def test_verdict_without_execute_is_not_green(self):
        results = results_folder(self, paths=[new_path(status="passed")])
        write_evidence(results, PATH_EVIDENCE, "the exported rows\n")
        k1_line = exact_k1_line()
        contract_check.assert_valid(self, k1_line, contract_check.K1_SCHEMA)
        write_json(results, "record.json", {"criteria": [{"id": "1", "acceptance": [k1_line]}]})
        self.assertFalse(os.path.exists(os.path.join(results, "plan.json")))
        self.assertFalse(os.path.exists(os.path.join(results, "checks.jsonl")))
        line = run_verdict(self, results)
        self.assertNotEqual(line["verdict"], "green", line)
        self.assertIn("C1.1", line["unproven"], line)

    def test_launch_prints_verdict_json_not_the_childs_line(self):
        written = {
            "verdict": "failures",
            "failures": ["C1.1"],
            "unproven": [],
            "flaky": [],
            "tokens": 0,
            "minutes": 0,
            "dollars": None,
            "pr": None,
        }
        childs_line = json.dumps(
            {
                "verdict": "green",
                "failures": [],
                "unproven": [],
                "flaky": [],
                "tokens": 10,
                "minutes": 1,
                "dollars": None,
                "pr": LAUNCH_PR,
            }
        )
        stubs = stub_folder(self, claude_reply("Every check passed.\n" + childs_line), verdict_to_write=written)
        completed, results = run_launch(self, stubs)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        printed = json.loads(completed.stdout.strip().splitlines()[-1])
        self.assertEqual(printed["verdict"], "failures", printed)
        self.assertEqual(printed["failures"], ["C1.1"], printed)
        self.assertEqual(printed["pr"], LAUNCH_PR, printed)
        with open(os.path.join(results, "launch.json"), encoding="utf-8") as handle:
            self.assertEqual(json.load(handle), printed)

    def test_launch_copies_the_record_beside_the_spec(self):
        spec_folder = scratch.temporary_folder(self, "lh-k3-spec-")
        spec = os.path.join(spec_folder, "hr-x.md")
        with open(spec, "w", encoding="utf-8") as handle:
            handle.write("# hr-x\n\nThe change under test.\n")
        k1_line = exact_k1_line()
        contract_check.assert_valid(self, k1_line, contract_check.K1_SCHEMA)
        record_path = os.path.join(spec_folder, "hr-x.record.json")
        with open(record_path, "w", encoding="utf-8") as handle:
            handle.write(json.dumps({"criteria": [{"id": "1", "acceptance": [k1_line]}]}, indent=3) + "\n\n")
        blocked_line = json.dumps(
            {
                "verdict": "blocked",
                "failures": [],
                "unproven": [],
                "flaky": [],
                "tokens": 0,
                "minutes": 0,
                "pr": None,
                "reason": "the profile is broken",
            }
        )
        stubs = stub_folder(self, claude_reply(blocked_line))
        completed, results = run_launch(self, stubs, ["--spec", spec])
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        expected = read_bytes(record_path)
        copied = os.path.join(results, "record.json")
        self.assertTrue(os.path.isfile(copied), "launch wrote no record.json into the results folder")
        self.assertEqual(read_bytes(copied), expected)
        seen = os.path.join(stubs, "record-seen-by-child.json")
        self.assertTrue(os.path.isfile(seen), "record.json was absent when the child started")
        self.assertEqual(read_bytes(seen), expected)

    def test_unavailable_surface_paths_are_unproven(self):
        results = results_folder(self, paths=[new_path(status="passed", surface="gone")])
        write_evidence(results, PATH_EVIDENCE, "the exported rows\n")
        write_json(results, "profile.json", profile_with_surface("gone", False))
        line = run_verdict(self, results)
        self.assertNotEqual(line["verdict"], "green", line)
        self.assertIn(PATH_NAME, line["unproven"], line)

    def test_unreached_surface_this_run_is_unproven(self):
        results = results_folder(self, paths=[new_path(status="passed", surface="gone")])
        write_evidence(results, PATH_EVIDENCE, "the exported rows\n")
        write_json(results, "profile.json", profile_with_surface("gone", True))
        write_json(results, "plan.json", plan_with([], reach={"gone": False}))
        line = run_verdict(self, results)
        self.assertNotEqual(line["verdict"], "green", line)
        self.assertIn(PATH_NAME, line["unproven"], line)


if __name__ == "__main__":
    unittest.main()
