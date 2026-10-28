import json
import os
import subprocess
import sys
import threading
import time
import unittest
from unittest import mock

from tests import scratch

COMMAND_SECONDS = 60
RETURN_SECONDS = 15
FEATURE_BRANCH = "feat/x"
MEASURED = {
    "setup_seconds": 0,
    "build_seconds": 0,
    "suite_seconds": 100,
    "start_seconds": 10,
    "drivers": {"a": {"seconds": 5, "exit": 0}},
}
BLOCKED_LINE = '{"verdict": "blocked", "failures": [], "unproven": [], "flaky": [], "tokens": 0, "minutes": 0, "pr": null, "reason": "the stub stopped"}'

CLAUDE_STUB = """#!{python}
import json
print(json.dumps({{"type": "result", "result": {line!r}, "session_id": "child-session-1", "duration_ms": 1000, "modelUsage": {{}}}}))
"""

CAFFEINATE_STUB = """#!{python}
import sys
sys.exit(0)
"""

SYSTEMD_INHIBIT_STUB = """#!{python}
import os
import sys
wrapped = [argument for argument in sys.argv[1:] if not argument.startswith("--what=") and not argument.startswith("--why=")]
os.execvp(wrapped[0], wrapped)
"""


def measured_profile(measured=None, timeout_minutes=None):
    profile = scratch.sample_profile()
    suite = {**profile["suite"], "timeout_minutes": timeout_minutes}
    with_suite = {**profile, "suite": suite}
    return with_suite if measured is None else {**with_suite, "measured": measured}


def limits_of(profile):
    from lighthouse_tool import limits

    return limits.of(profile)


def write_stub(folder, name, text):
    path = os.path.join(folder, name)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text.format(python=sys.executable, line=BLOCKED_LINE))
    os.chmod(path, 0o755)


def finished_within(test, seconds, action):
    outcome = {}

    def call():
        try:
            outcome["value"] = action()
        except BaseException as error:
            outcome["error"] = error

    started = time.monotonic()
    worker = threading.Thread(target=call, daemon=True)
    worker.start()
    worker.join(seconds)
    elapsed = time.monotonic() - started
    test.assertFalse(worker.is_alive(), "still running after {} seconds".format(seconds))
    if "error" in outcome:
        raise outcome["error"]
    return outcome["value"], elapsed


def lighthouse_wait(test, *arguments):
    env = scratch.environment(scratch.make_home(test))
    started = time.monotonic()
    completed = subprocess.run(
        [sys.executable, scratch.LIGHTHOUSE, "wait", *arguments],
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=COMMAND_SECONDS,
    )
    return completed.returncode, completed.stdout, completed.stderr, time.monotonic() - started


def last_json(stdout):
    return json.loads(stdout.strip().splitlines()[-1])


class TimeLimitsTest(unittest.TestCase):
    def assert_limits(self, found, **expected):
        for field, seconds in expected.items():
            self.assertEqual(getattr(found, field), seconds, field)

    def test_limits_derive_from_measured_durations(self):
        found = limits_of(measured_profile(MEASURED))
        self.assert_limits(
            found, suite_seconds=300, check_seconds=300, child_seconds=11490, run_seconds=12090, build_seconds=300
        )

    def test_stated_suite_timeout_wins(self):
        found = limits_of(measured_profile(MEASURED, timeout_minutes=2))
        self.assert_limits(found, suite_seconds=120, check_seconds=120)

    def test_short_suite_gets_the_floor(self):
        found = limits_of(measured_profile({"suite_seconds": 1}))
        self.assert_limits(found, suite_seconds=60)

    def test_slow_build_gets_its_own_limit(self):
        found = limits_of(measured_profile({"suite_seconds": 10, "setup_seconds": 0, "build_seconds": 600}))
        self.assert_limits(found, suite_seconds=60, build_seconds=1800)

    def test_unmeasured_profile_gets_bounded_defaults(self):
        found = limits_of(measured_profile())
        self.assert_limits(
            found, suite_seconds=3600, check_seconds=3600, child_seconds=18000, run_seconds=18600, build_seconds=3600
        )

    def test_child_session_is_stopped_at_its_limit(self):
        from lighthouse_tool import launch

        work = scratch.temporary_folder(self, "lh-work-")
        env = scratch.environment(scratch.make_home(self))
        child, elapsed = finished_within(
            self,
            RETURN_SECONDS,
            lambda: launch.run_child(["/bin/sh", "-c", "sleep 60"], work, "none", env, 1),
        )
        self.assertLess(elapsed, RETURN_SECONDS)
        self.assertIsNone(child.exit)
        self.assertIsNotNone(child.problem)
        self.assertIn("time limit of 1 seconds", child.problem)

    def test_launch_writes_its_limits(self):
        repo, _ = scratch.make_repo(self)
        profile = measured_profile(MEASURED)
        scratch.run_git(repo, "checkout", "-q", "-b", FEATURE_BRANCH)
        scratch.write_profile(repo, profile)
        scratch.run_git(repo, "add", "--", ".lighthouse/profile.json")
        scratch.run_git(repo, "commit", "-q", "-m", "measure the profile")
        scratch.run_git(repo, "checkout", "-q", "main")
        results = os.path.join(scratch.temporary_folder(self, "lh-results-"), "results")
        stubs = scratch.temporary_folder(self, "lh-stubs-")
        write_stub(stubs, "claude", CLAUDE_STUB)
        write_stub(stubs, "caffeinate", CAFFEINATE_STUB)
        write_stub(stubs, "systemd-inhibit", SYSTEMD_INHIBIT_STUB)
        scratch.stub_gh(stubs, {})
        env = {
            **scratch.environment(scratch.make_home(self), stubs),
            "PLUGIN_METRICS_DIR": scratch.temporary_folder(self, "lh-store-"),
        }
        completed = subprocess.run(
            [
                sys.executable, scratch.LIGHTHOUSE, "launch",
                "--repo", repo, "--core", "main", "--feature", FEATURE_BRANCH, "--results", results,
            ],
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=COMMAND_SECONDS,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        limits_path = os.path.join(results, "limits.json")
        self.assertTrue(os.path.isfile(limits_path), os.listdir(results))
        with open(limits_path, encoding="utf-8") as handle:
            written = json.load(handle)
        expected = limits_of(profile)
        for field in ("suite_seconds", "check_seconds", "child_seconds", "run_seconds"):
            self.assertEqual(written.get(field), getattr(expected, field), field)
        deadline = written.get("deadline")
        self.assertTrue(isinstance(deadline, (int, float)) and not isinstance(deadline, bool), deadline)

    def test_suite_step_stops_at_the_measured_limit(self):
        from lighthouse_tool import limits, suite

        work = scratch.temporary_folder(self, "lh-work-")
        log_path = os.path.join(work, "step.log")
        small = limits.Limits(suite_seconds=1, check_seconds=1, child_seconds=10, run_seconds=20, build_seconds=1)
        with mock.patch("lighthouse_tool.limits.of", return_value=small):
            step, elapsed = finished_within(
                self,
                RETURN_SECONDS,
                lambda: suite.run_step("suite", "sleep 60", work, "feature", log_path, scratch.sample_profile(), ()),
            )
        self.assertLess(elapsed, RETURN_SECONDS)
        self.assertIsNone(step.exit)
        self.assertIsNotNone(step.problem)
        self.assertIn("suite timed out after its limit of 1 seconds", step.problem)

    def test_wait_reports_expiry_past_the_deadline(self):
        folder = scratch.temporary_folder(self, "lh-limits-")
        limits_path = os.path.join(folder, "limits.json")
        with open(limits_path, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "suite_seconds": 60,
                    "check_seconds": 60,
                    "child_seconds": 120,
                    "run_seconds": 720,
                    "deadline": time.time() - 600,
                    "measured": True,
                },
                handle,
            )
        code, stdout, stderr, elapsed = lighthouse_wait(self, "--until", "false", "--limits", limits_path)
        self.assertEqual(code, 0, stdout + stderr)
        self.assertLess(elapsed, 10)
        line = last_json(stdout)
        self.assertIs(line["ready"], False)
        self.assertIs(line["expired"], True)

    def test_wait_reports_expiry_when_no_limits_appear(self):
        missing = os.path.join(scratch.temporary_folder(self, "lh-limits-"), "limits.json")
        code, stdout, stderr, _ = lighthouse_wait(self, "--until", "false", "--limits", missing, "--within", "1")
        self.assertEqual(code, 0, stdout + stderr)
        line = last_json(stdout)
        self.assertIs(line["ready"], False)
        self.assertIs(line["expired"], True)


if __name__ == "__main__":
    unittest.main()
