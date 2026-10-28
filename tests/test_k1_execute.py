import json
import os
import subprocess
import sys
import unittest

from tests import scratch

COMMAND_SECONDS = 60
FEATURE_BRANCH = "feat/x"
CLI_SURFACE = {"family": "cli", "target": "bin/tool"}
DIRECT_CHECK = {"kind": "direct", "why": "the command prints the outcome"}
PASSED_SUITE = {
    "result": "passed",
    "reason": None,
    "failures": [],
    "pre_existing": [],
    "flaky": [],
    "core": None,
    "feature": None,
}


def exact_line(identifier, command):
    return {"id": identifier, "kind": "exact", "surface": CLI_SURFACE, "command": command, "pass": "exit 0"}


def judged_line(identifier, command):
    return {
        **exact_line(identifier, command),
        "kind": "judged",
        "rubric": "the output reads as the change intends",
        "trials": 3,
    }


def record_of(*lines):
    return {"criteria": [{"number": "1.1", "acceptance": list(lines)}, {"number": "1.2"}]}


def surface(name, paths, reach=None):
    base = dict(scratch.sample_profile()["surfaces"][0])
    named = {**base, "name": name, "paths": paths}
    return {**named, "reach": reach} if reach is not None else named


def profile_with(surfaces):
    return scratch.sample_profile(surfaces=surfaces)


def write_json(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(value, indent=2) + "\n")
    return path


def read_json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def read_results(path):
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle.read().splitlines() if line.strip()]


def last_json(stdout):
    return json.loads(stdout.strip().splitlines()[-1])


def lighthouse(args, env):
    completed = subprocess.run(
        [sys.executable, scratch.LIGHTHOUSE, *args],
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=COMMAND_SECONDS,
    )
    return completed.returncode, completed.stdout, completed.stderr


def assert_k1_valid(test, line):
    from tests import contract_check

    contract_check.assert_valid(test, line, contract_check.K1_SCHEMA)


def assert_k3_valid(test, result):
    from tests import contract_check

    contract_check.assert_valid(test, result, contract_check.K3_SCHEMA)


class Prepared:
    def __init__(self, test, feature_files, surfaces):
        repo, _ = scratch.make_repo(test)
        scratch.run_git(repo, "checkout", "-q", "-b", FEATURE_BRANCH)
        self.feature_commit = scratch.commit_files(repo, feature_files, "add the feature")
        scratch.run_git(repo, "checkout", "-q", "main")
        self.repo = repo
        self.results = os.path.join(scratch.temporary_folder(test, "lh-results-"), "results")
        self.inputs = scratch.temporary_folder(test, "lh-inputs-")
        stubs = scratch.temporary_folder(test, "lh-stubs-")
        scratch.stub_gh(stubs, {})
        self.env = scratch.environment(scratch.make_home(test), stubs)
        self.profile = write_json(os.path.join(self.inputs, "profile.json"), profile_with(surfaces))
        code, stdout, stderr = lighthouse(
            ["worktrees", "--repo", repo, "--core", "main", "--feature", FEATURE_BRANCH, "--results", self.results],
            self.env,
        )
        test.assertEqual(code, 0, stdout + stderr)
        test.assertEqual(read_json(os.path.join(self.results, "commits.json"))["feature"], self.feature_commit)

    def record(self, *lines):
        return write_json(os.path.join(self.inputs, "record.json"), record_of(*lines))

    def execute(self, *flags):
        return lighthouse(["execute", "--results", self.results, *flags], self.env)

    def execute_record(self, *lines):
        return self.execute("--record", self.record(*lines), "--profile", self.profile)

    def checks(self):
        return read_results(os.path.join(self.results, "checks.jsonl"))

    def plan(self):
        return read_json(os.path.join(self.results, "plan.json"))

    def verdict(self, findings):
        write_json(os.path.join(self.results, "suite.json"), PASSED_SUITE)
        write_json(os.path.join(self.results, "findings.json"), findings)
        return lighthouse(["verdict", "--results", self.results], self.env)


def default_setup(test):
    return Prepared(test, {"feature-only.txt": "only on the feature branch\n"}, [surface("cli", ["README.md"])])


def findings_with(paths):
    return {
        "version": 1,
        "suite": dict(PASSED_SUITE),
        "build": {"result": "ok", "reason": None},
        "paths": paths,
        "spend": {"tokens": 100, "minutes": 1},
    }


def findings_path(name, kind, evidence):
    return {
        "name": name,
        "kind": kind,
        "surface": "alpha",
        "expected": "the surface still answers",
        "evidence": [evidence],
        "status": "passed",
        "retry": None,
        "core": None,
        "check": DIRECT_CHECK,
        "trials": None,
    }


def write_evidence(results, relative):
    path = os.path.join(results, relative)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("driven and observed\n")


class K1ExecuteTest(unittest.TestCase):
    def assert_results(self, results, check_id, statuses):
        self.assertEqual([result["check_id"] for result in results], [check_id] * len(statuses))
        self.assertEqual([result["status"] for result in results], statuses)
        for result in results:
            assert_k3_valid(self, result)

    def test_each_line_runs_from_the_feature_root_as_its_check(self):
        prepared = default_setup(self)
        line = exact_line("C1.1", "test -f feature-only.txt")
        assert_k1_valid(self, line)
        code, stdout, stderr = prepared.execute_record(line)
        self.assertEqual(code, 0, stdout + stderr)
        results = prepared.checks()
        self.assertEqual(len(results), 1, results)
        result = results[0]
        assert_k3_valid(self, result)
        self.assertEqual(result["check_id"], "C1.1")
        self.assertEqual(result["commit"], prepared.feature_commit)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["runner"], "lighthouse execute")
        self.assertEqual(len(result["evidence"]), 1, result["evidence"])
        item = result["evidence"][0]
        self.assertFalse(os.path.isabs(item), item)
        located = os.path.realpath(os.path.join(prepared.results, item))
        self.assertTrue(located.startswith(os.path.realpath(prepared.results) + os.sep), item)
        self.assertTrue(os.path.isfile(located), item)
        self.assertGreater(os.path.getsize(located), 0, item)

    def test_exit_one_fails_and_is_retried_once(self):
        prepared = default_setup(self)
        line = exact_line("C1.1", "exit 1")
        assert_k1_valid(self, line)
        code, stdout, stderr = prepared.execute_record(line)
        self.assertEqual(code, 0, stdout + stderr)
        self.assert_results(prepared.checks(), "C1.1", ["fail", "fail"])

    def test_other_exits_could_not_run(self):
        prepared = default_setup(self)
        line = exact_line("C1.1", "exit 3")
        assert_k1_valid(self, line)
        code, stdout, stderr = prepared.execute_record(line)
        self.assertEqual(code, 0, stdout + stderr)
        self.assert_results(prepared.checks(), "C1.1", ["could-not-run"])

    def test_judged_line_runs_its_trials(self):
        prepared = default_setup(self)
        line = judged_line("C1.1", "exit 0")
        assert_k1_valid(self, line)
        code, stdout, stderr = prepared.execute_record(line)
        self.assertEqual(code, 0, stdout + stderr)
        self.assert_results(prepared.checks(), "C1.1", ["pass", "pass", "pass"])

    def test_plan_lists_checks_and_code_computed_neighbours(self):
        prepared = Prepared(
            self,
            {"src/alpha/a.py": "print('alpha')\n"},
            [surface("alpha", ["src/alpha"]), surface("beta", ["src/beta"])],
        )
        first, second = exact_line("C1.1", "exit 0"), exact_line("C2.1", "exit 0")
        for line in (first, second):
            assert_k1_valid(self, line)
        code, stdout, stderr = prepared.execute_record(first, second)
        self.assertEqual(code, 0, stdout + stderr)
        plan = prepared.plan()
        self.assertEqual(
            plan["checks"],
            [{"id": "C1.1", "kind": "exact", "trials": 1}, {"id": "C2.1", "kind": "exact", "trials": 1}],
        )
        self.assertEqual(plan["neighbours"], ["alpha"])

    def test_malformed_line_is_refused(self):
        from tests import contract_check

        prepared = default_setup(self)
        line = exact_line("X1", "exit 0")
        self.assertNotEqual(contract_check.errors(line, contract_check.K1_SCHEMA), [])
        code, stdout, stderr = prepared.execute_record(line)
        self.assertEqual(code, 2, stdout + stderr)
        error = last_json(stdout)["error"]
        self.assertIn("X1", json.dumps(error), error)
        self.assertFalse(os.path.exists(os.path.join(prepared.results, "checks.jsonl")))

    def test_execute_reads_the_record_beside_the_spec(self):
        prepared = default_setup(self)
        line = exact_line("C1.1", "exit 0")
        assert_k1_valid(self, line)
        folder = scratch.temporary_folder(self, "lh-spec-")
        spec = os.path.join(folder, "hr-x.md")
        with open(spec, "w", encoding="utf-8") as handle:
            handle.write("# hr-x\n")
        write_json(os.path.join(folder, "hr-x.record.json"), record_of(line))
        code, stdout, stderr = prepared.execute("--spec", spec, "--profile", prepared.profile)
        self.assertEqual(code, 0, stdout + stderr)
        self.assert_results(prepared.checks(), "C1.1", ["pass"])

    def test_execute_reads_the_record_in_the_results_folder(self):
        prepared = default_setup(self)
        line = exact_line("C1.1", "exit 0")
        assert_k1_valid(self, line)
        write_json(os.path.join(prepared.results, "record.json"), record_of(line))
        code, stdout, stderr = prepared.execute("--profile", prepared.profile)
        self.assertEqual(code, 0, stdout + stderr)
        self.assert_results(prepared.checks(), "C1.1", ["pass"])

    def test_execute_reaches_each_surface(self):
        prepared = Prepared(
            self,
            {"feature-only.txt": "only on the feature branch\n"},
            [surface("alpha", ["src/alpha"], reach="true"), surface("beta", ["src/beta"], reach="exit 1")],
        )
        line = exact_line("C1.1", "test -f feature-only.txt")
        assert_k1_valid(self, line)
        code, stdout, stderr = prepared.execute_record(line)
        self.assertEqual(code, 0, stdout + stderr)
        self.assertEqual(prepared.plan()["reach"], {"alpha": True, "beta": False})

    def test_verdict_names_each_check_by_its_id(self):
        prepared = Prepared(
            self, {"feature-only.txt": "only on the feature branch\n"}, [surface("alpha", ["feature-only.txt"])]
        )
        passing, failing = exact_line("C1.1", "exit 0"), exact_line("C1.2", "exit 1")
        for line in (passing, failing):
            assert_k1_valid(self, line)
        code, stdout, stderr = prepared.execute_record(passing, failing)
        self.assertEqual(code, 0, stdout + stderr)
        for result in prepared.checks():
            assert_k3_valid(self, result)
        write_evidence(prepared.results, "evidence/alpha.txt")
        write_evidence(prepared.results, "evidence/c12.txt")
        findings = findings_with(
            [
                findings_path("alpha still answers", "neighbour", "evidence/alpha.txt"),
                findings_path("C1.2", "new", "evidence/c12.txt"),
            ]
        )
        code, stdout, stderr = prepared.verdict(findings)
        self.assertEqual(code, 0, stdout + stderr)
        line = last_json(stdout)
        self.assertEqual(line["verdict"], "failures", line)
        self.assertIn("C1.2", line["failures"])
        self.assertNotIn("C1.1", line["failures"])
        self.assertNotIn("C1.1", line["unproven"])

    def test_code_computed_neighbour_without_a_path_is_unproven(self):
        prepared = Prepared(
            self, {"feature-only.txt": "only on the feature branch\n"}, [surface("alpha", ["feature-only.txt"])]
        )
        line = exact_line("C1.1", "exit 0")
        assert_k1_valid(self, line)
        code, stdout, stderr = prepared.execute_record(line)
        self.assertEqual(code, 0, stdout + stderr)
        self.assertEqual(prepared.plan()["neighbours"], ["alpha"])
        code, stdout, stderr = prepared.verdict(findings_with([]))
        self.assertEqual(code, 0, stdout + stderr)
        verdict_line = last_json(stdout)
        self.assertNotEqual(verdict_line["verdict"], "green", verdict_line)
        self.assertIn("neighbour alpha", verdict_line["unproven"])


if __name__ == "__main__":
    unittest.main()
