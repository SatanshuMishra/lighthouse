import json
import os
import signal
import subprocess
import sys
import time
import unittest

from tests import scratch
from tests.test_process_tree import HOST_SECONDS, PID_SECONDS, gone_by, is_running, kill_listed_quietly, stop_host, turns_false_by, written_pids

PLUGIN = "demo"
MARKETPLACE = "market"

CLAUDE_STUB = """#!{python}
import json
import os
import select
import signal
import sys
import time

folder = os.path.dirname(os.path.realpath(__file__))
argv = sys.argv[1:]
with open(os.path.join(folder, "claude-plan.json"), encoding="utf-8") as handle:
    plan = json.load(handle)
started = os.path.join(folder, "started-" + str(os.getpid()))
open(started, "w").close()
if plan["pids"]:
    with open(plan["pids"], "a", encoding="utf-8") as listed:
        listed.write(str(os.getpid()) + " ")
    signal.pause()
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
loaded = [argv[argv.index("--plugin-dir") + 1]] if plan["loaded"] is None else plan["loaded"]
print(json.dumps({{"type": "system", "subtype": "init", "plugins": [{{"name": plan["plugin"], "path": path}} for path in loaded]}}))
print(json.dumps({{"type": "result", "subtype": "success", "result": "done"}}))
sys.stderr.write("stub stderr\\n")
sys.exit(plan["exit"])
"""

STAGED_STUB = """#!{python}
import json
import os
import subprocess
import sys

folder = os.path.dirname(os.path.realpath(__file__))
argv = sys.argv[1:]
with open(os.path.join(folder, "claude-plan.json"), encoding="utf-8") as handle:
    plan = json.load(handle)
init = json.dumps({{"type": "system", "subtype": "init", "plugins": [{{"name": plan["plugin"], "path": argv[argv.index("--plugin-dir") + 1]}}]}})
if os.getcwd() == plan["first"]:
    left = subprocess.Popen([sys.executable, "-c", "import signal; signal.pause()"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    with open(plan["left"], "w", encoding="utf-8") as listed:
        listed.write(str(left.pid) + " ")
    print(init)
    sys.exit(0)
with open(plan["waiting"], "w", encoding="utf-8") as listed:
    listed.write(str(os.getpid()) + " ")
with open(plan["release"], encoding="utf-8") as released:
    released.read()
print(init)
"""


def write_stub(folder, plan, text=CLAUDE_STUB):
    path = os.path.join(folder, "claude")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text.format(python=sys.executable))
    os.chmod(path, 0o755)
    with open(os.path.join(folder, "claude-plan.json"), "w", encoding="utf-8") as handle:
        json.dump(plan, handle)


def run_holding_input(arguments, environment):
    held, holder = os.pipe()
    try:
        completed = subprocess.run([sys.executable, scratch.LIGHTHOUSE, *arguments], env=environment, stdin=held, capture_output=True, text=True)
    finally:
        os.close(held)
        os.close(holder)
    return completed.returncode, completed.stdout, completed.stderr


def respelled(path, old, new):
    other = path.replace(old, new)
    return other if other != path and os.path.exists(other) and os.path.samefile(path, other) else None


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
    def __init__(self, test, sessions=2, loaded=None, exit_code=0, config=None, hold_seconds=0, pids=None):
        self.home = scratch.make_home(test)
        self.config = config or os.path.join(self.home, ".claude")
        self.installed = installed_copy(self.config)
        self.build = build_copy(test)
        self.stubs = scratch.temporary_folder(test, "lh-stubs-")
        self.plan = {"sessions": sessions, "hold_seconds": hold_seconds, "plugin": PLUGIN, "loaded": loaded, "exit": exit_code, "pids": pids}
        write_stub(self.stubs, self.plan)
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

    def named(self, name, folders):
        chosen = [part for folder in folders for part in ("--folder", folder)]
        return ["trial", "--plugin-dir", self.build, "--request", "Prepare the title.", "--evidence", self.evidence, "--name", name, *chosen]

    def run(self, *extra):
        return run_holding_input(self.arguments(*extra), self.environment)


def started_command(test, trial):
    host = subprocess.Popen(
        [sys.executable, scratch.LIGHTHOUSE, *trial.arguments()],
        env=trial.environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    test.addCleanup(stop_host, host)
    return host


def staged(test):
    trial = Trial(test)
    folder = scratch.temporary_folder(test, "lh-stage-")
    stage = {name: os.path.join(folder, name) for name in ("left", "waiting", "release")}
    os.mkfifo(stage["release"])
    write_stub(trial.stubs, {**trial.plan, **stage, "first": trial.folders[0]}, STAGED_STUB)
    host = started_command(test, trial)
    test.addCleanup(kill_listed_quietly, stage["left"])
    test.addCleanup(kill_listed_quietly, stage["waiting"])
    return host, stage


def let_go(release, seconds):
    def unread():
        try:
            os.close(os.open(release, os.O_WRONLY | os.O_NONBLOCK))
        except OSError:
            return True
        return False

    return turns_false_by(unread, time.monotonic() + seconds)


class TrialTest(unittest.TestCase):
    def test_a_trial_session_cannot_find_the_installed_copy_of_the_plugin_under_test(self):
        trial = Trial(self)
        linked = os.path.join(scratch.temporary_folder(self, "lh-link-"), "bin")
        os.symlink(os.path.join(trial.installed, "bin"), linked)
        environment = {**trial.environment, "PATH": os.pathsep.join([linked, trial.environment["PATH"]])}
        code, stdout, stderr = run_holding_input(trial.arguments(), environment)
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

    def test_a_session_that_loaded_the_build_and_another_copy_fails_the_call(self):
        trial = Trial(self)
        other = os.path.join(scratch.temporary_folder(self, "lh-other-"), "copy")
        write_stub(trial.stubs, {**trial.plan, "loaded": [trial.build, other]})
        code, stdout, _ = trial.run()
        self.assertEqual(code, 1)
        self.assertIn("another copy", json.loads(stdout.strip().splitlines()[-1])["error"])

    def test_a_loaded_path_no_file_can_have_counts_as_another_copy(self):
        trial = Trial(self, loaded=["no\u0000file"])
        code, stdout, stderr = trial.run()
        self.assertEqual(code, 1, stderr)
        self.assertIn("another copy", json.loads(stdout.strip().splitlines()[-1])["error"])

    def test_a_search_path_entry_of_more_parts_than_python_recurses_is_read(self):
        trial = Trial(self)
        deep = os.sep + os.sep.join(["part"] * 1100)
        environment = {**trial.environment, "PATH": os.pathsep.join([trial.environment["PATH"], deep])}
        code, _, stderr = run_holding_input(trial.arguments(), environment)
        self.assertEqual(code, 0, stderr[-300:])

    def test_a_session_that_loaded_no_copy_fails_the_call(self):
        trial = Trial(self, loaded=[])
        code, stdout, _ = trial.run()
        self.assertEqual(code, 1)
        report = json.loads(stdout.strip().splitlines()[-1])
        self.assertEqual([row["loaded"] for row in report["trials"]], [[], []])
        self.assertIn("error", report)

    def test_stopping_the_command_stops_its_sessions(self):
        for number in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP, signal.SIGQUIT):
            with self.subTest(signal=signal.Signals(number).name):
                pids = os.path.join(scratch.temporary_folder(self, "lh-pids-"), "pids")
                trial = Trial(self, pids=pids)
                host = started_command(self, trial)
                self.addCleanup(kill_listed_quietly, pids)
                sessions = written_pids(pids, 2, PID_SECONDS)
                self.assertIsNotNone(sessions)
                host.send_signal(number)
                host.wait(timeout=HOST_SECONDS)
                self.assertEqual([pid for pid in sessions if not gone_by(pid, time.monotonic() + PID_SECONDS)], [])

    def test_a_stopped_call_leaves_no_file_and_keeps_the_name_free(self):
        pids = os.path.join(scratch.temporary_folder(self, "lh-pids-"), "pids")
        trial = Trial(self, pids=pids)
        host = started_command(self, trial)
        self.addCleanup(kill_listed_quietly, pids)
        self.assertIsNotNone(written_pids(pids, 2, PID_SECONDS))
        host.send_signal(signal.SIGTERM)
        host.wait(timeout=HOST_SECONDS)
        self.assertEqual(os.listdir(trial.evidence), [])
        write_stub(trial.stubs, {**trial.plan, "pids": None})
        again, _, stderr = trial.run()
        self.assertEqual(again, 0, stderr)

    def test_what_an_ended_session_left_running_is_stopped_while_the_others_still_run(self):
        host, stage = staged(self)
        left = written_pids(stage["left"], 1, PID_SECONDS)
        self.assertIsNotNone(left)
        self.assertIsNotNone(written_pids(stage["waiting"], 1, PID_SECONDS))
        stopped = gone_by(left[0], time.monotonic() + PID_SECONDS)
        self.assertIsNone(host.poll())
        self.assertTrue(stopped, "what the first session left running outlived it while the second still ran")
        self.assertTrue(let_go(stage["release"], PID_SECONDS))
        self.assertEqual(host.wait(timeout=HOST_SECONDS), 0)

    def test_stopping_the_command_after_one_session_ended_stops_the_rest(self):
        host, stage = staged(self)
        left = written_pids(stage["left"], 1, PID_SECONDS)
        waiting = written_pids(stage["waiting"], 1, PID_SECONDS)
        self.assertIsNotNone(left)
        self.assertIsNotNone(waiting)
        self.assertTrue(gone_by(left[0], time.monotonic() + PID_SECONDS))
        host.send_signal(signal.SIGTERM)
        host.wait(timeout=HOST_SECONDS)
        self.assertEqual([pid for pid in waiting if not gone_by(pid, time.monotonic() + PID_SECONDS)], [])

    def test_a_start_that_fails_leaves_no_file_and_keeps_the_name_free(self):
        def without_claude(trial):
            return {**trial.environment, "PATH": os.pathsep.join(["/usr/bin", "/bin"])}, "claude"

        def with_a_folder_nobody_can_enter(trial):
            os.chmod(trial.folders[1], 0)
            self.addCleanup(os.chmod, trial.folders[1], 0o700)
            return trial.environment, trial.folders[1]

        enters_any_folder = os.geteuid() == 0
        breakages = (("no claude command to start", without_claude),) + (() if enters_any_folder else (("a folder that cannot be entered", with_a_folder_nobody_can_enter),))
        for name, broken in breakages:
            with self.subTest(name):
                trial = Trial(self)
                environment, named = broken(trial)
                code, stdout, _ = run_holding_input(trial.arguments(), environment)
                self.assertEqual(code, 2)
                self.assertIn(named, json.loads(stdout)["error"])
                self.assertEqual(os.listdir(trial.evidence) if os.path.isdir(trial.evidence) else [], [])
                os.chmod(trial.folders[1], 0o700)
                again, _, stderr = trial.run()
                self.assertEqual(again, 0, stderr)
                self.assertEqual(sorted(os.listdir(trial.evidence)), ["feature-1.jsonl", "feature-1.stderr", "feature-2.jsonl", "feature-2.stderr"])

    def test_two_spellings_of_one_folder_are_one_folder(self):
        trial = Trial(self)
        folder = respelled(trial.folders[0], "lh-trial-", "LH-TRIAL-")
        build = respelled(trial.build, "lh-build-", "LH-BUILD-")
        installed = respelled(os.path.join(trial.installed, "bin"), os.path.join("plugins", "cache"), os.path.join("plugins", "CACHE"))
        if not (folder and build and installed):
            self.skipTest("this file system tells the spellings of a folder apart")
        with self.subTest("one folder given in two spellings"):
            code, stdout, _ = run_holding_input(trial.named("twice", [trial.folders[0], folder]), trial.environment)
            self.assertEqual(code, 2)
            self.assertEqual(calls_of(trial.stubs), [])
        with self.subTest("the installed copy on the search path in another spelling"):
            environment = {**trial.environment, "PATH": os.pathsep.join([installed, trial.environment["PATH"]])}
            code, _, stderr = run_holding_input(trial.named("path", trial.folders), environment)
            self.assertEqual(code, 0, stderr)
            for call in calls_of(trial.stubs):
                self.assertEqual([entry for entry in call["path"] if os.path.exists(entry) and os.path.samefile(entry, installed)], [])
        with self.subTest("the build reported in another spelling"):
            write_stub(trial.stubs, {**trial.plan, "loaded": [build]})
            code, _, stderr = run_holding_input(trial.named("loaded", trial.folders), trial.environment)
            self.assertEqual(code, 0, stderr)

    def test_a_session_that_exits_nonzero_fails_the_call(self):
        trial = Trial(self, exit_code=3)
        code, stdout, _ = trial.run()
        self.assertEqual(code, 1)
        self.assertEqual([row["exit"] for row in json.loads(stdout.strip().splitlines()[-1])["trials"]], [3, 3])

    def test_it_refuses_before_any_session_starts(self):
        owned = ("-p", "--print", "--plugin-dir", "--settings", "--output-format", "--model", "--effort")
        refusals = {
            **{"{} passed on, which the command sets itself".format(flag): (lambda flag: lambda trial: trial.run("--", flag, "value"))(flag) for flag in owned},
            "a flag the command sets itself, joined to its value": lambda trial: trial.run("--", "--model=haiku"),
            "a request that reads as a flag": lambda trial: scratch.run_lighthouse(
                ["trial", "--plugin-dir", trial.build, "--request=--plugin-dir=/another/copy", "--evidence", trial.evidence, "--name", "feature", "--folder", trial.folders[0]],
                trial.environment,
            ),
            "a word ahead of the separator that the command does not know": lambda trial: scratch.run_lighthouse([*trial.arguments(), "stray"], trial.environment),
            "a request that begins with one dash": lambda trial: scratch.run_lighthouse([*trial.arguments(), "--request=-x"], trial.environment),
            **{
                "the separator given as the value of {}".format(flag): (lambda flag: lambda trial: scratch.run_lighthouse([*trial.arguments(), flag + "=--"], trial.environment))(flag)
                for flag in ("--model", "--effort", "--request", "--name")
            },
            "a missing folder": lambda trial: scratch.run_lighthouse(
                [*trial.arguments(), "--folder", os.path.join(trial.folders[0], "absent")], trial.environment
            ),
            "a file given as a folder": lambda trial: scratch.run_lighthouse(
                [*trial.arguments(), "--folder", os.path.join(trial.build, ".claude-plugin", "plugin.json")], trial.environment
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

    def test_it_never_overwrites_evidence(self):
        for kept_name in ("feature-2.jsonl", "feature-2.stderr"):
            with self.subTest(kept_name):
                trial = Trial(self)
                os.makedirs(trial.evidence)
                kept = os.path.join(trial.evidence, kept_name)
                with open(kept, "w", encoding="utf-8") as handle:
                    handle.write("earlier\n")
                code, stdout, _ = trial.run()
                self.assertEqual(code, 2)
                self.assertIn(kept, json.loads(stdout)["error"])
                self.assertEqual(calls_of(trial.stubs), [])
                self.assertEqual(os.listdir(trial.evidence), [kept_name])
                with open(kept, encoding="utf-8") as handle:
                    self.assertEqual(handle.read(), "earlier\n")
        with self.subTest("a link that leads nowhere"):
            trial = Trial(self)
            os.makedirs(trial.evidence)
            link = os.path.join(trial.evidence, "feature-2.jsonl")
            os.symlink(os.path.join(trial.evidence, "absent"), link)
            code, stdout, _ = trial.run()
            self.assertEqual(code, 2)
            self.assertIn(link, json.loads(stdout)["error"])
            self.assertEqual(calls_of(trial.stubs), [])
            self.assertEqual(os.listdir(trial.evidence), ["feature-2.jsonl"])
            self.assertTrue(os.path.islink(link))

    def test_a_build_without_a_plugin_manifest_is_refused(self):
        trial = Trial(self)
        os.remove(os.path.join(trial.build, ".claude-plugin", "plugin.json"))
        code, stdout, _ = trial.run()
        self.assertEqual(code, 2)
        self.assertIn("error", json.loads(stdout))
        self.assertEqual(calls_of(trial.stubs), [])


if __name__ == "__main__":
    unittest.main()
