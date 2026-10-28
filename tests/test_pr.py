import json
import os
import unittest

from tests import scratch

MERGED = [
    {"number": 1, "title": "feat(export): write a csv", "body": "export half", "url": "https://example.invalid/pull/1"},
    {"number": 2, "title": "feat(import): read the csv back", "body": "import half", "url": "https://example.invalid/pull/2"},
]


def suite(failures=()):
    return {
        "result": "failed" if failures else "passed",
        "reason": None,
        "failures": list(failures),
        "pre_existing": ["tests.test_legacy.test_old"],
        "flaky": [],
        "core": None,
        "feature": None,
    }


def path(name, kind, status, evidence, retry=None, core=None):
    return {
        "name": name,
        "kind": kind,
        "surface": "cli",
        "expected": "it works",
        "evidence": evidence,
        "status": status,
        "retry": retry,
        "core": core,
        "trials": None,
    }


def results_folder(test, findings, line):
    results = scratch.temporary_folder(test, "lh-results-")
    os.makedirs(os.path.join(results, "evidence"))
    with open(os.path.join(results, "findings.json"), "w", encoding="utf-8") as handle:
        handle.write(json.dumps(findings, indent=2) + "\n")
    with open(os.path.join(results, "verdict.json"), "w", encoding="utf-8") as handle:
        handle.write(json.dumps(line) + "\n")
    return results


def feature_branch(test):
    work, _ = scratch.make_repo(test)
    scratch.run_git(work, "checkout", "-q", "-b", "feat/x")
    scratch.commit_files(work, {"export.py": "EXPORT = 1\n"}, "add export")
    scratch.commit_files(work, {"importer.py": "IMPORT = 1\n"}, "add import")
    scratch.run_git(work, "push", "-q", "origin", "feat/x")
    scratch.run_git(work, "checkout", "-q", "main")
    return work


def lighthouse_pr(test, findings, line, extra=(), answers=None):
    work = feature_branch(test)
    results = results_folder(test, findings, line)
    stubs = os.path.join(scratch.make_home(test), "stubs")
    scratch.stub_gh(stubs, answers if answers is not None else {"feat/x": MERGED})
    env = scratch.environment(scratch.make_home(test), stubs)
    return scratch.run_lighthouse(
        [
            "pr",
            "--repo", work,
            "--core", "main",
            "--feature", "feat/x",
            "--results", results,
            "--summary", "add csv export and import",
            *extra,
        ],
        env,
    )


def waiting_findings():
    return {
        "version": 1,
        "suite": suite(),
        "build": {"result": "ok", "reason": None},
        "paths": [path("export writes a csv", "new", "passed", ["evidence/export.txt"])],
        "spend": {"tokens": 5000, "minutes": 2},
    }


def waiting_line(verdict, failures=(), unproven=()):
    return {
        "verdict": verdict,
        "failures": list(failures),
        "unproven": list(unproven),
        "flaky": [],
        "tokens": 5000,
        "minutes": 2,
        "pr": None,
    }


def risk_section(text):
    return text.split("## Risk\n", 1)[1].split("\n## ", 1)[0]


class PullRequestTest(unittest.TestCase):
    def test_green_opens(self):
        findings = {
            "version": 1,
            "suite": suite(),
            "build": {"result": "ok", "reason": None},
            "paths": [
                path("export writes a csv", "new", "passed", ["evidence/export.txt"]),
                path("import reads the csv back", "new", "failed", ["evidence/import-1.txt", "evidence/import-2.txt"], retry="passed"),
                path("report totals match", "neighbour", "passed", ["evidence/totals-feature.txt", "evidence/totals-core.txt"], core="passed"),
                path("settings page loads", "neighbour", "unproven", []),
            ],
            "spend": {"tokens": 12000, "minutes": 4.5},
        }
        line = {
            "verdict": "green",
            "failures": [],
            "unproven": ["settings page loads"],
            "flaky": ["import reads the csv back"],
            "tokens": 12000,
            "minutes": 4.5,
            "pr": None,
        }

        code, stdout, stderr = lighthouse_pr(self, findings, line)

        self.assertEqual(code, 0, stderr)
        composed = json.loads(stdout)
        self.assertEqual(sorted(composed), ["base", "body", "draft", "head", "title"])
        self.assertIs(composed["draft"], False)
        self.assertEqual(composed["title"], "feat(work): add csv export and import")
        self.assertLessEqual(len(composed["title"]), 72)
        self.assertEqual((composed["base"], composed["head"]), ("main", "feat/x"))
        self.assertEqual(
            composed["body"],
            "\n".join(
                [
                    "## What changed",
                    "",
                    "- feat(export): write a csv (#1)",
                    "- feat(import): read the csv back (#2)",
                    "",
                    "## Why",
                    "",
                    "Carries feat/x into main.",
                    "",
                    "## Risk",
                    "",
                    "Verdict: green",
                    "",
                    "- Unproven: settings page loads",
                    "- Flaky: import reads the csv back",
                    "",
                    "## Verification",
                    "",
                    "Suite: passed, 0 failures, 1 pre-existing",
                    "",
                    "- export writes a csv: new, passed; evidence: evidence/export.txt",
                    "- import reads the csv back: new, failed; evidence: evidence/import-1.txt, evidence/import-2.txt",
                    "- report totals match: neighbour, passed; evidence: evidence/totals-feature.txt, evidence/totals-core.txt",
                    "- settings page loads: neighbour, unproven; evidence: none",
                    "",
                    "Neighbours rechecked: report totals match",
                    "",
                    "lighthouse spent 12000 tokens over 4.5 minutes.",
                    "",
                    "## Links",
                    "",
                    "- https://example.invalid/pull/1",
                    "- https://example.invalid/pull/2",
                    "",
                ]
            ),
        )

    def test_failures_wait(self):
        code, stdout, stderr = lighthouse_pr(
            self, waiting_findings(), waiting_line("failures", failures=["report totals match"])
        )

        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        self.assertIn("failures", stderr)
        self.assertIn("--final", stderr)

    def test_blocked_waits(self):
        code, stdout, stderr = lighthouse_pr(self, waiting_findings(), waiting_line("blocked"))

        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        self.assertIn("blocked", stderr)
        self.assertIn("--final", stderr)

    def test_unproven_opens_as_a_draft(self):
        code, stdout, stderr = lighthouse_pr(
            self, waiting_findings(), waiting_line("unproven", unproven=["export writes a csv"])
        )

        self.assertEqual(code, 0, stderr)
        composed = json.loads(stdout)
        self.assertIs(composed["draft"], True)
        risk = risk_section(composed["body"])
        self.assertIn("Verdict: unproven", risk)
        self.assertIn("- Unproven: export writes a csv\n", risk)

    def test_final_opens_with_failures_listed(self):
        findings = {
            "version": 1,
            "suite": suite(failures=["tests.test_export.test_header"]),
            "build": {"result": "ok", "reason": None},
            "paths": [
                path("export writes a csv", "new", "passed", ["evidence/export.txt"]),
                path("report totals match", "neighbour", "failed", ["evidence/totals-feature.txt"], retry="failed", core="passed"),
            ],
            "spend": {"tokens": 9000, "minutes": 3},
        }
        line = waiting_line("failures", failures=["suite: tests.test_export.test_header", "report totals match"])

        code, stdout, stderr = lighthouse_pr(self, findings, line, extra=["--final"], answers={})

        self.assertEqual(code, 0, stderr)
        composed = json.loads(stdout)
        self.assertIs(composed["draft"], True)
        risk = risk_section(composed["body"])
        self.assertIn("Verdict: failures", risk)
        self.assertIn("- Unresolved: suite: tests.test_export.test_header\n", risk)
        self.assertIn("- Unresolved: report totals match\n", risk)
        self.assertIn("- add export\n- add import\n", composed["body"])
        self.assertIn("## Links\n\nNone.\n", composed["body"])


if __name__ == "__main__":
    unittest.main()
