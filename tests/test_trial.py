import json
import os
import sys
import unittest

from tests import scratch

PLUGIN = "demo"
MARKETPLACE = "market"

CLAUDE_STUB = """#!{python}
import json
import os
import select
import sys
import time

folder = os.path.dirname(os.path.realpath(__file__))
argv = sys.argv[1:]
with open(os.path.join(folder, "claude-plan.json"), encoding="utf-8") as handle:
    plan = json.load(handle)
started = os.path.join(folder, "started-" + str(os.getpid()))
open(started, "w").close()
deadline = time.time() + plan["hold_seconds"]
together = False
while time.time() < deadline:
    together = len([name for name in os.listdir(folder) if name.startswith("started-")]) >= plan["sessions"]
    if together:
        break
    time.sleep(0.02)
with open(os.path.join(folder, "claude-calls.jsonl"), "a", encoding="utf-8") as calls:
    calls.write(json.dumps({{
        "argv": argv,
        "cwd": os.getcwd(),
        "path": os.environ.get("PATH", "").split(os.pathsep),
        "cache": os.environ.get("CLAUDE_CODE_PROMPT_CACHE_TTL"),
        "effort": os.environ.get("CLAUDE_CODE_EFFORT_LEVEL"),
        "stdin_closed": bool(select.select([sys.stdin], [], [], 0.5)[0]) and sys.stdin.read() == "",
        "together": together,
    }}) + "\\n")
loaded = plan["loaded"] or [argv[argv.index("--plugin-dir") + 1]]
print(json.dumps({{"type": "system", "subtype": "init", "plugins": [{{"name": plan["plugin"], "path": path}} for path in loaded]}}))
print(json.dumps({{"type": "result", "subtype": "success", "result": "done"}}))
sys.stderr.write("stub stderr\\n")
sys.exit(plan["exit"])
"""


def write_stub(folder, plan):
    path = os.path.join(folder, "claude")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(CLAUDE_STUB.format(python=sys.executable))
    os.chmod(path, 0o755)
    with open(os.path.join(folder, "claude-plan.json"), "w", encoding="utf-8") as handle:
        json.dump(plan, handle)


def calls_of(folder):
    path = os.path.join(folder, "claude-calls.jsonl")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle.read().splitlines()]


def build_copy(test):
    build = scratch.temporary_folder(test, "lh-build-")
    os.makedirs(os.path.join(build, ".claude-plugin"))
    with open(os.path.join(build, ".claude-plugin", "plugin.json"), "w", encoding="utf-8") as handle:
        json.dump({"name": PLUGIN, "version": "2.0.0"}, handle)
    return os.path.realpath(build)


def installed_copy(config):
    installed = os.path.join(config, "plugins", "cache", MARKETPLACE, PLUGIN, "1.0.0")
    os.makedirs(os.path.join(installed, "bin"))
    record = {"version": 2, "plugins": {PLUGIN + "@" + MARKETPLACE: [{"installPath": installed}], "other@" + MARKETPLACE: [{"installPath": "elsewhere"}]}}
    with open(os.path.join(config, "plugins", "installed_plugins.json"), "w", encoding="utf-8") as handle:
        json.dump(record, handle)
    return installed


class Trial:
    def __init__(self, test, sessions=2, loaded=None, exit_code=0, config=None, hold_seconds=0):
        self.home = scratch.make_home(test)
        self.config = config or os.path.join(self.home, ".claude")
        self.installed = installed_copy(self.config)
        self.build = build_copy(test)
        self.stubs = scratch.temporary_folder(test, "lh-stubs-")
        write_stub(self.stubs, {"sessions": sessions, "hold_seconds": hold_seconds, "plugin": PLUGIN, "loaded": loaded, "exit": exit_code})
        self.evidence = os.path.join(scratch.temporary_folder(test, "lh-results-"), "evidence", "skill")
        self.folders = [os.path.realpath(scratch.temporary_folder(test, "lh-trial-")) for _ in range(sessions)]
        base = scratch.environment(self.home, self.stubs)
        self.environment = {
            **base,
            "PATH": os.pathsep.join([os.path.join(self.installed, "bin"), base["PATH"]]),
            "CLAUDE_CODE_EFFORT_LEVEL": "low",
            **({"CLAUDE_CONFIG_DIR": config} if config else {}),
        }

    def arguments(self, *extra):
        folders = [part for folder in self.folders for part in ("--folder", folder)]
        return ["trial", "--plugin-dir", self.build, "--request", "Prepare the title.", "--evidence", self.evidence, "--name", "feature", *folders, *extra]

    def run(self, *extra):
        return scratch.run_lighthouse(self.arguments(*extra), self.environment)


class TrialTest(unittest.TestCase):
    def test_a_trial_session_cannot_find_the_installed_copy_of_the_plugin_under_test(self):
        trial = Trial(self)
        code, stdout, stderr = trial.run()
        self.assertEqual(code, 0, stderr)
        calls = calls_of(trial.stubs)
        self.assertEqual(len(calls), 2)
        cache = os.path.realpath(os.path.join(trial.config, "plugins", "cache"))
        for call in calls:
            inside = [entry for entry in call["path"] if os.path.realpath(entry).startswith(cache + os.sep)]
            self.assertEqual(inside, [])
            self.assertIn(trial.stubs, call["path"])
            argv = call["argv"]
            self.assertEqual(argv[:2], ["-p", "Prepare the title."])
            self.assertEqual(argv[argv.index("--plugin-dir") + 1], trial.build)
            settings = json.loads(argv[argv.index("--settings") + 1])
            self.assertEqual(settings, {"enabledPlugins": {PLUGIN + "@" + MARKETPLACE: False}})

    def test_the_installed_copies_are_read_from_the_configuration_folder_in_force(self):
        config = os.path.join(scratch.temporary_folder(self, "lh-config-"), "claude")
        trial = Trial(self, config=config)
        code, stdout, stderr = trial.run()
        self.assertEqual(code, 0, stderr)
        self.assertEqual(json.loads(stdout.strip().splitlines()[-1])["disabled"], [PLUGIN + "@" + MARKETPLACE])
        cache = os.path.realpath(os.path.join(config, "plugins", "cache"))
        for call in calls_of(trial.stubs):
            self.assertEqual([entry for entry in call["path"] if os.path.realpath(entry).startswith(cache + os.sep)], [])

    def test_each_session_states_its_model_effort_and_cache_rate_and_starts_in_its_own_folder(self):
        trial = Trial(self)
        code, _, stderr = trial.run()
        self.assertEqual(code, 0, stderr)
        calls = calls_of(trial.stubs)
        self.assertEqual(sorted(call["cwd"] for call in calls), sorted(trial.folders))
        for call in calls:
            argv = call["argv"]
            self.assertEqual(argv[argv.index("--model") + 1], "opus")
            self.assertEqual(argv[argv.index("--effort") + 1], "high")
            self.assertEqual(argv[argv.index("--output-format") + 1], "stream-json")
            self.assertIn("--verbose", argv)
            self.assertEqual(call["cache"], "5m")
            self.assertIsNone(call["effort"])
            self.assertTrue(call["stdin_closed"])

    def test_the_sessions_of_one_call_run_at_the_same_time(self):
        trial = Trial(self, sessions=3, hold_seconds=20)
        code, _, stderr = trial.run()
        self.assertEqual(code, 0, stderr)
        self.assertEqual([call["together"] for call in calls_of(trial.stubs)], [True, True, True])

    def test_it_reports_each_transcript_and_the_copy_each_session_loaded(self):
        trial = Trial(self)
        code, stdout, stderr = trial.run("--model", "sonnet", "--effort", "medium", "--", "--permission-mode", "bypassPermissions")
        self.assertEqual(code, 0, stderr)
        report = json.loads(stdout.strip().splitlines()[-1])
        self.assertEqual(report["plugin"], PLUGIN)
        self.assertEqual(report["disabled"], [PLUGIN + "@" + MARKETPLACE])
        self.assertEqual((report["model"], report["effort"]), ("sonnet", "medium"))
        self.assertEqual([row["trial"] for row in report["trials"]], [1, 2])
        for row, folder in zip(report["trials"], trial.folders):
            self.assertEqual(row["folder"], folder)
            self.assertEqual(row["transcript"], os.path.join(os.path.realpath(trial.evidence), "feature-{}.jsonl".format(row["trial"])))
            self.assertEqual(row["exit"], 0)
            self.assertEqual(row["loaded"], [trial.build])
            with open(row["transcript"], encoding="utf-8") as handle:
                self.assertEqual(json.loads(handle.read().splitlines()[0])["subtype"], "init")
            with open(row["stderr"], encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "stub stderr\n")
        for call in calls_of(trial.stubs):
            self.assertEqual(call["argv"][-2:], ["--permission-mode", "bypassPermissions"])
            self.assertEqual(call["argv"][call["argv"].index("--model") + 1], "sonnet")

    def test_a_session_that_loaded_another_copy_fails_the_call(self):
        other = os.path.join(scratch.temporary_folder(self, "lh-other-"), "copy")
        trial = Trial(self, loaded=[other])
        code, stdout, _ = trial.run()
        self.assertEqual(code, 1)
        report = json.loads(stdout.strip().splitlines()[-1])
        self.assertEqual([row["loaded"] for row in report["trials"]], [[other], [other]])
        self.assertIn("another copy", report["error"])

    def test_a_session_that_exits_nonzero_fails_the_call(self):
        trial = Trial(self, exit_code=3)
        code, stdout, _ = trial.run()
        self.assertEqual(code, 1)
        self.assertEqual([row["exit"] for row in json.loads(stdout.strip().splitlines()[-1])["trials"]], [3, 3])

    def test_it_refuses_before_any_session_starts(self):
        refusals = {
            "a flag the command sets itself": lambda trial: trial.run("--", "--settings", "{}"),
            "a missing folder": lambda trial: scratch.run_lighthouse(
                [*trial.arguments(), "--folder", os.path.join(trial.folders[0], "absent")], trial.environment
            ),
            "a folder given twice": lambda trial: scratch.run_lighthouse([*trial.arguments(), "--folder", trial.folders[0]], trial.environment),
            "an empty request": lambda trial: scratch.run_lighthouse(
                ["trial", "--plugin-dir", trial.build, "--request", " ", "--evidence", trial.evidence, "--name", "feature", "--folder", trial.folders[0]],
                trial.environment,
            ),
            "a name that is not one file name": lambda trial: scratch.run_lighthouse(
                ["trial", "--plugin-dir", trial.build, "--request", "x", "--evidence", trial.evidence, "--name", "../feature", "--folder", trial.folders[0]],
                trial.environment,
            ),
        }
        for name, attempt in refusals.items():
            with self.subTest(name):
                trial = Trial(self)
                code, stdout, _ = attempt(trial)
                self.assertEqual(code, 2)
                self.assertIn("error", json.loads(stdout))
                self.assertEqual(calls_of(trial.stubs), [])
                self.assertFalse(os.path.exists(os.path.dirname(trial.evidence)))

    def test_it_never_overwrites_a_transcript(self):
        trial = Trial(self)
        os.makedirs(trial.evidence)
        kept = os.path.join(trial.evidence, "feature-2.jsonl")
        with open(kept, "w", encoding="utf-8") as handle:
            handle.write("earlier\n")
        code, stdout, _ = trial.run()
        self.assertEqual(code, 2)
        self.assertIn("error", json.loads(stdout))
        self.assertEqual(calls_of(trial.stubs), [])
        self.assertEqual(os.listdir(trial.evidence), ["feature-2.jsonl"])
        with open(kept, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "earlier\n")

    def test_a_build_without_a_plugin_manifest_is_refused(self):
        trial = Trial(self)
        os.remove(os.path.join(trial.build, ".claude-plugin", "plugin.json"))
        code, stdout, _ = trial.run()
        self.assertEqual(code, 2)
        self.assertIn("error", json.loads(stdout))
        self.assertEqual(calls_of(trial.stubs), [])


if __name__ == "__main__":
    unittest.main()
