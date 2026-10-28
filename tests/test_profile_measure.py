import datetime
import json
import os
import shlex
import subprocess
import sys
import unittest

from tests import scratch

COMMAND_TIMEOUT_SECONDS = 60
PROFILE_PATH = ".lighthouse/profile.json"


def lighthouse(test, *arguments):
    completed = subprocess.run(
        [sys.executable, scratch.LIGHTHOUSE, *arguments],
        env=scratch.environment(scratch.make_home(test)),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=COMMAND_TIMEOUT_SECONDS,
    )
    return completed.returncode, completed.stdout, completed.stderr


def surface(name, reach, available):
    return {
        **scratch.sample_profile()["surfaces"][0],
        "name": name,
        "available": available,
        "reach": reach,
    }


def measurable_profile(flag):
    quoted_flag = shlex.quote(flag)
    return scratch.sample_profile(
        suite={"command": "sleep 1", "junit": None, "timeout_minutes": None, "rerun": None, "isolated": False},
        start={
            "command": "sleep 1 && touch {} && exec sleep 30".format(quoted_flag),
            "ready": "test -f {}".format(quoted_flag),
        },
        surfaces=[surface("ready", "true", False), surface("gone", "exit 1", True)],
    )


def measurable_repo(test):
    work, _ = scratch.make_repo(test)
    flag = os.path.join(scratch.temporary_folder(test, "lh-flag-"), "started.flag")
    profile = measurable_profile(flag)
    scratch.commit_files(work, {PROFILE_PATH: json.dumps(profile, indent=2) + "\n"}, "record the profile")
    return work


def measured_repo(test):
    work = measurable_repo(test)
    code, stdout, stderr = lighthouse(test, "profile", "measure", "--repo", work)
    test.assertEqual(code, 0, stdout + stderr)
    return work, json.loads(stdout)


def read_profile(work):
    with open(os.path.join(work, PROFILE_PATH), encoding="utf-8") as handle:
        return json.load(handle)


def is_seconds(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def surface_named(profile, name):
    return next(item for item in profile["surfaces"] if item["name"] == name)


class ProfileMeasureTest(unittest.TestCase):
    def test_measure_records_suite_start_and_driver_durations(self):
        work, printed = measured_repo(self)

        profile = read_profile(work)
        measured = profile["measured"]
        self.assertTrue(is_seconds(measured["suite_seconds"]), measured)
        self.assertGreaterEqual(measured["suite_seconds"], 1)
        self.assertIs(type(measured["suite_exit"]), int)
        self.assertEqual(measured["suite_exit"], 0)
        self.assertTrue(is_seconds(measured["start_seconds"]), measured)
        self.assertGreaterEqual(measured["start_seconds"], 1)
        self.assertEqual(sorted(measured["drivers"]), ["gone", "ready"])
        self.assertEqual(measured["drivers"]["ready"]["exit"], 0)
        self.assertEqual(measured["drivers"]["gone"]["exit"], 1)
        for name in ["ready", "gone"]:
            with self.subTest(driver=name):
                self.assertTrue(is_seconds(measured["drivers"][name]["seconds"]), measured["drivers"][name])
        self.assertEqual(measured["commit"], scratch.run_git(work, "rev-parse", "HEAD").strip())
        stamp = datetime.datetime.fromisoformat(measured["measured_at"].replace("Z", "+00:00"))
        self.assertEqual(stamp.utcoffset(), datetime.timedelta(0))
        self.assertIs(surface_named(profile, "ready")["available"], True)
        self.assertIs(surface_named(profile, "gone")["available"], False)
        self.assertEqual(printed["available"], {"ready": True, "gone": False})

    def test_measured_profile_still_passes_the_check(self):
        work, _ = measured_repo(self)

        code, stdout, stderr = lighthouse(self, "profile", "check", "--repo", work)

        self.assertEqual(code, 0, stdout + stderr)
        report = json.loads(stdout)
        self.assertIs(report["ok"], True)
        self.assertEqual(report["problems"], [])

    def test_measure_writes_only_the_profile(self):
        work, _ = measured_repo(self)

        status = scratch.run_git(work, "status", "--porcelain", "--untracked-files=all", "--ignored")

        self.assertEqual([line[3:] for line in status.splitlines()], [PROFILE_PATH])

    def test_missing_measurement_is_an_upgrade(self):
        work, _ = scratch.make_repo(self)
        scratch.write_profile(work, scratch.sample_profile())

        code, stdout, stderr = lighthouse(self, "profile", "check", "--repo", work)

        self.assertEqual(code, 0, stdout + stderr)
        report = json.loads(stdout)
        self.assertIs(report["ok"], True)
        self.assertIn(
            {"field": "measured", "detail": "measured is not set, and lighthouse:doctor writes it"},
            report["upgrades"],
        )


if __name__ == "__main__":
    unittest.main()
