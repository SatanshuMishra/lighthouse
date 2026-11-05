import json
import os
import sys
import unittest

from lighthouse_tool import pr_fields
from tests import scratch

SUMMARY = "add csv export and import"
SPEND = {"tokens": 5000, "minutes": 2, "dollars": None}
RENDER_STUB = """#!{python}
import json
import sys

CALLS = {calls!r}
arguments = sys.argv[1:]
with open(CALLS, "a", encoding="utf-8") as handle:
    handle.write(json.dumps({{"argv": arguments, "stdin": sys.stdin.read()}}) + "\\n")
sys.stdout.write({output!r})
sys.stderr.write({error!r})
sys.exit({code})
"""
GREEN_DRAFT = {
    "problem": ["Exports need a round trip.", "Users lose data today."],
    "change": ["Write a csv on export.", "Read the csv back on import."],
    "approach": ["The importer reuses the export header."],
    "impact": ["Users can move data between workspaces."],
    "tradeoffs": [
        "Unproven: settings page loads was not driven.",
        "Flaky: import reads the csv back passed on retry.",
    ],
}
GREEN_FIELDS = {
    "title": "feat(work): add csv export and import",
    "problem": ["Exports need a round trip.", "Users lose data today."],
    "change": ["Write a csv on export.", "Read the csv back on import."],
    "approach": ["The importer reuses the export header."],
    "impact": ["Users can move data between workspaces."],
    "tradeoffs": [
        "Unproven: settings page loads was not driven.",
        "Flaky: import reads the csv back passed on retry.",
    ],
    "testing": [
        {"check": "Lighthouse verdict", "result": "green"},
        {"check": "Project suite", "result": "passed"},
        {"check": "Failures", "result": "0"},
        {"check": "Unproven", "result": "1"},
        {"check": "Flaky", "result": "1"},
    ],
}
GREEN_BODY = "\n".join(
    [
        "## Problem",
        "Exports need a round trip. Users lose data today.",
        "",
        "## Change",
        "- Write a csv on export.",
        "- Read the csv back on import.",
        "",
        "The importer reuses the export header.",
        "",
        "## Impact",
        "Users can move data between workspaces.",
        "",
        "## Trade-offs and open problems",
        "- Unproven: settings page loads was not driven.",
        "- Flaky: import reads the csv back passed on retry.",
        "",
        "## Testing",
        "| Check | Result |",
        "|---|---|",
        "| Lighthouse verdict | green |",
        "| Project suite | passed |",
        "| Failures | 0 |",
        "| Unproven | 1 |",
        "| Flaky | 1 |",
    ]
)
PLAIN_DRAFT = {
    "problem": ["Exports need a round trip."],
    "change": ["Write a csv on export."],
    "impact": ["No user-visible change."],
}
PLAIN_BODY = "\n".join(
    [
        "## Problem",
        "Exports need a round trip.",
        "",
        "## Change",
        "- Write a csv on export.",
        "",
        "## Impact",
        "No user-visible change.",
        "",
        "## Testing",
        "| Check | Result |",
        "|---|---|",
        "| Lighthouse verdict | green |",
        "| Project suite | passed |",
        "| Failures | 0 |",
        "| Unproven | 0 |",
        "| Flaky | 0 |",
    ]
)


def suite(failures=()):
    return {
        "result": "failures" if failures else "passed",
        "reason": None,
        "failures": list(failures),
        "pre_existing": ["tests.test_legacy.test_old"],
        "flaky": [],
        "core": None,
        "feature": None,
    }


def findings(failures=()):
    return {
        "version": 1,
        "suite": suite(failures),
        "build": {"result": "ok", "reason": None},
        "paths": [],
        "spend": dict(SPEND),
    }


def verdict_line(verdict, failures=(), unproven=(), flaky=()):
    return {
        "verdict": verdict,
        "failures": list(failures),
        "unproven": list(unproven),
        "flaky": list(flaky),
        "tokens": 5000,
        "minutes": 2,
        "dollars": None,
        "pr": None,
    }


def write_json(path, value):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(value, indent=2) + "\n")
    return path


def read_json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def results_folder(test, line, found):
    results = scratch.temporary_folder(test, "lh-results-")
    write_json(os.path.join(results, "findings.json"), found)
    write_json(os.path.join(results, "verdict.json"), line)
    return results


def draft_file(test, draft):
    return write_json(os.path.join(scratch.temporary_folder(test, "lh-inputs-"), "fields.draft.json"), draft)


def feature_branch(test, folder_name=None):
    work, _ = scratch.make_repo(test)
    scratch.run_git(work, "checkout", "-q", "-b", "feat/x")
    scratch.commit_files(work, {"export.py": "EXPORT = 1\n"}, "add export")
    scratch.run_git(work, "push", "-q", "origin", "feat/x")
    scratch.run_git(work, "checkout", "-q", "main")
    if folder_name is None:
        return work
    renamed = os.path.join(os.path.dirname(work), folder_name)
    os.rename(work, renamed)
    return renamed


def path_without(program, path):
    return os.pathsep.join(
        entry for entry in path.split(os.pathsep) if entry and not os.access(os.path.join(entry, program), os.X_OK)
    )


def stub_render(folder, output, code=0, error=""):
    calls = os.path.join(folder, "render-calls.jsonl")
    program = os.path.join(folder, "pull-request")
    with open(program, "w", encoding="utf-8") as handle:
        handle.write(RENDER_STUB.format(python=sys.executable, calls=calls, output=output, error=error, code=code))
    os.chmod(program, 0o755)
    return calls


def render_calls(calls):
    if not os.path.exists(calls):
        return []
    with open(calls, encoding="utf-8") as handle:
        return [json.loads(text) for text in handle if text.strip()]


class Run:
    def __init__(self, test, line, found=None, draft=GREEN_DRAFT, folder_name=None):
        self.work = feature_branch(test, folder_name)
        self.results = results_folder(test, line, found if found is not None else findings())
        self.draft = draft_file(test, draft)
        self.stubs = scratch.temporary_folder(test, "lh-stubs-")
        scratch.stub_gh(self.stubs, {})
        self.home = scratch.make_home(test)

    def environment(self):
        env = scratch.environment(self.home)
        return {**env, "PATH": os.pathsep.join([self.stubs, path_without("pull-request", env["PATH"])])}

    def flags(self, scope="work"):
        return [
            "pr",
            "--repo", self.work,
            "--core", "main",
            "--feature", "feat/x",
            "--results", self.results,
            "--summary", SUMMARY,
            "--draft-fields", self.draft,
            *(["--scope", scope] if scope is not None else []),
        ]

    def pr(self, extra=(), scope="work", flags=None):
        return scratch.run_lighthouse([*(flags if flags is not None else self.flags(scope)), *extra], self.environment())

    def fields_path(self):
        return os.path.join(self.results, "pr-fields.json")


def green_line():
    return verdict_line("green", unproven=["settings page loads"], flaky=["import reads the csv back"])


class PullRequestTest(unittest.TestCase):
    def test_green_composes_a_ready_pull_request_in_the_built_in_layout(self):
        run = Run(self, green_line())

        code, stdout, stderr = run.pr()

        self.assertEqual(code, 0, stdout + stderr)
        composed = json.loads(stdout)
        self.assertEqual(sorted(composed), ["base", "body", "draft", "head", "title"])
        self.assertEqual(composed["title"], "feat(work): add csv export and import")
        self.assertEqual(composed["body"], GREEN_BODY)
        self.assertEqual((composed["base"], composed["head"]), ("main", "feat/x"))
        self.assertIs(composed["draft"], False)
        self.assertEqual(read_json(run.fields_path()), GREEN_FIELDS)

    def test_empty_approach_and_tradeoffs_are_left_out_of_the_body(self):
        run = Run(self, verdict_line("green"), draft={**PLAIN_DRAFT, "approach": [], "tradeoffs": []})

        code, stdout, stderr = run.pr()

        self.assertEqual(code, 0, stdout + stderr)
        self.assertEqual(json.loads(stdout)["body"], PLAIN_BODY)

    def test_type_sets_the_title(self):
        run = Run(self, verdict_line("green"), draft=PLAIN_DRAFT)

        code, stdout, stderr = run.pr(extra=["--type", "fix"])

        self.assertEqual(code, 0, stdout + stderr)
        self.assertEqual(json.loads(stdout)["title"], "fix(work): add csv export and import")

    def test_scope_comes_from_the_repository_folder(self):
        run = Run(self, verdict_line("green"), draft=PLAIN_DRAFT, folder_name="--Voice_Combobulator.Plugin")

        code, stdout, stderr = run.pr(scope=None)

        self.assertEqual(code, 0, stdout + stderr)
        self.assertEqual(json.loads(stdout)["title"], "feat(voicecombobulato): add csv export and import")

    def test_a_folder_leaving_no_scope_gives_a_title_without_one(self):
        run = Run(self, verdict_line("green"), draft=PLAIN_DRAFT, folder_name="___")

        code, stdout, stderr = run.pr(scope=None)

        self.assertEqual(code, 0, stdout + stderr)
        self.assertEqual(json.loads(stdout)["title"], "feat: add csv export and import")

    def test_failures_wait(self):
        run = Run(self, verdict_line("failures", failures=["report totals match"]))

        code, stdout, stderr = run.pr()

        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        self.assertIn("failures", stderr)
        self.assertIn("--final", stderr)
        self.assertFalse(os.path.exists(run.fields_path()))

    def test_blocked_waits(self):
        run = Run(self, verdict_line("blocked"))

        code, stdout, stderr = run.pr()

        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        self.assertIn("blocked", stderr)
        self.assertIn("--final", stderr)

    def test_final_opens_failures_as_a_draft(self):
        line = verdict_line("failures", failures=["suite: tests.test_export.test_header", "report totals match"])
        draft = {
            **PLAIN_DRAFT,
            "tradeoffs": [
                "Unresolved: suite: tests.test_export.test_header still fails.",
                "Unresolved: report totals match differs from core.",
            ],
        }
        run = Run(self, line, found=findings(failures=["tests.test_export.test_header"]), draft=draft)

        code, stdout, stderr = run.pr(extra=["--final"])

        self.assertEqual(code, 0, stdout + stderr)
        composed = json.loads(stdout)
        self.assertIs(composed["draft"], True)
        self.assertIn("| Lighthouse verdict | failures |\n| Project suite | failures |\n| Failures | 2 |", composed["body"])

    def test_why_is_refused_as_an_unknown_flag(self):
        run = Run(self, green_line())

        code, stdout, stderr = run.pr(extra=["--why", "the intent"])

        self.assertEqual(code, 2, stdout + stderr)
        self.assertIn("--why", json.loads(stdout)["error"])
        self.assertFalse(os.path.exists(run.fields_path()))

    def test_draft_fields_is_required(self):
        run = Run(self, green_line())
        flags = [flag for flag in run.flags() if flag not in ("--draft-fields", run.draft)]

        code, stdout, stderr = run.pr(flags=flags)

        self.assertEqual(code, 2, stdout + stderr)
        self.assertIn("--draft-fields", json.loads(stdout)["error"])

    def test_a_draft_key_outside_the_draft_is_refused(self):
        run = Run(self, green_line(), draft={**GREEN_DRAFT, "testing": [{"check": "Mine", "result": "ok"}]})

        code, stdout, stderr = run.pr()

        self.assertEqual(code, 2, stdout + stderr)
        error = json.loads(stdout)["error"]
        self.assertIn("testing", error)
        self.assertIn("problem, change, impact, approach, tradeoffs", error)
        self.assertFalse(os.path.exists(run.fields_path()))

    def test_every_h15_error_is_named(self):
        run = Run(self, green_line(), draft={**GREEN_DRAFT, "problem": ["lowercase."], "impact": []})

        code, stdout, stderr = run.pr()

        self.assertEqual(code, 2, stdout + stderr)
        printed = json.loads(stdout)
        self.assertEqual(printed["schema"], "h15-pr-fields.schema.json")
        self.assertTrue(any(error.startswith("#/problem/0") for error in printed["errors"]), printed["errors"])
        self.assertTrue(any(error.startswith("#/impact") for error in printed["errors"]), printed["errors"])
        self.assertFalse(os.path.exists(run.fields_path()))

    def test_a_flaky_name_missing_from_the_tradeoffs_is_refused(self):
        draft = {**GREEN_DRAFT, "tradeoffs": ["Unproven: settings page loads was not driven."]}
        run = Run(self, green_line(), draft=draft)

        code, stdout, stderr = run.pr()

        self.assertEqual(code, 2, stdout + stderr)
        error = json.loads(stdout)["error"]
        self.assertIn("missing: import reads the csv back", error)
        self.assertNotIn("missing: settings page loads", error)
        self.assertFalse(os.path.exists(run.fields_path()))

    def test_a_verdict_breaking_h13_is_refused(self):
        line = {key: value for key, value in green_line().items() if key != "dollars"}
        run = Run(self, line)

        code, stdout, stderr = run.pr()

        self.assertEqual(code, 2, stdout + stderr)
        self.assertIn("h13-lighthouse-verdict-line", json.loads(stdout)["error"])

    def test_a_refusal_in_verdict_json_is_refused(self):
        run = Run(self, {"error": "the run stopped"})

        code, stdout, stderr = run.pr()

        self.assertEqual(code, 2, stdout + stderr)
        self.assertIn("holds a refusal, not a verdict line", json.loads(stdout)["error"])

    def test_render_on_path_composes_the_pull_request(self):
        run = Run(self, green_line())
        calls = stub_render(run.stubs, json.dumps({"title": GREEN_FIELDS["title"], "body": GREEN_BODY}) + "\n")

        code, stdout, stderr = run.pr()

        self.assertEqual(code, 0, stdout + stderr)
        self.assertEqual(render_calls(calls), [{"argv": ["render", "--fields", run.fields_path()], "stdin": ""}])
        composed = json.loads(stdout)
        self.assertEqual((composed["title"], composed["body"]), (GREEN_FIELDS["title"], GREEN_BODY))

    def test_render_exiting_non_zero_is_refused(self):
        run = Run(self, green_line())
        stub_render(run.stubs, "", code=3, error="render: the fields are stale\n")

        code, stdout, stderr = run.pr()

        self.assertEqual(code, 2, stdout + stderr)
        printed = json.loads(stdout)
        self.assertEqual(printed, {"error": "pull-request render exited 3: render: the fields are stale"})

    def test_render_printing_two_lines_is_refused(self):
        run = Run(self, green_line())
        line = json.dumps({"title": GREEN_FIELDS["title"], "body": GREEN_BODY})
        stub_render(run.stubs, line + "\n" + line + "\n")

        code, stdout, stderr = run.pr()

        self.assertEqual(code, 2, stdout + stderr)
        self.assertIn("pull-request render printed 2 lines", json.loads(stdout)["error"])


class ScopeFromFolderTest(unittest.TestCase):
    def test_scope_rows(self):
        rows = [
            ("lighthouse", "lighthouse"),
            ("Lighthouse", "lighthouse"),
            ("voice-combobulator", "voice-combobulat"),
            (".windful-ocean", "windful-ocean"),
            ("--a-b-c-d-e-f-g-h-i", "a-b-c-d-e-f-g-h"),
            ("My_Repo 2", "myrepo2"),
            ("___", ""),
            ("---", ""),
        ]
        for folder, scope in rows:
            with self.subTest(folder=folder):
                self.assertEqual(pr_fields.scope_from_folder(folder), scope)


if __name__ == "__main__":
    unittest.main()
