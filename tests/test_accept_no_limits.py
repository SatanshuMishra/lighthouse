import json
import os
import shlex
import subprocess
import sys
import time
import unittest

from tests import accept_support as support
from tests import scratch

SLOW_COMMAND = "python3 -c 'import time; time.sleep(3)'"
WAIT_SECONDS = 120


def slow_suite_profile(command):
    return scratch.sample_profile(suite={"command": command, "junit": None, "timeout_minutes": 0.02})


def started_wait(test, *flags):
    process = subprocess.Popen(
        [sys.executable, support.LIGHTHOUSE, "wait", *flags],
        env=support.environment(test),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    test.addCleanup(support.stop_process, process)
    return process


def finished(test, process):
    try:
        stdout, stderr = process.communicate(timeout=WAIT_SECONDS)
    except subprocess.TimeoutExpired:
        support.stop_process(process)
        test.fail("lighthouse wait did not end within {} seconds".format(WAIT_SECONDS))
    return process.returncode, stdout, stderr


def one_object(test, stdout):
    lines = stdout.strip().splitlines()
    test.assertEqual(len(lines), 1, stdout)
    printed = json.loads(lines[0])
    test.assertIsInstance(printed, dict)
    return printed


class NoLimits(unittest.TestCase):
    def test_slow_suite_step_runs_to_its_end(self):
        repo, _ = support.feature_repo(self)
        stubs = support.Stubs(self)
        env = support.environment(self, stubs.folder)
        profile = support.write_json(
            os.path.join(support.folder(self, "lh-inputs-"), "profile.json"), slow_suite_profile(SLOW_COMMAND)
        )
        results = support.results_folder(self)
        support.worktrees(self, repo, results, env)

        code, stdout, stderr = support.lighthouse(
            ["suite", "--repo", repo, "--core", "main", "--feature", "feature", "--results", results, "--profile", profile],
            env,
        )

        self.assertEqual(code, 0, stdout + stderr)
        self.assertEqual(support.last_json(stdout)["result"], "passed", stdout)
        self.assertNotIn("timed out", stdout + stderr)

    def test_slow_acceptance_check_runs_to_its_end(self):
        repo, _ = support.feature_repo(self)
        stubs = support.Stubs(self)
        env = support.environment(self, stubs.folder)
        inputs = support.folder(self, "lh-inputs-")
        profile = support.write_json(os.path.join(inputs, "profile.json"), slow_suite_profile("true"))
        record = support.record_with([support.exact_line("C1.1", SLOW_COMMAND, target="slow")])
        self.assertEqual(support.referee_errors(support.H11, record), ())
        record_path = support.write_json(os.path.join(inputs, "record.json"), record)
        results = support.results_folder(self)
        support.worktrees(self, repo, results, env)

        code, stdout, stderr = support.lighthouse(
            ["execute", "--results", results, "--record", record_path, "--profile", profile], env
        )

        self.assertEqual(code, 0, stdout + stderr)
        checks = support.json_lines(os.path.join(results, "checks.jsonl"))
        self.assertEqual(len(checks), 1, checks)
        self.assertEqual(checks[0]["check_id"], "C1.1")
        self.assertEqual(checks[0]["status"], "pass", checks[0])

    def test_launch_writes_no_limits_file(self):
        repo, _ = support.feature_repo(self, {".lighthouse/profile.json": "not json"})
        results = support.results_folder(self)
        stubs = support.Stubs(self)
        line = support.blocked_line("stub reason")
        stubs.claude(results, [{"envelope": support.envelope(line, result=json.dumps(line))}])
        env = support.environment(self, stubs.folder)

        code, stdout, stderr = support.lighthouse(["launch", *support.launch_flags(repo, results)], env)

        self.assertEqual(code, 0, stdout + stderr)
        printed = support.last_json(stdout)
        self.assertEqual(printed["verdict"], "blocked", stdout)
        self.assertEqual(printed["reason"], "stub reason", stdout)
        self.assertEqual(len(stubs.calls("claude")), 1)
        self.assertFalse(os.path.exists(os.path.join(results, "limits.json")))


class Waits(unittest.TestCase):
    def test_wait_ends_when_the_awaited_process_exits(self):
        holder = support.folder(self, "lh-wait-")
        never = os.path.join(holder, "never-created")
        exit_file = os.path.join(holder, "start.exit")
        process = started_wait(
            self, "--until", "test -e " + shlex.quote(never), "--exit-file", exit_file, "--every", "0.2"
        )
        time.sleep(1)
        support.replace_text(exit_file, "0\n")

        code, stdout, stderr = finished(self, process)

        self.assertEqual(code, 0, stdout + stderr)
        printed = one_object(self, stdout)
        self.assertIs(printed["ready"], False, stdout)
        self.assertIs(printed["exited"], True, stdout)
        self.assertEqual(printed["status"], 0, stdout)

    def test_wait_ends_when_its_check_passes_with_no_window(self):
        holder = support.folder(self, "lh-wait-")
        flag = os.path.join(holder, "ready.flag")
        exit_file = os.path.join(holder, "never.exit")
        process = started_wait(self, "--until", "test -e " + shlex.quote(flag), "--exit-file", exit_file, "--every", "0.2")
        time.sleep(3)
        support.write_text(flag, "")

        code, stdout, stderr = finished(self, process)

        self.assertEqual(code, 0, stdout + stderr)
        printed = one_object(self, stdout)
        self.assertIs(printed["ready"], True, stdout)
        self.assertIs(printed["exited"], False, stdout)
        self.assertGreaterEqual(printed["seconds"], 2, stdout)

    def test_wait_refuses_a_window_a_deadline_and_no_exit_file(self):
        holder = support.folder(self, "lh-wait-")
        exit_file = os.path.join(holder, "start.exit")
        limits_file = support.write_json(os.path.join(holder, "limits.json"), {"deadline": 0})
        env = support.environment(self)
        runs = (
            ("--within", ["--exit-file", exit_file, "--within", "5"]),
            ("--limits", ["--exit-file", exit_file, "--limits", limits_file]),
            ("--exit-file", []),
        )
        for named, flags in runs:
            with self.subTest(named=named):
                code, stdout, stderr = support.lighthouse(["wait", "--until", "true", *flags], env)
                self.assertEqual(code, 2, stdout + stderr)
                printed = support.last_json(stdout)
                self.assertIsInstance(printed, dict)
                self.assertIn(named, printed["error"])

    def test_measure_waits_for_readiness_past_the_suite_time(self):
        flag = os.path.join(support.folder(self, "lh-flag-"), "ready.flag")
        self.addCleanup(support.stop_processes_naming, flag)
        start = "python3 -c 'import pathlib, time; time.sleep(3); pathlib.Path(\"{}\").touch(); time.sleep(600)'".format(flag)
        profile = scratch.sample_profile(
            suite={"command": "true", "junit": None},
            start={"command": start, "ready": "test -e " + flag},
        )
        repo, _ = support.feature_repo(
            self, {".lighthouse/profile.json": json.dumps(profile, indent=2) + "\n"}, stay_on_feature=True
        )
        stubs = support.Stubs(self)
        env = support.environment(self, stubs.folder)

        code, stdout, stderr = support.lighthouse(["profile", "measure", "--repo", repo], env)

        self.assertEqual(code, 0, stdout + stderr)
        measured = support.last_json(stdout)["measured"]
        self.assertIs(measured["ready"], True, stdout)
        self.assertGreaterEqual(measured["start_seconds"], 3, stdout)
        self.assertLess(measured["suite_seconds"], 3, stdout)
        self.assertFalse(os.path.exists(os.path.join(support.ROOT, "lighthouse_tool", "limits.py")))

    def test_release_stops_every_started_process(self):
        repo, _ = support.feature_repo(self)
        stubs = support.Stubs(self)
        env = support.environment(self, stubs.folder)
        results = support.results_folder(self)
        support.worktrees(self, repo, results, env)
        pid_file = os.path.join(results, "feature-start.pid")
        exit_file = os.path.join(results, "feature-start.exit")
        script = "(python3 -c 'import time; time.sleep(600)') < /dev/null & echo $! > {}; wait $!; echo $? > {}".format(
            shlex.quote(pid_file), shlex.quote(exit_file)
        )
        shell = subprocess.Popen(
            ["/bin/sh", "-c", script],
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.addCleanup(support.stop_process, shell)
        support.wait_for(
            lambda: os.path.exists(pid_file) and support.plain_text(pid_file).strip().isdigit(), 30, "feature-start.pid"
        )
        pid = int(support.plain_text(pid_file).strip())
        self.addCleanup(support.stop_quietly, pid)

        code, stdout, stderr = support.lighthouse(["release", "--repo", repo, "--results", results], env)

        self.assertEqual(code, 0, stdout + stderr)
        self.assertIn("feature-start.pid", json.dumps(support.last_json(stdout).get("stopped")), stdout)
        support.wait_for(lambda: not support.is_running(pid), 30, "the started process to end")
        support.wait_for(lambda: os.path.exists(exit_file), 30, "feature-start.exit")
        shell.wait(timeout=30)
        self.assertIsNotNone(shell.returncode)


class RetiredKey(unittest.TestCase):
    def test_profile_check_reports_the_retired_time_limit(self):
        repo, _ = scratch.make_repo(self)
        base = scratch.sample_profile()
        scratch.write_profile(repo, {**base, "suite": {**base["suite"], "timeout_minutes": 15}})
        env = support.environment(self)

        code, stdout, stderr = support.lighthouse(["profile", "check", "--repo", repo], env)

        self.assertEqual(code, 1, stdout + stderr)
        retired = [item for item in support.last_json(stdout)["problems"] if item.get("kind") == "retired"]
        self.assertEqual(len(retired), 1, stdout)
        self.assertIn("suite.timeout_minutes", retired[0]["detail"])
        self.assertIn("remove", retired[0]["detail"])

    def test_profile_without_the_time_limit_passes(self):
        repo, _ = scratch.make_repo(self)
        base = scratch.sample_profile()
        suite = {key: value for key, value in base["suite"].items() if key != "timeout_minutes"}
        scratch.write_profile(repo, {**base, "suite": suite})
        env = support.environment(self)

        code, stdout, stderr = support.lighthouse(["profile", "check", "--repo", repo], env)

        self.assertEqual(code, 0, stdout + stderr)
        printed = support.last_json(stdout)
        self.assertIs(printed["ok"], True)
        for item in printed["problems"]:
            self.assertNotIn("timeout_minutes", item.get("detail", ""))
        for item in printed["upgrades"]:
            self.assertNotIn("timeout_minutes", item.get("field", ""))
            self.assertNotIn("timeout_minutes", item.get("detail", ""))


if __name__ == "__main__":
    unittest.main()
