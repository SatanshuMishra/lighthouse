import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

from lighthouse_tool import launch as launch_tool
from lighthouse_tool.repo import Refusal
from tests import scratch

ONE_WEEK_MS = 7 * 24 * 60 * 60 * 1000
LONGEST_TIMER_MS = 2**31 - 1
TEN_MINUTES_MS = 10 * 60 * 1000
ASKED_TIMEOUT = re.compile(r"timeout argument set to (\d+)")
INSTRUCTIONS = tuple(scratch.skill_path(name) for name in ("test", "init", "doctor")) + (
    os.path.join(scratch.ROOT, "agents", "driver.md"),
)

CLAUDE_STUB = """#!{python}
import json
import os
import sys
import time

folder = os.path.dirname(os.path.realpath(__file__))
results = os.path.dirname(os.getcwd())
earlier_line = os.path.join(results, "launch.json")
earlier_names = ("verdict.json", "checks.jsonl", "plan.json", "record.json", "findings.json", "findings.draft.json", "child.out", "core-start.pid", "core-start.exit", "feature-start.pid", "feature-start.exit")
earlier_files = [name for name in earlier_names if os.path.exists(os.path.join(results, name))]
calls_path = os.path.join(folder, "claude-calls.jsonl")
with open(calls_path, "a", encoding="utf-8") as calls:
    calls.write(json.dumps({{"argv": sys.argv[1:], "cwd": os.getcwd(), "pid": os.getpid(), "saw_launch": os.path.exists(earlier_line), "saw_earlier": earlier_files, "bash_ceilings": [os.environ.get("BASH_DEFAULT_TIMEOUT_MS"), os.environ.get("BASH_MAX_TIMEOUT_MS")], "effort": os.environ.get("CLAUDE_CODE_EFFORT_LEVEL")}}) + "\\n")
with open(calls_path, encoding="utf-8") as calls:
    index = len([line for line in calls.read().splitlines() if line.strip()]) - 1
time.sleep(0.5)
with open(os.path.join(folder, "claude-replies.json"), encoding="utf-8") as handle:
    replies = json.load(handle)
reply = replies[min(index, len(replies) - 1)]
for name, text in sorted(reply.get("files", {{}}).items()):
    with open(os.path.join(results, name), "w", encoding="utf-8") as written:
        written.write(text)
sys.stdout.write(reply["output"])
sys.exit(reply.get("exit", 0))
"""

CAFFEINATE_STUB = """#!{python}
import json
import os
import signal
import sys
import time

folder = os.path.dirname(os.path.realpath(__file__))
arguments = sys.argv[1:]
watched = int(arguments[arguments.index("-w") + 1])
follows_the_child = not os.path.exists(os.path.join(folder, "caffeinate-ignores-the-child"))


def alive():
    try:
        os.kill(watched, 0)
    except ProcessLookupError:
        return False
    return True


def record(stopped):
    with open(os.path.join(folder, "caffeinate-calls.jsonl"), "a", encoding="utf-8") as calls:
        calls.write(json.dumps({{"argv": arguments, "alive_at_start": alive_at_start, "ended_after_child": not alive(), "stopped": stopped}}) + "\\n")


def on_stop(number, frame):
    record(True)
    os._exit(0)


alive_at_start = alive()
signal.signal(signal.SIGTERM, on_stop)
deadline = time.monotonic() + 600
while (alive() or not follows_the_child) and time.monotonic() < deadline:
    time.sleep(0.05)
signal.signal(signal.SIGTERM, signal.SIG_IGN)
record(False)
"""

SYSTEMD_INHIBIT_STUB = """#!{python}
import json
import os
import sys

folder = os.path.dirname(os.path.realpath(__file__))
arguments = sys.argv[1:]
with open(os.path.join(folder, "systemd-inhibit-calls.jsonl"), "a", encoding="utf-8") as calls:
    calls.write(json.dumps({{"argv": arguments}}) + "\\n")
wrapped = [argument for argument in arguments if not argument.startswith("--what=") and not argument.startswith("--why=")]
os.execvp(wrapped[0], wrapped)
"""

BLOCKING_CLAUDE_STUB = """#!{python}
import json
import shlex
import subprocess
import sys

words = shlex.split(sys.argv[2])
results = words[words.index("--results") + 1]
stopped = subprocess.run(
    [sys.executable, {lighthouse!r}, "verdict", "--blocked", "the profile is broken", "--results", results],
    capture_output=True,
    text=True,
)
line = stopped.stdout.strip().splitlines()[-1]
print(json.dumps({{"type": "result", "result": line, "structured_output": {{"verdict_line": json.loads(line)}}, "session_id": "child-session-1", "duration_ms": 1000, "modelUsage": {{}}}}))
"""

SLOW_CLAUDE_STUB = CLAUDE_STUB.replace("time.sleep(0.5)", "time.sleep(3)")
LAUNCH_SECONDS = 300

GREEN_LINE = '{"verdict": "green", "failures": [], "unproven": [], "flaky": [], "tokens": 1200, "minutes": 3, "dollars": 1.25, "pr": null}'
RED_LINE = '{"verdict": "failures", "failures": ["export writes a csv"], "unproven": [], "flaky": [], "tokens": 900, "minutes": 4, "dollars": 1.5, "pr": null}'
BLOCKED_LINE = '{"verdict": "blocked", "failures": [], "unproven": [], "flaky": [], "tokens": 0, "minutes": 0, "pr": null, "reason": "the profile is broken"}'
PULL_REQUEST = "https://github.com/o/r/pull/2"
FINDINGS = {
    "version": 1,
    "suite": {"result": "passed", "reason": None, "failures": [], "pre_existing": [], "flaky": [], "core": None, "feature": None},
    "build": {"result": "ok", "reason": None},
    "paths": [
        {
            "name": "one",
            "kind": "new",
            "surface": "cli",
            "expected": "works",
            "evidence": ["evidence/one.log"],
            "status": "passed",
            "retry": None,
            "core": None,
            "trials": None,
            "check": {"kind": "direct", "why": "it answers"},
        }
    ],
    "spend": {"tokens": 10, "minutes": 1, "dollars": None},
}


def write_stub(folder, name, text):
    path = os.path.join(folder, name)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text.format(python=sys.executable, lighthouse=scratch.LIGHTHOUSE))
    os.chmod(path, 0o755)


def seed_earlier_run(results):
    os.makedirs(results, exist_ok=True)
    with open(os.path.join(results, "launch.json"), "w", encoding="utf-8") as handle:
        handle.write(GREEN_LINE + "\n")
    with open(os.path.join(results, "child.json"), "w", encoding="utf-8") as handle:
        handle.write("{}\n")
    for name in ("verdict.json", "plan.json", "record.json", "findings.json", "findings.draft.json", "child.out"):
        with open(os.path.join(results, name), "w", encoding="utf-8") as handle:
            handle.write("{}\n")
    for name in ("core-start.pid", "core-start.exit", "feature-start.pid", "feature-start.exit"):
        with open(os.path.join(results, name), "w", encoding="utf-8") as handle:
            handle.write("0\n")
    with open(os.path.join(results, "checks.jsonl"), "w", encoding="utf-8") as handle:
        handle.write("{}\n")


def last_verdict_object(result):
    found = [line for line in (json_object(text.strip()) for text in result.splitlines()) if line is not None]
    return found[-1] if found else None


def json_object(text):
    try:
        value = json.loads(text)
    except ValueError:
        return None
    return value if isinstance(value, dict) and "verdict" in value else None


def claude_output(result, cost=1.25, model="claude-opus-5-5", usage=None):
    line = last_verdict_object(result)
    return json.dumps(
        {
            "type": "result",
            "result": result,
            **({"structured_output": {"verdict_line": line}} if line is not None else {}),
            "session_id": "child-session-1",
            "duration_ms": 120000,
            "total_cost_usd": cost,
            "modelUsage": usage if usage is not None else {model: {"inputTokens": 10, "outputTokens": 20, "costUSD": cost}},
        }
    )


def written_files(written):
    if written is None:
        return {}
    return {"verdict.json": written + "\n", "findings.json": json.dumps(FINDINGS, indent=2) + "\n"}


def stub_folder(test, output, exit_code=0, written=None, then=()):
    folder = scratch.temporary_folder(test, "lh-stubs-")
    write_stub(folder, "claude", CLAUDE_STUB)
    write_stub(folder, "caffeinate", CAFFEINATE_STUB)
    write_stub(folder, "systemd-inhibit", SYSTEMD_INHIBIT_STUB)
    replies = [{"output": output, "exit": exit_code, "files": written_files(written)}, *then]
    with open(os.path.join(folder, "claude-replies.json"), "w", encoding="utf-8") as handle:
        handle.write(json.dumps(replies))
    return folder


def calls_of(folder, name):
    path = os.path.join(folder, name + "-calls.jsonl")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle.read().splitlines()]


def read_json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def ledger_path(home):
    return os.path.join(home, ".lighthouse", "work", "runs.jsonl")


def summary_files(store, repo):
    folder = os.path.join(store, "plugin=lighthouse", "kind=summary", "repo=" + os.path.basename(repo))
    return sorted(os.path.join(folder, name) for name in os.listdir(folder)) if os.path.isdir(folder) else []


def launch_environment(test, home, stubs):
    return {**scratch.environment(home, stubs), "PLUGIN_METRICS_DIR": scratch.temporary_folder(test, "lh-store-")}


def launch_flags(repo, results):
    return ["--repo", repo, "--core", "main", "--feature", "feat/x", "--results", results]


def launch(
    test, output, exit_code=0, nice=None, earlier=False, claude=CLAUDE_STUB, written=None, marks=(), then=(), caller=None
):
    repo, _ = scratch.make_repo(test)
    home = scratch.make_home(test)
    store = scratch.temporary_folder(test, "lh-store-")
    results = os.path.join(scratch.temporary_folder(test, "lh-results-"), "results")
    if earlier:
        seed_earlier_run(results)
    stubs = stub_folder(test, output, exit_code, written, then)
    write_stub(stubs, "claude", claude)
    for mark in marks:
        open(os.path.join(stubs, mark), "w", encoding="utf-8").close()
    env = {**scratch.environment(home, stubs), "PLUGIN_METRICS_DIR": store, **(caller or {})}
    prefix = ["nice", "-n", str(nice)] if nice is not None else []
    completed = subprocess.run(
        [*prefix, sys.executable, scratch.LIGHTHOUSE, "launch", *launch_flags(repo, results)],
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=LAUNCH_SECONDS,
    )
    return {
        "code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "repo": repo,
        "home": home,
        "store": store,
        "results": results,
        "stubs": stubs,
    }


class LaunchTest(unittest.TestCase):
    def test_the_child_takes_no_effort_from_the_callers_environment(self):
        ran = launch(self, claude_output("Driven every path.\n" + BLOCKED_LINE), caller={"CLAUDE_CODE_EFFORT_LEVEL": "low"})
        self.assertEqual(ran["code"], 0, ran["stderr"])
        call = calls_of(ran["stubs"], "claude")[0]
        self.assertEqual((call["argv"][call["argv"].index("--effort") + 1], call["effort"]), ("high", None))

    def test_launch_runs_the_child_with_its_flags(self):
        ran = launch(self, claude_output("Driven every path.\n" + BLOCKED_LINE))
        self.assertEqual(ran["code"], 0, ran["stderr"])
        calls = calls_of(ran["stubs"], "claude")
        self.assertEqual(len(calls), 1)
        argv = calls[0]["argv"]
        prompt = "/lighthouse:test --child --repo {} --core main --feature feat/x --results {}".format(
            ran["repo"], ran["results"]
        )
        self.assertEqual(argv[:2], ["-p", prompt])
        self.assertEqual(argv[argv.index("--model") + 1], "opus")
        self.assertEqual(argv[argv.index("--effort") + 1], "high")
        self.assertIn("--plugin-dir", argv)
        self.assertTrue(os.path.isfile(os.path.join(argv[argv.index("--plugin-dir") + 1], ".claude-plugin", "plugin.json")))
        self.assertEqual(argv[argv.index("--permission-mode") + 1], "bypassPermissions")
        self.assertEqual(argv[argv.index("--disallowedTools") + 1], "AskUserQuestion")
        self.assertEqual(argv[argv.index("--output-format") + 1], "json")
        schema = json.loads(argv[argv.index("--json-schema") + 1])
        self.assertEqual(schema["type"], "object")
        self.assertEqual(schema["required"], ["verdict_line"])
        self.assertNotIn("$schema", schema)
        self.assertNotIn("--resume", argv)
        self.assertEqual(os.path.realpath(calls[0]["cwd"]), os.path.realpath(os.path.join(ran["results"], "work")))

    def test_the_child_and_its_re_ask_may_hold_a_step_for_a_week_and_keep_the_two_minute_default(self):
        ran = launch(self, claude_output("I could not finish."), caller={"BASH_DEFAULT_TIMEOUT_MS": str(ONE_WEEK_MS), "BASH_MAX_TIMEOUT_MS": str(TEN_MINUTES_MS)})
        self.assertEqual(ran["code"], 0, ran["stderr"])
        calls = calls_of(ran["stubs"], "claude")
        self.assertEqual(len(calls), 2)
        for call in calls:
            default, longest = call["bash_ceilings"]
            self.assertIsNotNone(longest, "the child session keeps the Bash tool's own ten-minute ceiling")
            self.assertGreaterEqual(int(longest), ONE_WEEK_MS)
            self.assertLessEqual(int(longest), LONGEST_TIMER_MS)
            self.assertIsNone(default, "a command that hangs in the child is held instead of moved after two minutes")
            for path in INSTRUCTIONS:
                asked = [int(value) for value in ASKED_TIMEOUT.findall(scratch.read_text(path))]
                self.assertTrue(asked, "{} asks for no timeout".format(path))
                self.assertLessEqual(max(asked), int(longest), "{} asks for a timeout the child's Bash tool refuses".format(path))

    def test_launch_reads_the_reply_from_structured_output_not_the_result_text(self):
        text_line = json.dumps({**json.loads(BLOCKED_LINE), "reason": "text reason"})
        output = json.dumps({**json.loads(claude_output(BLOCKED_LINE)), "result": text_line})
        ran = launch(self, output)
        self.assertEqual(ran["code"], 0, ran["stderr"])
        self.assertEqual(json.loads(ran["stdout"].strip().splitlines()[-1]), json.loads(BLOCKED_LINE))
        self.assertEqual(len(calls_of(ran["stubs"], "claude")), 1)

    def test_launch_prints_verdict_json_with_the_replys_pr(self):
        opened = json.dumps({**json.loads(RED_LINE), "pr": PULL_REQUEST})
        ran = launch(self, claude_output("Then:\n" + opened + "\n"), written=GREEN_LINE)
        self.assertEqual(ran["code"], 0, ran["stderr"])
        expected = {**json.loads(GREEN_LINE), "pr": PULL_REQUEST}
        self.assertEqual(json.loads(ran["stdout"].strip().splitlines()[-1]), expected)
        self.assertEqual(read_json(os.path.join(ran["results"], "launch.json")), expected)
        self.assertEqual(len(calls_of(ran["stubs"], "claude")), 1)

    def test_launch_without_verdict_json_re_asks_then_blocks_naming_the_file(self):
        ran = launch(self, claude_output("Driven every path.\n" + GREEN_LINE))
        self.assertEqual(ran["code"], 0, ran["stderr"])
        calls = calls_of(ran["stubs"], "claude")
        self.assertEqual(len(calls), 2)
        second = calls[1]["argv"]
        self.assertEqual(second[second.index("--resume") + 1], "child-session-1")
        self.assertIn("verdict.json fails h13-lighthouse-verdict-line.schema.json#/$defs/verdict", second[1])
        self.assertIn("findings.json fails h14-lighthouse-findings.schema.json", second[1])
        self.assertEqual(json.loads(second[second.index("--json-schema") + 1])["required"], ["verdict_line"])
        self.assertEqual(os.path.realpath(calls[1]["cwd"]), os.path.realpath(os.path.join(ran["results"], "work")))
        line = json.loads(ran["stdout"].strip().splitlines()[-1])
        self.assertEqual(line["verdict"], "blocked")
        self.assertIn("verdict.json", line["reason"])
        self.assertIn("h13-lighthouse-verdict-line", line["reason"])
        self.assertIn("# missing: the child session left no verdict.json", line["reason"])
        self.assertEqual(read_json(os.path.join(ran["results"], "launch.json")), line)

    def test_a_re_asked_reply_that_passes_is_printed_and_both_calls_are_recorded(self):
        noted = json.dumps({**json.loads(BLOCKED_LINE), "note": "x"})
        second = {"output": claude_output(BLOCKED_LINE, cost=0.5), "exit": 0}
        ran = launch(self, claude_output(noted, cost=1.25), then=(second,))
        self.assertEqual(ran["code"], 0, ran["stderr"])
        calls = calls_of(ran["stubs"], "claude")
        self.assertEqual(len(calls), 2)
        self.assertIn('property "note" is not allowed', calls[1]["argv"][1])
        self.assertEqual(json.loads(ran["stdout"].strip().splitlines()[-1]), json.loads(BLOCKED_LINE))
        child = read_json(os.path.join(ran["results"], "child.json"))
        self.assertEqual(
            child["calls"],
            [
                {"session_id": "child-session-1", "minutes": 2, "exit": 0},
                {"session_id": "child-session-1", "minutes": 2, "exit": 0},
            ],
        )
        self.assertEqual(child["cost"], {"claude-opus-5-5": 1.75})
        self.assertEqual(child["minutes"], 4)
        self.assertIn("re-asked once", ran["stderr"])

    def test_launch_passes_the_record_to_the_child_and_copies_it(self):
        repo, _ = scratch.make_repo(self)
        results = os.path.join(scratch.temporary_folder(self, "lh-results-"), "results")
        record = os.path.join(scratch.temporary_folder(self, "lh-record-"), "chosen.json")
        with open(record, "w", encoding="utf-8") as handle:
            handle.write('{"criteria": []}\n')
        stubs = stub_folder(self, claude_output(BLOCKED_LINE))
        env = launch_environment(self, scratch.make_home(self), stubs)
        code, _, stderr = scratch.run_lighthouse(["launch", *launch_flags(repo, results), "--record", record], env)
        self.assertEqual(code, 0, stderr)
        call = calls_of(stubs, "claude")[0]
        self.assertIn("--record {}".format(record), call["argv"][1])
        self.assertEqual(call["saw_earlier"], ["record.json"])
        with open(os.path.join(results, "record.json"), encoding="utf-8") as handle:
            self.assertEqual(handle.read(), '{"criteria": []}\n')

    def test_launch_re_asks_then_blocks_when_the_child_gives_no_structured_output(self):
        ran = launch(self, claude_output("I could not finish."), exit_code=1)
        self.assertEqual(ran["code"], 0, ran["stderr"])
        self.assertEqual(len(calls_of(ran["stubs"], "claude")), 2)
        line = json.loads(ran["stdout"].strip().splitlines()[-1])
        self.assertEqual(line["verdict"], "blocked")
        self.assertIn("the reply fails the reply schema built from h13-lighthouse-verdict-line.schema.json", line["reason"])
        self.assertIn("# required: the reply carries no structured_output", line["reason"])
        self.assertIn("exited 1", ran["stderr"])

    def test_launch_keeps_output_that_is_not_json_in_child_out_and_blocks(self):
        ran = launch(self, "not json at all\nsecond line", exit_code=1)
        self.assertEqual(ran["code"], 0, ran["stderr"])
        self.assertEqual(len(calls_of(ran["stubs"], "claude")), 1)
        kept = os.path.join(os.path.realpath(ran["results"]), "child.out")
        line = json.loads(ran["stdout"].strip().splitlines()[-1])
        self.assertEqual(line["verdict"], "blocked")
        self.assertEqual(
            line["reason"], "the child session printed no JSON result with a session_id; its output is kept in " + kept
        )
        with open(kept, "rb") as handle:
            self.assertEqual(handle.read(), b"not json at all\nsecond line")
        child = read_json(os.path.join(ran["results"], "child.json"))
        self.assertEqual((child["session_id"], child["exit"], child["cost"], child["unpriced"]), (None, 1, {}, []))

    def test_launch_refuses_results_inside_the_repository(self):
        repo, _ = scratch.make_repo(self)
        stubs = stub_folder(self, claude_output(GREEN_LINE))
        results = os.path.join(repo, "results")
        env = launch_environment(self, scratch.make_home(self), stubs)
        code, stdout, _ = scratch.run_lighthouse(["launch", *launch_flags(repo, results)], env)
        self.assertEqual(code, 2)
        self.assertIn("error", json.loads(stdout))
        self.assertEqual(calls_of(stubs, "claude"), [])
        self.assertFalse(os.path.exists(results))

    def test_launch_keeps_the_machine_awake(self):
        ran = launch(self, claude_output(BLOCKED_LINE))
        self.assertEqual(ran["code"], 0, ran["stderr"])
        child = read_json(os.path.join(ran["results"], "child.json"))
        claude_call = calls_of(ran["stubs"], "claude")[0]
        if sys.platform == "darwin":
            calls = calls_of(ran["stubs"], "caffeinate")
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0]["argv"], ["-i", "-w", str(claude_call["pid"])])
            self.assertTrue(calls[0]["alive_at_start"])
            self.assertTrue(calls[0]["ended_after_child"])
            self.assertEqual(child["keep_awake"], "caffeinate")
        elif sys.platform.startswith("linux"):
            calls = calls_of(ran["stubs"], "systemd-inhibit")
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0]["argv"][:2], ["--what=idle:sleep", "--why=lighthouse"])
            self.assertEqual(calls[0]["argv"][2:4], ["claude", "-p"])
            self.assertEqual(child["keep_awake"], "systemd-inhibit")
        else:
            self.assertEqual(child["keep_awake"], "none")

    def test_launch_records_cost_and_priority(self):
        ran = launch(self, claude_output(BLOCKED_LINE, cost=1.25), nice=5)
        self.assertEqual(ran["code"], 0, ran["stderr"])
        child = read_json(os.path.join(ran["results"], "child.json"))
        self.assertEqual(child["cost"], {"claude-opus-5-5": 1.25})
        self.assertEqual(child["unpriced"], [])
        self.assertEqual(child["calls"], [{"session_id": "child-session-1", "minutes": 2, "exit": 0}])
        self.assertEqual(child["priority"]["nice"], 5)
        self.assertEqual(child["session_id"], "child-session-1")
        self.assertEqual(child["minutes"], 2)
        self.assertEqual(child["exit"], 0)
        if sys.platform == "darwin":
            self.assertIn(child["priority"]["background"], (True, False))
        else:
            self.assertIsNone(child["priority"]["background"])

    def test_launch_lists_a_cost_it_cannot_read_as_unpriced_and_names_it(self):
        usage = {
            "claude-opus-5-5": {"costUSD": 1.25},
            "claude-haiku-5-5": {"costUSD": None},
            "claude-sonnet-5-5": "not an entry",
        }
        ran = launch(self, claude_output(BLOCKED_LINE, usage=usage))
        self.assertEqual(ran["code"], 0, ran["stderr"])
        child = read_json(os.path.join(ran["results"], "child.json"))
        self.assertEqual(child["cost"], {"claude-opus-5-5": 1.25})
        self.assertEqual(child["unpriced"], ["claude-haiku-5-5", "claude-sonnet-5-5"])
        self.assertIn("no number costUSD for claude-haiku-5-5", ran["stderr"])
        self.assertIn("no number costUSD for claude-sonnet-5-5", ran["stderr"])
        self.assertNotIn("costUSD for claude-opus-5-5", ran["stderr"])

    def test_the_printed_line_is_checked_against_h13(self):
        broken = launch_tool.Conversation((), {"verdict": "green", "pr": None}, None)
        with self.assertRaises(Refusal) as raised:
            launch_tool.printed_line(broken)
        self.assertIn("h13-lighthouse-verdict-line", str(raised.exception))
        passing = launch_tool.Conversation((), json.loads(GREEN_LINE), None)
        self.assertEqual(json.loads(launch_tool.printed_line(passing)), json.loads(GREEN_LINE))

    def test_launch_writes_no_ledger(self):
        green = launch(self, claude_output(GREEN_LINE), written=GREEN_LINE)
        self.assertEqual(green["code"], 0, green["stderr"])
        self.assertFalse(os.path.exists(ledger_path(green["home"])))
        ran = launch(self, claude_output("The run stopped.", cost=0.8), exit_code=1)
        self.assertEqual(ran["code"], 0, ran["stderr"])
        self.assertFalse(os.path.exists(ledger_path(ran["home"])))
        printed = ran["stdout"].strip().splitlines()[-1]
        self.assertEqual(json.loads(printed)["verdict"], "blocked")
        with open(os.path.join(ran["results"], "launch.json"), encoding="utf-8") as handle:
            self.assertEqual(handle.read().strip(), printed)

    def test_launch_clears_an_earlier_launch_line_before_the_child_starts(self):
        ran = launch(self, claude_output(RED_LINE), earlier=True, written=RED_LINE)
        self.assertEqual(ran["code"], 0, ran["stderr"])
        self.assertFalse(calls_of(ran["stubs"], "claude")[0]["saw_launch"])
        self.assertEqual(calls_of(ran["stubs"], "claude")[0]["saw_earlier"], [])
        self.assertEqual(read_json(os.path.join(ran["results"], "launch.json")), json.loads(RED_LINE))

    def test_a_refused_launch_replaces_an_earlier_launch_line_with_a_blocked_one(self):
        repo, _ = scratch.make_repo(self)
        plain = scratch.temporary_folder(self, "lh-plain-")
        stubs = stub_folder(self, claude_output(GREEN_LINE))
        env = launch_environment(self, scratch.make_home(self), stubs)
        refusals = {
            "not a git repository": lambda results: launch_flags(plain, results),
            "a flag is missing": lambda results: [flag for flag in launch_flags(repo, results) if flag not in ("--core", "main")],
        }
        for refusal, flags_for in refusals.items():
            with self.subTest(refusal=refusal):
                results = os.path.join(scratch.temporary_folder(self, "lh-results-"), "results")
                seed_earlier_run(results)
                code, stdout, stderr = scratch.run_lighthouse(["launch", *flags_for(results)], env)
                self.assertEqual(code, 2, stderr)
                self.assertIn("error", json.loads(stdout.strip().splitlines()[-1]))
                self.assertEqual(read_json(os.path.join(results, "launch.json"))["verdict"], "blocked")
                self.assertFalse(os.path.exists(os.path.join(results, "child.json")))
        self.assertEqual(calls_of(stubs, "claude"), [])

    def test_a_refused_launch_leaves_a_checkout_it_cannot_judge_untouched(self):
        repo, _ = scratch.make_repo(self)
        user = os.path.join(scratch.temporary_folder(self, "lh-user-"), "checkout")
        os.makedirs(os.path.join(user, ".vscode"))
        scratch.run_git(user, "init", "-q")
        for name in ("launch.json", "child.json"):
            with open(os.path.join(user, ".vscode", name), "w", encoding="utf-8") as handle:
                handle.write("{}\n")
        scratch.run_git(user, "add", "-A")
        scratch.run_git(user, "-c", "user.name=u", "-c", "user.email=u@example.invalid", "commit", "-qm", "init")
        plain = scratch.temporary_folder(self, "lh-plain-")
        stubs = stub_folder(self, claude_output(GREEN_LINE))
        env = launch_environment(self, scratch.make_home(self), stubs)
        unjudged = {
            "repo omitted": lambda results: [flag for flag in launch_flags(repo, results) if flag not in ("--repo", repo)],
            "repo not a git repository": lambda results: launch_flags(plain, results),
        }
        for refusal, flags_for in unjudged.items():
            for results in (os.path.join(user, ".vscode"), os.path.join(user, "out", "run")):
                with self.subTest(refusal=refusal, results=results):
                    code, _, stderr = scratch.run_lighthouse(["launch", *flags_for(results)], env)
                    self.assertEqual(code, 2, stderr)
                    status = subprocess.run(
                        ["git", "-C", user, "status", "--porcelain", "--untracked-files=all"], capture_output=True, text=True
                    )
                    self.assertEqual(status.stdout, "")
        self.assertEqual(calls_of(stubs, "claude"), [])

    def test_launch_refuses_a_results_path_that_is_a_file_without_a_traceback(self):
        repo, _ = scratch.make_repo(self)
        results = os.path.join(scratch.temporary_folder(self, "lh-results-"), "results")
        with open(results, "w", encoding="utf-8") as handle:
            handle.write("not a folder\n")
        env = launch_environment(self, scratch.make_home(self), stub_folder(self, claude_output(GREEN_LINE)))
        code, stdout, stderr = scratch.run_lighthouse(["launch", *launch_flags(repo, results)], env)
        self.assertEqual(code, 2, stderr)
        self.assertIn("error", json.loads(stdout.strip().splitlines()[-1]))
        self.assertNotIn("Traceback", stderr)

    def test_a_blocked_child_and_its_launch_count_as_one_run(self):
        ran = launch(self, "", claude=BLOCKING_CLAUDE_STUB)
        self.assertEqual(ran["code"], 0, ran["stderr"])
        printed = json.loads(ran["stdout"].strip().splitlines()[-1])
        self.assertEqual((printed["verdict"], printed["reason"]), ("blocked", "the profile is broken"))
        summaries = summary_files(ran["store"], ran["repo"])
        self.assertEqual(len(summaries), 1)
        summary = read_json(summaries[0])
        self.assertEqual((summary["verdict"], summary["reason"]), ("blocked", "the profile is broken"))
        self.assertEqual(summary["results"], os.path.realpath(ran["results"]))
        self.assertFalse(os.path.exists(ledger_path(ran["home"])))


class UncreatableStateFolderTest(unittest.TestCase):
    def setUp(self):
        self.repo, _ = scratch.make_repo(self)
        self.home = scratch.make_home(self)
        open(os.path.join(self.home, ".lighthouse"), "w").close()
        self.results = os.path.join(scratch.temporary_folder(self, "lh-results-"), "results")
        self.env = launch_environment(self, self.home, stub_folder(self, claude_output(GREEN_LINE), written=GREEN_LINE))

    def test_a_refused_launch_with_an_uncreatable_state_folder_still_leaves_a_blocked_line(self):
        flags = [flag for flag in launch_flags(self.repo, self.results) if flag not in ("--core", "main")]
        code, stdout, stderr = scratch.run_lighthouse(["launch", *flags], self.env)
        self.assertEqual(code, 2, stderr)
        self.assertNotIn("Traceback", stderr)
        self.assertIn("error", json.loads(stdout.strip().splitlines()[-1]))
        self.assertEqual(read_json(os.path.join(self.results, "launch.json"))["verdict"], "blocked")

    def test_a_launch_with_an_uncreatable_state_folder_keeps_the_childs_verdict_line(self):
        code, stdout, stderr = scratch.run_lighthouse(["launch", *launch_flags(self.repo, self.results)], self.env)
        self.assertEqual(code, 0, stderr)
        self.assertNotIn("Traceback", stderr)
        self.assertEqual(json.loads(stdout.strip().splitlines()[-1]), json.loads(GREEN_LINE))
        self.assertEqual(read_json(os.path.join(self.results, "launch.json")), json.loads(GREEN_LINE))

    def test_a_blocked_verdict_with_an_uncreatable_state_folder_prints_its_line_without_a_traceback(self):
        code, stdout, stderr = scratch.run_lighthouse(["verdict", "--blocked", "x"], self.env)
        self.assertEqual(code, 0, stderr)
        self.assertNotIn("Traceback", stderr)
        line = json.loads(stdout.strip().splitlines()[-1])
        self.assertEqual((line["verdict"], line["reason"]), ("blocked", "x"))
        self.assertTrue(os.path.isfile(os.path.join(self.home, ".lighthouse")))


class NoLimitTest(unittest.TestCase):
    def test_a_slow_child_runs_to_its_end_and_launch_writes_no_limits_file(self):
        ran = launch(self, claude_output("Driven every path.\n" + GREEN_LINE), claude=SLOW_CLAUDE_STUB, written=GREEN_LINE)
        self.assertEqual(ran["code"], 0, ran["stderr"])
        self.assertEqual(json.loads(ran["stdout"].strip().splitlines()[-1]), json.loads(GREEN_LINE))
        self.assertEqual(read_json(os.path.join(ran["results"], "child.json"))["exit"], 0)
        self.assertFalse(os.path.exists(os.path.join(ran["results"], "limits.json")))
        self.assertNotIn("time limit", ran["stdout"] + ran["stderr"])

    def test_launch_ends_the_keep_awake_guard_once_the_child_has_exited(self):
        ran = launch(self, claude_output(GREEN_LINE), written=GREEN_LINE, marks=("caffeinate-ignores-the-child",))
        self.assertEqual(ran["code"], 0, ran["stderr"])
        calls = calls_of(ran["stubs"], "caffeinate")
        if sys.platform == "darwin":
            self.assertEqual(len(calls), 1, calls)
            self.assertIs(calls[0]["stopped"], True)
            self.assertIs(calls[0]["ended_after_child"], True)
        else:
            self.assertEqual(calls, [])


class ChildStderrTest(unittest.TestCase):
    def test_child_out_keeps_what_the_child_printed_on_stderr(self):
        results = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, results, True)
        environment = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
        ran = launch_tool.run_child(
            ["sh", "-c", 'echo "Error: unknown option --json-schema" >&2; exit 1'],
            results,
            launch_tool.NO_KEEP_AWAKE,
            environment,
        )
        self.assertEqual(ran.exit, 1)
        answer = launch_tool.answered(launch_tool.Call(ran, None), results, {})
        kept = os.path.join(results, launch_tool.CHILD_OUT)
        self.assertIn(kept, answer.reason)
        with open(kept, "rb") as handle:
            self.assertIn(b"Error: unknown option --json-schema", handle.read())


if __name__ == "__main__":
    unittest.main()
