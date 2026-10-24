import json
import os
import subprocess
import sys
import unittest

from tests import scratch

CLAUDE_STUB = """#!{python}
import json
import os
import sys
import time

folder = os.path.dirname(os.path.realpath(__file__))
with open(os.path.join(folder, "claude-calls.jsonl"), "a", encoding="utf-8") as calls:
    calls.write(json.dumps({{"argv": sys.argv[1:], "cwd": os.getcwd(), "pid": os.getpid()}}) + "\\n")
time.sleep(0.5)
with open(os.path.join(folder, "claude-output.txt"), encoding="utf-8") as output:
    sys.stdout.write(output.read())
with open(os.path.join(folder, "claude-exit.txt"), encoding="utf-8") as code:
    sys.exit(int(code.read()))
"""

CAFFEINATE_STUB = """#!{python}
import json
import os
import sys
import time

folder = os.path.dirname(os.path.realpath(__file__))
arguments = sys.argv[1:]
watched = int(arguments[arguments.index("-w") + 1])


def alive():
    try:
        os.kill(watched, 0)
    except ProcessLookupError:
        return False
    return True


alive_at_start = alive()
deadline = time.monotonic() + 30
while alive() and time.monotonic() < deadline:
    time.sleep(0.05)
with open(os.path.join(folder, "caffeinate-calls.jsonl"), "a", encoding="utf-8") as calls:
    calls.write(json.dumps({{"argv": arguments, "alive_at_start": alive_at_start, "ended_after_child": not alive()}}) + "\\n")
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

GREEN_LINE = '{"verdict": "green", "failures": [], "unproven": [], "flaky": [], "tokens": 1200, "minutes": 3, "dollars": 1.25, "pr": null}'


def write_stub(folder, name, text):
    path = os.path.join(folder, name)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text.format(python=sys.executable))
    os.chmod(path, 0o755)


def claude_output(result, cost=1.25, model="claude-opus-5-5"):
    return json.dumps(
        {
            "type": "result",
            "result": result,
            "session_id": "child-session-1",
            "duration_ms": 120000,
            "total_cost_usd": cost,
            "modelUsage": {model: {"inputTokens": 10, "outputTokens": 20, "costUSD": cost}},
        }
    )


def stub_folder(test, output, exit_code=0):
    folder = scratch.temporary_folder(test, "lh-stubs-")
    write_stub(folder, "claude", CLAUDE_STUB)
    write_stub(folder, "caffeinate", CAFFEINATE_STUB)
    write_stub(folder, "systemd-inhibit", SYSTEMD_INHIBIT_STUB)
    with open(os.path.join(folder, "claude-output.txt"), "w", encoding="utf-8") as handle:
        handle.write(output)
    with open(os.path.join(folder, "claude-exit.txt"), "w", encoding="utf-8") as handle:
        handle.write(str(exit_code))
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


def ledger_lines(home):
    with open(os.path.join(home, ".lighthouse", "work", "runs.jsonl"), encoding="utf-8") as handle:
        return [json.loads(line) for line in handle.read().splitlines()]


def launch_flags(repo, results):
    return ["--repo", repo, "--core", "main", "--feature", "feat/x", "--results", results]


def launch(test, output, exit_code=0, nice=None):
    repo, _ = scratch.make_repo(test)
    home = scratch.make_home(test)
    results = os.path.join(scratch.temporary_folder(test, "lh-results-"), "results")
    stubs = stub_folder(test, output, exit_code)
    env = scratch.environment(home, stubs)
    prefix = ["nice", "-n", str(nice)] if nice is not None else []
    completed = subprocess.run(
        [*prefix, sys.executable, scratch.LIGHTHOUSE, "launch", *launch_flags(repo, results)],
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
    )
    return {
        "code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "repo": repo,
        "home": home,
        "results": results,
        "stubs": stubs,
    }


class LaunchTest(unittest.TestCase):
    def test_launch_runs_the_child_with_its_flags(self):
        ran = launch(self, claude_output("Driven every path.\n" + GREEN_LINE))
        self.assertEqual(ran["code"], 0, ran["stderr"])
        calls = calls_of(ran["stubs"], "claude")
        self.assertEqual(len(calls), 1)
        argv = calls[0]["argv"]
        prompt = "/lighthouse:test --child --repo {} --core main --feature feat/x --results {}".format(
            ran["repo"], ran["results"]
        )
        self.assertEqual(argv[:2], ["-p", prompt])
        self.assertEqual(argv[argv.index("--model") + 1], "opus")
        self.assertIn("--plugin-dir", argv)
        self.assertTrue(os.path.isfile(os.path.join(argv[argv.index("--plugin-dir") + 1], ".claude-plugin", "plugin.json")))
        self.assertEqual(argv[argv.index("--permission-mode") + 1], "bypassPermissions")
        self.assertEqual(argv[argv.index("--disallowedTools") + 1], "AskUserQuestion")
        self.assertEqual(argv[argv.index("--output-format") + 1], "json")
        self.assertEqual(os.path.realpath(calls[0]["cwd"]), os.path.realpath(os.path.join(ran["results"], "work")))

    def test_launch_prints_the_childs_verdict_line(self):
        earlier = '{"verdict": "unproven", "failures": [], "unproven": ["x"], "flaky": [], "tokens": 1, "minutes": 1, "pr": null}'
        ran = launch(self, claude_output("First try:\n" + earlier + "\nThen:\n" + GREEN_LINE + "\n"))
        self.assertEqual(ran["code"], 0, ran["stderr"])
        self.assertEqual(ran["stdout"].strip().splitlines()[-1], GREEN_LINE)
        self.assertEqual(read_json(os.path.join(ran["results"], "launch.json")), json.loads(GREEN_LINE))

    def test_launch_prints_a_blocked_line_when_the_child_gives_none(self):
        ran = launch(self, claude_output("I could not finish."), exit_code=1)
        self.assertEqual(ran["code"], 0, ran["stderr"])
        line = json.loads(ran["stdout"].strip().splitlines()[-1])
        self.assertEqual(line["verdict"], "blocked")
        self.assertIn("exited 1", ran["stderr"])
        self.assertIn("exited 1", ledger_lines(ran["home"])[-1]["reason"])

    def test_launch_prints_a_blocked_line_when_the_output_is_not_json(self):
        ran = launch(self, "not json at all", exit_code=1)
        self.assertEqual(ran["code"], 0, ran["stderr"])
        self.assertEqual(json.loads(ran["stdout"].strip().splitlines()[-1])["verdict"], "blocked")
        self.assertIn("not JSON", ran["stderr"])

    def test_launch_refuses_results_inside_the_repository(self):
        repo, _ = scratch.make_repo(self)
        stubs = stub_folder(self, claude_output(GREEN_LINE))
        results = os.path.join(repo, "results")
        env = scratch.environment(scratch.make_home(self), stubs)
        code, stdout, _ = scratch.run_lighthouse(["launch", *launch_flags(repo, results)], env)
        self.assertEqual(code, 2)
        self.assertIn("error", json.loads(stdout))
        self.assertEqual(calls_of(stubs, "claude"), [])
        self.assertFalse(os.path.exists(results))

    def test_launch_keeps_the_machine_awake(self):
        ran = launch(self, claude_output(GREEN_LINE))
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
        ran = launch(self, claude_output(GREEN_LINE, cost=1.25), nice=5)
        self.assertEqual(ran["code"], 0, ran["stderr"])
        child = read_json(os.path.join(ran["results"], "child.json"))
        self.assertEqual(child["cost"], {"claude-opus-5-5": 1.25})
        self.assertEqual(child["priority"]["nice"], 5)
        self.assertEqual(child["session_id"], "child-session-1")
        self.assertEqual(child["minutes"], 2)
        self.assertEqual(child["exit"], 0)
        if sys.platform == "darwin":
            self.assertIn(child["priority"]["background"], (True, False))
        else:
            self.assertIsNone(child["priority"]["background"])

    def test_launch_appends_a_ledger_line_when_the_child_gives_no_verdict(self):
        ran = launch(self, claude_output("The run stopped.", cost=0.8), exit_code=1)
        self.assertEqual(ran["code"], 0, ran["stderr"])
        lines = [line for line in ledger_lines(ran["home"]) if line["kind"] == "launch"]
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["verdict"], "blocked")
        self.assertEqual(lines[0]["cost"], {"claude-opus-5-5": 0.8})
        self.assertEqual(lines[0]["run"], os.path.realpath(ran["results"]))
        self.assertIn("keep_awake", lines[0])
        self.assertIn("priority", lines[0])
        printed = ran["stdout"].strip().splitlines()[-1]
        with open(os.path.join(ran["results"], "launch.json"), encoding="utf-8") as handle:
            self.assertEqual(handle.read().strip(), printed)


if __name__ == "__main__":
    unittest.main()
