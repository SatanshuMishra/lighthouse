import json
import os
import subprocess
import sys
import unittest

from tests import scratch

COMMAND_TIMEOUT_SECONDS = 60
MERGED = [
    {"number": 7, "title": "feat(execute): run the acceptance lines", "body": "executor", "url": "https://example.invalid/pull/7"},
]


def findings():
    return {
        "version": 1,
        "suite": {
            "result": "passed",
            "reason": None,
            "failures": [],
            "pre_existing": [],
            "flaky": [],
            "core": None,
            "feature": None,
        },
        "build": {"result": "ok", "reason": None},
        "paths": [
            {
                "name": "export writes a csv",
                "kind": "new",
                "surface": "cli",
                "expected": "a csv file appears",
                "evidence": ["evidence/export.txt"],
                "status": "passed",
                "retry": None,
                "core": None,
                "trials": None,
            }
        ],
        "spend": {"tokens": 5000, "minutes": 2},
    }


def verdict_line(verdict, unproven):
    return {
        "verdict": verdict,
        "failures": [],
        "unproven": list(unproven),
        "flaky": [],
        "tokens": 5000,
        "minutes": 2,
        "pr": None,
    }


def write_json(path, value):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(value, indent=2) + "\n")


def results_folder(test, line):
    results = scratch.temporary_folder(test, "lh-results-")
    os.makedirs(os.path.join(results, "evidence"))
    with open(os.path.join(results, "evidence", "export.txt"), "w", encoding="utf-8") as handle:
        handle.write("export.csv written with 3 rows\n")
    write_json(os.path.join(results, "findings.json"), findings())
    write_json(os.path.join(results, "verdict.json"), line)
    return results


def feature_branch(test):
    work, _ = scratch.make_repo(test)
    scratch.run_git(work, "checkout", "-q", "-b", "feat/x")
    scratch.commit_files(work, {"execute.py": "EXECUTE = 1\n"}, "add the executor")
    scratch.run_git(work, "push", "-q", "origin", "feat/x")
    scratch.run_git(work, "checkout", "-q", "main")
    return work


def lighthouse_pr(test, line):
    work = feature_branch(test)
    results = results_folder(test, line)
    stubs = os.path.join(scratch.make_home(test), "stubs")
    scratch.stub_gh(stubs, {"feat/x": MERGED})
    completed = subprocess.run(
        [
            sys.executable,
            scratch.LIGHTHOUSE,
            "pr",
            "--repo", work,
            "--core", "main",
            "--feature", "feat/x",
            "--results", results,
            "--summary", "add the executor",
        ],
        env=scratch.environment(scratch.make_home(test), stubs),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=COMMAND_TIMEOUT_SECONDS,
    )
    return completed.returncode, completed.stdout, completed.stderr


class PrUnprovenTest(unittest.TestCase):
    def test_unproven_verdict_composes_a_draft_without_final(self):
        code, stdout, stderr = lighthouse_pr(self, verdict_line("unproven", ["C2.1"]))

        self.assertEqual(code, 0, stdout + stderr)
        composed = json.loads(stdout)
        self.assertIs(composed.get("draft"), True)
        self.assertIn("- Unproven: C2.1", composed["body"].splitlines())

    def test_green_verdict_composes_a_ready_pull_request(self):
        code, stdout, stderr = lighthouse_pr(self, verdict_line("green", []))

        self.assertEqual(code, 0, stdout + stderr)
        composed = json.loads(stdout)
        self.assertIs(composed.get("draft"), False)


if __name__ == "__main__":
    unittest.main()
