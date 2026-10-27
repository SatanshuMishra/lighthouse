import datetime
import json
import os
import re
import unittest
from unittest import mock

from lighthouse_tool import run_record
from tests import scratch
from tests.test_launch import CAFFEINATE_STUB, GREEN_LINE, SYSTEMD_INHIBIT_STUB, claude_output, write_stub
from tests.test_spend import assistant, bash, tool_result

RECORDING_CLAUDE_STUB = """#!{python}
import datetime
import json
import os
import re
import shlex
import sys
import time

folder = os.path.dirname(os.path.realpath(__file__))
with open(os.path.join(folder, "plan.json"), encoding="utf-8") as handle:
    plan = json.load(handle)
words = shlex.split(sys.argv[2])
results = words[words.index("--results") + 1]
work = os.path.realpath(os.getcwd())
began = datetime.datetime.now(datetime.timezone.utc)
with open(os.path.join(folder, "claude-calls.jsonl"), "a", encoding="utf-8") as calls:
    calls.write(json.dumps({{"argv": sys.argv[1:], "env": dict(os.environ)}}) + "\\n")


def timed(text, cwd):
    entry = json.loads(text)
    for key in ("timestamp", "time"):
        if isinstance(entry.get(key), str) and entry[key].startswith("@"):
            moment = began + datetime.timedelta(seconds=float(entry[key][1:]))
            entry[key] = moment.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    if cwd is not None:
        entry["cwd"] = cwd
    return json.dumps(entry)


def append(path, lines, cwd):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write("".join(timed(line, cwd) + "\\n" for line in lines))


for name, text in plan.get("files", {{}}).items():
    with open(os.path.join(results, name), "w", encoding="utf-8") as handle:
        handle.write(text)
if plan.get("marks"):
    append(os.path.join(results, "marks.jsonl"), plan["marks"], None)
if plan.get("child"):
    project = re.sub(r"[^A-Za-z0-9]", "-", work)
    append(os.path.join(os.environ["HOME"], ".claude", "projects", project, "child.jsonl"), plan["child"], work)
if plan.get("caller"):
    append(plan["caller"]["path"], plan["caller"]["lines"], None)
time.sleep(1.0)
sys.stdout.write(plan["output"])
sys.exit(plan.get("exit", 0))
"""

ENVELOPE = ["v", "ts", "plugin", "plugin_version", "kind", "event", "run", "parent", "session", "repo"]
REPO_FOLDER = "work"
STAMPED = r"\.\d{8}T\d{6}Z"
NEW_PATH = {
    "name": "opens the report",
    "surface": "web",
    "kind": "new",
    "expected": "the report opens",
    "status": "passed",
    "retry": None,
    "core": None,
    "evidence": [],
    "trials": None,
    "check": {"kind": "drive", "why": "the change adds it"},
}
NEIGHBOUR_PATH = {
    "name": "exports a csv",
    "surface": "web",
    "kind": "neighbour",
    "expected": "the csv downloads",
    "status": "failed",
    "retry": "failed",
    "core": "passed",
    "evidence": [],
    "trials": None,
    "check": {"kind": "direct", "why": "it shares the export code"},
}
FAILURES_LINE = json.dumps(
    {"verdict": "failures", "failures": ["exports a csv"], "unproven": [], "flaky": [], "tokens": 900, "minutes": 4, "pr": None}
)
BLOCKED_LINE = json.dumps(
    {
        "verdict": "blocked",
        "failures": [],
        "unproven": [],
        "flaky": [],
        "tokens": 0,
        "minutes": 0,
        "pr": None,
        "reason": "worktrees: the core branch does not exist",
    }
)
CORE_COMMIT = "a" * 40
FEATURE_COMMIT = "b" * 40
SUITE = {
    "result": "passed",
    "reason": None,
    "failures": [],
    "pre_existing": [],
    "flaky": [],
    "core": {"exit": 0, "log": "suite-core.log", "prepare_minutes": 0.0, "suite_minutes": 0.0, "rerun_minutes": None, "reused": True},
    "feature": {"exit": 0, "log": "suite-feature.log", "prepare_minutes": 0.5, "suite_minutes": 2.5, "rerun_minutes": None},
}
FINDINGS = {
    "version": 1,
    "suite": {"result": "passed", "reason": None, "failures": [], "pre_existing": [], "flaky": []},
    "build": {"result": "ok", "reason": None},
    "paths": [NEW_PATH, NEIGHBOUR_PATH],
    "spend": {"tokens": 900, "minutes": 4, "dollars": None},
}
NO_USAGE = {}


def mark_command(results, step, edge, build=None, path=None):
    words = ["lighthouse", "mark", "--results", results, "--step", step]
    built = words + (["--build", build] if build else []) + (["--path", "'{}'".format(path)] if path else [])
    return " ".join(built + [edge])


def mark_entry(step, edge, time, build=None, path=None):
    return json.dumps({"step": step, "build": build, "path": path, "folder": None, "edge": edge, "time": time})


def marked_child(results):
    suite_start = mark_command(results, "suite", "start")
    suite_end = mark_command(results, "suite", "end")
    drive_start = mark_command(results, "drive", "start", build="feature", path="opens the report")
    drive_end = mark_command(results, "drive", "end", build="feature", path="opens the report")
    return [
        assistant("msg_suite_start", "@0.1", NO_USAGE, content=bash("toolu_suite_start", suite_start)),
        tool_result("toolu_suite_start", "@0.15"),
        assistant("msg_suite_work", "@0.2", {"output_tokens": 1000}),
        assistant("msg_suite_end", "@0.3", NO_USAGE, content=bash("toolu_suite_end", suite_end)),
        tool_result("toolu_suite_end", "@0.35"),
        assistant("msg_drive_start", "@0.4", NO_USAGE, content=bash("toolu_drive_start", drive_start)),
        tool_result("toolu_drive_start", "@0.45"),
        assistant("msg_drive_work", "@0.5", {"output_tokens": 500}, model="claude-sonnet-5-5"),
        assistant("msg_drive_end", "@0.6", NO_USAGE, content=bash("toolu_drive_end", drive_end)),
        tool_result("toolu_drive_end", "@0.65"),
    ]


def matching_marks():
    return [
        mark_entry("suite", "start", "@0.11"),
        mark_entry("suite", "end", "@0.31"),
        mark_entry("drive", "start", "@0.41", build="feature", path="opens the report"),
        mark_entry("drive", "end", "@0.61", build="feature", path="opens the report"),
    ]


def caller_path(home, session):
    return os.path.join(home, ".claude", "projects", "-caller-project", session + ".jsonl")


def write_caller_before(home, session, lines):
    path = caller_path(home, session)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("".join(line + "\n" for line in lines))


def an_hour_ago():
    moment = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)
    return moment.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def launch_flags(repo, results, feature="feat/x", extra=()):
    return ["--repo", repo, "--core", "main", "--feature", feature, "--results", results, *extra]


def store_folder(store, kind, repo=REPO_FOLDER):
    return os.path.join(store, "plugin=lighthouse", "kind=" + kind, "repo=" + repo)


def read_lines(path):
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle.read().splitlines()]


def files_in(folder):
    return sorted(os.listdir(folder)) if os.path.isdir(folder) else []


def read_bytes(path):
    with open(path, "rb") as handle:
        return handle.read()


def read_json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


class Launched:
    def __init__(self, test, plan, home=None, feature="feat/x", env=None, extra=(), results=None, repo=None, store=None):
        self.repo = repo or scratch.make_repo(test)[0]
        self.home = home or scratch.make_home(test)
        self.store = store or scratch.temporary_folder(test, "lh-store-")
        self.results = results or os.path.join(scratch.temporary_folder(test, "lh-results-"), "results")
        self.stubs = scratch.temporary_folder(test, "lh-stubs-")
        write_stub(self.stubs, "claude", RECORDING_CLAUDE_STUB)
        write_stub(self.stubs, "caffeinate", CAFFEINATE_STUB)
        write_stub(self.stubs, "systemd-inhibit", SYSTEMD_INHIBIT_STUB)
        with open(os.path.join(self.stubs, "plan.json"), "w", encoding="utf-8") as handle:
            handle.write(json.dumps(plan))
        environment = {**scratch.environment(self.home, self.stubs), "PLUGIN_METRICS_DIR": self.store, **(env or {})}
        flags = launch_flags(self.repo, self.results, feature, extra)
        self.code, self.stdout, self.stderr = scratch.run_lighthouse(["launch", *flags], environment)

    def event_files(self):
        return files_in(store_folder(self.store, "event"))

    def summary_files(self):
        return files_in(store_folder(self.store, "summary"))

    def events(self):
        names = self.event_files()
        return read_lines(os.path.join(store_folder(self.store, "event"), names[0])) if names else []

    def summary(self):
        names = self.summary_files()
        return read_lines(os.path.join(store_folder(self.store, "summary"), names[0]))[0]

    def lines(self):
        event = [os.path.join(store_folder(self.store, "event"), name) for name in self.event_files()]
        summary = [os.path.join(store_folder(self.store, "summary"), name) for name in self.summary_files()]
        return [line for path in event + summary for line in read_lines(path)]

    def child_calls(self):
        with open(os.path.join(self.stubs, "claude-calls.jsonl"), encoding="utf-8") as handle:
            return [json.loads(line) for line in handle.read().splitlines()]


def green_plan(home, session):
    write_caller_before(home, session, [assistant("msg_caller_before", an_hour_ago(), {"cache_read_input_tokens": 2000})])
    return {
        "files": {
            "commits.json": json.dumps({"core": CORE_COMMIT, "feature": FEATURE_COMMIT}),
            "suite.json": json.dumps(SUITE),
            "findings.json": json.dumps(FINDINGS),
            "retest.json": json.dumps({"retest": [], "carried_paths": [NEW_PATH]}),
        },
        "caller": {
            "path": caller_path(home, session),
            "lines": [assistant("msg_caller_during", "@0.2", {"output_tokens": 1000})],
        },
        "marks": matching_marks(),
        "output": claude_output("Done.\n" + FAILURES_LINE),
    }


def green_run(test):
    home = scratch.make_home(test)
    results = os.path.join(scratch.temporary_folder(test, "lh-results-"), "results")
    plan = {**green_plan(home, "s-green"), "child": marked_child(results)}
    return Launched(test, plan, home=home, results=results, env={"CLAUDE_CODE_SESSION_ID": "s-green"})


TYPE_CHECKS = {
    "integer": lambda value: isinstance(value, int) and not isinstance(value, bool),
    "number": lambda value: isinstance(value, (int, float)) and not isinstance(value, bool),
    "string": lambda value: isinstance(value, str),
    "boolean": lambda value: isinstance(value, bool),
    "object": lambda value: isinstance(value, dict),
    "array": lambda value: isinstance(value, list),
    "null": lambda value: value is None,
}


def undescribed(label, value, entry):
    if value is None:
        return []
    kind = entry["type"]
    if kind == "enum":
        return [] if value in entry["values"] else ["{} is {!r}, not one of {}".format(label, value, entry["values"])]
    if not TYPE_CHECKS[kind](value):
        return ["{} is {!r}, not {}".format(label, value, kind)]
    if kind == "object" and "fields" in entry:
        return [
            problem
            for key, item in value.items()
            for problem in (
                undescribed("{}.{}".format(label, key), item, entry["fields"][key])
                if key in entry["fields"]
                else ["{}.{} is not described".format(label, key)]
            )
        ]
    if kind == "array" and "items" in entry:
        return [problem for index, item in enumerate(value) for problem in undescribed("{}[{}]".format(label, index), item, entry["items"])]
    return []


class RunRecordTest(unittest.TestCase):
    def test_launch_writes_start_and_end(self):
        ran = Launched(self, {"output": claude_output(GREEN_LINE)}, feature="feat/Unified Metrics")
        self.assertEqual(ran.code, 0, ran.stderr)
        names = ran.event_files()
        self.assertEqual(len(names), 1)
        self.assertRegex(names[0], "^feat-unified-metrics" + STAMPED + r"\.jsonl$")
        events = ran.events()
        self.assertEqual([event["event"] for event in events], ["run.start", "run.end"])
        version = read_json(os.path.join(scratch.ROOT, ".claude-plugin", "plugin.json"))["version"]
        for event in events:
            self.assertEqual(event["plugin"], "lighthouse")
            self.assertEqual(event["plugin_version"], version)
            self.assertIsNone(event["parent"])
            self.assertIsNone(event["session"])
        self.assertEqual(events[1]["verdict"], "green")
        self.assertEqual(events[1]["child_exit"], 0)

    def test_parent_flag_wins(self):
        ran = Launched(
            self,
            {"output": claude_output(GREEN_LINE)},
            env={"PLUGIN_METRICS_PARENT": "pipeline/other.20261001T100000Z"},
            extra=["--parent", "pipeline/feat-a.20261001T100000Z"],
        )
        self.assertEqual(ran.code, 0, ran.stderr)
        lines = ran.lines()
        self.assertEqual([line["event"] for line in lines], ["run.start", "run.end", "run.summary"])
        for line in lines:
            self.assertEqual(line["parent"], "pipeline/feat-a.20261001T100000Z")

    def test_parent_and_session_from_environment(self):
        ran = Launched(
            self,
            {"output": claude_output(GREEN_LINE)},
            env={"PLUGIN_METRICS_PARENT": "pipeline/other.20261001T100000Z", "CLAUDE_CODE_SESSION_ID": "s-1"},
        )
        self.assertEqual(ran.code, 0, ran.stderr)
        lines = ran.lines()
        self.assertEqual(len(lines), 3)
        for line in lines:
            self.assertEqual(line["parent"], "pipeline/other.20261001T100000Z")
            self.assertEqual(line["session"], "s-1")

    def test_long_feature_cut_to_120(self):
        ran = Launched(self, {"output": claude_output(GREEN_LINE)}, feature="a" * 200)
        self.assertEqual(ran.code, 0, ran.stderr)
        run = ran.events()[0]["run"]
        self.assertEqual(len(run), 120)
        self.assertRegex(run, "^a{103}" + STAMPED + "$")

    def test_catalogue_copied(self):
        ran = Launched(self, {"output": claude_output(GREEN_LINE)})
        self.assertEqual(ran.code, 0, ran.stderr)
        copied = read_json(os.path.join(ran.store, "plugin=lighthouse", "catalogue.json"))
        self.assertEqual(copied, read_json(os.path.join(scratch.ROOT, "lighthouse_tool", "catalogue.json")))

    def test_green_run_summary(self):
        ran = green_run(self)
        self.assertEqual(ran.code, 0, ran.stderr)
        summary = ran.summary()
        self.assertEqual(summary["verdict"], "failures")
        self.assertIsNone(summary["reason"])
        self.assertEqual(summary["failures"], 1)
        self.assertEqual((summary["core_commit"], summary["feature_commit"]), (CORE_COMMIT, FEATURE_COMMIT))
        self.assertEqual(summary["suite"]["feature"]["suite_seconds"], 150)
        self.assertIs(summary["suite"]["core"]["reused"], True)
        self.assertEqual(
            summary["paths"],
            [
                {"name": "opens the report", "kind": "new", "status": "passed", "check": "drive", "retry": None, "carried": True},
                {"name": "exports a csv", "kind": "neighbour", "status": "failed", "check": "direct", "retry": "failed", "carried": False},
            ],
        )
        self.assertEqual(summary["child_exit"], 0)
        self.assertEqual(summary["spend_scope"], "own")
        self.assertIs(summary["imported"], False)

    def test_missing_sources_are_null(self):
        ran = Launched(self, {"output": claude_output(GREEN_LINE)})
        self.assertEqual(ran.code, 0, ran.stderr)
        summary = ran.summary()
        for key in ("core_commit", "feature_commit", "build", "suite", "paths"):
            self.assertIsNone(summary[key], key)
        self.assertEqual(summary["verdict"], "green")

    def test_blocked_child_records_reason(self):
        ran = Launched(self, {"output": claude_output(BLOCKED_LINE)})
        self.assertEqual(ran.code, 0, ran.stderr)
        summary = ran.summary()
        self.assertEqual(summary["verdict"], "blocked")
        self.assertEqual(summary["reason"], "worktrees: the core branch does not exist")

    def test_child_without_verdict_records_launch_reason(self):
        ran = Launched(self, {"output": claude_output("I could not finish."), "exit": 1})
        self.assertEqual(ran.code, 0, ran.stderr)
        summary = ran.summary()
        self.assertEqual(summary["verdict"], "blocked")
        self.assertEqual(summary["reason"], "the child session exited 1 without a verdict line")

    def test_records_written_before_launch_json(self):
        ran = Launched(self, {"output": claude_output(GREEN_LINE)})
        self.assertEqual(ran.code, 0, ran.stderr)
        launched = os.stat(os.path.join(ran.results, "launch.json")).st_mtime_ns
        summary = os.path.join(store_folder(ran.store, "summary"), ran.summary_files()[0])
        event = os.path.join(store_folder(ran.store, "event"), ran.event_files()[0])
        self.assertLessEqual(os.stat(summary).st_mtime_ns, launched)
        self.assertLessEqual(os.stat(event).st_mtime_ns, launched)

    def test_truncated_marks_keep_the_run(self):
        cut = mark_entry("suite", "start", "2026-10-16T10:00:00Z") + "\n" + '{"step": "suite", "edge": "en'
        ran = Launched(self, {"files": {"marks.jsonl": cut}, "output": claude_output(GREEN_LINE)})
        self.assertEqual(ran.code, 0, ran.stderr)
        self.assertEqual(ran.stdout, GREEN_LINE + "\n")
        with open(os.path.join(ran.results, "launch.json"), encoding="utf-8") as handle:
            self.assertEqual(handle.read(), GREEN_LINE + "\n")
        summary = ran.summary()
        for key in ("steps", "drives", "shared"):
            self.assertIsNone(summary[key], key)

    def test_summary_counts_child_and_caller(self):
        home = scratch.make_home(self)
        write_caller_before(home, "s-caller", [assistant("msg_caller_before", an_hour_ago(), {"cache_read_input_tokens": 2000})])
        plan = {
            "child": [
                assistant("msg_child_opus", "@0.1", {"input_tokens": 1000}),
                assistant("msg_child_sonnet", "@0.2", {"output_tokens": 500}, model="claude-sonnet-5-5"),
            ],
            "caller": {
                "path": caller_path(home, "s-caller"),
                "lines": [
                    assistant("msg_caller_during", "@0.3", {"output_tokens": 1000}),
                    assistant("msg_caller_after", "@3600", {"output_tokens": 7000}),
                ],
            },
            "output": claude_output(GREEN_LINE),
        }
        ran = Launched(self, plan, home=home, env={"CLAUDE_CODE_SESSION_ID": "s-caller"})
        self.assertEqual(ran.code, 0, ran.stderr)
        summary = ran.summary()
        self.assertEqual(summary["usd"], 0.029)
        self.assertEqual(
            summary["tokens"], {"input": 1000, "cache_write_5m": 0, "cache_write_1h": 0, "cache_read": 0, "output": 1500}
        )
        self.assertEqual(summary["messages"], 3)
        self.assertEqual(
            summary["caller"],
            {
                "usd": 0.02,
                "tokens": {"input": 0, "cache_write_5m": 0, "cache_write_1h": 0, "cache_read": 0, "output": 1000},
                "messages": 1,
            },
        )
        self.assertEqual(
            [(model["model"], model["usd"]) for model in summary["models"]],
            [("claude-opus-5-5", 0.024), ("claude-sonnet-5-5", 0.005)],
        )

    def test_caller_transcript_missing_gives_null(self):
        plan = {"child": [assistant("msg_child", "@0.1", {"output_tokens": 100})], "output": claude_output(GREEN_LINE)}
        ran = Launched(self, plan, env={"CLAUDE_CODE_SESSION_ID": "s-missing"})
        self.assertEqual(ran.code, 0, ran.stderr)
        summary = ran.summary()
        self.assertIsNone(summary["caller"])
        self.assertIsNone(summary["usd"])
        self.assertEqual(summary["tokens"]["output"], 100)
        self.assertEqual(summary["messages"], 1)

    def test_unpriced_model_gives_null_usd(self):
        plan = {
            "child": [assistant("msg_unknown", "@0.1", {"output_tokens": 50}, model="claude-unknown-9")],
            "output": claude_output(GREEN_LINE),
        }
        ran = Launched(self, plan)
        self.assertEqual(ran.code, 0, ran.stderr)
        summary = ran.summary()
        self.assertIsNone(summary["usd"])
        self.assertEqual(summary["unpriced"], ["claude-unknown-9"])
        self.assertEqual(summary["tokens"]["output"], 50)

    def test_message_counted_once(self):
        home = scratch.make_home(self)
        write_caller_before(home, "s-once", [])
        same = assistant("msg_same", "@0.2", {"output_tokens": 1000})
        plan = {
            "child": [same],
            "caller": {"path": caller_path(home, "s-once"), "lines": [same]},
            "output": claude_output(GREEN_LINE),
        }
        ran = Launched(self, plan, home=home, env={"CLAUDE_CODE_SESSION_ID": "s-once"})
        self.assertEqual(ran.code, 0, ran.stderr)
        summary = ran.summary()
        self.assertEqual(summary["messages"], 1)
        self.assertEqual(summary["usd"], 0.02)

    def test_steps_and_drives_from_marks(self):
        results = os.path.join(scratch.temporary_folder(self, "lh-results-"), "results")
        plan = {"child": marked_child(results), "marks": matching_marks(), "output": claude_output(GREEN_LINE)}
        ran = Launched(self, plan, results=results)
        self.assertEqual(ran.code, 0, ran.stderr)
        summary = ran.summary()
        suite = next(step for step in summary["steps"] if step["step"] == "suite")
        self.assertIsNone(suite["build"])
        self.assertEqual(suite["usd"], 0.02)
        self.assertEqual(suite["tokens"], {"input": 0, "cache_write_5m": 0, "cache_write_1h": 0, "cache_read": 0, "output": 1000})
        self.assertEqual([drive["path"] for drive in summary["drives"]], ["opens the report"])
        drive = summary["drives"][0]
        self.assertEqual(drive["build"], "feature")
        self.assertEqual(drive["usd"], 0.005)
        self.assertEqual(drive["tokens"], {"input": 0, "cache_write_5m": 0, "cache_write_1h": 0, "cache_read": 0, "output": 500})

    def test_price_date_recorded(self):
        ran = Launched(self, {"output": claude_output(GREEN_LINE)})
        self.assertEqual(ran.code, 0, ran.stderr)
        shipped = read_json(os.path.join(scratch.ROOT, "lighthouse_tool", "prices.json"))
        self.assertEqual(ran.summary()["price_date"], shipped["date"])

    def test_child_gets_its_own_store(self):
        ran = Launched(
            self,
            {"output": claude_output(GREEN_LINE)},
            env={"PLUGIN_METRICS_PARENT": "pipeline/x.20261001T100000Z"},
            extra=["--parent", "pipeline/y.20261001T100000Z"],
        )
        self.assertEqual(ran.code, 0, ran.stderr)
        call = ran.child_calls()[0]
        self.assertEqual(
            os.path.realpath(call["env"]["PLUGIN_METRICS_DIR"]), os.path.join(os.path.realpath(ran.results), "plugin-metrics")
        )
        self.assertNotIn("PLUGIN_METRICS_PARENT", call["env"])
        self.assertNotIn("--parent", call["argv"][1])
        written = sorted(
            os.path.relpath(os.path.join(directory, name), ran.store)
            for directory, _, names in os.walk(ran.store)
            for name in names
        )
        event, summary = ran.event_files()[0], ran.summary_files()[0]
        self.assertEqual(
            written,
            sorted(
                [
                    os.path.join("plugin=lighthouse", "catalogue.json"),
                    os.path.join("plugin=lighthouse", "kind=event", "repo=" + REPO_FOLDER, event),
                    os.path.join("plugin=lighthouse", "kind=summary", "repo=" + REPO_FOLDER, summary),
                ]
            ),
        )

    def test_refusal_inside_repo_is_recorded(self):
        repo, _ = scratch.make_repo(self)
        ran = Launched(self, {"output": claude_output(GREEN_LINE)}, repo=repo, results=os.path.join(repo, "results"))
        self.assertEqual(ran.code, 2, ran.stderr)
        self.assertIn("error", json.loads(ran.stdout.strip().splitlines()[-1]))
        self.assertEqual([event["event"] for event in ran.events()], ["run.start", "run.end"])
        summary = ran.summary()
        self.assertEqual(summary["verdict"], "blocked")
        self.assertIn("is inside the repository", summary["reason"])
        self.assertIsNone(summary["child_exit"])

    def test_not_a_repository_writes_nothing(self):
        plain = scratch.temporary_folder(self, "lh-plain-")
        ran = Launched(self, {"output": claude_output(GREEN_LINE)}, repo=plain)
        self.assertEqual(ran.code, 2, ran.stderr)
        self.assertEqual(os.listdir(ran.store), [])

    def test_unwritable_store_keeps_the_run(self):
        store = os.path.join(scratch.temporary_folder(self, "lh-store-file-"), "store")
        with open(store, "w", encoding="utf-8") as handle:
            handle.write("not a folder\n")
        ran = Launched(self, {"output": claude_output(GREEN_LINE)}, store=store)
        self.assertEqual(ran.code, 0, ran.stderr)
        self.assertEqual(ran.stdout, GREEN_LINE + "\n")
        self.assertEqual(read_json(os.path.join(ran.results, "launch.json")), json.loads(GREEN_LINE))
        self.assertTrue(os.path.isfile(os.path.join(ran.results, "child.json")))
        self.assertIn("metrics not written: ", ran.stderr)

    def test_written_keys_are_described(self):
        ran = green_run(self)
        self.assertEqual(ran.code, 0, ran.stderr)
        catalogue = read_json(os.path.join(ran.store, "plugin=lighthouse", "catalogue.json"))
        lines = ran.lines()
        self.assertEqual([line["event"] for line in lines], ["run.start", "run.end", "run.summary"])
        for line in lines:
            described = (
                catalogue["summary"]["fields"] if line["kind"] == "summary" else catalogue["events"][line["event"]]["fields"]
            )
            problems = [
                problem
                for key, value in line.items()
                if key not in ENVELOPE
                for problem in (undescribed(key, value, described[key]) if key in described else [key + " is not described"])
            ]
            self.assertEqual(problems, [], line["event"])

    def test_lines_meet_the_line_schema(self):
        ran = green_run(self)
        self.assertEqual(ran.code, 0, ran.stderr)
        schema = read_json(os.path.join(scratch.ROOT, "metrics", "schema", "line.schema.json"))
        required = schema["required"]
        lines = ran.lines()
        self.assertEqual(len(lines), 3)
        for line in lines:
            self.assertEqual(list(line)[: len(required)], required)
            for key in required:
                rule = schema["properties"][key]
                kinds = rule["type"] if isinstance(rule["type"], list) else [rule["type"]]
                value = line[key]
                self.assertTrue(any(TYPE_CHECKS[kind](value) for kind in kinds), "{} is {!r}".format(key, value))
                if isinstance(value, str) and "pattern" in rule:
                    self.assertRegex(value, rule["pattern"])
                if isinstance(value, str) and "enum" in rule:
                    self.assertIn(value, rule["enum"])
                if isinstance(value, str) and "maxLength" in rule:
                    self.assertLessEqual(len(value), rule["maxLength"])

    def test_launch_prunes_old_runs(self):
        from lighthouse_tool import metrics_writer

        home = scratch.make_home(self)
        store = scratch.temporary_folder(self, "lh-store-")
        environ = {"HOME": home, "PLUGIN_METRICS_DIR": store}
        starts = [datetime.datetime(2026, 10, 1, 0, minute // 60, minute % 60, tzinfo=datetime.timezone.utc) for minute in range(100)]
        earlier = [metrics_writer.run_id("feat-x", start) for start in starts]
        for run, start in zip(earlier, starts):
            self.assertIsNone(
                metrics_writer.append_event("lighthouse", "0.3.0", REPO_FOLDER, run, "run.start", {}, environ=environ, now=start)
            )
        other = metrics_writer.run_id("feat-y", starts[0])
        self.assertIsNone(
            metrics_writer.append_event("lighthouse", "0.3.0", "other-repo", other, "run.start", {}, environ=environ, now=starts[0])
        )
        other_path = os.path.join(store_folder(store, "event", "other-repo"), other + ".jsonl")
        with open(other_path, "rb") as handle:
            other_bytes = handle.read()
        ran = Launched(self, {"output": claude_output(GREEN_LINE)}, home=home, store=store)
        self.assertEqual(ran.code, 0, ran.stderr)
        remaining = ran.event_files()
        self.assertNotIn(earlier[0] + ".jsonl", remaining)
        self.assertEqual(len(remaining), 100)
        summaries = ran.summary_files()
        self.assertEqual(len(summaries), 1)
        self.assertIn(summaries[0][: -len(".json")] + ".jsonl", remaining)
        self.assertNotIn(summaries[0][: -len(".json")], earlier)
        with open(other_path, "rb") as handle:
            self.assertEqual(handle.read(), other_bytes)

    def test_rerun_into_same_folder_drops_earlier_sources(self):
        first = green_run(self)
        self.assertEqual(first.code, 0, first.stderr)
        earlier_sources = ("core_commit", "feature_commit", "build", "suite", "paths")

        stopped = Launched(
            self, {"output": claude_output("I could not finish."), "exit": 1}, results=first.results, repo=first.repo, store=first.store
        )
        self.assertEqual(stopped.code, 0, stopped.stderr)
        latest = newest_summary(first.store)
        self.assertEqual(latest["verdict"], "blocked")
        for key in earlier_sources:
            with self.subTest(rerun="child stops early", key=key):
                self.assertIsNone(latest[key])

        second = green_run(self)
        environment = {**scratch.environment(second.home, second.stubs), "PLUGIN_METRICS_DIR": second.store}
        code, _, _ = scratch.run_lighthouse(["launch", "--repo", second.repo, "--feature", "feat/x", "--results", second.results], environment)
        self.assertEqual(code, 2)
        latest = newest_summary(second.store)
        self.assertEqual(latest["verdict"], "blocked")
        self.assertIsNone(latest["child_exit"])
        for key in earlier_sources:
            with self.subTest(rerun="refused", key=key):
                self.assertIsNone(latest[key])

        cut = mark_entry("suite", "start", "2026-10-16T10:00:00Z") + "\n" + '{"step": "suite", "edge": "en'
        marked = Launched(self, {"files": {"marks.jsonl": cut}, "output": claude_output(GREEN_LINE)})
        Launched(self, {"output": claude_output(GREEN_LINE)}, results=marked.results, repo=marked.repo, store=marked.store)
        latest = newest_summary(marked.store)
        for key in ("steps", "drives", "shared"):
            with self.subTest(rerun="earlier cut marks", key=key):
                self.assertIsNotNone(latest[key])

    def test_launch_refuses_previous_naming_the_results_folder(self):
        first = green_run(self)
        self.assertEqual(first.code, 0, first.stderr)
        alias = os.path.join(scratch.temporary_folder(self, "lh-alias-"), "results")
        os.symlink(first.results, alias)
        sources = {name: read_bytes(os.path.join(first.results, name)) for name in run_record.RESULTS_SOURCES}
        calls = read_bytes(os.path.join(first.stubs, "claude-calls.jsonl"))
        environment = {**scratch.environment(first.home, first.stubs), "PLUGIN_METRICS_DIR": first.store}
        spellings = {"same path": first.results, "trailing slash": first.results + os.sep, "symlink": alias}
        shapes = {
            "full flags": lambda previous: launch_flags(first.repo, first.results, extra=["--previous", previous]),
            "missing core": lambda previous: ["--repo", first.repo, "--feature", "feat/x", "--results", first.results, "--previous", previous],
        }
        for spelling, previous in spellings.items():
            for shape, flags in shapes.items():
                with self.subTest(spelling=spelling, shape=shape):
                    code, _, stderr = scratch.run_lighthouse(["launch", *flags(previous)], environment)
                    self.assertEqual(code, 2)
                    self.assertIn("--previous", stderr)
                    self.assertEqual({name: read_bytes(os.path.join(first.results, name)) for name in sources}, sources)
                    self.assertEqual(read_bytes(os.path.join(first.stubs, "claude-calls.jsonl")), calls)
                    latest = newest_summary(first.store)
                    self.assertEqual(latest["verdict"], "blocked")
                    self.assertIn("--previous", latest["reason"])
                    self.assertIsNone(latest["child_exit"])

    def test_malformed_parent_is_left_out(self):
        for parent in ("<plugin>/<run>", "../../x' OR 1=1 --", "pipeline/" + "a" * 5000):
            with self.subTest(parent=parent[:40]):
                ran = Launched(self, {"output": claude_output(GREEN_LINE)}, extra=["--parent", parent])
                self.assertEqual(ran.code, 0, ran.stderr)
                self.assertEqual([line["parent"] for line in ran.lines()], [None, None, None])
                self.assertIn("--parent", ran.stderr)

    def test_session_id_outside_the_projects_folder_is_not_read(self):
        home = scratch.make_home(self)
        projects = os.path.join(home, ".claude", "projects", "-caller-project")
        os.makedirs(projects)
        outside = os.path.join(scratch.temporary_folder(self, "lh-outside-"), "s")
        with open(outside + ".jsonl", "w", encoding="utf-8") as handle:
            handle.write("{}\n")
        with open(os.path.join(home, "s.jsonl"), "w", encoding="utf-8") as handle:
            handle.write("{}\n")
        with mock.patch.dict(os.environ, {"HOME": home}):
            for session in (outside, "../../s", ".."):
                with self.subTest(session=session):
                    self.assertIsNone(run_record.caller_transcript(session))


def newest_summary(store):
    folder = store_folder(store, "summary")
    return max((read_lines(os.path.join(folder, name))[0] for name in files_in(folder)), key=lambda line: line["started"])


if __name__ == "__main__":
    unittest.main()
