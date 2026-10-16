import json
import os
import posixpath
import subprocess
import unittest

from tests import e2e_harness, scratch

INIT_FIXTURES = ("H1", "H2", "H3", "H4", "H5")
DOCTOR_FIXTURE = "H4"
RUNS = 2
PROFILE = ".lighthouse/profile.json"
SUITE_TIMEOUT_SECONDS = 600


def quiet_environment(env):
    return {**env, "PYTHONDONTWRITEBYTECODE": "1"}


def profile_check(repo, env):
    return scratch.run_lighthouse(["profile", "check", "--repo", repo], env)


def read_profile(repo):
    with open(os.path.join(repo, PROFILE), encoding="utf-8") as handle:
        return json.load(handle)


def run_suite(command, repo, env):
    completed = subprocess.run(
        ["/bin/sh", "-c", command],
        cwd=repo,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=SUITE_TIMEOUT_SECONDS,
    )
    return completed.returncode, completed.stdout + completed.stderr


def normalized(path):
    return posixpath.normpath(path.strip().rstrip("/"))


def overlaps(recorded, wanted):
    return recorded == wanted or recorded.startswith(wanted + "/") or wanted.startswith(recorded + "/")


def recorded_paths(profile):
    return [normalized(path) for surface in profile.get("surfaces", []) for path in surface.get("paths", [])]


def missing_surfaces(profile, wanted_paths):
    recorded = recorded_paths(profile)
    return [
        wanted
        for wanted in (normalized(path) for path in wanted_paths)
        if not any(overlaps(path, wanted) for path in recorded)
    ]


def changed_paths(repo):
    status = scratch.run_git(repo, "status", "--porcelain", "--untracked-files=all")
    return sorted(line[3:] for line in status.splitlines() if line.strip())


def commit_all(repo, message):
    scratch.run_git(repo, "commit", "-q", "-m", message)


def rename_suite_script(repo):
    scratch.run_git(repo, "mv", "scripts/run_tests.sh", "scripts/test.sh")
    commit_all(repo, "rename the test script")


def delete_surface_path(repo):
    scratch.run_git(repo, "rm", "-q", "tillkit/receipt.py")
    commit_all(repo, "remove the receipt module")


def add_source_file(repo):
    scratch.commit_files(
        repo,
        {"bench/pyproject.toml": '[project]\nname = "tillkit-bench"\nversion = "0.1.0"\n'},
        "add a benchmark project",
    )


def delete_profile(repo):
    scratch.run_git(repo, "rm", "-q", PROFILE)
    commit_all(repo, "remove the test profile")


PROBLEMS = (
    ("renamed suite command", rename_suite_script),
    ("deleted surface path", delete_surface_path),
    ("new unrecorded source file", add_source_file),
    ("deleted profile", delete_profile),
)


def held_out_profile():
    return e2e_harness.read_text(os.path.join(e2e_harness.FIXTURES, DOCTOR_FIXTURE, "profile.json"))


@unittest.skipUnless(e2e_harness.E2E, "end-to-end tests run only when LIGHTHOUSE_E2E=1")
class InitDoctorEndToEndTest(unittest.TestCase):
    def test_init_writes_a_checked_profile(self):
        for fid in INIT_FIXTURES:
            fixture = e2e_harness.load(fid)
            for run in range(1, RUNS + 1):
                with self.subTest(fixture=fid, run=run):
                    base = e2e_harness.build(self, fid, "base")
                    repo = base["repo"]
                    env = quiet_environment(base["env"])
                    self.assertFalse(os.path.exists(os.path.join(repo, PROFILE)))
                    code, transcript = e2e_harness.run_claude(
                        "/lighthouse:init --unattended --repo {}".format(repo), cwd=repo, env=env
                    )
                    check_code, check_out, check_err = profile_check(repo, env)
                    self.assertEqual(check_code, 0, "claude exit {}\n{}\n{}\n{}".format(code, transcript, check_out, check_err))
                    profile = read_profile(repo)
                    suite_code, suite_output = run_suite(profile["suite"]["command"], repo, env)
                    self.assertEqual(suite_code, 0, suite_output)
                    self.assertEqual(missing_surfaces(profile, fixture["surfaces"]), [], json.dumps(profile, indent=2))

    def test_doctor_repairs_only_the_profile(self):
        for label, apply_problem in PROBLEMS:
            for run in range(1, RUNS + 1):
                with self.subTest(problem=label, run=run):
                    base = e2e_harness.build(self, DOCTOR_FIXTURE, "base")
                    repo = base["repo"]
                    env = quiet_environment(base["env"])
                    scratch.commit_files(repo, {PROFILE: held_out_profile()}, "record the test profile")
                    apply_problem(repo)
                    before_code, _, before_err = profile_check(repo, env)
                    self.assertNotEqual(before_code, 0, before_err)
                    code, transcript = e2e_harness.run_claude(
                        "/lighthouse:doctor --unattended --repo {}".format(repo), cwd=repo, env=env
                    )
                    check_code, check_out, check_err = profile_check(repo, env)
                    self.assertEqual(check_code, 0, "claude exit {}\n{}\n{}\n{}".format(code, transcript, check_out, check_err))
                    self.assertEqual(changed_paths(repo), [PROFILE], transcript)


if __name__ == "__main__":
    unittest.main()
